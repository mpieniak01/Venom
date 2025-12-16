"""Moduł: routes/tasks - Endpointy API dla zadań i historii."""

import asyncio
import json
from datetime import datetime, timezone
from typing import Optional
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


# Modele dla history endpoints
class HistoryRequestSummary(BaseModel):
    """Skrócony widok requestu dla listy historii."""

    request_id: UUID
    prompt: str
    status: str
    created_at: str
    finished_at: str = None
    duration_seconds: float = None
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    llm_endpoint: Optional[str] = None


class HistoryRequestDetail(BaseModel):
    """Szczegółowy widok requestu z krokami."""

    request_id: UUID
    prompt: str
    status: str
    created_at: str
    finished_at: str = None
    duration_seconds: float = None
    steps: list
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    llm_endpoint: Optional[str] = None


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


@router.post("/tasks", response_model=TaskResponse, status_code=201)
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


@router.get("/tasks/{task_id}", response_model=VenomTask)
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


@router.get("/tasks/{task_id}/stream")
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

        poll_interval_seconds = 1.0
        heartbeat_every_ticks = 10
        previous_status: Optional[TaskStatus] = None
        previous_log_index = 0
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
            should_emit = (
                status_changed
                or logs_delta
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
                    "task_update" if (status_changed or logs_delta) else "heartbeat"
                )

                # json.dumps nie obsługuje Enum więc wymuś str()
                yield "event:{event}\ndata:{data}\n\n".format(
                    event=event_name,
                    data=json.dumps(payload, default=str),
                )

                previous_status = task.status
                previous_log_index = len(task.logs)
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
                await asyncio.sleep(poll_interval_seconds)
            except asyncio.CancelledError:
                logger.debug("Zamknięto stream SSE dla zadania %s", task_id)
                break

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/tasks", response_model=list[VenomTask])
async def get_all_tasks():
    """
    Pobiera listę wszystkich zadań.

    Returns:
        Lista wszystkich zadań w systemie
    """
    if _state_manager is None:
        raise HTTPException(status_code=503, detail="StateManager nie jest dostępny")

    return _state_manager.get_all_tasks()


@router.get("/history/requests", response_model=list[HistoryRequestSummary])
async def get_request_history(
    limit: int = Query(
        default=50, ge=1, le=1000, description="Maksymalna liczba wyników"
    ),
    offset: int = Query(default=0, ge=0, description="Offset dla paginacji"),
    status: Optional[str] = Query(
        default=None,
        description="Filtr po statusie (PENDING, PROCESSING, COMPLETED, FAILED, LOST)",
    ),
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
                created_at=trace.created_at.isoformat(),
                finished_at=(
                    trace.finished_at.isoformat() if trace.finished_at else None
                ),
                duration_seconds=duration,
                llm_provider=trace.llm_provider,
                llm_model=trace.llm_model,
                llm_endpoint=trace.llm_endpoint,
            )
        )

    return result


@router.get("/history/requests/{request_id}", response_model=HistoryRequestDetail)
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

    return HistoryRequestDetail(
        request_id=trace.request_id,
        prompt=trace.prompt,
        status=trace.status,
        created_at=trace.created_at.isoformat(),
        finished_at=trace.finished_at.isoformat() if trace.finished_at else None,
        duration_seconds=duration,
        steps=steps_list,
        llm_provider=trace.llm_provider,
        llm_model=trace.llm_model,
        llm_endpoint=trace.llm_endpoint,
    )
