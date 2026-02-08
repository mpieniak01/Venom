"""Moduł: routes/agents - Endpointy API dla agentów (gardener, shadow, watcher, documenter)."""

from fastapi import APIRouter, HTTPException

from venom_core.core.models import TaskRequest
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["agents"])

# Dependencies - będą ustawione w main.py
_gardener_agent = None
_shadow_agent = None
_file_watcher = None
_documenter_agent = None
_orchestrator = None


def set_dependencies(
    gardener_agent, shadow_agent, file_watcher, documenter_agent, orchestrator
):
    """Ustaw zależności dla routera."""
    global _gardener_agent
    global _shadow_agent
    global _file_watcher
    global _documenter_agent
    global _orchestrator

    _gardener_agent = gardener_agent
    _shadow_agent = shadow_agent
    _file_watcher = file_watcher
    _documenter_agent = documenter_agent
    _orchestrator = orchestrator


@router.get(
    "/gardener/status",
    responses={
        503: {"description": "GardenerAgent nie jest dostępny"},
        500: {"description": "Błąd wewnętrzny podczas pobierania statusu"},
    },
)
def get_gardener_status():
    """
    Zwraca status agenta Ogrodnika.

    Returns:
        Status GardenerAgent

    Raises:
        HTTPException: 503 jeśli GardenerAgent nie jest dostępny
    """
    if _gardener_agent is None:
        raise HTTPException(status_code=503, detail="GardenerAgent nie jest dostępny")

    try:
        status = _gardener_agent.get_status()
        return {"status": "success", "gardener": status}
    except Exception as e:
        logger.exception("Błąd podczas pobierania statusu Ogrodnika")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@router.get(
    "/watcher/status",
    responses={
        503: {"description": "FileWatcher nie jest dostępny"},
        500: {"description": "Błąd wewnętrzny podczas pobierania statusu"},
    },
)
def get_watcher_status():
    """
    Zwraca status obserwatora plików.

    Returns:
        Status watchera

    Raises:
        HTTPException: 503 jeśli watcher nie jest dostępny
    """
    if _file_watcher is None:
        raise HTTPException(status_code=503, detail="FileWatcher nie jest dostępny")

    try:
        status = _file_watcher.get_status()
        return {"status": "success", "watcher": status}
    except Exception as e:
        logger.exception("Błąd podczas pobierania statusu watchera")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@router.get(
    "/documenter/status",
    responses={
        503: {"description": "DocumenterAgent nie jest dostępny"},
        500: {"description": "Błąd wewnętrzny podczas pobierania statusu"},
    },
)
def get_documenter_status():
    """
    Zwraca status agenta dokumentalisty.

    Returns:
        Status DocumenterAgent

    Raises:
        HTTPException: 503 jeśli documenter nie jest dostępny
    """
    if _documenter_agent is None:
        raise HTTPException(status_code=503, detail="DocumenterAgent nie jest dostępny")

    try:
        status = _documenter_agent.get_status()
        return {"status": "success", "documenter": status}
    except Exception as e:
        logger.exception("Błąd podczas pobierania statusu dokumentalisty")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@router.get(
    "/shadow/status",
    responses={
        500: {"description": "Błąd wewnętrzny podczas pobierania statusu"},
    },
)
def get_shadow_status():
    """
    Zwraca status Shadow Agent, Desktop Sensor i Notifier.

    Returns:
        Status Shadow Agent

    Raises:
        HTTPException: 503 jeśli Shadow Agent nie jest dostępny
    """
    if _shadow_agent is None:
        return {
            "status": "disabled",
            "message": "Shadow Agent (Proactive Mode) jest wyłączony",
            "shadow_agent": None,
            "desktop_sensor": None,
            "notifier": None,
        }

    try:
        status = _shadow_agent.get_status()
        return {"status": "success", "shadow_agent": status}
    except Exception as e:
        logger.exception("Błąd podczas pobierania statusu Shadow Agent")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@router.post(
    "/shadow/reject",
    responses={
        503: {"description": "Shadow Agent lub Orchestrator nie jest dostępny"},
        500: {"description": "Błąd wewnętrzny podczas odrzucania sugestii"},
    },
)
def reject_shadow_suggestion(request: TaskRequest):
    """
    Odrzuca sugestię Shadow Agent.

    Args:
        request: Treść sugestii do odrzucenia

    Returns:
        Potwierdzenie odrzucenia

    Raises:
        HTTPException: 503 jeśli Shadow Agent lub orchestrator nie jest dostępny
    """
    if _shadow_agent is None:
        raise HTTPException(status_code=503, detail="Shadow Agent nie jest dostępny")

    if _orchestrator is None:
        raise HTTPException(status_code=503, detail="Orchestrator nie jest dostępny")

    try:
        # Reject suggestion - przekaż treść sugestii
        _shadow_agent.reject_suggestion(request.content)

        return {
            "status": "success",
            "message": f"Suggestion rejected: {request.content[:100]}...",
        }
    except Exception as e:
        logger.exception("Błąd podczas odrzucania sugestii Shadow Agent")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e
