"""Moduł: dispatcher - dyspozytornia zadań."""

from typing import Dict

from semantic_kernel import Kernel

from venom_core.agents.base import BaseAgent
from venom_core.agents.chat import ChatAgent
from venom_core.agents.coder import CoderAgent
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class TaskDispatcher:
    """Dyspozytornia zadań - kieruje zadania do odpowiednich agentów."""

    def __init__(self, kernel: Kernel):
        """
        Inicjalizacja TaskDispatcher.

        Args:
            kernel: Skonfigurowane jądro Semantic Kernel dla agentów
        """
        self.kernel = kernel

        # Inicjalizuj agentów
        self.coder_agent = CoderAgent(kernel)
        self.chat_agent = ChatAgent(kernel)

        # Mapa intencji do agentów
        self.agent_map: Dict[str, BaseAgent] = {
            "CODE_GENERATION": self.coder_agent,
            "GENERAL_CHAT": self.chat_agent,
            "KNOWLEDGE_SEARCH": self.chat_agent,  # TODO: podpiąć GraphRAG w przyszłości
        }

        logger.info("TaskDispatcher zainicjalizowany z agentami")

    async def dispatch(self, intent: str, content: str) -> str:
        """
        Kieruje zadanie do odpowiedniego agenta na podstawie intencji.

        Args:
            intent: Sklasyfikowana intencja (CODE_GENERATION, GENERAL_CHAT, KNOWLEDGE_SEARCH)
            content: Treść zadania do wykonania

        Returns:
            Wynik przetworzenia zadania przez agenta

        Raises:
            ValueError: Jeśli intencja jest nieznana
        """
        logger.info(f"Dispatcher kieruje zadanie z intencją: {intent}")

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
