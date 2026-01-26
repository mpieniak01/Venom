"""Moduł: orchestrator - orkiestracja zadań w tle (zrefaktoryzowany)."""

import os
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional
from uuid import UUID

from venom_core.core.dispatcher import TaskDispatcher
from venom_core.core.flow_router import FlowRouter
from venom_core.core.flows.base import EventBroadcaster
from venom_core.core.intent_manager import IntentManager
from venom_core.core.lessons_manager import LessonsManager
from venom_core.core.models import (
    TaskExtraContext,
    TaskRequest,
    TaskResponse,
    VenomTask,
)
from venom_core.core.queue_manager import QueueManager
from venom_core.core.state_manager import StateManager
from venom_core.core.streaming_handler import StreamingHandler
from venom_core.core.tracer import RequestTracer
from venom_core.execution.kernel_builder import KernelBuilder
from venom_core.memory.memory_skill import MemorySkill
from venom_core.perception.eyes import Eyes
from venom_core.utils.logger import get_logger

# Import decomposed modules
from .event_broadcaster import EventBroadcasterClient
from .flow_coordinator import FlowCoordinator
from .kernel_lifecycle import KernelLifecycleManager
from .learning_handler import LearningHandler
from .middleware import Middleware
from .orchestrator_dispatch import run_task as run_task_operation
from .orchestrator_events import broadcast_event as broadcast_event_operation
from .orchestrator_events import build_error_envelope as build_error_envelope_operation
from .orchestrator_events import set_runtime_error as set_runtime_error_operation
from .orchestrator_events import trace_llm_start as trace_llm_start_operation
from .orchestrator_events import trace_step_async as trace_step_async_operation
from .orchestrator_flows import (
    code_generation_with_review as code_generation_with_review_operation,
)
from .orchestrator_flows import execute_campaign_mode as execute_campaign_mode_operation
from .orchestrator_flows import (
    execute_forge_workflow as execute_forge_workflow_operation,
)
from .orchestrator_flows import execute_healing_cycle as execute_healing_cycle_operation
from .orchestrator_flows import (
    generate_help_response as generate_help_response_operation,
)
from .orchestrator_flows import handle_remote_issue as handle_remote_issue_operation
from .orchestrator_flows import is_public_plugin as is_public_plugin_operation
from .orchestrator_flows import run_council as run_council_operation
from .orchestrator_flows import should_use_council as should_use_council_operation
from .orchestrator_kernel import (
    get_runtime_context_char_limit,
    refresh_kernel,
    refresh_kernel_if_needed,
)
from .orchestrator_queue import abort_task as abort_task_operation
from .orchestrator_queue import emergency_stop as emergency_stop_operation
from .orchestrator_queue import get_queue_status as get_queue_status_operation
from .orchestrator_queue import pause_queue as pause_queue_operation
from .orchestrator_queue import purge_queue as purge_queue_operation
from .orchestrator_queue import resume_queue as resume_queue_operation
from .orchestrator_submit import run_task_fastpath as run_task_fastpath_operation
from .orchestrator_submit import run_task_with_queue as run_task_with_queue_operation
from .orchestrator_submit import should_use_fast_path as should_use_fast_path_operation
from .orchestrator_submit import submit_task as submit_task_operation
from .session_handler import SessionHandler
from .task_manager import TaskManager

logger = get_logger(__name__)

if TYPE_CHECKING:
    from venom_core.core.council import CouncilConfig
    from venom_core.core.flows.campaign import CampaignFlow
    from venom_core.core.flows.code_review import CodeReviewLoop
    from venom_core.core.flows.council import CouncilFlow
    from venom_core.core.flows.forge import ForgeFlow
    from venom_core.core.flows.healing import HealingFlow
    from venom_core.core.flows.issue_handler import IssueHandlerFlow


class Orchestrator:
    """Orkiestrator zadań - zarządzanie wykonywaniem zadań w tle."""

    def __init__(
        self,
        state_manager: StateManager,
        intent_manager: Optional[IntentManager] = None,
        task_dispatcher: Optional[TaskDispatcher] = None,
        event_broadcaster: Optional[EventBroadcaster] = None,
        lessons_store: Optional[Any] = None,
        node_manager: Optional[Any] = None,
        session_store: Optional[Any] = None,
        request_tracer: Optional[RequestTracer] = None,
    ):
        """
        Inicjalizacja Orchestrator.

        Args:
            state_manager: Menedżer stanu zadań
            intent_manager: Opcjonalny menedżer klasyfikacji intencji (jeśli None, zostanie utworzony)
            task_dispatcher: Opcjonalny dispatcher zadań (jeśli None, zostanie utworzony)
            event_broadcaster: Opcjonalny broadcaster zdarzeń do WebSocket
            lessons_store: Opcjonalny magazyn lekcji (dla meta-uczenia)
            node_manager: Opcjonalny menedżer węzłów (dla distributed execution)
            session_store: Opcjonalny magazyn historii sesji
            request_tracer: Opcjonalny tracer do śledzenia przepływu zadań
        """
        self.state_manager = state_manager
        self.intent_manager: IntentManager = intent_manager or IntentManager()
        self.event_broadcaster: Optional[EventBroadcaster] = event_broadcaster
        self.lessons_store: Optional[Any] = lessons_store
        self.node_manager: Optional[Any] = node_manager
        self.request_tracer: Optional[RequestTracer] = request_tracer
        self._testing_mode = bool(os.getenv("PYTEST_CURRENT_TEST"))

        # Inicjalizuj dispatcher jeśli nie został przekazany
        if task_dispatcher is None:
            kernel_builder = KernelBuilder()
            kernel = kernel_builder.build_kernel()
            task_dispatcher = TaskDispatcher(
                kernel, event_broadcaster=event_broadcaster, node_manager=node_manager
            )

        self.task_dispatcher: TaskDispatcher = task_dispatcher

        # Inicjalizuj Eyes dla obsługi obrazów
        self.eyes = Eyes()
        self.memory_skill = MemorySkill()

        # Inicjalizuj nowe komponenty (refactored)
        self.streaming_handler = StreamingHandler(state_manager=state_manager)
        self.lessons_manager = LessonsManager(
            state_manager=state_manager,
            lessons_store=lessons_store,
            event_broadcaster=event_broadcaster,
        )
        self.flow_router = FlowRouter()

        # Inicjalizuj zrefaktoryzowane moduły zarządzające
        self.kernel_manager = KernelLifecycleManager(
            task_dispatcher=task_dispatcher,
            event_broadcaster=event_broadcaster,
            node_manager=node_manager,
        )
        self.event_client = EventBroadcasterClient(event_broadcaster)
        self.session_handler = SessionHandler(
            state_manager=state_manager,
            memory_skill=self.memory_skill,
            session_store=session_store,
            testing_mode=self._testing_mode,
            request_tracer=request_tracer,
        )
        self.learning_handler = LearningHandler(
            state_manager=state_manager,
            lessons_manager=self.lessons_manager,
        )
        self.middleware = Middleware(
            state_manager=state_manager,
            event_broadcaster=event_broadcaster,
            request_tracer=request_tracer,
        )
        self.flow_coordinator = FlowCoordinator(
            state_manager=state_manager,
            task_dispatcher=task_dispatcher,
            event_broadcaster=event_broadcaster,
            orchestrator_submit_task=self.submit_task,
        )

        # Inicjalizuj flows (delegowane logiki biznesowe)
        self._code_review_loop: Optional[CodeReviewLoop] = None
        self._council_flow: Optional[CouncilFlow] = None
        self._council_config: Optional["CouncilConfig"] = None
        self._forge_flow: Optional[ForgeFlow] = None
        self._campaign_flow: Optional[CampaignFlow] = None
        self._healing_flow: Optional[HealingFlow] = None
        self._issue_handler_flow: Optional[IssueHandlerFlow] = None

        # Tracking ostatniej aktywności dla idle mode
        self.last_activity: Optional[datetime] = None

        # Queue Manager (Dashboard v2.3) - delegacja zarządzania kolejką
        self.task_manager = TaskManager(
            queue_manager=QueueManager(
                state_manager=state_manager, event_broadcaster=event_broadcaster
            )
        )

        # Pipeline components
        from .task_pipeline.context_builder import ContextBuilder
        from .task_pipeline.result_processor import ResultProcessor
        from .task_pipeline.task_validator import TaskValidator

        self.context_builder = ContextBuilder(self)
        self.result_processor = ResultProcessor(self)
        self.validator = TaskValidator(self)

    def _get_runtime_context_char_limit(self, runtime_info) -> int:
        """Wyznacza przybliżony limit znaków dla promptu na podstawie runtime."""
        return get_runtime_context_char_limit(runtime_info)

    def _refresh_kernel(self, runtime_info=None) -> None:
        """Odtwarza kernel i agentów po zmianie konfiguracji LLM (delegacja do KernelManager)."""
        self.task_dispatcher = refresh_kernel(
            self.kernel_manager, self.flow_coordinator, runtime_info
        )

    def _refresh_kernel_if_needed(self) -> None:
        """Sprawdza drift konfiguracji i odświeża kernel przy zmianie (delegacja do KernelManager)."""
        updated_dispatcher = refresh_kernel_if_needed(
            self.kernel_manager, self.flow_coordinator
        )
        if updated_dispatcher is not None:
            self.task_dispatcher = updated_dispatcher

    @property
    def is_paused(self) -> bool:
        """Zwraca, czy kolejka jest wstrzymana (delegacja do queue_manager)."""
        return self.task_manager.is_paused

    @property
    def active_tasks(self) -> dict:
        """Zwraca słownik aktywnych zadań (delegacja do queue_manager)."""
        return self.task_manager.active_tasks

    async def _broadcast_event(
        self,
        event_type: str,
        message: str,
        agent: Optional[str] = None,
        data: Optional[dict[str, Any]] = None,
    ) -> None:
        """Wysyła zdarzenie do WebSocket (delegacja)."""
        await broadcast_event_operation(
            self, event_type=event_type, message=message, agent=agent, data=data
        )

    def _trace_llm_start(self, task_id: UUID, intent: str) -> None:
        """Zapisuje krok startu LLM dla pomiarów latencji (delegacja)."""
        trace_llm_start_operation(self, task_id, intent)

    async def submit_task(self, request: TaskRequest) -> TaskResponse:
        """Przyjmuje nowe zadanie do wykonania (delegacja)."""
        return await submit_task_operation(self, request)

    async def _run_task_with_queue(self, task_id: UUID, request: TaskRequest) -> None:
        """Wrapper dla _run_task z obsługą kolejki (delegacja)."""
        await run_task_with_queue_operation(self, task_id, request)

    async def _run_task_fastpath(self, task_id: UUID, request: TaskRequest) -> None:
        """Fast-path: uruchamia zadanie bez oczekiwania w kolejce (delegacja)."""
        await run_task_fastpath_operation(self, task_id, request)

    async def pause_queue(self) -> dict:
        """
        Wstrzymuje przyjmowanie nowych zadań do wykonania.

        Returns:
            Dict z wynikiem operacji
        """
        return await pause_queue_operation(self.task_manager)

    async def resume_queue(self) -> dict:
        """
        Wznawia przyjmowanie zadań.

        Returns:
            Dict z wynikiem operacji
        """
        return await resume_queue_operation(self.task_manager)

    async def purge_queue(self) -> dict:
        """
        Usuwa wszystkie zadania o statusie PENDING z kolejki.

        Returns:
            Dict z wynikiem operacji (liczba usuniętych zadań)
        """
        return await purge_queue_operation(self.task_manager)

    async def abort_task(self, task_id: UUID) -> dict:
        """
        Przerywa wykonywanie konkretnego zadania.

        Args:
            task_id: ID zadania do przerwania

        Returns:
            Dict z wynikiem operacji
        """
        return await abort_task_operation(self.task_manager, task_id)

    async def emergency_stop(self) -> dict:
        """
        Awaryjne zatrzymanie - przerywa wszystkie aktywne zadania i czyści kolejkę.

        Returns:
            Dict z wynikiem operacji
        """
        return await emergency_stop_operation(self.task_manager)

    def get_queue_status(self) -> dict:
        """
        Zwraca aktualny status kolejki zadań.

        Returns:
            Dict ze statusem kolejki
        """
        return get_queue_status_operation(self.task_manager)

    def get_token_economist(self):
        """
        Zwraca instancję TokenEconomist z task_dispatcher.

        Returns:
            TokenEconomist lub None jeśli nie jest dostępny

        Raises:
            NotImplementedError: Funkcja nie jest jeszcze w pełni zaimplementowana
        """
        raise NotImplementedError(
            "get_token_economist niezaimplementowane - dodać getter w KernelBuilder"
        )

    NON_LEARNING_INTENTS = {
        "TIME_REQUEST",
        "INFRA_STATUS",
    }

    NON_LLM_INTENTS = {
        "TIME_REQUEST",
        "INFRA_STATUS",
        "UNSUPPORTED_TASK",
    }

    KERNEL_FUNCTION_INTENTS = {
        "CODE_GENERATION",
        "KNOWLEDGE_SEARCH",
        "FILE_OPERATION",
        "RESEARCH",
        "VERSION_CONTROL",
        "TOOL_CREATION",
        "E2E_TESTING",
        "DOCUMENTATION",
        "RELEASE_PROJECT",
    }

    def _build_error_envelope(
        self,
        *,
        error_code: str,
        error_message: str,
        error_details: Optional[dict] = None,
        stage: Optional[str] = None,
        retryable: bool = False,
        error_class: Optional[str] = None,
    ) -> dict:
        return build_error_envelope_operation(
            error_code=error_code,
            error_message=error_message,
            error_details=error_details,
            stage=stage,
            retryable=retryable,
            error_class=error_class,
        )

    def _set_runtime_error(self, task_id: UUID, envelope: dict) -> None:
        set_runtime_error_operation(self, task_id, envelope)

    def _should_store_lesson(
        self,
        request: TaskRequest,
        intent: str = "",
        agent=None,
    ) -> bool:
        """
        Sprawdza czy należy zapisać lekcję dla danego zadania.

        Args:
            request: Oryginalne żądanie zadania
            intent: Sklasyfikowana intencja
            agent: Opcjonalny agent

        Returns:
            True jeśli lekcja powinna być zapisana
        """
        # Deleguj do LessonsManager
        return self.lessons_manager.should_store_lesson(request, intent, agent)

    def _should_log_learning(
        self,
        request: TaskRequest,
        intent: str,
        tool_required: bool,
        agent=None,
    ) -> bool:
        """
        Sprawdza czy należy zapisać wpis procesu nauki (LLM-only).

        Zachowane dla kompatybilności z testami.
        """
        if not request.store_knowledge:
            return False
        if tool_required:
            return False
        if intent in self.NON_LEARNING_INTENTS:
            return False
        if agent and getattr(agent, "disable_learning", False):
            return False
        return True

    def _append_learning_log(
        self,
        task_id: UUID,
        intent: str,
        prompt: str,
        result: str,
        success: bool,
        error: str = "",
    ) -> None:
        """Zapisuje wpis procesu nauki do JSONL (delegacja)."""
        from .orchestrator_dispatch import append_learning_log

        append_learning_log(self, task_id, intent, prompt, result, success, error)

    def _heuristic_summary(self, full_history: list) -> str:
        """Delegacja do SessionHandler (kompatybilność z testami)."""
        return self.session_handler._heuristic_summary(full_history)

    def _summarize_history_llm(self, history_text: str) -> str:
        """Delegacja do SessionHandler (kompatybilność z testami)."""
        return self.session_handler._summarize_history_llm(history_text)

    def _ensure_session_summary(self, task_id: UUID, task: VenomTask) -> None:
        """Tworzy streszczenie historii sesji (delegacja)."""
        from .orchestrator_dispatch import ensure_session_summary

        ensure_session_summary(self, task_id, task)

    def _persist_session_context(self, task_id: UUID, request: TaskRequest) -> None:
        """Delegacja do session_handler."""
        self.session_handler.persist_session_context(task_id, request)

    def _append_session_history(
        self, task_id: UUID, role: str, content: str, session_id: Optional[str]
    ) -> None:
        """Delegacja do session_handler."""
        self.session_handler.append_session_history(task_id, role, content, session_id)

    def _build_session_context_block(
        self,
        request: TaskRequest,
        task_id: UUID,
        include_memory: bool = True,
    ) -> str:
        """Delegacja do session_handler."""
        return self.session_handler.build_session_context_block(
            request, task_id, include_memory=include_memory
        )

    def _should_use_fast_path(self, request: TaskRequest) -> bool:
        """Fast-path dla prostych zadań (delegacja)."""
        return should_use_fast_path_operation(request)

    async def _trace_step_async(
        self, task_id: UUID, actor: str, action: str, **kwargs
    ) -> None:
        await trace_step_async_operation(self, task_id, actor, action, **kwargs)

    async def _apply_preferred_language(
        self, task_id: UUID, request: TaskRequest, result: str
    ) -> str:
        """Delegacja do session_handler."""
        return await self.session_handler.apply_preferred_language(
            task_id, request, result, self.intent_manager
        )

    async def _run_task(
        self,
        task_id: UUID,
        request: TaskRequest,
        fast_path: bool = False,
    ) -> None:
        """Wykonuje zadanie w tle (delegacja)."""
        await run_task_operation(self, task_id, request, fast_path=fast_path)

    def _is_perf_test_prompt(self, content: str) -> bool:
        """Sprawdź, czy treść zadania pochodzi z testów wydajności (delegacja)."""
        return self.context_builder.is_perf_test_prompt(content)

    async def _complete_perf_test_task(self, task_id: UUID) -> None:
        """Zakończ zadanie testu wydajności (delegacja)."""
        await self.context_builder.complete_perf_test_task(task_id)

    async def _prepare_context(self, task_id: UUID, request: TaskRequest) -> str:
        """Przygotowuje kontekst zadania (delegacja)."""
        return await self.context_builder.prepare_context(task_id, request)

    @staticmethod
    def _format_extra_context(extra_context: "TaskExtraContext") -> str:
        """Formatuje dodatkowy kontekst do czytelnego bloku tekstu (delegacja)."""
        from .task_pipeline.context_builder import format_extra_context as format_fn

        return format_fn(extra_context)

    async def _code_generation_with_review(
        self, task_id: UUID, user_request: str
    ) -> str:
        """Pętla generowania kodu z oceną (delegacja)."""
        return await code_generation_with_review_operation(self, task_id, user_request)

    def _should_use_council(
        self,
        content: str | None = None,
        intent: str = "",
        context: str | None = None,
    ) -> bool:
        """Decyduje czy użyć trybu Council (delegacja)."""
        return should_use_council_operation(self, content, intent, context)

    async def run_council(self, task_id: UUID, context: str) -> str:
        """Uruchamia tryb Council (delegacja)."""
        return await run_council_operation(self, task_id, context)

    def _normalize_council_tuple(self, council_result):
        """Zapewnia że create_council zwraca krotkę (user_proxy, group_chat, manager)."""

        if isinstance(council_result, tuple):
            padded = list(council_result) + [None] * (3 - len(council_result))
            return tuple(padded[:3])

        user_proxy = getattr(council_result, "user_proxy", None)
        group_chat = getattr(council_result, "group_chat", None)
        manager = getattr(council_result, "manager", None)
        return user_proxy, group_chat, manager

    async def execute_healing_cycle(self, task_id: UUID, test_path: str = ".") -> dict:
        """
        Pętla samonaprawy (Test-Diagnose-Fix-Apply).

        Delegowane do HealingFlow.

        Args:
            task_id: ID zadania
            test_path: Ścieżka do testów

        Returns:
            Słownik z wynikami (success, iterations, final_report)
        """
        return await execute_healing_cycle_operation(self, task_id, test_path)

    async def execute_forge_workflow(
        self, task_id: UUID, tool_specification: str, tool_name: str
    ) -> dict:
        """
        Wykonuje workflow "The Forge" - tworzenie nowego narzędzia.

        Algorytm:
        1. CRAFT: Toolmaker generuje kod narzędzia
        2. TEST: Toolmaker generuje test jednostkowy
        3. VERIFY: Guardian testuje narzędzie w Dockerze
        4. LOAD: SkillManager ładuje narzędzie do Kernela

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
        return await execute_forge_workflow_operation(
            self, task_id, tool_specification, tool_name
        )

    async def handle_remote_issue(self, issue_number: int) -> dict:
        """
        Obsługuje Issue z GitHub: pobiera szczegóły, tworzy plan, implementuje fix, tworzy PR.

        Delegowane do IssueHandlerFlow.

        Args:
            issue_number: Numer Issue do obsłużenia

        Returns:
            Dict z wynikiem operacji
        """
        return await handle_remote_issue_operation(self, issue_number)

    async def execute_campaign_mode(
        self, goal_store=None, max_iterations: int = 10
    ) -> dict:
        """
        Tryb Kampanii - autonomiczna realizacja roadmapy.

        Delegowane do CampaignFlow.

        Args:
            goal_store: Magazyn celów (GoalStore)
            max_iterations: Maksymalna liczba iteracji (zabezpieczenie)

        Returns:
            Dict z wynikami kampanii
        """
        return await execute_campaign_mode_operation(self, goal_store, max_iterations)

    async def _generate_help_response(self, task_id: UUID) -> str:
        """
        Generuje dynamiczną odpowiedź pomocy z informacjami o dostępnych umiejętnościach.

        Args:
            task_id: ID zadania

        Returns:
            Sformatowana odpowiedź pomocy w formacie Markdown
        """
        return await generate_help_response_operation(self, task_id)

    def _is_public_plugin(self, plugin_name: str) -> bool:
        """
        Sprawdza czy plugin jest publiczny (nie wewnętrzny).

        Args:
            plugin_name: Nazwa pluginu

        Returns:
            True jeśli plugin jest publiczny
        """
        return is_public_plugin_operation(plugin_name)
