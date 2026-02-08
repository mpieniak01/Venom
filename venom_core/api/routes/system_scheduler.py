"""Moduł: routes/system_scheduler - Endpointy schedulera."""

from typing import Any

from fastapi import APIRouter, HTTPException

from venom_core.api.routes import system_deps
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["system"])

SCHEDULER_RESPONSES: dict[int | str, dict[str, Any]] = {
    503: {"description": "BackgroundScheduler nie jest dostępny"},
    500: {"description": "Błąd wewnętrzny podczas obsługi schedulera"},
}


@router.get("/scheduler/status", responses=SCHEDULER_RESPONSES)
async def get_scheduler_status():
    """
    Zwraca status schedulera zadań w tle.
    """
    background_scheduler = system_deps.get_background_scheduler()
    if background_scheduler is None:
        raise HTTPException(
            status_code=503, detail="BackgroundScheduler nie jest dostępny"
        )

    try:
        status = background_scheduler.get_status()
        return {"status": "success", "scheduler": status}
    except Exception as e:
        logger.exception("Błąd podczas pobierania statusu schedulera")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@router.get("/scheduler/jobs", responses=SCHEDULER_RESPONSES)
async def get_scheduler_jobs():
    """
    Zwraca listę zadań w tle.
    """
    background_scheduler = system_deps.get_background_scheduler()
    if background_scheduler is None:
        raise HTTPException(
            status_code=503, detail="BackgroundScheduler nie jest dostępny"
        )

    try:
        jobs = background_scheduler.get_jobs()
        return {"status": "success", "jobs": jobs, "count": len(jobs)}
    except Exception as e:
        logger.exception("Błąd podczas pobierania listy zadań")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@router.post("/scheduler/pause", responses=SCHEDULER_RESPONSES)
async def pause_scheduler():
    """
    Wstrzymuje wszystkie zadania w tle.
    """
    background_scheduler = system_deps.get_background_scheduler()
    if background_scheduler is None:
        raise HTTPException(
            status_code=503, detail="BackgroundScheduler nie jest dostępny"
        )

    try:
        await background_scheduler.pause_all_jobs()
        return {"status": "success", "message": "All background jobs paused"}
    except Exception as e:
        logger.exception("Błąd podczas wstrzymywania zadań")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@router.post("/scheduler/resume", responses=SCHEDULER_RESPONSES)
async def resume_scheduler():
    """
    Wznawia wszystkie zadania w tle.
    """
    background_scheduler = system_deps.get_background_scheduler()
    if background_scheduler is None:
        raise HTTPException(
            status_code=503, detail="BackgroundScheduler nie jest dostępny"
        )

    try:
        await background_scheduler.resume_all_jobs()
        return {"status": "success", "message": "All background jobs resumed"}
    except Exception as e:
        logger.exception("Błąd podczas wznawiania zadań")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e
