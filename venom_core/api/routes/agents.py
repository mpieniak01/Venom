"""Moduł: routes/agents - Endpointy API dla agentów (gardener, shadow, watcher, documenter, ghost)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from venom_core.api.routes.permission_denied_contract import (
    raise_permission_denied_http,
    resolve_actor_from_request,
)
from venom_core.config import SETTINGS
from venom_core.core.environment_policy import ensure_data_mutation_allowed
from venom_core.core.models import TaskRequest
from venom_core.services.audit_stream import get_audit_stream
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["agents"])

# Dependencies - będą ustawione w main.py
_gardener_agent = None
_shadow_agent = None
_file_watcher = None
_documenter_agent = None
_orchestrator = None
_ghost_agent = None
_ghost_run_task: asyncio.Task[str] | None = None
_ghost_run_state: dict[str, Any] | None = None


class GhostRunRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    runtime_profile: str | None = Field(default=None, max_length=64)


def _ghost_api_enabled() -> bool:
    return bool(getattr(SETTINGS, "ENABLE_GHOST_API", False)) and bool(
        getattr(SETTINGS, "ENABLE_GHOST_AGENT", False)
    )


def _publish_ghost_audit(
    *,
    action: str,
    status: str,
    actor: str,
    context: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    get_audit_stream().publish(
        source="api.ghost",
        action=action,
        actor=actor,
        status=status,
        context=context,
        details=details or {},
    )


async def _run_ghost_job(*, task_id: str, payload: GhostRunRequest, actor: str) -> str:
    global _ghost_run_task
    global _ghost_run_state

    if _ghost_run_state is None:
        _ghost_run_state = {
            "task_id": task_id,
            "status": "running",
            "started_at": datetime.now(timezone.utc).isoformat(),
        }

    try:
        result = await _ghost_agent.process(payload.content)
        _ghost_run_state.update(
            {
                "status": "completed",
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "result": result,
            }
        )
        _publish_ghost_audit(
            action="ghost.run.completed",
            status="success",
            actor=actor,
            context=task_id,
            details={
                "runtime_profile": _ghost_run_state.get("runtime_profile"),
                "result_excerpt": result[:500],
            },
        )
        return result
    except asyncio.CancelledError:
        _ghost_run_state.update(
            {
                "status": "cancelled",
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "result": "Cancelled by API emergency stop",
            }
        )
        _publish_ghost_audit(
            action="ghost.run.cancelled",
            status="cancelled",
            actor=actor,
            context=task_id,
            details={"runtime_profile": _ghost_run_state.get("runtime_profile")},
        )
        raise
    except Exception as e:
        logger.exception("Błąd podczas wykonywania zadania Ghost")
        _ghost_run_state.update(
            {
                "status": "failed",
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "result": str(e),
            }
        )
        _publish_ghost_audit(
            action="ghost.run.failed",
            status="failure",
            actor=actor,
            context=task_id,
            details={
                "runtime_profile": _ghost_run_state.get("runtime_profile"),
                "error": str(e),
            },
        )
        raise
    finally:
        _ghost_run_task = None


def set_dependencies(
    gardener_agent,
    shadow_agent,
    file_watcher,
    documenter_agent,
    orchestrator,
    ghost_agent=None,
):
    """Ustaw zależności dla routera."""
    global _gardener_agent
    global _shadow_agent
    global _file_watcher
    global _documenter_agent
    global _orchestrator
    global _ghost_agent

    _gardener_agent = gardener_agent
    _shadow_agent = shadow_agent
    _file_watcher = file_watcher
    _documenter_agent = documenter_agent
    _orchestrator = orchestrator
    _ghost_agent = ghost_agent


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


@router.get(
    "/ghost/status",
    responses={503: {"description": "Ghost API lub Ghost Agent nie jest dostępny"}},
)
def get_ghost_status():
    """Zwraca status wykonania zadań Ghost Agent."""
    if not _ghost_api_enabled():
        return {
            "status": "disabled",
            "message": "Ghost API jest wyłączone (ENABLE_GHOST_API/ENABLE_GHOST_AGENT=false)",
            "ghost": None,
            "run": _ghost_run_state,
        }

    if _ghost_agent is None:
        raise HTTPException(status_code=503, detail="Ghost Agent nie jest dostępny")

    try:
        return {
            "status": "success",
            "ghost": _ghost_agent.get_status(),
            "run": _ghost_run_state,
            "task_active": bool(_ghost_run_task and not _ghost_run_task.done()),
        }
    except Exception as e:
        logger.exception("Błąd podczas pobierania statusu Ghost Agent")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@router.post(
    "/ghost/start",
    responses={
        403: {"description": "Mutacje są zablokowane przez policy/autonomy"},
        409: {"description": "Ghost Agent wykonuje już zadanie"},
        503: {"description": "Ghost API lub Ghost Agent nie jest dostępny"},
    },
)
async def start_ghost_task(request: GhostRunRequest, req: Request):
    """Uruchamia zadanie Ghost Agent w tle."""
    global _ghost_run_task
    global _ghost_run_state

    if not _ghost_api_enabled():
        raise HTTPException(
            status_code=503,
            detail="Ghost API jest wyłączone (ENABLE_GHOST_API/ENABLE_GHOST_AGENT=false)",
        )
    if _ghost_agent is None:
        raise HTTPException(status_code=503, detail="Ghost Agent nie jest dostępny")
    if _ghost_run_task and not _ghost_run_task.done():
        raise HTTPException(status_code=409, detail="Ghost Agent już wykonuje zadanie")

    actor = resolve_actor_from_request(req)
    try:
        ensure_data_mutation_allowed("agents.ghost.start")
    except PermissionError as e:
        raise_permission_denied_http(
            e,
            operation="agents.ghost.start",
            actor=actor,
        )

    runtime_profile = request.runtime_profile or getattr(
        SETTINGS, "GHOST_RUNTIME_PROFILE", "desktop_safe"
    )
    profile_payload = _ghost_agent.apply_runtime_profile(runtime_profile)

    task_id = str(uuid4())
    started_at = datetime.now(timezone.utc).isoformat()
    _ghost_run_state = {
        "task_id": task_id,
        "status": "running",
        "content": request.content,
        "runtime_profile": profile_payload["profile"],
        "started_at": started_at,
    }

    _ghost_run_task = asyncio.create_task(
        _run_ghost_job(task_id=task_id, payload=request, actor=actor)
    )

    _publish_ghost_audit(
        action="ghost.run.start",
        status="accepted",
        actor=actor,
        context=task_id,
        details={
            "runtime_profile": profile_payload["profile"],
            "content_excerpt": request.content[:300],
        },
    )

    return {
        "status": "accepted",
        "task_id": task_id,
        "runtime_profile": profile_payload["profile"],
        "started_at": started_at,
    }


@router.post(
    "/ghost/cancel",
    responses={
        403: {"description": "Mutacje są zablokowane przez policy/autonomy"},
        503: {"description": "Ghost API lub Ghost Agent nie jest dostępny"},
    },
)
async def cancel_ghost_task(req: Request):
    """Anuluje aktywne zadanie Ghost Agent i aktywuje emergency stop."""
    global _ghost_run_task

    if not _ghost_api_enabled():
        raise HTTPException(
            status_code=503,
            detail="Ghost API jest wyłączone (ENABLE_GHOST_API/ENABLE_GHOST_AGENT=false)",
        )
    if _ghost_agent is None:
        raise HTTPException(status_code=503, detail="Ghost Agent nie jest dostępny")

    actor = resolve_actor_from_request(req)
    try:
        ensure_data_mutation_allowed("agents.ghost.cancel")
    except PermissionError as e:
        raise_permission_denied_http(
            e,
            operation="agents.ghost.cancel",
            actor=actor,
        )

    if _ghost_run_task is None or _ghost_run_task.done():
        _publish_ghost_audit(
            action="ghost.run.cancel",
            status="success",
            actor=actor,
            details={"cancelled": False, "reason": "no_active_task"},
        )
        return {"status": "success", "cancelled": False, "task_id": None}

    task_id = (_ghost_run_state or {}).get("task_id")
    _ghost_agent.emergency_stop_trigger()
    _ghost_run_task.cancel()
    try:
        await _ghost_run_task
    except asyncio.CancelledError:
        pass

    _publish_ghost_audit(
        action="ghost.run.cancel",
        status="success",
        actor=actor,
        context=str(task_id) if task_id else None,
        details={"cancelled": True, "task_id": task_id},
    )
    return {"status": "success", "cancelled": True, "task_id": task_id}
