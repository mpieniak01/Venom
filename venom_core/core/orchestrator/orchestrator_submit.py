"""Submit and queue handling for Orchestrator."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from venom_core.config import SETTINGS
from venom_core.core.models import TaskRequest, TaskResponse, TaskStatus
from venom_core.utils.llm_runtime import get_active_llm_runtime
from venom_core.utils.logger import get_logger

if TYPE_CHECKING:
    from .orchestrator_core import Orchestrator

logger = get_logger(__name__)


async def submit_task(orch: "Orchestrator", request: TaskRequest) -> TaskResponse:
    """Create task, apply queue limits, and schedule execution."""
    orch._refresh_kernel_if_needed()
    orch.last_activity = datetime.now()

    task = orch.state_manager.create_task(content=request.content)

    runtime_info = get_active_llm_runtime()
    runtime_context = runtime_info.to_payload()
    if request.expected_config_hash:
        runtime_context["expected_config_hash"] = request.expected_config_hash
    if request.expected_runtime_id:
        runtime_context["expected_runtime_id"] = request.expected_runtime_id
    runtime_context["status"] = "ready"
    orch.state_manager.update_context(task.id, {"llm_runtime": runtime_context})

    if orch.request_tracer:
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

    log_message = f"Zadanie uruchomione: {datetime.now().isoformat()}"
    orch.state_manager.add_log(task.id, log_message)

    asyncio.create_task(
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
            asyncio.create_task(run_task_with_queue(orch, task.id, request))
            return _build_task_response(task, runtime_info)

    if should_use_fast_path(request):
        asyncio.create_task(run_task_fastpath(orch, task.id, request))
    else:
        asyncio.create_task(run_task_with_queue(orch, task.id, request))

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
        llm_provider=runtime_info.provider,
        llm_model=runtime_info.model_name,
        llm_endpoint=runtime_info.endpoint,
    )
