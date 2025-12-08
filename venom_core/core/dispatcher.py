"""Moduł: dispatcher - dyspozytornia zadań."""

from typing import Dict

from semantic_kernel import Kernel

from venom_core.agents.architect import ArchitectAgent
from venom_core.agents.base import BaseAgent
from venom_core.agents.chat import ChatAgent
from venom_core.agents.coder import CoderAgent
from venom_core.agents.critic import CriticAgent
from venom_core.agents.integrator import IntegratorAgent
from venom_core.agents.librarian import LibrarianAgent
from venom_core.agents.publisher import PublisherAgent
from venom_core.agents.release_manager import ReleaseManagerAgent
from venom_core.agents.researcher import ResearcherAgent
from venom_core.agents.tester import TesterAgent
from venom_core.agents.toolmaker import ToolmakerAgent
from venom_core.execution.skill_manager import SkillManager
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class TaskDispatcher:
    """Dyspozytornia zadań - kieruje zadania do odpowiednich agentów."""

    def __init__(self, kernel: Kernel, event_broadcaster=None, node_manager=None):
        """
        Inicjalizacja TaskDispatcher.

        Args:
            kernel: Skonfigurowane jądro Semantic Kernel dla agentów
            event_broadcaster: Opcjonalny broadcaster zdarzeń
            node_manager: Opcjonalny NodeManager dla distributed execution
        """
        self.kernel = kernel
        self.event_broadcaster = event_broadcaster
        self.node_manager = node_manager

        # Inicjalizuj SkillManager - zarządza dynamicznymi pluginami
        self.skill_manager = SkillManager(kernel)

        # Załaduj istniejące custom skills przy starcie
        try:
            loaded_skills = self.skill_manager.load_skills_from_dir()
            if loaded_skills:
                logger.info(f"Załadowano custom skills: {', '.join(loaded_skills)}")
        except Exception as e:
            logger.warning(f"Nie udało się załadować custom skills: {e}")

        # Inicjalizuj agentów
        self.coder_agent = CoderAgent(kernel)
        self.chat_agent = ChatAgent(kernel)
        self.librarian_agent = LibrarianAgent(kernel)
        self.critic_agent = CriticAgent(kernel)
        self.researcher_agent = ResearcherAgent(kernel)
        self.integrator_agent = IntegratorAgent(kernel)
        self.toolmaker_agent = ToolmakerAgent(kernel)
        self.architect_agent = ArchitectAgent(
            kernel, event_broadcaster=event_broadcaster
        )
        self.tester_agent = TesterAgent(kernel)
        self.publisher_agent = PublisherAgent(kernel)
        self.release_manager_agent = ReleaseManagerAgent(kernel)

        # Ustawienie referencji do dispatchera w Architect (circular dependency)
        self.architect_agent.set_dispatcher(self)

        # Mapa intencji do agentów
        self.agent_map: Dict[str, BaseAgent] = {
            "CODE_GENERATION": self.coder_agent,
            "GENERAL_CHAT": self.chat_agent,
            "KNOWLEDGE_SEARCH": self.librarian_agent,
            "FILE_OPERATION": self.librarian_agent,
            "CODE_REVIEW": self.critic_agent,
            "RESEARCH": self.researcher_agent,
            "COMPLEX_PLANNING": self.architect_agent,
            "VERSION_CONTROL": self.integrator_agent,
            "TOOL_CREATION": self.toolmaker_agent,
            "E2E_TESTING": self.tester_agent,
            "DOCUMENTATION": self.publisher_agent,
            "RELEASE_PROJECT": self.release_manager_agent,
        }

        logger.info("TaskDispatcher zainicjalizowany z agentami (+ QA/Delivery layer)")

    async def dispatch(self, intent: str, content: str, node_preference: dict = None) -> str:
        """
        Kieruje zadanie do odpowiedniego agenta na podstawie intencji.

        Args:
            intent: Sklasyfikowana intencja
            content: Treść zadania do wykonania
            node_preference: Opcjonalne preferencje węzła (np. {"tag": "location:server_room", "skill": "ShellSkill"})

        Returns:
            Wynik przetworzenia zadania przez agenta

        Raises:
            ValueError: Jeśli intencja jest nieznana
        """
        logger.info(f"Dispatcher kieruje zadanie z intencją: {intent}")

        # Sprawdź czy zadanie powinno być wykonane na zdalnym węźle
        if self.node_manager and node_preference:
            try:
                result = await self._dispatch_to_node(intent, content, node_preference)
                if result:
                    return result
            except Exception as e:
                logger.warning(f"Nie udało się wykonać na węźle zdalnym: {e}. Fallback do lokalnego wykonania.")

        # Znajdź odpowiedniego agenta
        agent = self.agent_map.get(intent)

        if agent is None:
            error_msg = (
                f"Nieznana intencja: {intent}. "
                f"Dostępne intencje: {list(self.agent_map.keys())}"
            )
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Przekaż zadanie do agenta
        try:
            logger.info(f"Agent {agent.__class__.__name__} przejmuje zadanie")
            result = await agent.process(content)
            logger.info(f"Agent {agent.__class__.__name__} zakończył przetwarzanie")
            return result

        except Exception as e:
            logger.error(f"Błąd podczas przetwarzania zadania przez agenta: {e}")
            raise

    async def _dispatch_to_node(self, intent: str, content: str, node_preference: dict) -> str:
        """
        Próbuje wykonać zadanie na zdalnym węźle.

        Args:
            intent: Sklasyfikowana intencja
            content: Treść zadania
            node_preference: Preferencje węzła

        Returns:
            Wynik wykonania lub None jeśli nie udało się
        """
        # Parsuj preferencje
        tag = node_preference.get("tag")
        skill_name = node_preference.get("skill")
        method_name = node_preference.get("method", "run")

        if not skill_name:
            return None

        # Znajdź odpowiedni węzeł
        node = None
        if tag:
            nodes = self.node_manager.find_nodes_by_tag(tag)
            if nodes:
                node = nodes[0]  # Weź pierwszy pasujący węzeł
        else:
            node = self.node_manager.select_best_node(skill_name)

        if not node:
            logger.warning(f"Nie znaleziono węzła obsługującego {skill_name}" + (f" z tagiem {tag}" if tag else ""))
            return None

        logger.info(f"Wykonuję zadanie na węźle zdalnym: {node.node_name} ({node.node_id})")

        # Wykonaj na węźle
        response = await self.node_manager.execute_skill_on_node(
            node_id=node.node_id,
            skill_name=skill_name,
            method_name=method_name,
            parameters={"command": content} if skill_name == "ShellSkill" else {},
            timeout=60,
        )

        if response.success:
            logger.info(f"Zadanie wykonane na węźle {node.node_name} w {response.execution_time:.2f}s")
            return response.result
        else:
            logger.error(f"Błąd wykonania na węźle {node.node_name}: {response.error}")
            raise RuntimeError(f"Remote execution failed: {response.error}")
