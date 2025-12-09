"""Moduł: routes/tasks - Endpointy API dla zadań i historii."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from venom_core.core.metrics import metrics_collector
from venom_core.core.models import TaskRequest, TaskResponse, VenomTask
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


class HistoryRequestDetail(BaseModel):
    """Szczegółowy widok requestu z krokami."""

    request_id: UUID
    prompt: str
    status: str
    created_at: str
    finished_at: str = None
    duration_seconds: float = None
    steps: list


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
        if metrics_collector:
            metrics_collector.increment_task_created()

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
    )
