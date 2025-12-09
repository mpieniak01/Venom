"""Moduł: council - Logika The Council (AutoGen Group Chat)."""

from typing import Callable, Optional
from uuid import UUID

from venom_core.core.dispatcher import TaskDispatcher
from venom_core.core.state_manager import StateManager
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

# Ustawienia dla The Council (AutoGen Group Chat)
ENABLE_COUNCIL_MODE = True  # Flaga do włączania/wyłączania trybu Council
COUNCIL_TASK_THRESHOLD = (
    100  # Minimalna długość zadania aby użyć Council (liczba znaków)
)

# Słowa kluczowe sugerujące potrzebę współpracy agentów (dla decyzji Council vs Standard)
COUNCIL_COLLABORATION_KEYWORDS = [
    "projekt",
    "aplikacja",
    "system",
    "stwórz grę",
    "zbuduj",
    "zaprojektuj",
    "zaimplementuj",
    "kompletny",
    "cała aplikacja",
]


class CouncilFlow:
    """Logika The Council - autonomiczna dyskusja agentów."""

    def __init__(
        self,
        state_manager: StateManager,
        task_dispatcher: TaskDispatcher,
        event_broadcaster: Optional[Callable] = None,
    ):
        """
        Inicjalizacja CouncilFlow.

        Args:
            state_manager: Menedżer stanu zadań
            task_dispatcher: Dispatcher zadań (dostęp do agentów)
            event_broadcaster: Opcjonalny broadcaster zdarzeń
        """
        self.state_manager = state_manager
        self.task_dispatcher = task_dispatcher
        self.event_broadcaster = event_broadcaster
        self._council_config = None

    async def _broadcast_event(
        self, event_type: str, message: str, agent: str = None, data: dict = None
    ):
        """
        Wysyła zdarzenie do WebSocket (jeśli broadcaster jest dostępny).

        Args:
            event_type: Typ zdarzenia
            message: Treść wiadomości
            agent: Opcjonalna nazwa agenta
            data: Opcjonalne dodatkowe dane
        """
        if self.event_broadcaster:
            await self.event_broadcaster.broadcast_event(
                event_type=event_type, message=message, agent=agent, data=data
            )

    def should_use_council(self, context: str, intent: str) -> bool:
        """
        Decyduje czy użyć trybu Council dla danego zadania.

        Args:
            context: Kontekst zadania
            intent: Sklasyfikowana intencja

        Returns:
            True jeśli należy użyć Council, False dla standardowego flow
        """
        if not ENABLE_COUNCIL_MODE:
            return False

        # Council dla złożonych zadań planistycznych
        if intent == "COMPLEX_PLANNING":
            return True

        # Council dla długich zadań wymagających współpracy
        if len(context) > COUNCIL_TASK_THRESHOLD:
            # Sprawdź czy zadanie zawiera słowa kluczowe sugerujące współpracę
            context_lower = context.lower()
            for keyword in COUNCIL_COLLABORATION_KEYWORDS:
                if keyword in context_lower:
                    logger.info(f"Wykryto słowo kluczowe '{keyword}' - użyję Council")
                    return True

        return False

    async def run(self, task_id: UUID, context: str) -> str:
        """
        Uruchamia tryb Council (AutoGen Group Chat) dla złożonych zadań.

        W tym trybie agenci prowadzą autonomiczną dyskusję:
        - Architect planuje
        - Coder implementuje
        - Critic sprawdza
        - Guardian weryfikuje testy

        Args:
            task_id: ID zadania
            context: Kontekst zadania

        Returns:
            Wynik dyskusji Council
        """
        logger.info(f"Uruchamiam The Council dla zadania {task_id}")

        self.state_manager.add_log(
            task_id, "🏛️ THE COUNCIL: Rozpoczynam tryb Group Chat (Swarm Intelligence)"
        )

        await self._broadcast_event(
            event_type="COUNCIL_STARTED",
            message="The Council rozpoczyna dyskusję nad zadaniem",
            data={"task_id": str(task_id)},
        )

        try:
            # Lazy init council config
            if self._council_config is None:
                from venom_core.core.council import (
                    CouncilConfig,
                    create_local_llm_config,
                )

                # Pobierz agentów z dispatchera
                coder = self.task_dispatcher.coder_agent
                critic = self.task_dispatcher.critic_agent
                architect = self.task_dispatcher.architect_agent

                # Guardian musimy utworzyć (nie ma go w standardowym dispatcher)
                from venom_core.agents.guardian import GuardianAgent

                guardian = GuardianAgent(kernel=self.task_dispatcher.kernel)

                # Stwórz konfigurację LLM (lokalny model)
                llm_config = create_local_llm_config()

                # Inicjalizuj Council Config
                self._council_config = CouncilConfig(
                    coder_agent=coder,
                    critic_agent=critic,
                    architect_agent=architect,
                    guardian_agent=guardian,
                    llm_config=llm_config,
                )

                logger.info("Council Config zainicjalizowany")

            # Stwórz sesję Council
            # UWAGA: Tworzymy nową sesję przy każdym wywołaniu aby zapewnić czysty stan
            # i uniknąć kontaminacji historii między różnymi zadaniami.
            # GroupChat przechowuje historię wiadomości, więc ponowne użycie
            # mogłoby prowadzić do nieprawidłowych kontekstów dla kolejnych zadań.
            from venom_core.core.council import CouncilSession

            user_proxy, group_chat, manager = self._council_config.create_council()
            session = CouncilSession(user_proxy, group_chat, manager)

            # Broadcast informacji o uczestnikach
            await self._broadcast_event(
                event_type="COUNCIL_MEMBERS",
                message=f"Council składa się z {len(group_chat.agents)} członków",
                data={
                    "task_id": str(task_id),
                    "members": [agent.name for agent in group_chat.agents],
                },
            )

            # Uruchom dyskusję
            result = await session.run(context)

            # Loguj szczegóły dyskusji
            message_count = session.get_message_count()
            speakers = session.get_speakers()

            self.state_manager.add_log(
                task_id,
                f"🏛️ THE COUNCIL: Dyskusja zakończona - {message_count} wiadomości, "
                f"uczestnicy: {', '.join(speakers)}",
            )

            await self._broadcast_event(
                event_type="COUNCIL_COMPLETED",
                message=f"Council zakończył dyskusję po {message_count} wiadomościach",
                data={
                    "task_id": str(task_id),
                    "message_count": message_count,
                    "speakers": speakers,
                },
            )

            logger.info(f"Council zakończył zadanie {task_id}")
            return result

        except Exception as e:
            error_msg = f"❌ Błąd podczas działania Council: {e}"
            logger.error(error_msg)

            self.state_manager.add_log(task_id, error_msg)

            await self._broadcast_event(
                event_type="COUNCIL_ERROR",
                message=error_msg,
                data={"task_id": str(task_id), "error": str(e)},
            )

            # Fallback do standardowego flow
            logger.warning("Council zawiódł - powrót do standardowego flow")
            return f"{error_msg}\n\nPróbuję standardowy flow jako fallback..."
