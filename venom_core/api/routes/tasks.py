"""Moduł: routes/tasks - Endpointy API dla zadań i historii."""

import asyncio
import json
import multiprocessing as mp
import os
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from typing import Annotated, Any, AsyncGenerator, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from venom_core.api.dependencies import (
    get_orchestrator,
    get_request_tracer,
    get_state_manager,
)
from venom_core.api.routes import system_deps
from venom_core.api.schemas.tasks import (
    HistoryRequestDetail,
    HistoryRequestSummary,
    TaskRequest,
    TaskResponse,
)
from venom_core.core import metrics as metrics_module
from venom_core.core.models import TaskStatus, VenomTask
from venom_core.core.orchestrator import Orchestrator
from venom_core.core.state_manager import StateManager
from venom_core.core.tracer import RequestTracer, TraceStatus
from venom_core.execution.onnx_llm_client import OnnxLlmClient
from venom_core.utils.llm_runtime import get_active_llm_runtime
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["tasks"])
_ONNX_EXECUTOR: ProcessPoolExecutor | None = None
_ONNX_WORKER_CLIENT: OnnxLlmClient | None = None

ORCHESTRATOR_UNAVAILABLE = "Orchestrator nie jest dostępny"
STATE_MANAGER_UNAVAILABLE = "StateManager nie jest dostępny"
REQUEST_TRACER_UNAVAILABLE = "RequestTracer nie jest dostępny"

TASK_CREATE_RESPONSES: dict[int | str, dict[str, Any]] = {
    503: {"description": ORCHESTRATOR_UNAVAILABLE},
    500: {"description": "Błąd wewnętrzny podczas tworzenia zadania"},
}
TASK_GET_RESPONSES: dict[int | str, dict[str, Any]] = {
    503: {"description": STATE_MANAGER_UNAVAILABLE},
    404: {"description": "Zadanie o podanym ID nie istnieje"},
}
TASK_STREAM_RESPONSES: dict[int | str, dict[str, Any]] = {
    503: {"description": STATE_MANAGER_UNAVAILABLE},
    404: {"description": "Zadanie o podanym ID nie istnieje"},
}
TASKS_LIST_RESPONSES: dict[int | str, dict[str, Any]] = {
    503: {"description": STATE_MANAGER_UNAVAILABLE},
}
HISTORY_LIST_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"description": "Nieprawidłowy filtr statusu"},
    503: {"description": REQUEST_TRACER_UNAVAILABLE},
}
HISTORY_DETAIL_RESPONSES: dict[int | str, dict[str, Any]] = {
    503: {"description": REQUEST_TRACER_UNAVAILABLE},
    404: {"description": "Request o podanym ID nie istnieje"},
}


def _get_onnx_executor() -> ProcessPoolExecutor:
    global _ONNX_EXECUTOR
    if _ONNX_EXECUTOR is None:
        # Dedicated process avoids GIL/event-loop starvation during heavy ONNX generation.
        _ONNX_EXECUTOR = ProcessPoolExecutor(
            max_workers=1,
            mp_context=mp.get_context("spawn"),
        )
    return _ONNX_EXECUTOR


def _generate_onnx_response_sync(
    messages: list[dict[str, str]],
    max_new_tokens: int | None,
    temperature: float | None,
) -> str:
    global _ONNX_WORKER_CLIENT
    # Keep a warm ONNX client in the dedicated worker process so model weights
    # stay resident between consecutive requests.
    if _ONNX_WORKER_CLIENT is None:
        _ONNX_WORKER_CLIENT = OnnxLlmClient()
    client = _ONNX_WORKER_CLIENT
    return client.generate(
        messages=messages,
        max_new_tokens=max_new_tokens,
        temperature=temperature,
    ).strip()


def _get_llm_runtime(task: VenomTask) -> dict:
    """Wyciąga informacje o runtime LLM zapisane w zadaniu."""
    context = getattr(task, "context_history", {}) or {}
    runtime = context.get("llm_runtime", {}) or {}
    return runtime


def _extract_context_preview(steps: list) -> Optional[dict]:
    """
    Wyszukuje krok `context_preview` w TraceStep i zwraca zdekodowane detale (json).
    """
    for step in steps or []:
        try:
            if getattr(step, "action", None) == "context_preview" and step.details:
                return json.loads(step.details)
        except Exception:
            continue
    return None


def _build_history_summary(trace) -> HistoryRequestSummary:
    duration = (
        (trace.finished_at - trace.created_at).total_seconds()
        if trace.finished_at
        else None
    )
    return HistoryRequestSummary(
        request_id=trace.request_id,
        prompt=trace.prompt,
        status=trace.status,
        session_id=trace.session_id,
        created_at=trace.created_at.isoformat(),
        finished_at=(trace.finished_at.isoformat() if trace.finished_at else None),
        duration_seconds=duration,
        llm_provider=trace.llm_provider,
        llm_model=trace.llm_model,
        llm_endpoint=trace.llm_endpoint,
        llm_config_hash=trace.llm_config_hash,
        llm_runtime_id=trace.llm_runtime_id,
        forced_tool=trace.forced_tool,
        forced_provider=trace.forced_provider,
        forced_intent=trace.forced_intent,
        error_code=trace.error_code,
        error_class=trace.error_class,
        error_message=trace.error_message,
        error_details=trace.error_details,
        error_stage=trace.error_stage,
        error_retryable=trace.error_retryable,
        feedback=trace.feedback,
    )


def _validate_trace_status(status: Optional[str]) -> None:
    if status is None:
        return
    valid_statuses = [s.value for s in TraceStatus]
    if status in valid_statuses:
        return
    raise HTTPException(
        status_code=400,
        detail=f"Nieprawidłowy status. Dozwolone wartości: {', '.join(valid_statuses)}",
    )


def _serialize_trace_steps(trace) -> list[dict[str, Any]]:
    return [
        {
            "component": step.component,
            "action": step.action,
            "timestamp": step.timestamp.isoformat(),
            "status": step.status,
            "details": step.details,
        }
        for step in trace.steps
    ]


def _extract_task_context(task: Optional[VenomTask]) -> dict[str, Any]:
    if task is None:
        return {}
    return getattr(task, "context_history", {}) or {}


def _serialize_context_used(task: Optional[VenomTask]) -> Optional[dict]:
    if task is None or not hasattr(task, "context_used") or not task.context_used:
        return None
    context_used = task.context_used
    if isinstance(context_used, dict):
        return context_used
    if hasattr(context_used, "model_dump"):
        return context_used.model_dump()
    if hasattr(context_used, "dict"):
        return context_used.dict()
    if hasattr(context_used, "__dict__"):
        return dict(context_used.__dict__)
    return None


def _should_emit_stream_event(
    *,
    status_changed: bool,
    logs_delta: list[str],
    result_changed: bool,
    ticks_since_emit: int,
    heartbeat_every_ticks: int,
) -> bool:
    return (
        status_changed
        or bool(logs_delta)
        or result_changed
        or ticks_since_emit >= heartbeat_every_ticks
    )


def _build_stream_payload(task: VenomTask, logs_delta: list[str]) -> dict[str, Any]:
    runtime_info = _get_llm_runtime(task)
    return {
        "task_id": str(task.id),
        "status": task.status,
        "logs": logs_delta,
        "result": task.result,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "llm_provider": runtime_info.get("provider"),
        "llm_model": runtime_info.get("model"),
        "llm_endpoint": runtime_info.get("endpoint"),
        "llm_status": runtime_info.get("status"),
        "context_history": task.context_history,
    }


def _build_task_finished_payload(task: VenomTask) -> dict[str, Any]:
    runtime_info = _get_llm_runtime(task)
    return {
        "task_id": str(task.id),
        "status": task.status,
        "result": task.result,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "llm_provider": runtime_info.get("provider"),
        "llm_model": runtime_info.get("model"),
        "llm_endpoint": runtime_info.get("endpoint"),
        "llm_status": runtime_info.get("status"),
        "context_history": task.context_history,
    }


def _resolve_stream_event_name(
    *, status_changed: bool, logs_delta: list[str], result_changed: bool
) -> str:
    if status_changed or logs_delta or result_changed:
        return "task_update"
    return "heartbeat"


def _resolve_poll_interval(
    *,
    previous_result: Optional[str],
    status: TaskStatus,
    fast_poll_interval_seconds: float,
    poll_interval_seconds: float,
) -> float:
    if previous_result is None and status == TaskStatus.PROCESSING:
        return fast_poll_interval_seconds
    return poll_interval_seconds


def _assert_task_available_for_stream(
    task_id: UUID, state_manager: StateManager
) -> None:
    if state_manager.get_task(task_id) is None:
        raise HTTPException(status_code=404, detail=f"Zadanie {task_id} nie istnieje")


def _build_missing_task_payload(task_id: UUID) -> dict[str, Any]:
    return {
        "task_id": str(task_id),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": "gone",
        "detail": "Task no longer available in StateManager",
    }


def _is_terminal_status(status: TaskStatus) -> bool:
    return status in (TaskStatus.COMPLETED, TaskStatus.FAILED)


def _build_onnx_task_messages(request: TaskRequest) -> list[dict[str, str]]:
    system_prompt = "Jesteś operacyjnym asystentem Venom."
    if request.forced_intent == "COMPLEX_PLANNING":
        system_prompt += (
            " Odpowiadaj planem krok po kroku: analiza, plan, ryzyka, wykonanie."
        )
    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    messages.append({"role": "user", "content": request.content})
    return messages


def _trace_onnx_task_start(task_id: UUID, request: TaskRequest, runtime) -> None:
    tracer = system_deps.get_request_tracer()
    if tracer is None:
        return
    tracer.create_trace(task_id, request.content, session_id=request.session_id)
    tracer.set_llm_metadata(
        task_id,
        provider=runtime.provider,
        model=runtime.model_name,
        endpoint=runtime.endpoint,
        metadata={
            "config_hash": runtime.config_hash,
            "runtime_id": runtime.runtime_id,
        },
    )
    tracer.update_status(task_id, TraceStatus.PROCESSING)
    tracer.add_step(
        task_id,
        "OnnxTask",
        "start_processing",
        status="ok",
        details=f"forced_intent={request.forced_intent or '-'}",
    )


def _trace_onnx_task_success(task_id: UUID, result: str) -> None:
    tracer = system_deps.get_request_tracer()
    if tracer is None:
        return
    tracer.add_step(
        task_id,
        "OnnxTask",
        "complete",
        status="ok",
        details=f"result_chars={len(result)}",
    )
    tracer.update_status(task_id, TraceStatus.COMPLETED)


def _trace_onnx_task_failure(task_id: UUID, exc: Exception) -> None:
    tracer = system_deps.get_request_tracer()
    if tracer is None:
        return
    tracer.add_step(
        task_id,
        "OnnxTask",
        "error",
        status="error",
        details=str(exc),
    )
    tracer.set_error_metadata(
        task_id,
        {
            "error_code": "onnx_task_error",
            "error_class": exc.__class__.__name__,
            "error_message": str(exc),
            "error_details": {"provider": "onnx"},
            "stage": "onnx_task_execution",
            "retryable": False,
        },
    )
    tracer.update_status(task_id, TraceStatus.FAILED)


async def _run_onnx_task(
    *,
    orchestrator: Orchestrator,
    task_id: UUID,
    request: TaskRequest,
    runtime,
) -> None:
    state_manager = orchestrator.state_manager
    try:
        await state_manager.update_status(task_id, TaskStatus.PROCESSING)
        state_manager.add_log(task_id, "ONNX: rozpoczęto przetwarzanie zadania.")
        messages = _build_onnx_task_messages(request)
        max_tokens = None
        temperature = None
        if isinstance(request.generation_params, dict):
            mt = request.generation_params.get("max_tokens")
            temp = request.generation_params.get("temperature")
            if isinstance(mt, (int, float)):
                max_tokens = int(mt)
            if isinstance(temp, (int, float)):
                temperature = float(temp)

        # In tests keep thread path (monkeypatch-friendly). In runtime use process
        # executor to avoid potential GIL/event-loop starvation on heavy ONNX calls.
        if os.getenv("PYTEST_CURRENT_TEST"):
            result = (
                await asyncio.to_thread(
                    _generate_onnx_response_sync,
                    messages,
                    max_tokens,
                    temperature,
                )
            ).strip()
        else:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                _get_onnx_executor(),
                _generate_onnx_response_sync,
                messages,
                max_tokens,
                temperature,
            )
        if not result:
            result = "Brak odpowiedzi z runtime ONNX."

        state_manager.update_context(
            task_id,
            {
                "llm_runtime": runtime.to_payload() | {"status": "ready"},
                "session": {"session_id": request.session_id},
                "generation_params": request.generation_params or {},
            },
        )
        state_manager.add_log(task_id, "ONNX: zakończono generację.")
        await state_manager.update_status(task_id, TaskStatus.COMPLETED, result=result)
        _trace_onnx_task_success(task_id, result)
    except Exception as exc:
        logger.exception("Błąd ONNX task execution: %s", exc)
        state_manager.add_log(task_id, f"ONNX: błąd: {exc}")
        await state_manager.update_status(
            task_id, TaskStatus.FAILED, result=f"Błąd: {exc}"
        )
        _trace_onnx_task_failure(task_id, exc)


async def _submit_onnx_task(
    request: TaskRequest, orchestrator: Orchestrator, runtime
) -> TaskResponse:
    state_manager = orchestrator.state_manager
    task = state_manager.create_task(request.content)
    state_manager.update_context(
        task.id,
        {
            "session": {"session_id": request.session_id},
            "llm_runtime": runtime.to_payload() | {"status": "ready"},
        },
    )
    _trace_onnx_task_start(task.id, request, runtime)
    asyncio.create_task(
        _run_onnx_task(
            orchestrator=orchestrator,
            task_id=task.id,
            request=request,
            runtime=runtime,
        )
    )
    return TaskResponse(
        task_id=task.id,
        status=TaskStatus.PENDING.value,
        llm_provider=runtime.provider,
        llm_model=runtime.model_name,
        llm_endpoint=runtime.endpoint,
    )


async def _task_stream_generator(
    task_id: UUID, state_manager: StateManager
) -> AsyncGenerator[str, None]:
    poll_interval_seconds = 0.25
    fast_poll_interval_seconds = 0.05
    heartbeat_every_ticks = 10
    previous_status: Optional[TaskStatus] = None
    previous_log_index = 0
    previous_result: Optional[str] = None
    ticks_since_emit = 0

    while True:
        task: Optional[VenomTask] = state_manager.get_task(task_id)
        if task is None:
            payload = _build_missing_task_payload(task_id)
            yield f"event:task_missing\ndata:{json.dumps(payload)}\n\n"
            break

        logs_delta = task.logs[previous_log_index:]
        status_changed = task.status != previous_status
        result_changed = task.result != previous_result
        should_emit = _should_emit_stream_event(
            status_changed=status_changed,
            logs_delta=logs_delta,
            result_changed=result_changed,
            ticks_since_emit=ticks_since_emit,
            heartbeat_every_ticks=heartbeat_every_ticks,
        )

        if should_emit:
            payload = _build_stream_payload(task, logs_delta)
            event_name = _resolve_stream_event_name(
                status_changed=status_changed,
                logs_delta=logs_delta,
                result_changed=result_changed,
            )
            yield "event:{event}\ndata:{data}\n\n".format(
                event=event_name,
                data=json.dumps(payload, default=str),
            )
            previous_status = task.status
            previous_log_index = len(task.logs)
            previous_result = task.result
            ticks_since_emit = 0
        else:
            ticks_since_emit += 1

        if _is_terminal_status(task.status):
            complete_payload = _build_task_finished_payload(task)
            yield "event:task_finished\ndata:{data}\n\n".format(
                data=json.dumps(complete_payload, default=str),
            )
            break

        try:
            interval = _resolve_poll_interval(
                previous_result=previous_result,
                status=task.status,
                fast_poll_interval_seconds=fast_poll_interval_seconds,
                poll_interval_seconds=poll_interval_seconds,
            )
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            logger.debug("Zamknięto stream SSE dla zadania %s", task_id)
            raise


@router.post(
    "/tasks",
    response_model=TaskResponse,
    status_code=201,
    responses=TASK_CREATE_RESPONSES,
)
async def create_task(
    request: TaskRequest,
    orchestrator: Annotated[Orchestrator, Depends(get_orchestrator)],
):
    """
    Tworzy nowe zadanie i uruchamia je w tle.

    Args:
        request: Żądanie z treścią zadania
        orchestrator: Orchestrator injected via Depends

    Returns:
        Odpowiedź z ID zadania i statusem

    Raises:
        HTTPException: 400 przy błędnym body, 500 przy błędzie wewnętrznym
    """
    try:
        # Inkrementuj licznik zadań
        collector = metrics_module.metrics_collector
        if collector:
            collector.increment_task_created()

        runtime = get_active_llm_runtime()
        if runtime.provider == "onnx":
            return await _submit_onnx_task(request, orchestrator, runtime)

        response = await orchestrator.submit_task(request)
        return response
    except Exception as e:
        logger.exception("Błąd podczas tworzenia zadania")
        raise HTTPException(
            status_code=500, detail="Błąd wewnętrzny podczas tworzenia zadania"
        ) from e


@router.get("/tasks/{task_id}", response_model=VenomTask, responses=TASK_GET_RESPONSES)
def get_task(
    task_id: UUID,
    state_manager: Annotated[StateManager, Depends(get_state_manager)],
):
    """
    Pobiera szczegóły zadania po ID.

    Args:
        task_id: UUID zadania
        state_manager: StateManager injected via Depends

    Returns:
        Szczegóły zadania

    Raises:
        HTTPException: 404 jeśli zadanie nie istnieje
    """
    task = state_manager.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Zadanie {task_id} nie istnieje")
    return task


@router.get("/tasks/{task_id}/stream", responses=TASK_STREAM_RESPONSES)
def stream_task(
    task_id: UUID,
    state_manager: Annotated[StateManager, Depends(get_state_manager)],
):
    """
    Strumieniuje zmiany zadania jako Server-Sent Events (SSE).

    Args:
        task_id: UUID zadania
        state_manager: StateManager injected via Depends

    Returns:
        StreamingResponse z wydarzeniami `task_update`/`heartbeat`
    """

    _assert_task_available_for_stream(task_id, state_manager)
    return StreamingResponse(
        _task_stream_generator(task_id, state_manager), media_type="text/event-stream"
    )


@router.get("/tasks", response_model=list[VenomTask], responses=TASKS_LIST_RESPONSES)
def get_all_tasks(state_manager: Annotated[StateManager, Depends(get_state_manager)]):
    """
    Pobiera listę wszystkich zadań.

    Args:
        state_manager: StateManager injected via Depends

    Returns:
        Lista wszystkich zadań w systemie
    """
    return state_manager.get_all_tasks()


@router.get(
    "/history/requests",
    response_model=list[HistoryRequestSummary],
    responses=HISTORY_LIST_RESPONSES,
)
def get_request_history(
    request_tracer: Annotated[RequestTracer, Depends(get_request_tracer)],
    limit: Annotated[
        int, Query(ge=1, le=1000, description="Maksymalna liczba wyników")
    ] = 50,
    offset: Annotated[int, Query(ge=0, description="Offset dla paginacji")] = 0,
    status: Annotated[
        Optional[str],
        Query(
            description="Filtr po statusie (PENDING, PROCESSING, COMPLETED, FAILED, LOST)"
        ),
    ] = None,
):
    """
    Pobiera listę requestów z historii (paginowana).

    Args:
        limit: Maksymalna liczba wyników (1-1000, domyślnie 50)
        offset: Offset dla paginacji (>=0, domyślnie 0)
        status: Opcjonalny filtr po statusie (PENDING, PROCESSING, COMPLETED, FAILED, LOST)

    Returns:
        Lista requestów z podstawowymi informacjami

    Raises:
        HTTPException: 400 jeśli podano nieprawidłowy status
        HTTPException: 503 jeśli RequestTracer nie jest dostępny
    """
    _validate_trace_status(status)

    traces = request_tracer.get_all_traces(
        limit=limit, offset=offset, status_filter=status
    )
    return [_build_history_summary(trace) for trace in traces]


@router.get(
    "/history/requests/{request_id}",
    response_model=HistoryRequestDetail,
    responses=HISTORY_DETAIL_RESPONSES,
)
def get_request_detail(
    request_id: UUID,
    request_tracer: Annotated[RequestTracer, Depends(get_request_tracer)],
    state_manager: Annotated[StateManager, Depends(get_state_manager)],
):
    """
    Pobiera szczegóły requestu z pełną listą kroków.

    Args:
        request_id: UUID requestu
        request_tracer: RequestTracer injected via Depends

    Returns:
        Szczegółowe informacje o requestie wraz z timeline kroków

    Raises:
        HTTPException: 404 jeśli request nie istnieje
    """
    trace = request_tracer.get_trace(request_id)
    if trace is None:
        raise HTTPException(
            status_code=404, detail=f"Request {request_id} nie istnieje w historii"
        )

    duration = (
        (trace.finished_at - trace.created_at).total_seconds()
        if trace.finished_at
        else None
    )
    task = state_manager.get_task(request_id)
    context = _extract_task_context(task)
    context_preview = _extract_context_preview(trace.steps)

    return HistoryRequestDetail(
        request_id=trace.request_id,
        prompt=trace.prompt,
        status=trace.status,
        session_id=trace.session_id,
        created_at=trace.created_at.isoformat(),
        finished_at=trace.finished_at.isoformat() if trace.finished_at else None,
        duration_seconds=duration,
        steps=_serialize_trace_steps(trace),
        llm_provider=trace.llm_provider,
        llm_model=trace.llm_model,
        llm_endpoint=trace.llm_endpoint,
        llm_config_hash=trace.llm_config_hash,
        llm_runtime_id=trace.llm_runtime_id,
        forced_tool=trace.forced_tool,
        forced_provider=trace.forced_provider,
        forced_intent=trace.forced_intent,
        first_token=context.get("first_token"),
        streaming=context.get("streaming"),
        context_preview=context_preview,
        generation_params=context.get("generation_params"),
        llm_runtime=context.get("llm_runtime"),
        routing_decision=context.get("routing_decision"),
        context_used=_serialize_context_used(task),
        error_code=trace.error_code,
        error_class=trace.error_class,
        error_message=trace.error_message,
        error_details=trace.error_details,
        error_stage=trace.error_stage,
        error_retryable=trace.error_retryable,
        result=task.result if task else None,
        feedback=trace.feedback,
    )
