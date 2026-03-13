"""Submit and queue handling for Orchestrator."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Coroutine
from uuid import UUID

from venom_core.config import SETTINGS
from venom_core.core import routing_integration
from venom_core.core.models import TaskRequest, TaskResponse, TaskStatus
from venom_core.utils.helpers import get_utc_now, get_utc_now_iso
from venom_core.utils.llm_runtime import get_active_llm_runtime
from venom_core.utils.logger import get_logger

if TYPE_CHECKING:
    from .orchestrator_core import Orchestrator

logger = get_logger(__name__)
_background_tasks: set[asyncio.Task[Any]] = set()


def _prepare_runtime_context(request: TaskRequest, runtime_info) -> dict:
    """
    Przygotowuje kontekst runtime dla zadania.

    Args:
        request: Żądanie zadania
        runtime_info: Informacje o runtime LLM

    Returns:
        Słownik z kontekstem runtime
    """
    runtime_context = runtime_info.to_payload()
    model_name = str(runtime_info.model_name or "").strip()
    adapter_prefix = "venom-adapter-"
    if model_name.startswith(adapter_prefix):
        runtime_context["adapter_applied"] = True
        runtime_context["adapter_id"] = (
            model_name[len(adapter_prefix) :].strip() or None
        )
    else:
        runtime_context["adapter_applied"] = False
        runtime_context["adapter_id"] = None
    if request.expected_config_hash:
        runtime_context["expected_config_hash"] = request.expected_config_hash
    if request.expected_runtime_id:
        runtime_context["expected_runtime_id"] = request.expected_runtime_id
    runtime_context["status"] = "ready"
    return runtime_context


def _init_request_trace(
    orch: "Orchestrator", task, request: TaskRequest, runtime_context: dict
) -> None:
    """
    Inicjalizuje tracer dla żądania.

    Args:
        orch: Orchestrator
        task: Zadanie
        request: Żądanie zadania
        runtime_context: Kontekst runtime
    """
    if not orch.request_tracer:
        return

    orch.request_tracer.create_trace(
        task.id,
        request.content,
        session_id=request.session_id,
    )
    orch.request_tracer.add_step(
        task.id,
        "User",
        "submit_request",
        status="ok",
        details="Request received",
    )
    orch.request_tracer.set_llm_metadata(task.id, metadata=runtime_context.copy())


async def _handle_queue_or_pause(
    orch: "Orchestrator", task, request: TaskRequest, runtime_info
) -> TaskResponse | None:
    """
    Obsługuje kolejkowanie lub pauzę zadania.

    Args:
        orch: Orchestrator
        task: Zadanie
        request: Żądanie zadania
        runtime_info: Informacje o runtime

    Returns:
        TaskResponse jeśli zadanie zakolejkowano, None jeśli można wykonać od razu
    """
    # Sprawdź czy system w pauzie
    if orch.task_manager.is_paused:
        orch.state_manager.add_log(
            task.id, "⏸️ System w trybie pauzy - zadanie czeka w kolejce"
        )
        await orch._broadcast_event(
            event_type="TASK_QUEUED",
            message=f"Zadanie {task.id} oczekuje - system wstrzymany",
            data={"task_id": str(task.id)},
        )
        logger.info("Zadanie %s zakolejkowane - system w pauzie", task.id)
        return _build_task_response(task, runtime_info)

    # Sprawdź limity kolejki
    if SETTINGS.ENABLE_QUEUE_LIMITS:
        has_capacity, active_count = await orch.task_manager.check_capacity()
        if not has_capacity:
            orch.state_manager.add_log(
                task.id,
                (
                    "⏳ Osiągnięto limit współbieżności "
                    f"({active_count}/{SETTINGS.MAX_CONCURRENT_TASKS}) - zadanie czeka"
                ),
            )
            await orch._broadcast_event(
                event_type="TASK_QUEUED",
                message=f"Zadanie {task.id} oczekuje - limit zadań równoległych",
                data={
                    "task_id": str(task.id),
                    "active": active_count,
                    "limit": SETTINGS.MAX_CONCURRENT_TASKS,
                },
            )
            logger.info(
                "Zadanie %s czeka - limit współbieżności (%s/%s)",
                task.id,
                active_count,
                SETTINGS.MAX_CONCURRENT_TASKS,
            )
            _spawn_background_task(run_task_with_queue(orch, task.id, request))
            return _build_task_response(task, runtime_info)

    return None


def _schedule_task_execution(
    orch: "Orchestrator", task_id: UUID, request: TaskRequest
) -> None:
    """
    Planuje wykonanie zadania (fast path lub queue).

    Args:
        orch: Orchestrator
        task_id: ID zadania
        request: Żądanie zadania
    """
    if should_use_fast_path(request):
        _spawn_background_task(run_task_fastpath(orch, task_id, request))
    else:
        _spawn_background_task(run_task_with_queue(orch, task_id, request))


def _log_background_task_failure(task: asyncio.Task[Any]) -> None:
    """Odbiera wyjątek taska w tle, aby nie gubić błędów i uniknąć warningów asyncio."""
    try:
        exc = task.exception()
    except asyncio.CancelledError:
        return
    if exc is None:
        return
    logger.error(
        "Task w tle zakończył się wyjątkiem: %s",
        exc,
        exc_info=(type(exc), exc, exc.__traceback__),
    )


def _spawn_background_task(coro: Coroutine[Any, Any, Any]) -> None:
    """Uruchamia task i trzyma referencję do czasu zakończenia."""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_log_background_task_failure)
    task.add_done_callback(_background_tasks.discard)


async def submit_task(orch: "Orchestrator", request: TaskRequest) -> TaskResponse:
    """Create task, apply queue limits, and schedule execution."""
    orch._refresh_kernel_if_needed()
    orch.last_activity = get_utc_now()

    task = orch.state_manager.create_task(content=request.content)

    runtime_info = get_active_llm_runtime()
    runtime_context = _prepare_runtime_context(request, runtime_info)
    routing_decision = routing_integration.build_routing_decision(
        request=request,
        runtime_info=runtime_info,
        state_manager=orch.state_manager,
    )
    orch.state_manager.update_context(
        task.id,
        {
            "llm_runtime": runtime_context,
            "routing_decision": routing_decision.to_dict(),
        },
    )

    _init_request_trace(orch, task, request, runtime_context)
    if orch.request_tracer:
        orch.request_tracer.add_step(
            task.id,
            "RoutingDecision",
            "compute",
            status="ok",
            details=str(routing_decision.to_dict()),
        )

    log_message = f"Zadanie uruchomione: {get_utc_now_iso()}"
    orch.state_manager.add_log(task.id, log_message)

    _spawn_background_task(
        orch._broadcast_event(
            event_type="TASK_CREATED",
            message=f"Utworzono nowe zadanie: {request.content[:100]}...",
            data={"task_id": str(task.id), "content": request.content},
        )
    )

    if request.images:
        orch.state_manager.add_log(
            task.id, f"Zadanie zawiera {len(request.images)} obrazów"
        )

    # Handle queue or pause
    queue_response = await _handle_queue_or_pause(orch, task, request, runtime_info)
    if queue_response is not None:
        return queue_response

    # Schedule execution
    _schedule_task_execution(orch, task.id, request)

    logger.info("Zadanie %s przyjęte do wykonania", task.id)
    return _build_task_response(task, runtime_info)


async def run_task_with_queue(
    orch: "Orchestrator", task_id: UUID, request: TaskRequest
) -> None:
    """Queue-aware wrapper around _run_task."""
    while True:
        if orch.task_manager.is_paused:
            await asyncio.sleep(0.5)
            continue

        has_capacity, _ = await orch.task_manager.check_capacity()
        if has_capacity:
            task_handle = asyncio.current_task()
            if task_handle is None:
                logger.error("Nie można uzyskać task handle dla %s", task_id)
                await orch.state_manager.update_status(
                    task_id,
                    TaskStatus.FAILED,
                    result="Błąd systemu: nie można uzyskać task handle",
                )
                return
            await orch.task_manager.register_task(task_id, task_handle)
            break

        await asyncio.sleep(0.5)

    try:
        await orch._run_task(task_id, request, fast_path=False)
    finally:
        await orch.task_manager.unregister_task(task_id)


async def run_task_fastpath(
    orch: "Orchestrator", task_id: UUID, request: TaskRequest
) -> None:
    """Fast-path execution without queue delay."""
    task_handle = asyncio.current_task()
    if task_handle is None:
        logger.error("Nie można uzyskać task handle dla %s", task_id)
        await orch.state_manager.update_status(
            task_id,
            TaskStatus.FAILED,
            result="Błąd systemu: nie można uzyskać task handle",
        )
        return
    await orch.task_manager.register_task(task_id, task_handle)
    try:
        await orch._run_task(task_id, request, fast_path=True)
    finally:
        await orch.task_manager.unregister_task(task_id)


def should_use_fast_path(request: TaskRequest) -> bool:
    """Fast-path for simple LLM-only requests."""
    if not request.content:
        return False
    if request.images:
        return False
    if request.forced_tool or request.forced_provider:
        return False
    return len(request.content) <= 500


def _build_task_response(task, runtime_info) -> TaskResponse:
    return TaskResponse(
        task_id=task.id,
        status=task.status,
        decision="allow",
        llm_provider=runtime_info.provider,
        llm_model=runtime_info.model_name,
        llm_endpoint=runtime_info.endpoint,
    )
