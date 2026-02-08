"""Moduł: routes/tasks - Endpointy API dla zadań i historii."""

import asyncio
import json
from datetime import datetime, timezone
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from venom_core.core import metrics as metrics_module
from venom_core.core.models import TaskRequest, TaskResponse, TaskStatus, VenomTask
from venom_core.core.tracer import TraceStatus
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["tasks"])

TASK_CREATE_RESPONSES = {
    503: {"description": "Orchestrator nie jest dostępny"},
    500: {"description": "Błąd wewnętrzny podczas tworzenia zadania"},
}
TASK_GET_RESPONSES = {
    503: {"description": "StateManager nie jest dostępny"},
    404: {"description": "Zadanie o podanym ID nie istnieje"},
}
TASK_STREAM_RESPONSES = {
    503: {"description": "StateManager nie jest dostępny"},
    404: {"description": "Zadanie o podanym ID nie istnieje"},
}
TASKS_LIST_RESPONSES = {
    503: {"description": "StateManager nie jest dostępny"},
}
HISTORY_LIST_RESPONSES = {
    400: {"description": "Nieprawidłowy filtr statusu"},
    503: {"description": "RequestTracer nie jest dostępny"},
}
HISTORY_DETAIL_RESPONSES = {
    503: {"description": "RequestTracer nie jest dostępny"},
    404: {"description": "Request o podanym ID nie istnieje"},
}


# Modele dla history endpoints
class HistoryRequestSummary(BaseModel):
    """Skrócony widok requestu dla listy historii."""

    request_id: UUID
    prompt: str
    status: str
    session_id: Optional[str] = None
    created_at: str
    finished_at: Optional[str] = None
    duration_seconds: Optional[float] = None
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    llm_endpoint: Optional[str] = None
    llm_config_hash: Optional[str] = None
    llm_runtime_id: Optional[str] = None
    forced_tool: Optional[str] = None
    forced_provider: Optional[str] = None
    forced_intent: Optional[str] = None
    error_code: Optional[str] = None
    error_class: Optional[str] = None
    error_message: Optional[str] = None
    error_details: Optional[dict] = None
    error_stage: Optional[str] = None
    error_retryable: Optional[bool] = None
    feedback: Optional[dict] = None
    result: Optional[str] = None


class HistoryRequestDetail(BaseModel):
    """Szczegółowy widok requestu z krokami."""

    request_id: UUID
    prompt: str
    status: str
    session_id: Optional[str] = None
    created_at: str
    finished_at: Optional[str] = None
    duration_seconds: Optional[float] = None
    steps: list
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    llm_endpoint: Optional[str] = None
    llm_config_hash: Optional[str] = None
    llm_runtime_id: Optional[str] = None
    forced_tool: Optional[str] = None
    forced_provider: Optional[str] = None
    forced_intent: Optional[str] = None
    first_token: Optional[dict] = None
    streaming: Optional[dict] = None
    context_preview: Optional[dict] = None
    generation_params: Optional[dict] = None
    llm_runtime: Optional[dict] = None
    context_used: Optional[dict] = None
    error_code: Optional[str] = None
    error_class: Optional[str] = None
    error_message: Optional[str] = None
    error_details: Optional[dict] = None
    error_stage: Optional[str] = None
    error_retryable: Optional[bool] = None
    result: Optional[str] = None
    feedback: Optional[dict] = None


# Dependency - będzie ustawione w main.py
_orchestrator = None
_state_manager = None
_request_tracer = None


def set_dependencies(orchestrator, state_manager, request_tracer):
    """Ustaw zależności dla routera."""
    global _orchestrator, _state_manager, _request_tracer
    _orchestrator = orchestrator
    _state_manager = state_manager
    _request_tracer = request_tracer


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


def _bootstrap_orchestrator_if_testing():
    """
    Zachowane dla kompatybilności wstecznej.

    Pierwotnie inicjalizowało orchestrator "ad-hoc" w trybie testowym na podstawie
    venom_core.main, co powodowało mutację globalnego stanu i ryzyko zależności
    cyklicznych. Obecnie nie wykonuje żadnej logiki – zależności muszą być
    wstrzyknięte jawnie przez `set_dependencies` (np. w lifespan lub w fixture'ach).

    DEPRECATED: Ta funkcja będzie usunięta w przyszłych wersjach.
    Używaj dependency injection przez set_dependencies() zamiast tego.
    """
    # Funkcja celowo pusta - inicjalizacja powinna odbywać się przez set_dependencies
    return


@router.post(
    "/tasks",
    response_model=TaskResponse,
    status_code=201,
    responses=TASK_CREATE_RESPONSES,
)
async def create_task(request: TaskRequest):
    """
    Tworzy nowe zadanie i uruchamia je w tle.

    Args:
        request: Żądanie z treścią zadania

    Returns:
        Odpowiedź z ID zadania i statusem

    Raises:
        HTTPException: 400 przy błędnym body, 500 przy błędzie wewnętrznym
    """
    _bootstrap_orchestrator_if_testing()

    if _orchestrator is None:
        raise HTTPException(status_code=503, detail="Orchestrator nie jest dostępny")

    try:
        # Inkrementuj licznik zadań
        collector = metrics_module.metrics_collector
        if collector:
            collector.increment_task_created()

        response = await _orchestrator.submit_task(request)
        return response
    except Exception as e:
        logger.exception("Błąd podczas tworzenia zadania")
        raise HTTPException(
            status_code=500, detail="Błąd wewnętrzny podczas tworzenia zadania"
        ) from e


@router.get("/tasks/{task_id}", response_model=VenomTask, responses=TASK_GET_RESPONSES)
async def get_task(task_id: UUID):
    """
    Pobiera szczegóły zadania po ID.

    Args:
        task_id: UUID zadania

    Returns:
        Szczegóły zadania

    Raises:
        HTTPException: 404 jeśli zadanie nie istnieje
    """
    if _state_manager is None:
        raise HTTPException(status_code=503, detail="StateManager nie jest dostępny")

    task = _state_manager.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Zadanie {task_id} nie istnieje")
    return task


@router.get("/tasks/{task_id}/stream", responses=TASK_STREAM_RESPONSES)
async def stream_task(task_id: UUID):
    """
    Strumieniuje zmiany zadania jako Server-Sent Events (SSE).

    Args:
        task_id: UUID zadania

    Returns:
        StreamingResponse z wydarzeniami `task_update`/`heartbeat`
    """

    if _state_manager is None:
        raise HTTPException(status_code=503, detail="StateManager nie jest dostępny")

    if _state_manager.get_task(task_id) is None:
        raise HTTPException(status_code=404, detail=f"Zadanie {task_id} nie istnieje")

    async def event_generator():
        """Asynchroniczny generator zdarzeń SSE."""

        poll_interval_seconds = 0.25
        fast_poll_interval_seconds = 0.05
        heartbeat_every_ticks = 10
        previous_status: Optional[TaskStatus] = None
        previous_log_index = 0
        previous_result: Optional[str] = None
        ticks_since_emit = 0

        while True:
            task: Optional[VenomTask] = _state_manager.get_task(task_id)
            if task is None:
                payload = {
                    "task_id": str(task_id),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "event": "gone",
                    "detail": "Task no longer available in StateManager",
                }
                yield f"event:task_missing\ndata:{json.dumps(payload)}\n\n"
                break

            logs_delta = task.logs[previous_log_index:]
            status_changed = task.status != previous_status
            result_changed = task.result != previous_result
            should_emit = (
                status_changed
                or logs_delta
                or result_changed
                or ticks_since_emit >= heartbeat_every_ticks
            )

            if should_emit:
                runtime_info = _get_llm_runtime(task)
                payload = {
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

                event_name = (
                    "task_update"
                    if (status_changed or logs_delta or result_changed)
                    else "heartbeat"
                )

                # json.dumps nie obsługuje Enum więc wymuś str()
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

            if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                # Wyślij końcowy event i zamknij stream
                runtime_info = _get_llm_runtime(task)
                complete_payload = {
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
                yield "event:task_finished\ndata:{data}\n\n".format(
                    data=json.dumps(complete_payload, default=str),
                )
                break

            try:
                interval = (
                    fast_poll_interval_seconds
                    if previous_result is None and task.status == TaskStatus.PROCESSING
                    else poll_interval_seconds
                )
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                logger.debug("Zamknięto stream SSE dla zadania %s", task_id)
                raise

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/tasks", response_model=list[VenomTask], responses=TASKS_LIST_RESPONSES)
async def get_all_tasks():
    """
    Pobiera listę wszystkich zadań.

    Returns:
        Lista wszystkich zadań w systemie
    """
    if _state_manager is None:
        raise HTTPException(status_code=503, detail="StateManager nie jest dostępny")

    return _state_manager.get_all_tasks()


@router.get(
    "/history/requests",
    response_model=list[HistoryRequestSummary],
    responses=HISTORY_LIST_RESPONSES,
)
async def get_request_history(
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
    if _request_tracer is None:
        raise HTTPException(status_code=503, detail="RequestTracer nie jest dostępny")

    # Walidacja statusu jeśli podano
    if status is not None:
        valid_statuses = [s.value for s in TraceStatus]
        if status not in valid_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"Nieprawidłowy status. Dozwolone wartości: {', '.join(valid_statuses)}",
            )

    traces = _request_tracer.get_all_traces(
        limit=limit, offset=offset, status_filter=status
    )

    result = []
    for trace in traces:
        duration = None
        if trace.finished_at:
            duration = (trace.finished_at - trace.created_at).total_seconds()

        result.append(
            HistoryRequestSummary(
                request_id=trace.request_id,
                prompt=trace.prompt,
                status=trace.status,
                session_id=trace.session_id,
                created_at=trace.created_at.isoformat(),
                finished_at=(
                    trace.finished_at.isoformat() if trace.finished_at else None
                ),
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
        )

    return result


@router.get(
    "/history/requests/{request_id}",
    response_model=HistoryRequestDetail,
    responses=HISTORY_DETAIL_RESPONSES,
)
async def get_request_detail(request_id: UUID):
    """
    Pobiera szczegóły requestu z pełną listą kroków.

    Args:
        request_id: UUID requestu

    Returns:
        Szczegółowe informacje o requestie wraz z timeline kroków

    Raises:
        HTTPException: 404 jeśli request nie istnieje
    """
    if _request_tracer is None:
        raise HTTPException(status_code=503, detail="RequestTracer nie jest dostępny")

    trace = _request_tracer.get_trace(request_id)
    if trace is None:
        raise HTTPException(
            status_code=404, detail=f"Request {request_id} nie istnieje w historii"
        )

    duration = None
    if trace.finished_at:
        duration = (trace.finished_at - trace.created_at).total_seconds()

    # Konwertuj steps do słowników dla serializacji
    steps_list = []
    for step in trace.steps:
        steps_list.append(
            {
                "component": step.component,
                "action": step.action,
                "timestamp": step.timestamp.isoformat(),
                "status": step.status,
                "details": step.details,
            }
        )

    first_token = None
    streaming = None
    context_used = None
    context_preview = None
    generation_params = None
    llm_runtime = None
    if _state_manager is not None:
        task = _state_manager.get_task(request_id)
        context = getattr(task, "context_history", {}) or {} if task else {}
        first_token = context.get("first_token")
        streaming = context.get("streaming")
        generation_params = context.get("generation_params")
        llm_runtime = context.get("llm_runtime")
        # Extract context_used if available
        if task and hasattr(task, "context_used") and task.context_used:
            # Convert model to dict
            if hasattr(task.context_used, "model_dump"):
                context_used = task.context_used.model_dump()
            elif hasattr(task.context_used, "dict"):
                context_used = task.context_used.dict()
            else:
                context_used = task.context_used

    context_preview = _extract_context_preview(trace.steps)

    return HistoryRequestDetail(
        request_id=trace.request_id,
        prompt=trace.prompt,
        status=trace.status,
        session_id=trace.session_id,
        created_at=trace.created_at.isoformat(),
        finished_at=trace.finished_at.isoformat() if trace.finished_at else None,
        duration_seconds=duration,
        steps=steps_list,
        llm_provider=trace.llm_provider,
        llm_model=trace.llm_model,
        llm_endpoint=trace.llm_endpoint,
        llm_config_hash=trace.llm_config_hash,
        llm_runtime_id=trace.llm_runtime_id,
        forced_tool=trace.forced_tool,
        forced_provider=trace.forced_provider,
        forced_intent=trace.forced_intent,
        first_token=first_token,
        streaming=streaming,
        context_preview=context_preview,
        generation_params=generation_params,
        llm_runtime=llm_runtime,
        context_used=context_used,
        error_code=trace.error_code,
        error_class=trace.error_class,
        error_message=trace.error_message,
        error_details=trace.error_details,
        error_stage=trace.error_stage,
        error_retryable=trace.error_retryable,
        result=task.result if task else None,
        feedback=trace.feedback,
    )
