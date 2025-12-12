"""Moduł: council - Konfiguracja The Council (Group Chat).

The Council to "Rada" agentów, którzy wspólnie rozwiązują złożone problemy
poprzez swobodną konwersację (Swarm Intelligence).
"""

from typing import Dict, List

from venom_core.agents.architect import ArchitectAgent
from venom_core.agents.coder import CoderAgent
from venom_core.agents.critic import CriticAgent
from venom_core.agents.guardian import GuardianAgent
from venom_core.config import SETTINGS
from venom_core.core.swarm import create_venom_agent_wrapper
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

try:
    from autogen import GroupChat, GroupChatManager, UserProxyAgent
except ImportError:  # pragma: no cover - fallback for environments bez AutoGen
    logger.warning(
        "Pakiet 'autogen' nie jest dostępny - używam lekkich stubów na potrzeby testów."
    )

    class UserProxyAgent:  # type: ignore
        def __init__(
            self,
            name: str,
            system_message: str,
            code_execution_config=False,
            human_input_mode: str = "NEVER",
            llm_config=None,
        ):
            self.name = name
            self.system_message = system_message
            self.code_execution_config = code_execution_config
            self.human_input_mode = human_input_mode
            self.llm_config = llm_config
            self._history = []

        def initiate_chat(self, manager, message: str):
            """Prosta implementacja - dodaje wiadomość użytkownika."""
            manager.groupchat.messages.append({"name": self.name, "content": message})

    class GroupChat:  # type: ignore
        def __init__(
            self,
            agents,
            messages=None,
            max_round=20,
            speaker_selection_method="auto",
            allow_repeat_speaker=False,
            allowed_or_disallowed_speaker_transitions=None,
            speaker_transitions_type="allowed",
        ):
            self.agents = agents
            self.messages = messages or []
            self.max_round = max_round
            self.speaker_selection_method = speaker_selection_method
            self.allow_repeat_speaker = allow_repeat_speaker
            self.allowed_or_disallowed_speaker_transitions = (
                allowed_or_disallowed_speaker_transitions or {}
            )
            self.speaker_transitions_type = speaker_transitions_type

    class GroupChatManager:  # type: ignore
        def __init__(self, groupchat, llm_config=None):
            self.groupchat = groupchat
            self.llm_config = llm_config or {}


# Konfiguracja Group Chat
DEFAULT_MAX_COUNCIL_ROUNDS = 20  # Maksymalna liczba rund konwersacji w Council
COUNCIL_SESSION_TIMEOUT = 300  # Timeout dla sesji Council w sekundach (5 minut)


class CouncilConfig:
    """Konfiguracja The Council - Group Chat agentów."""

    def __init__(
        self,
        coder_agent: CoderAgent,
        critic_agent: CriticAgent,
        architect_agent: ArchitectAgent,
        guardian_agent: GuardianAgent,
        llm_config: Dict,
    ):
        """
        Inicjalizacja konfiguracji Council.

        Args:
            coder_agent: Instancja CoderAgent
            critic_agent: Instancja CriticAgent
            architect_agent: Instancja ArchitectAgent
            guardian_agent: Instancja GuardianAgent
            llm_config: Konfiguracja LLM dla AutoGen
        """
        self.coder_agent = coder_agent
        self.critic_agent = critic_agent
        self.architect_agent = architect_agent
        self.guardian_agent = guardian_agent
        self.llm_config = llm_config

        logger.info("CouncilConfig zainicjalizowany")

    def create_council(self) -> tuple:
        """
        Tworzy instancję Group Chat z odpowiednią konfiguracją.

        Returns:
            Tupla (UserProxyAgent, GroupChat, GroupChatManager)
        """
        logger.info("Tworzę The Council (Group Chat)...")

        # 1. Stwórz UserProxy - reprezentuje użytkownika w czacie
        user_proxy = UserProxyAgent(
            name="User",
            system_message="Reprezentujesz użytkownika. Zadajesz pytanie/zlecasz zadanie, a następnie obserwujesz dyskusję agentów.",
            code_execution_config=False,  # Nie wykonuje kodu samodzielnie
            human_input_mode="NEVER",  # Tryb autonomiczny - bez ingerencji człowieka
            llm_config=False,  # UserProxy nie potrzebuje LLM
        )

        # 2. Stwórz wrappery dla agentów Venom
        architect_wrapper = create_venom_agent_wrapper(
            agent=self.architect_agent,
            name="Architect",
            system_message=self.architect_agent.PLANNING_PROMPT,
            llm_config=self.llm_config,
        )

        coder_wrapper = create_venom_agent_wrapper(
            agent=self.coder_agent,
            name="Coder",
            system_message=self.coder_agent.SYSTEM_PROMPT,
            llm_config=self.llm_config,
        )

        critic_wrapper = create_venom_agent_wrapper(
            agent=self.critic_agent,
            name="Critic",
            system_message=self.critic_agent.SYSTEM_PROMPT,
            llm_config=self.llm_config,
        )

        guardian_wrapper = create_venom_agent_wrapper(
            agent=self.guardian_agent,
            name="Guardian",
            system_message=self.guardian_agent.SYSTEM_PROMPT,
            llm_config=self.llm_config,
        )

        # 3. Zdefiniuj uczestników Group Chat
        agents = [
            user_proxy,
            architect_wrapper,
            coder_wrapper,
            critic_wrapper,
            guardian_wrapper,
        ]

        # 4. Zdefiniuj graf przepływu konwersacji (allowed_speaker_transitions)
        # Format: {from_agent: [to_agent1, to_agent2, ...]}
        allowed_transitions = {
            user_proxy: [architect_wrapper],  # User -> Architect
            architect_wrapper: [
                coder_wrapper,
                critic_wrapper,
            ],  # Architect -> Coder/Critic
            coder_wrapper: [
                critic_wrapper,
                guardian_wrapper,
            ],  # Coder -> Critic/Guardian
            critic_wrapper: [
                coder_wrapper,
                architect_wrapper,
            ],  # Critic -> Coder (naprawa) lub Architect (replan)
            guardian_wrapper: [
                coder_wrapper,
                user_proxy,
            ],  # Guardian -> Coder (naprawa) lub User (TERMINATE)
        }

        # 5. Stwórz Group Chat
        group_chat = GroupChat(
            agents=agents,
            messages=[],
            max_round=DEFAULT_MAX_COUNCIL_ROUNDS,
            speaker_selection_method="auto",  # AutoGen wybiera następnego mówcę
            allow_repeat_speaker=False,  # Nie pozwól temu samemu agentowi mówić dwa razy z rzędu
            allowed_or_disallowed_speaker_transitions=allowed_transitions,
            speaker_transitions_type="allowed",
        )

        # 6. Stwórz Manager do zarządzania Group Chat
        manager = GroupChatManager(
            groupchat=group_chat,
            llm_config=self.llm_config,
        )

        logger.info(f"The Council utworzony z {len(agents)} agentami")

        return user_proxy, group_chat, manager


class CouncilSession:
    """Sesja rozmowy Council - enkapsuluje pojedynczy dialog."""

    def __init__(
        self,
        user_proxy: UserProxyAgent,
        group_chat: GroupChat,
        manager: GroupChatManager,
    ):
        """
        Inicjalizacja sesji Council.

        Args:
            user_proxy: Agent użytkownika
            group_chat: Instancja Group Chat
            manager: Manager Group Chat
        """
        self.user_proxy = user_proxy
        self.group_chat = group_chat
        self.manager = manager

        logger.info("CouncilSession zainicjalizowana")

    async def run(self, task: str) -> str:
        """
        Uruchamia dyskusję Council dla zadanego zadania.

        Args:
            task: Zadanie/pytanie od użytkownika

        Returns:
            Skonsolidowany wynik dyskusji
        """
        logger.info(f"Council rozpoczyna dyskusję: {task[:100]}...")

        try:
            # Zainicjuj dyskusję - UserProxy wysyła zadanie do Managera
            # Manager koordynuje rozmowę między agentami
            # UWAGA: initiate_chat jest synchroniczny w AutoGen 0.2.x
            # Używamy asyncio.to_thread aby nie blokować event loop
            import asyncio

            # Dodaj timeout aby uniknąć zawieszonych sesji
            await asyncio.wait_for(
                asyncio.to_thread(
                    self.user_proxy.initiate_chat, self.manager, message=task
                ),
                timeout=COUNCIL_SESSION_TIMEOUT,
            )

            # Zbierz wyniki z historii czatu
            result = self._extract_result()

            logger.info("Council zakończył dyskusję")
            return result

        except asyncio.TimeoutError:
            error_msg = f"Council przekroczył timeout ({COUNCIL_SESSION_TIMEOUT}s)"
            logger.error(error_msg)
            return error_msg
        except Exception as e:
            error_msg = f"Błąd podczas dyskusji Council: {e}"
            logger.error(error_msg)
            return error_msg

    def _extract_result(self) -> str:
        """
        Ekstrahuje wynik z historii Group Chat.

        Returns:
            Skonsolidowany wynik dyskusji
        """
        if not self.group_chat.messages:
            return "Brak wiadomości w dyskusji"

        # Stwórz podsumowanie dyskusji
        result = "=== THE COUNCIL - TRANSKRYPCJA DYSKUSJI ===\n\n"

        for msg in self.group_chat.messages:
            # Waliduj strukturę wiadomości
            if not isinstance(msg, dict):
                logger.warning(f"Nieprawidłowa wiadomość (nie dict): {msg}")
                continue

            # Każda wiadomość to dict z kluczami: 'role', 'content', 'name'
            speaker = msg.get("name", "Unknown")
            content = msg.get("content", "")

            # Pomiń puste wiadomości
            if not content:
                continue

            result += f"[{speaker}]:\n{content}\n\n"

        # Sprawdź czy dyskusja zakończyła się słowem "TERMINATE"
        last_message = self.group_chat.messages[-1].get("content", "")
        if "TERMINATE" in last_message:
            result += "✅ Zadanie zakończone sukcesem (Guardian zatwierdził)\n"
        else:
            result += "⚠️ Dyskusja przerwana przed zakończeniem\n"

        return result

    def get_message_count(self) -> int:
        """
        Zwraca liczbę wiadomości w dyskusji.

        Returns:
            Liczba wiadomości
        """
        return len(self.group_chat.messages)

    def get_speakers(self) -> List[str]:
        """
        Zwraca listę agentów, którzy wzięli udział w dyskusji.

        Returns:
            Lista nazw agentów
        """
        speakers = set()
        for msg in self.group_chat.messages:
            speaker = msg.get("name")
            if speaker:
                speakers.add(speaker)

        return list(speakers)


def create_local_llm_config(
    base_url: str = None,
    model: str = None,
    temperature: float = 0.7,
) -> Dict:
    """
    Tworzy konfigurację LLM dla lokalnego modelu (Ollama/LiteLLM).

    Args:
        base_url: URL do lokalnego serwera LLM. Jeśli None, użyje SETTINGS.LLM_LOCAL_ENDPOINT
        model: Nazwa modelu. Jeśli None, użyje SETTINGS.LOCAL_LLAMA3_MODEL
        temperature: Temperatura dla generacji (0.0-1.0)

    Returns:
        Dict z konfiguracją LLM dla AutoGen

    Raises:
        ValueError: Jeśli parametry są nieprawidłowe

    Note:
        Parametry base_url i model domyślnie są None i automatycznie pobierane z SETTINGS.
        Można je nadpisać przekazując konkretne wartości.
    """
    # Użyj wartości z SETTINGS jeśli nie podano
    if base_url is None:
        base_url = SETTINGS.LLM_LOCAL_ENDPOINT
    if model is None:
        model = SETTINGS.LOCAL_LLAMA3_MODEL

    # Walidacja parametrów
    if not 0.0 <= temperature <= 1.0:
        raise ValueError(
            f"Temperature musi być w zakresie 0.0-1.0, otrzymano: {temperature}"
        )

    if not base_url or not isinstance(base_url, str):
        raise ValueError(
            f"base_url musi być niepustym stringiem, otrzymano: {base_url}"
        )

    if not model or not isinstance(model, str):
        raise ValueError(f"model musi być niepustym stringiem, otrzymano: {model}")

    config = {
        "config_list": [
            {
                "model": model,
                "base_url": base_url,
                "api_key": "EMPTY",  # Lokalny model nie wymaga klucza
            }
        ],
        "temperature": temperature,
        "timeout": 120,  # Timeout w sekundach
    }

    logger.info(f"Utworzono konfigurację dla lokalnego LLM: {model} @ {base_url}")
    return config
