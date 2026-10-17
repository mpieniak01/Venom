"""Moduł: council - Konfiguracja The Council (native MAF Group Chat).

The Council to "Rada" agentów, którzy wspólnie rozwiązują złożone problemy
poprzez swobodną konwersację (Swarm Intelligence).
"""

from typing import Any, Dict, List, Optional

from agent_framework import AgentResponse, Message
from agent_framework_orchestrations import GroupChatBuilder, GroupChatState

from venom_core.agents.architect import ArchitectAgent
from venom_core.agents.coder import CoderAgent
from venom_core.agents.critic import CriticAgent
from venom_core.agents.guardian import GuardianAgent
from venom_core.config import SETTINGS
from venom_core.core.swarm import create_venom_agent_wrapper
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class CouncilExecutionError(RuntimeError):
    """A failed/incomplete Council must not become a completed task transcript."""


COUNCIL_TURN_INSTRUCTIONS = """
Pracujesz jako uczestnik konsultacji Council. Wykonaj jedną turę swojej roli,
uwzględniając zadanie użytkownika i dotychczasową dyskusję. Plan Architecta jest
propozycją do recenzji. Każdy etap wykonawczy wymaga uprawnień istniejących narzędzi.
Dla zadania tekstowego przygotuj odpowiedź tekstową; operacje wykonuj tylko wtedy,
gdy są wymagane przez użytkownika. Uwzględnij uwagi poprzednich uczestników.
"""
CRITIC_REVIEW_INSTRUCTIONS = """
Oceń ostatni wynik Coder względem zadania użytkownika, także gdy jest to tekst,
a nie kod. Pierwsza niepusta linia odpowiedzi musi być jednym z:
APPROVED
REVISE
REPLAN
APPROVED oznacza gotowość do kontroli Guardian. REVISE oznacza konkretny błąd do
poprawy przez Coder. REPLAN oznacza konieczną zmianę planu przez Architect.
Zapisz samo słowo decyzji w pierwszej linii, uzasadnienie w kolejnych liniach.
Nie wymagaj kodu, plików ani testów programu dla zadania wyłącznie tekstowego.
"""
COUNCIL_ROLE_INSTRUCTIONS = {
    "Architect": """Jesteś Architect w Council. Zaproponuj krótki plan realizacji
oryginalnego zadania w 2–3 krokach. Nie wykonuj planu i nie generuj JSON planu
samodzielnego workflow. Nie dodawaj plików ani operacji do zadania tekstowego.
""",
    "Coder": """Jesteś Coder w Council. Przygotuj lub popraw właściwy wynik zadania,
uwzględniając ostatnią recenzję. Dla pytania tekstowego odpowiedz tekstem w formie
wymaganej przez użytkownika. Kod lub operacje są potrzebne tylko wtedy, gdy wymaga
ich zadanie. Dostępne narzędzia nadal podlegają uprawnieniom. Nie wymyślaj dowodów
wykonania. Nie pisz recenzji ani kolejnych tur innych uczestników.
""",
    "Critic": """Jesteś Critic w Council. Recenzuj ostatni wynik Coder względem
oryginalnego zadania. Jeżeli spełnia wymagania i nie zawiera błędów, zatwierdź go.
Opcjonalny inny styl nie jest błędem wymagającym kolejnej poprawki. Nie kontynuuj
dialogu innych ról i nie odgrywaj Codera.
""",
    "Guardian": """Jesteś Guardian w Council. Wykonaj końcową kontrolę ostatniego
wyniku Coder i recenzji Critic względem oryginalnego zadania. Nie wprowadzaj nowych
wymagań. Dla zadania tekstowego oceń treść; testy programu dotyczą zmiany kodu.
""",
}
GUARDIAN_COMPLETION_INSTRUCTIONS = """
Oceń końcowy wynik względem zadania. Jeżeli zadanie wymaga kodu lub wykonania
operacji, wymagaj rzeczywistych dowodów ich weryfikacji; nie wymyślaj wyników testów.
Dla odpowiedzi tekstowej sprawdź jej poprawność i kompletność. Zakończ ostatnią
linią TERMINATE wyłącznie po zatwierdzeniu wyniku. W innym przypadku opisz,
co trzeba poprawić, bez słowa TERMINATE w ostatniej linii.
"""


class UserProxyAgent:
    """The human initiator, not an independently executing model."""

    def __init__(self, name: str, system_message: str = "", **kwargs):
        self.name = name
        self.system_message = system_message


class GroupChat:
    """Venom conversation state retained at the existing session boundary."""

    def __init__(
        self,
        agents,
        messages=None,
        max_round=20,
        allowed_or_disallowed_speaker_transitions=None,
        **kwargs,
    ):
        if not 1 <= max_round <= 100:
            raise ValueError("council_round_limit_out_of_range")
        self.agents = agents
        self.messages = list(messages or [])
        self.max_round = max_round
        self.allowed_or_disallowed_speaker_transitions = (
            allowed_or_disallowed_speaker_transitions or {}
        )
        self.allow_repeat_speaker = False
        self.speaker_selection_method = "venom_policy"
        self.speaker_transitions_type = "allowed"


def _guardian_finished(messages: list[Message]) -> bool:
    if not messages:
        return False
    last = messages[-1]
    lines = [line.strip() for line in last.text.splitlines() if line.strip()]
    return last.author_name == "Guardian" and bool(lines) and lines[-1] == "TERMINATE"


class GroupChatManager:
    """Run the native MAF group workflow under the configured transition graph."""

    def __init__(self, groupchat: GroupChat, llm_config=None):
        self.groupchat = groupchat
        self.llm_config = llm_config or {}

    def _select(self, state: GroupChatState) -> str:
        last = state.conversation[-1]
        speaker = last.author_name or "User"
        if speaker == "User":
            selected = "Architect"
        elif speaker == "Architect":
            selected = "Coder"
        elif speaker == "Coder":
            selected = "Critic"
        elif speaker == "Critic":
            decision = next(
                (line.strip() for line in last.text.splitlines() if line.strip()), ""
            )
            selected = {"APPROVED": "Guardian", "REPLAN": "Architect"}.get(
                decision, "Coder"
            )
        elif speaker == "Guardian":
            selected = "Coder"
        else:
            raise ValueError("unknown_council_speaker")
        transitions = self.groupchat.allowed_or_disallowed_speaker_transitions
        allowed: list[Any] = next(
            (
                targets
                for source, targets in transitions.items()
                if source.name == speaker
            ),
            [],
        )
        if selected not in {target.name for target in allowed}:
            raise ValueError("council_transition_not_allowed")
        return selected

    async def run(
        self, task: str, *, generation_params: Dict[str, Any] | None = None
    ) -> None:
        participants = [a for a in self.groupchat.agents if hasattr(a, "venom_agent")]
        initial = Message("user", [task], author_name="User")
        transcript = [initial]
        for participant in participants:
            participant.conversation.clear()
            participant.output_messages = transcript
            participant.generation_params = dict(generation_params or {})
        workflow = GroupChatBuilder(
            participants=participants,
            selection_func=self._select,
            termination_condition=_guardian_finished,
            max_rounds=self.groupchat.max_round,
        ).build()
        try:
            result = await workflow.run([initial])
            outputs = result.get_outputs()
            # The released SDK emits a terminal AgentResponse, not the full
            # history promised by older examples. Venom owns its transcript.
            if not outputs or not isinstance(outputs[-1], AgentResponse):
                raise RuntimeError("council_workflow_missing_completion")
            if not _guardian_finished(transcript):
                raise CouncilExecutionError("council_incomplete_no_guardian_approval")
        finally:
            self.groupchat.messages = [
                {"role": m.role, "name": m.author_name or m.role, "content": m.text}
                for m in transcript
            ]


# Konfiguracja Group Chat
DEFAULT_MAX_COUNCIL_ROUNDS = 20  # Maksymalna liczba rund konwersacji w Council
COUNCIL_SESSION_TIMEOUT = 300  # Timeout dla sesji Council w sekundach (5 minut)
DEFAULT_LOCAL_LLM_ENDPOINT = "http://localhost:11434/v1"


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
            llm_config: Konfiguracja LLM dla MAF
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
        logger.info("Tworzę The Council (native MAF Group Chat)...")

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
            system_message=COUNCIL_ROLE_INSTRUCTIONS["Architect"]
            + COUNCIL_TURN_INSTRUCTIONS,
            llm_config=self.llm_config,
            deliberation=True,
        )

        coder_wrapper = create_venom_agent_wrapper(
            agent=self.coder_agent,
            name="Coder",
            system_message=COUNCIL_ROLE_INSTRUCTIONS["Coder"]
            + COUNCIL_TURN_INSTRUCTIONS,
            llm_config=self.llm_config,
            deliberation=True,
        )

        critic_wrapper = create_venom_agent_wrapper(
            agent=self.critic_agent,
            name="Critic",
            system_message=(
                COUNCIL_ROLE_INSTRUCTIONS["Critic"]
                + COUNCIL_TURN_INSTRUCTIONS
                + CRITIC_REVIEW_INSTRUCTIONS
            ),
            llm_config=self.llm_config,
            deliberation=True,
        )

        guardian_wrapper = create_venom_agent_wrapper(
            agent=self.guardian_agent,
            name="Guardian",
            system_message=(
                COUNCIL_ROLE_INSTRUCTIONS["Guardian"]
                + COUNCIL_TURN_INSTRUCTIONS
                + GUARDIAN_COMPLETION_INSTRUCTIONS
            ),
            llm_config=self.llm_config,
            deliberation=True,
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
            architect_wrapper: [coder_wrapper],
            coder_wrapper: [critic_wrapper],  # Every new candidate requires review
            critic_wrapper: [coder_wrapper, architect_wrapper, guardian_wrapper],
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
            speaker_selection_method="auto",  # Venom policy wybiera następnego mówcę
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

    async def run(
        self, task: str, *, generation_params: Dict[str, Any] | None = None
    ) -> str:
        """
        Uruchamia dyskusję Council dla zadanego zadania.

        Args:
            task: Zadanie/pytanie od użytkownika

        Returns:
            Skonsolidowany wynik dyskusji
        """
        logger.info(f"Council rozpoczyna dyskusję: {task[:100]}...")

        try:
            import asyncio

            await asyncio.wait_for(
                self.manager.run(task, generation_params=generation_params),
                timeout=COUNCIL_SESSION_TIMEOUT,
            )

            # Zbierz wyniki z historii czatu
            result = self._extract_result()

            logger.info("Council zakończył dyskusję")
            return result

        except asyncio.TimeoutError:
            error_msg = f"Council przekroczył timeout ({COUNCIL_SESSION_TIMEOUT}s)"
            logger.error(error_msg)
            raise CouncilExecutionError(error_msg) from None
        except Exception as e:
            error_msg = f"Błąd podczas dyskusji Council: {e}"
            logger.error(error_msg)
            raise CouncilExecutionError(error_msg) from e

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
        if self.group_chat.messages[-1].get(
            "name"
        ) == "Guardian" and last_message.strip().splitlines()[-1:] == ["TERMINATE"]:
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
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.7,
) -> Dict:
    """
    Tworzy konfigurację LLM dla lokalnego modelu (Ollama/LiteLLM).

    Args:
        base_url: URL do lokalnego serwera LLM. Jeśli None, użyje SETTINGS.LLM_LOCAL_ENDPOINT
        model: Nazwa modelu. Jeśli None, użyje SETTINGS.LLM_MODEL_NAME
        temperature: Temperatura dla generacji (0.0-1.0)

    Returns:
        Dict z konfiguracją LLM dla MAF

    Raises:
        ValueError: Jeśli parametry są nieprawidłowe

    Note:
        Parametry base_url i model domyślnie są None i automatycznie pobierane z SETTINGS.
        Można je nadpisać przekazując konkretne wartości.
    """
    # Użyj wartości z SETTINGS jeśli nie podano
    if base_url is None:
        base_url = SETTINGS.LLM_LOCAL_ENDPOINT or DEFAULT_LOCAL_LLM_ENDPOINT
    if model is None:
        model = SETTINGS.LLM_MODEL_NAME or SETTINGS.LOCAL_LLAMA3_MODEL

    # Walidacja parametrów
    if not 0.0 <= temperature <= 1.0:
        raise ValueError(
            f"Temperature musi być w zakresie 0.0-1.0, otrzymano: {temperature}"
        )

    if not model or not isinstance(model, str):
        raise ValueError(f"model musi być niepustym stringiem, otrzymano: {model}")

    if not base_url or not isinstance(base_url, str):
        raise ValueError(
            f"base_url musi być niepustym stringiem, otrzymano: {base_url}"
        )

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
