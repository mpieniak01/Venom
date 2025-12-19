"""Moduł: dispatcher - dyspozytornia zadań."""

import json
import re
from typing import Dict, Optional

from semantic_kernel import Kernel
from semantic_kernel.contents import ChatHistory
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.utils.author_role import AuthorRole

from venom_core.agents.architect import ArchitectAgent
from venom_core.agents.base import BaseAgent
from venom_core.agents.chat import ChatAgent
from venom_core.agents.coder import CoderAgent
from venom_core.agents.critic import CriticAgent
from venom_core.agents.executive import ExecutiveAgent
from venom_core.agents.integrator import IntegratorAgent
from venom_core.agents.librarian import LibrarianAgent
from venom_core.agents.publisher import PublisherAgent
from venom_core.agents.release_manager import ReleaseManagerAgent
from venom_core.agents.researcher import ResearcherAgent
from venom_core.agents.system_status import SystemStatusAgent
from venom_core.agents.tester import TesterAgent
from venom_core.agents.time_assistant import TimeAssistantAgent
from venom_core.agents.toolmaker import ToolmakerAgent
from venom_core.agents.unsupported import UnsupportedAgent
from venom_core.core.goal_store import GoalStore
from venom_core.core.models import Intent
from venom_core.execution.skill_manager import SkillManager
from venom_core.execution.skills.assistant_skill import AssistantSkill
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class TaskDispatcher:
    """Dyspozytornia zadań - kieruje zadania do odpowiednich agentów."""

    # Wzorzec regex dla ścieżek plików - skompilowany raz dla wydajności
    FILE_PATH_PATTERN = re.compile(
        r"[\w/\-]+(?:\.[\w\-]+)*\.(?:py|js|ts|txt|md|json|yaml|yml|html|css|java|go|rs|cpp|c|h)(?=$|[^0-9A-Za-z_])",
        re.IGNORECASE,
    )

    # Słowa kluczowe do wykrywania akcji
    ACTION_KEYWORDS = {
        "edit": ["edytuj", "popraw", "zmień", "edit", "fix", "modify"],
        "create": ["stwórz", "utwórz", "create"],
        "delete": ["usuń", "delete", "remove"],
        "read": ["czytaj", "pokaż", "read", "show"],
    }

    def __init__(
        self,
        kernel: Kernel,
        event_broadcaster=None,
        node_manager=None,
        goal_store: Optional[GoalStore] = None,
    ):
        """
        Inicjalizacja TaskDispatcher.

        Args:
            kernel: Skonfigurowane jądro Semantic Kernel dla agentów
            event_broadcaster: Opcjonalny broadcaster zdarzeń
            node_manager: Opcjonalny NodeManager dla distributed execution
            goal_store: Opcjonalny GoalStore dla Executive Agent
        """
        self.kernel = kernel
        self.event_broadcaster = event_broadcaster
        self.node_manager = node_manager

        # Inicjalizuj GoalStore jeśli nie przekazano
        self.goal_store = goal_store or GoalStore()

        # Inicjalizuj SkillManager - zarządza dynamicznymi pluginami
        self.skill_manager = SkillManager(kernel)

        # Załaduj istniejące custom skills przy starcie
        try:
            loaded_skills = self.skill_manager.load_skills_from_dir()
            if loaded_skills:
                logger.info(f"Załadowano custom skills: {', '.join(loaded_skills)}")
        except Exception as e:
            logger.warning(f"Nie udało się załadować custom skills: {e}")

        # Zarejestruj wbudowane podstawowe umiejętności asystenta
        try:
            self.kernel.add_plugin(AssistantSkill(), plugin_name="AssistantSkill")
            logger.info("Zarejestrowano plugin: AssistantSkill")
        except Exception as e:
            logger.warning(f"Nie udało się zarejestrować AssistantSkill: {e}")

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
        self.executive_agent = ExecutiveAgent(kernel, self.goal_store)
        self.system_status_agent = SystemStatusAgent(kernel)
        self.time_assistant_agent = TimeAssistantAgent(kernel)
        self.unsupported_agent = UnsupportedAgent(kernel)

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
            "STATUS_REPORT": self.executive_agent,
            "INFRA_STATUS": self.system_status_agent,
            "TIME_REQUEST": self.time_assistant_agent,
            "UNSUPPORTED_TASK": self.unsupported_agent,
        }

        logger.info("TaskDispatcher zainicjalizowany z agentami (+ Executive layer)")

    async def parse_intent(self, content: str) -> Intent:
        """
        Parsuje intencję użytkownika - hybrydowe podejście (regex + LLM fallback).

        Krok 1: Próbuje wyciągnąć ścieżki plików za pomocą regex.
        Krok 2: Jeśli regex nie znalazł wystarczających danych, używa LLM.

        Args:
            content: Tekst od użytkownika

        Returns:
            Intent: Sparsowana intencja z akcją, celami i parametrami
        """
        logger.debug(f"Parsowanie intencji z treści: {content[:100]}...")

        # Krok 1: Regex - próba znalezienia ścieżek plików
        # Używamy skompilowanego wzorca z klasy
        targets = []
        for match in self.FILE_PATH_PATTERN.finditer(content):
            targets.append(match.group(0))

        # Próba wykrycia akcji z prostych słów kluczowych
        action = "unknown"
        content_lower = content.lower()

        for action_name, keywords in self.ACTION_KEYWORDS.items():
            if any(word in content_lower for word in keywords):
                action = action_name
                break

        # Krok 2: LLM Fallback - jeśli nie znaleziono ścieżek lub akcji, użyj LLM
        if not targets or action == "unknown":
            logger.debug(
                "Regex nie znalazł wystarczających danych, używam LLM fallback..."
            )
            try:
                llm_result = await self._parse_with_llm(content)
                # Jeśli LLM znalazł coś lepszego, użyj tego
                if llm_result.targets:
                    targets = llm_result.targets
                if llm_result.action != "unknown":
                    action = llm_result.action
            except Exception as e:
                logger.warning(f"LLM fallback failed: {e}, używam wyniku regex")

        logger.info(
            f"Sparsowana intencja: action={action}, targets={targets}, params={{}}"
        )
        return Intent(action=action, targets=targets, params={})

    async def _parse_with_llm(self, content: str) -> Intent:
        """
        Użyj LLM do wyciągnięcia intencji z tekstu.

        Args:
            content: Tekst użytkownika

        Returns:
            Intent: Sparsowana intencja
        """
        prompt = f"""Wyciągnij z poniższego tekstu:
1. Akcję (edit/create/delete/read)
2. Ścieżki plików (jeśli są wymienione)

Tekst użytkownika: "{content}"

Odpowiedz w formacie JSON:
{{
  "action": "edit",
  "targets": ["venom_core/main.py"]
}}

Jeśli nie ma ścieżek plików, zwróć pustą listę targets. Jeśli nie ma jasnej akcji, użyj "unknown"."""

        # Przygotuj historię rozmowy
        chat_history = ChatHistory()
        chat_history.add_message(
            ChatMessageContent(
                role=AuthorRole.USER,
                content=prompt,
            )
        )

        try:
            # Pobierz serwis chat completion
            chat_service = self.kernel.get_service()

            # Wywołaj model
            response = await chat_service.get_chat_message_content(
                chat_history=chat_history, settings=None
            )

            # Parse odpowiedzi JSON
            response_text = str(response).strip()
            # Usuń markdown code blocks jeśli są
            response_text = re.sub(r"```json\s*", "", response_text)
            response_text = re.sub(r"```\s*", "", response_text)

            parsed = json.loads(response_text)
            return Intent(
                action=parsed.get("action", "unknown"),
                targets=parsed.get("targets", []),
                params={},
            )
        except Exception as e:
            logger.error(f"Błąd podczas parsowania LLM: {e}")
            return Intent(action="unknown", targets=[], params={})

    async def dispatch(
        self,
        intent: str,
        content: str,
        node_preference: dict = None,
        generation_params: dict = None,
    ) -> str:
        """
        Kieruje zadanie do odpowiedniego agenta na podstawie intencji.

        Args:
            intent: Sklasyfikowana intencja
            content: Treść zadania do wykonania
            node_preference: Opcjonalne preferencje węzła (np. {"tag": "location:server_room", "skill": "ShellSkill"})
            generation_params: Opcjonalne parametry generacji (temperature, max_tokens, etc.)

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
                logger.warning(
                    f"Nie udało się wykonać na węźle zdalnym: {e}. Fallback do lokalnego wykonania."
                )

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
            if intent == "STATUS_REPORT" and hasattr(agent, "generate_status_report"):
                result = await agent.generate_status_report()
            else:
                # Sprawdź czy agent wspiera generation_params
                if generation_params and hasattr(agent, "process_with_params"):
                    logger.debug(
                        f"Przekazuję parametry generacji do agenta: {generation_params}"
                    )
                    result = await agent.process_with_params(content, generation_params)
                else:
                    result = await agent.process(content)
            logger.info(f"Agent {agent.__class__.__name__} zakończył przetwarzanie")
            return result

        except Exception as e:
            logger.error(f"Błąd podczas przetwarzania zadania przez agenta: {e}")
            raise

    async def _dispatch_to_node(
        self, intent: str, content: str, node_preference: dict
    ) -> str:
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
            logger.warning(
                f"Nie znaleziono węzła obsługującego {skill_name}"
                + (f" z tagiem {tag}" if tag else "")
            )
            return None

        logger.info(
            f"Wykonuję zadanie na węźle zdalnym: {node.node_name} ({node.node_id})"
        )

        # Wykonaj na węźle
        response = await self.node_manager.execute_skill_on_node(
            node_id=node.node_id,
            skill_name=skill_name,
            method_name=method_name,
            parameters=self._prepare_skill_parameters(skill_name, content),
            timeout=60,
        )

        if response.success:
            logger.info(
                f"Zadanie wykonane na węźle {node.node_name} w {response.execution_time:.2f}s"
            )
            return response.result
        else:
            logger.error(f"Błąd wykonania na węźle {node.node_name}: {response.error}")
            raise RuntimeError(f"Remote execution failed: {response.error}")

    def _prepare_skill_parameters(self, skill_name: str, content: str) -> dict:
        """
        Przygotowuje parametry dla konkretnego skilla.

        Args:
            skill_name: Nazwa skilla
            content: Treść zadania

        Returns:
            Słownik parametrów dla skilla
        """
        if skill_name == "ShellSkill":
            return {"command": content}
        elif skill_name == "FileSkill":
            # TODO: Parsowanie content dla operacji na plikach
            # W przyszłości można dodać logikę parsowania z content
            return {}
        else:
            return {}
