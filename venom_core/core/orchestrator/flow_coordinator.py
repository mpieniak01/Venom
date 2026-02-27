"""Koordynacja i routing przepływów pracy (flows/workflows)."""

from typing import TYPE_CHECKING, Any, Awaitable, Callable, Optional, Protocol, Tuple
from uuid import UUID

from venom_core.agents.guardian import GuardianAgent
from venom_core.core.council import (
    CouncilConfig,
    CouncilSession,
    create_local_llm_config,
)
from venom_core.core.flow_router import FlowRouter
from venom_core.core.flows.base import EventBroadcaster
from venom_core.core.flows.campaign import CampaignFlow
from venom_core.core.flows.code_review import CodeReviewLoop
from venom_core.core.flows.council import CouncilFlow
from venom_core.core.flows.forge import ForgeFlow
from venom_core.core.flows.healing import HealingFlow
from venom_core.core.flows.issue_handler import IssueHandlerFlow
from venom_core.core.models import TaskRequest, TaskResponse
from venom_core.utils.logger import get_logger

if TYPE_CHECKING:
    from venom_core.core.dispatcher import TaskDispatcher
    from venom_core.core.state_manager import StateManager

logger = get_logger(__name__)


class MiddlewareLike(Protocol):
    async def broadcast_event(
        self,
        *,
        event_type: str,
        message: str,
        agent: Optional[str] = None,
        data: Optional[dict[str, object]] = None,
    ) -> None: ...


class FlowCoordinator:
    """Koordynuje i zarządza różnymi przepływami pracy."""

    def __init__(
        self,
        state_manager: "StateManager",
        task_dispatcher: "TaskDispatcher",
        event_broadcaster: Optional[EventBroadcaster] = None,
        orchestrator_submit_task: Optional[
            Callable[[TaskRequest], Awaitable[TaskResponse]]
        ] = None,
    ):
        """
        Inicjalizacja FlowCoordinator.

        Args:
            state_manager: Menedżer stanu zadań
            task_dispatcher: Dispatcher zadań
            event_broadcaster: Opcjonalny broadcaster zdarzeń
            orchestrator_submit_task: Referencja do metody submit_task w Orchestrator
        """
        self.state_manager = state_manager
        self.task_dispatcher = task_dispatcher
        self.event_broadcaster = event_broadcaster
        self.orchestrator_submit_task = orchestrator_submit_task

        # Lazy-initialized flows
        self._code_review_loop: Optional[CodeReviewLoop] = None
        self._council_flow: Optional[CouncilFlow] = None
        self._council_config: Optional[CouncilConfig] = None
        self._forge_flow: Optional[ForgeFlow] = None
        self._campaign_flow: Optional[CampaignFlow] = None
        self._healing_flow: Optional[HealingFlow] = None
        self._issue_handler_flow: Optional[IssueHandlerFlow] = None

        # Flow router
        self.flow_router = FlowRouter()

    def reset_flows(self) -> None:
        """Resetuje flowy zależne od dispatcherów (używane po odświeżeniu kernela)."""
        self._code_review_loop = None
        self._council_flow = None
        self._forge_flow = None
        self._campaign_flow = None
        self._healing_flow = None
        self._issue_handler_flow = None

    def should_use_council(self, content: str, intent: str) -> bool:
        """
        Decyduje czy użyć trybu Council dla danego zadania.

        Args:
            content: Treść zadania
            intent: Sklasyfikowana intencja

        Returns:
            True jeśli należy użyć Council, False dla standardowego flow
        """
        # Lazy init CouncilFlow
        if self._council_flow is None:
            self._council_flow = CouncilFlow(
                state_manager=self.state_manager,
                task_dispatcher=self.task_dispatcher,
                event_broadcaster=self.event_broadcaster,
            )
            # Zaktualizuj flow_router z council_flow
            self.flow_router.set_council_flow(self._council_flow)

        # Deleguj decyzję do FlowRouter
        return self.flow_router.should_use_council(content, intent)

    async def run_council(
        self, task_id: UUID, context: str, middleware: MiddlewareLike
    ) -> str:
        """
        Uruchamia tryb Council (AutoGen Group Chat) dla złożonych zadań.

        Args:
            task_id: ID zadania
            context: Kontekst zadania
            middleware: Middleware do broadcast_event

        Returns:
            Wynik dyskusji Council
        """
        self.state_manager.add_log(
            task_id, "🏛️ THE COUNCIL: Rozpoczynam tryb Group Chat (Swarm Intelligence)"
        )

        await middleware.broadcast_event(
            event_type="COUNCIL_STARTED",
            message="The Council rozpoczyna dyskusję nad zadaniem",
            data={"task_id": str(task_id)},
        )

        try:
            if self._council_config is None:
                coder = getattr(self.task_dispatcher, "coder_agent", None)
                critic = getattr(self.task_dispatcher, "critic_agent", None)
                architect = getattr(self.task_dispatcher, "architect_agent", None)

                guardian = GuardianAgent(kernel=self.task_dispatcher.kernel)
                llm_config = create_local_llm_config()

                if coder is None or critic is None or architect is None:
                    raise RuntimeError(
                        "Brak wymaganych agentów Council (coder/critic/architect)"
                    )

                self._council_config = CouncilConfig(
                    coder_agent=coder,
                    critic_agent=critic,
                    architect_agent=architect,
                    guardian_agent=guardian,
                    llm_config=llm_config,
                )

            council_tuple = self._council_config.create_council()
            user_proxy, group_chat, manager = self._normalize_council_tuple(
                council_tuple
            )

            session = CouncilSession(user_proxy, group_chat, manager)

            members = []
            if group_chat is not None and getattr(group_chat, "agents", None):
                members = [
                    getattr(agent, "name", str(agent)) for agent in group_chat.agents
                ]

            await middleware.broadcast_event(
                event_type="COUNCIL_MEMBERS",
                message=f"Council składa się z {len(members)} członków",
                data={"task_id": str(task_id), "members": members},
            )

            result = await session.run(context)

            get_message_count = getattr(session, "get_message_count", lambda: 0)
            get_speakers = getattr(session, "get_speakers", lambda: members)
            message_count = get_message_count()
            speakers = get_speakers() or members

            self.state_manager.add_log(
                task_id,
                f"🏛️ THE COUNCIL: Dyskusja zakończona - {message_count} wiadomości, "
                f"uczestnicy: {', '.join(speakers)}",
            )

            await middleware.broadcast_event(
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

            await middleware.broadcast_event(
                event_type="COUNCIL_ERROR",
                message=error_msg,
                data={"task_id": str(task_id), "error": str(e)},
            )

            logger.warning("Council zawiódł - powrót do standardowego flow")
            return f"Council mode nie powiódł się: {e}"

    def _normalize_council_tuple(
        self, council_result: Any
    ) -> Tuple[Optional[Any], Optional[Any], Optional[Any]]:
        """Zapewnia że create_council zwraca krotkę (user_proxy, group_chat, manager)."""

        if isinstance(council_result, tuple):
            padded = list(council_result) + [None] * (3 - len(council_result))
            return tuple(padded[:3])

        user_proxy = getattr(council_result, "user_proxy", None)
        group_chat = getattr(council_result, "group_chat", None)
        manager = getattr(council_result, "manager", None)
        return user_proxy, group_chat, manager

    async def code_generation_with_review(
        self, task_id: UUID, user_request: str
    ) -> str:
        """
        Pętla generowania kodu z oceną przez CriticAgent.

        Args:
            task_id: ID zadania
            user_request: Żądanie użytkownika

        Returns:
            Zaakceptowany kod lub kod po naprawach
        """
        coder = getattr(self.task_dispatcher, "coder_agent", None)
        critic = getattr(self.task_dispatcher, "critic_agent", None)

        if coder is None or critic is None:
            logger.warning(
                "TaskDispatcher nie ma zainicjalizowanych agentów coder/critic - używam prostego dispatch"
            )
            return await self.task_dispatcher.dispatch("CODE_GENERATION", user_request)

        # Lazy init CodeReviewLoop
        if self._code_review_loop is None:
            skill_manager = getattr(self.task_dispatcher, "skill_manager", None)
            self._code_review_loop = CodeReviewLoop(
                state_manager=self.state_manager,
                coder_agent=coder,
                critic_agent=critic,
                skill_manager=skill_manager,
            )

        # Deleguj do CodeReviewLoop
        return await self._code_review_loop.execute(task_id, user_request)

    async def execute_healing_cycle(self, task_id: UUID, test_path: str = ".") -> dict:
        """
        Pętla samonaprawy (Test-Diagnose-Fix-Apply).

        Args:
            task_id: ID zadania
            test_path: Ścieżka do testów

        Returns:
            Słownik z wynikami (success, iterations, final_report)
        """
        # Lazy init HealingFlow
        if self._healing_flow is None:
            self._healing_flow = HealingFlow(
                state_manager=self.state_manager,
                task_dispatcher=self.task_dispatcher,
                event_broadcaster=self.event_broadcaster,
            )

        return await self._healing_flow.execute(task_id, test_path)

    async def execute_forge_workflow(
        self, task_id: UUID, tool_specification: str, tool_name: str
    ) -> dict:
        """
        Wykonuje workflow "The Forge" - tworzenie nowego narzędzia.

        Args:
            task_id: ID zadania
            tool_specification: Specyfikacja narzędzia (co ma robić)
            tool_name: Nazwa narzędzia (snake_case, bez .py)

        Returns:
            Słownik z wynikami:
            - success: bool - czy narzędzie zostało stworzone i załadowane
            - tool_name: str - nazwa narzędzia
            - message: str - opis wyniku
            - code: str - wygenerowany kod (jeśli sukces)
        """
        # Lazy init ForgeFlow
        if self._forge_flow is None:
            self._forge_flow = ForgeFlow(
                state_manager=self.state_manager,
                task_dispatcher=self.task_dispatcher,
                event_broadcaster=self.event_broadcaster,
            )

        # Deleguj do ForgeFlow
        return await self._forge_flow.execute(task_id, tool_specification, tool_name)

    async def handle_remote_issue(self, issue_number: int) -> dict:
        """
        Obsługuje Issue z GitHub.

        Args:
            issue_number: Numer Issue do obsłużenia

        Returns:
            Dict z wynikiem operacji
        """
        # Lazy init IssueHandlerFlow
        if self._issue_handler_flow is None:
            self._issue_handler_flow = IssueHandlerFlow(
                state_manager=self.state_manager,
                task_dispatcher=self.task_dispatcher,
                event_broadcaster=self.event_broadcaster,
            )

        return await self._issue_handler_flow.execute(issue_number)

    async def execute_campaign_mode(
        self, goal_store=None, max_iterations: int = 10
    ) -> dict:
        """
        Tryb Kampanii - autonomiczna realizacja roadmapy.

        Args:
            goal_store: Magazyn celów (GoalStore)
            max_iterations: Maksymalna liczba iteracji (zabezpieczenie)

        Returns:
            Dict z wynikami kampanii
        """
        if self.orchestrator_submit_task is None:
            raise RuntimeError("Brak orchestrator_submit_task dla CampaignFlow")
        if self._campaign_flow is None:
            self._campaign_flow = CampaignFlow(
                state_manager=self.state_manager,
                orchestrator_submit_task=self.orchestrator_submit_task,
                event_broadcaster=self.event_broadcaster,
            )

        return await self._campaign_flow.execute(goal_store, max_iterations)
