"""Moduł: routes/queue - Endpointy API dla zarządzania kolejką zadań."""

from uuid import UUID

from fastapi import APIRouter, HTTPException

from venom_core.utils.logger import get_logger
from venom_core.utils.ttl_cache import TTLCache

logger = get_logger(__name__)
_queue_cache = TTLCache[dict](ttl_seconds=1.0)

router = APIRouter(prefix="/api/v1/queue", tags=["queue"])

# Dependency - będzie ustawione w main.py
_orchestrator = None


def set_dependencies(orchestrator):
    """Ustaw zależności dla routera."""
    global _orchestrator
    _orchestrator = orchestrator


@router.get("/status")
async def get_queue_status():
    """
    Pobiera status kolejki zadań.

    Returns:
        Dict ze statusem: paused, pending, active, limit

    Raises:
        HTTPException: 503 jeśli Orchestrator nie jest dostępny
    """
    if _orchestrator is None:
        raise HTTPException(status_code=503, detail="Orchestrator nie jest dostępny")

    try:
        cached = _queue_cache.get()
        if cached is not None:
            return cached
        status = _orchestrator.get_queue_status()
        _queue_cache.set(status)
        return status
    except Exception as e:
        logger.exception("Błąd podczas pobierania statusu kolejki")
        raise HTTPException(
            status_code=500, detail="Błąd podczas pobierania statusu kolejki"
        ) from e


@router.post("/pause")
async def pause_queue():
    """
    Wstrzymuje kolejkę zadań - nowe zadania nie będą przetwarzane.

    Returns:
        Dict z wynikiem operacji

    Raises:
        HTTPException: 503 jeśli Orchestrator nie jest dostępny
    """
    if _orchestrator is None:
        raise HTTPException(status_code=503, detail="Orchestrator nie jest dostępny")

    try:
        result = await _orchestrator.pause_queue()
        _queue_cache.clear()
        logger.info("Kolejka zadań wstrzymana przez API")
        return result
    except Exception as e:
        logger.exception("Błąd podczas wstrzymywania kolejki")
        raise HTTPException(
            status_code=500, detail="Błąd podczas wstrzymywania kolejki"
        ) from e


@router.post("/resume")
async def resume_queue():
    """
    Wznawia kolejkę zadań - przetwarzanie zostanie kontynuowane.

    Returns:
        Dict z wynikiem operacji

    Raises:
        HTTPException: 503 jeśli Orchestrator nie jest dostępny
    """
    if _orchestrator is None:
        raise HTTPException(status_code=503, detail="Orchestrator nie jest dostępny")

    try:
        result = await _orchestrator.resume_queue()
        _queue_cache.clear()
        logger.info("Kolejka zadań wznowiona przez API")
        return result
    except Exception as e:
        logger.exception("Błąd podczas wznawiania kolejki")
        raise HTTPException(
            status_code=500, detail="Błąd podczas wznawiania kolejki"
        ) from e


@router.post("/purge")
async def purge_queue():
    """
    Czyści kolejkę - usuwa wszystkie oczekujące zadania.

    Returns:
        Dict z liczbą usuniętych zadań

    Raises:
        HTTPException: 503 jeśli Orchestrator nie jest dostępny
    """
    if _orchestrator is None:
        raise HTTPException(status_code=503, detail="Orchestrator nie jest dostępny")

    try:
        result = await _orchestrator.purge_queue()
        _queue_cache.clear()
        logger.warning(
            f"Kolejka zadań wyczyszczona przez API - usunięto {result.get('removed', 0)} zadań"
        )
        return result
    except Exception as e:
        logger.exception("Błąd podczas czyszczenia kolejki")
        raise HTTPException(
            status_code=500, detail="Błąd podczas czyszczenia kolejki"
        ) from e


@router.post("/emergency-stop")
async def emergency_stop():
    """
    Awaryjne zatrzymanie systemu - anuluje wszystkie zadania i czyści kolejkę.

    Returns:
        Dict z wynikiem operacji

    Raises:
        HTTPException: 503 jeśli Orchestrator nie jest dostępny
    """
    if _orchestrator is None:
        raise HTTPException(status_code=503, detail="Orchestrator nie jest dostępny")

    try:
        result = await _orchestrator.emergency_stop()
        logger.error("🚨 Emergency Stop wywołany przez API")
        return result
    except Exception as e:
        logger.exception("Błąd podczas Emergency Stop")
        raise HTTPException(
            status_code=500, detail="Błąd podczas Emergency Stop"
        ) from e


@router.post("/task/{task_id}/abort")
async def abort_task(task_id: UUID):
    """
    Przerywa wykonywanie konkretnego zadania.

    Args:
        task_id: UUID zadania do przerwania

    Returns:
        Dict z wynikiem operacji

    Raises:
        HTTPException: 404 jeśli zadanie nie istnieje lub nie jest aktywne
        HTTPException: 503 jeśli Orchestrator nie jest dostępny
    """
    if _orchestrator is None:
        raise HTTPException(status_code=503, detail="Orchestrator nie jest dostępny")

    try:
        result = await _orchestrator.abort_task(task_id)

        if not result.get("success"):
            raise HTTPException(
                status_code=404,
                detail=result.get("message", "Nie można przerwać zadania"),
            )

        logger.warning(f"Zadanie {task_id} przerwane przez API")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Błąd podczas przerywania zadania {task_id}")
        raise HTTPException(
            status_code=500, detail="Błąd podczas przerywania zadania"
        ) from e
