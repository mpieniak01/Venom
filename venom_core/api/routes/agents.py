"""Moduł: routes/agents - Endpointy API dla agentów (gardener, shadow, watcher, documenter, ghost)."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import tempfile
from contextlib import contextmanager, suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol
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

GHOST_API_DISABLED_DETAIL = (
    "Ghost API jest wyłączone (ENABLE_GHOST_API/ENABLE_GHOST_AGENT=false)"
)
GHOST_AGENT_UNAVAILABLE_DETAIL = "Ghost Agent nie jest dostępny"


class _GhostAgentLike(Protocol):
    async def process(self, content: str) -> str: ...

    def emergency_stop_trigger(self) -> None: ...

    def get_status(self) -> dict[str, Any]: ...

    def apply_runtime_profile(self, profile: str) -> dict[str, Any]: ...


# Dependencies - będą ustawione w main.py
_gardener_agent = None
_shadow_agent = None
_file_watcher = None
_documenter_agent = None
_orchestrator = None
_ghost_agent: _GhostAgentLike | None = None

_fcntl: Any
try:
    import fcntl as _fcntl
except ImportError:  # pragma: no cover - fallback for non-POSIX platforms
    _fcntl = None
fcntl = _fcntl


def _resolve_ghost_run_state_path() -> Path:
    """Return canonical ghost runtime state path in process-scoped temp runtime dir."""
    return (
        Path(tempfile.gettempdir()).resolve()
        / "venom"
        / "runtime"
        / f"ghost_run_state_{os.getpid()}.json"
    ).resolve()


class _GhostRunStateStore:
    """Shared run-state store used by Ghost API across multiple workers."""

    ACTIVE_STATUSES = {"running", "cancelling"}
    TERMINAL_STATUSES = {"completed", "cancelled", "failed"}

    def __init__(self):
        self._state_path = _resolve_ghost_run_state_path()
        self._lock_path = self._state_path.with_suffix(
            f"{self._state_path.suffix}.lock"
        )
        self._state_path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def is_active(state: dict[str, Any] | None) -> bool:
        return bool(
            state and state.get("status") in _GhostRunStateStore.ACTIVE_STATUSES
        )

    @contextmanager
    def _locked(self):
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock_path.open("a+", encoding="utf-8") as handle:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                if fcntl is not None:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _read_state_unlocked(self) -> dict[str, Any] | None:
        if not self._state_path.exists():
            return None
        try:
            payload = json.loads(self._state_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Nie udało się odczytać ghost run state: %s", exc)
            return None
        return payload if isinstance(payload, dict) else None

    def _write_state_unlocked(self, state: dict[str, Any] | None) -> None:
        if state is None:
            with suppress(FileNotFoundError):
                self._state_path.unlink()
            return

        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_raw = tempfile.mkstemp(
            prefix=f"{self._state_path.name}.",
            suffix=".tmp",
            dir=str(self._state_path.parent),
        )
        os.close(fd)
        temp_path = Path(temp_raw)
        try:
            temp_path.write_text(
                json.dumps(state, ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )
            os.replace(temp_path, self._state_path)
        finally:
            with suppress(FileNotFoundError):
                temp_path.unlink()

    def get(self) -> dict[str, Any] | None:
        with self._locked():
            return self._read_state_unlocked()

    def clear(self) -> None:
        with self._locked():
            self._write_state_unlocked(None)

    def try_start(self, state: dict[str, Any]) -> bool:
        with self._locked():
            current = self._read_state_unlocked()
            if self.is_active(current):
                return False
            self._write_state_unlocked(state)
            return True

    def update(self, task_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        with self._locked():
            current = self._read_state_unlocked()
            if current is None:
                return None
            if current.get("task_id") != task_id:
                return current
            current.update(patch)
            self._write_state_unlocked(current)
            return current


_ghost_run_store = _GhostRunStateStore()
_ghost_local_tasks: dict[str, asyncio.Task[str]] = {}


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


def _utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_content(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _get_runtime_profile(task_id: str) -> str | None:
    state = _ghost_run_store.get()
    if not state or state.get("task_id") != task_id:
        return None
    profile = state.get("runtime_profile")
    return str(profile) if profile is not None else None


def _require_ghost_agent() -> _GhostAgentLike:
    ghost_agent = _ghost_agent
    if ghost_agent is None:
        raise RuntimeError(GHOST_AGENT_UNAVAILABLE_DETAIL)
    return ghost_agent


async def _run_ghost_process_with_cancel_watch(*, task_id: str, content: str) -> str:
    ghost_agent = _require_ghost_agent()
    process_task = asyncio.create_task(ghost_agent.process(content))
    try:
        while True:
            done, _ = await asyncio.wait({process_task}, timeout=0.25)
            if process_task in done:
                return process_task.result()
            run_state = _ghost_run_store.get()
            if (
                run_state
                and run_state.get("task_id") == task_id
                and run_state.get("status") == "cancelling"
            ):
                ghost_agent.emergency_stop_trigger()
                process_task.cancel()
                with suppress(asyncio.CancelledError):
                    await process_task
                raise asyncio.CancelledError
    finally:
        if not process_task.done():
            process_task.cancel()
            with suppress(asyncio.CancelledError):
                await process_task


async def _run_ghost_job(*, task_id: str, payload: GhostRunRequest, actor: str) -> str:
    try:
        result = await _run_ghost_process_with_cancel_watch(
            task_id=task_id, content=payload.content
        )
        _ghost_run_store.update(
            task_id,
            {
                "status": "completed",
                "finished_at": _utc_iso_now(),
                "result": result,
            },
        )
        _publish_ghost_audit(
            action="ghost.run.completed",
            status="success",
            actor=actor,
            context=task_id,
            details={
                "runtime_profile": _get_runtime_profile(task_id),
                "result_excerpt": result[:500],
            },
        )
        return result
    except asyncio.CancelledError:
        _ghost_run_store.update(
            task_id,
            {
                "status": "cancelled",
                "finished_at": _utc_iso_now(),
                "result": "Cancelled by API emergency stop",
            },
        )
        _publish_ghost_audit(
            action="ghost.run.cancelled",
            status="cancelled",
            actor=actor,
            context=task_id,
            details={"runtime_profile": _get_runtime_profile(task_id)},
        )
        raise
    except Exception as e:
        logger.exception("Błąd podczas wykonywania zadania Ghost")
        _ghost_run_store.update(
            task_id,
            {
                "status": "failed",
                "finished_at": _utc_iso_now(),
                "result": str(e),
            },
        )
        _publish_ghost_audit(
            action="ghost.run.failed",
            status="failure",
            actor=actor,
            context=task_id,
            details={
                "runtime_profile": _get_runtime_profile(task_id),
                "error": str(e),
            },
        )
        raise
    finally:
        _ghost_local_tasks.pop(task_id, None)


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
    responses={
        503: {"description": "Ghost API lub Ghost Agent nie jest dostępny"},
        500: {"description": "Błąd wewnętrzny podczas pobierania statusu"},
    },
)
def get_ghost_status():
    """Zwraca status wykonania zadań Ghost Agent."""
    if not _ghost_api_enabled():
        return {
            "status": "disabled",
            "message": GHOST_API_DISABLED_DETAIL,
            "ghost": None,
            "run": None,
        }

    if _ghost_agent is None:
        raise HTTPException(status_code=503, detail=GHOST_AGENT_UNAVAILABLE_DETAIL)

    try:
        run_state = _ghost_run_store.get()
        task_id = (run_state or {}).get("task_id")
        local_task = _ghost_local_tasks.get(str(task_id)) if task_id else None
        task_active = _GhostRunStateStore.is_active(run_state)
        if local_task is not None and local_task.done():
            task_active = False
        return {
            "status": "success",
            "ghost": _ghost_agent.get_status(),
            "run": run_state,
            "task_active": task_active,
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
    if not _ghost_api_enabled():
        raise HTTPException(
            status_code=503,
            detail=GHOST_API_DISABLED_DETAIL,
        )
    if _ghost_agent is None:
        raise HTTPException(status_code=503, detail=GHOST_AGENT_UNAVAILABLE_DETAIL)
    ghost_agent = _require_ghost_agent()
    if _GhostRunStateStore.is_active(_ghost_run_store.get()):
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

    runtime_profile = str(
        request.runtime_profile
        or getattr(SETTINGS, "GHOST_RUNTIME_PROFILE", "desktop_safe")
    )
    profile_payload = ghost_agent.apply_runtime_profile(runtime_profile)

    task_id = str(uuid4())
    started_at = _utc_iso_now()
    run_state = {
        "task_id": task_id,
        "status": "running",
        "content_sha256": _hash_content(request.content),
        "content_length": len(request.content),
        "runtime_profile": profile_payload["profile"],
        "started_at": started_at,
    }
    if not _ghost_run_store.try_start(run_state):
        raise HTTPException(status_code=409, detail="Ghost Agent już wykonuje zadanie")

    task = asyncio.create_task(
        _run_ghost_job(task_id=task_id, payload=request, actor=actor)
    )
    _ghost_local_tasks[task_id] = task

    _publish_ghost_audit(
        action="ghost.run.start",
        status="accepted",
        actor=actor,
        context=task_id,
        details={
            "runtime_profile": profile_payload["profile"],
            "content_sha256": _hash_content(request.content),
            "content_length": len(request.content),
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
    if not _ghost_api_enabled():
        raise HTTPException(
            status_code=503,
            detail=GHOST_API_DISABLED_DETAIL,
        )
    if _ghost_agent is None:
        raise HTTPException(status_code=503, detail=GHOST_AGENT_UNAVAILABLE_DETAIL)

    actor = resolve_actor_from_request(req)
    try:
        ensure_data_mutation_allowed("agents.ghost.cancel")
    except PermissionError as e:
        raise_permission_denied_http(
            e,
            operation="agents.ghost.cancel",
            actor=actor,
        )

    run_state = _ghost_run_store.get()
    if not _GhostRunStateStore.is_active(run_state):
        _publish_ghost_audit(
            action="ghost.run.cancel",
            status="success",
            actor=actor,
            details={"cancelled": False, "reason": "no_active_task"},
        )
        return {"status": "success", "cancelled": False, "task_id": None}

    task_id = str((run_state or {}).get("task_id") or "")
    _ghost_run_store.update(
        task_id,
        {
            "status": "cancelling",
            "cancel_requested_at": _utc_iso_now(),
        },
    )

    local_task = _ghost_local_tasks.get(task_id)
    cancelled_local = False
    if local_task is not None and not local_task.done():
        _ghost_agent.emergency_stop_trigger()
        local_task.cancel()
        cancelled_local = True
        with suppress(asyncio.CancelledError):
            await local_task

    _publish_ghost_audit(
        action="ghost.run.cancel",
        status="success",
        actor=actor,
        context=str(task_id) if task_id else None,
        details={
            "cancelled": True,
            "task_id": task_id,
            "local_task_cancelled": cancelled_local,
        },
    )
    return {"status": "success", "cancelled": True, "task_id": task_id}
