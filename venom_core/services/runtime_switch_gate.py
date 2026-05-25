"""Global gate for runtime switch drain / request blocking.

The switch flow needs a single source of truth for whether new runtime-bound
requests may start. This module keeps a small in-memory gate that:

- rejects new requests while a switch is in progress,
- tracks active runtime-bound requests so switch can wait for drain,
- exposes a read-only status snapshot for diagnostics.
"""

from __future__ import annotations

import asyncio
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, AsyncIterator
from uuid import uuid4

from fastapi import HTTPException

from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

_HTTP_409_RUNTIME_SWITCH_IN_PROGRESS = 409
_DRAIN_TIMEOUT_SECONDS = 30.0
_DRAIN_POLL_INTERVAL_SECONDS = 0.05
_STALE_SWITCH_SECONDS = 90.0


@dataclass(frozen=True)
class RuntimeSwitchGateSnapshot:
    in_progress: bool
    active_requests: int
    switch_id: str | None
    source: str | None
    from_runtime: str | None
    to_runtime: str | None
    started_at_utc: str | None
    reason: str | None


@dataclass
class _RuntimeSwitchGateState:
    in_progress: bool = False
    active_requests: int = 0
    switch_id: str | None = None
    source: str | None = None
    from_runtime: str | None = None
    to_runtime: str | None = None
    started_at_utc: str | None = None
    reason: str | None = None


_STATE_LOCK = threading.Lock()
_STATE = _RuntimeSwitchGateState()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _snapshot_unlocked() -> RuntimeSwitchGateSnapshot:
    return RuntimeSwitchGateSnapshot(
        in_progress=_STATE.in_progress,
        active_requests=_STATE.active_requests,
        switch_id=_STATE.switch_id,
        source=_STATE.source,
        from_runtime=_STATE.from_runtime,
        to_runtime=_STATE.to_runtime,
        started_at_utc=_STATE.started_at_utc,
        reason=_STATE.reason,
    )


def _parse_iso_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _clear_gate_unlocked() -> None:
    _STATE.in_progress = False
    _STATE.switch_id = None
    _STATE.source = None
    _STATE.from_runtime = None
    _STATE.to_runtime = None
    _STATE.started_at_utc = None
    _STATE.reason = None


def _recover_stale_gate_unlocked() -> bool:
    if not _STATE.in_progress:
        return False
    if _STATE.active_requests > 0:
        return False
    started_at = _parse_iso_utc(_STATE.started_at_utc)
    if started_at is None:
        return False
    age_seconds = (datetime.now(UTC) - started_at).total_seconds()
    if age_seconds < _STALE_SWITCH_SECONDS:
        return False
    stale_switch_id = _STATE.switch_id
    stale_source = _STATE.source
    stale_from = _STATE.from_runtime
    stale_to = _STATE.to_runtime
    _clear_gate_unlocked()
    logger.warning(
        "runtime_switch_gate_stale_recovered switch_id={} source={} from={} to={} age_seconds={:.1f}",
        stale_switch_id,
        stale_source,
        stale_from,
        stale_to,
        age_seconds,
    )
    return True


def get_runtime_switch_gate_status() -> dict[str, Any]:
    snapshot = get_runtime_switch_gate_snapshot()
    return {
        "in_progress": snapshot.in_progress,
        "active_requests": snapshot.active_requests,
        "switch_id": snapshot.switch_id,
        "source": snapshot.source,
        "from_runtime": snapshot.from_runtime,
        "to_runtime": snapshot.to_runtime,
        "started_at_utc": snapshot.started_at_utc,
        "reason": snapshot.reason,
    }


def get_runtime_switch_gate_snapshot() -> RuntimeSwitchGateSnapshot:
    with _STATE_LOCK:
        _recover_stale_gate_unlocked()
        return _snapshot_unlocked()


def assert_runtime_request_allowed(*, request_kind: str) -> None:
    with _STATE_LOCK:
        if not _STATE.in_progress:
            return
        snapshot = _snapshot_unlocked()
    logger.info(
        "runtime_request_blocked kind={} switch_id={} source={} target={} active_requests={}",
        request_kind,
        snapshot.switch_id,
        snapshot.source,
        snapshot.to_runtime,
        snapshot.active_requests,
    )
    raise HTTPException(
        status_code=_HTTP_409_RUNTIME_SWITCH_IN_PROGRESS,
        detail={
            "code": "runtime_switch_in_progress",
            "message": "Przełączanie runtime w toku. Spróbuj ponownie za chwilę.",
            "request_kind": request_kind,
            "runtime_switch_gate": get_runtime_switch_gate_status(),
        },
    )


def begin_runtime_switch(
    *,
    source: str,
    from_runtime: str,
    to_runtime: str,
    reason: str | None = None,
) -> RuntimeSwitchGateSnapshot:
    with _STATE_LOCK:
        _recover_stale_gate_unlocked()
        if _STATE.in_progress:
            snapshot = _snapshot_unlocked()
            raise HTTPException(
                status_code=_HTTP_409_RUNTIME_SWITCH_IN_PROGRESS,
                detail={
                    "code": "runtime_switch_in_progress",
                    "message": "Przełączanie runtime już trwa.",
                    "runtime_switch_gate": {
                        "in_progress": snapshot.in_progress,
                        "active_requests": snapshot.active_requests,
                        "switch_id": snapshot.switch_id,
                        "source": snapshot.source,
                        "from_runtime": snapshot.from_runtime,
                        "to_runtime": snapshot.to_runtime,
                        "started_at_utc": snapshot.started_at_utc,
                        "reason": snapshot.reason,
                    },
                },
            )
        _STATE.in_progress = True
        _STATE.switch_id = uuid4().hex
        _STATE.source = str(source or "").strip() or "ui"
        _STATE.from_runtime = str(from_runtime or "").strip() or None
        _STATE.to_runtime = str(to_runtime or "").strip() or None
        _STATE.started_at_utc = _utc_now()
        _STATE.reason = str(reason or "").strip() or None
        snapshot = _snapshot_unlocked()

    logger.info(
        "runtime_switch_gate_opened switch_id={} source={} from={} to={}",
        snapshot.switch_id,
        snapshot.source,
        snapshot.from_runtime,
        snapshot.to_runtime,
    )
    return snapshot


def finish_runtime_switch(*, switch_id: str | None) -> None:
    with _STATE_LOCK:
        if switch_id and _STATE.switch_id and _STATE.switch_id != switch_id:
            logger.warning(
                "runtime_switch_gate_finish_mismatch current={} requested={}",
                _STATE.switch_id,
                switch_id,
            )
            return
        _clear_gate_unlocked()
        _STATE.active_requests = max(0, _STATE.active_requests)

    logger.info("runtime_switch_gate_closed switch_id={}", switch_id)


async def wait_for_runtime_requests_to_drain(
    *, timeout_seconds: float = _DRAIN_TIMEOUT_SECONDS
) -> bool:
    deadline = time.monotonic() + max(0.0, timeout_seconds)
    while True:
        with _STATE_LOCK:
            active_requests = _STATE.active_requests
        if active_requests <= 0:
            return True
        if time.monotonic() >= deadline:
            logger.warning(
                "runtime_switch_gate_drain_timeout active_requests={} timeout_seconds={}",
                active_requests,
                timeout_seconds,
            )
            return False
        await asyncio.sleep(_DRAIN_POLL_INTERVAL_SECONDS)


@asynccontextmanager
async def runtime_request_guard(
    *, request_kind: str, provider: str | None = None, model: str | None = None
) -> AsyncIterator[RuntimeSwitchGateSnapshot]:
    with _STATE_LOCK:
        _recover_stale_gate_unlocked()
        if _STATE.in_progress:
            snapshot = _snapshot_unlocked()
            raise HTTPException(
                status_code=_HTTP_409_RUNTIME_SWITCH_IN_PROGRESS,
                detail={
                    "code": "runtime_switch_in_progress",
                    "message": "Przełączanie runtime już trwa.",
                    "runtime_switch_gate": {
                        "in_progress": snapshot.in_progress,
                        "active_requests": snapshot.active_requests,
                        "switch_id": snapshot.switch_id,
                        "source": snapshot.source,
                        "from_runtime": snapshot.from_runtime,
                        "to_runtime": snapshot.to_runtime,
                        "started_at_utc": snapshot.started_at_utc,
                        "reason": snapshot.reason,
                    },
                },
            )
        _STATE.active_requests += 1
        snapshot = _snapshot_unlocked()
    logger.info(
        "runtime_request_entered kind={} provider={} model={} active_requests={}",
        request_kind,
        provider or "",
        model or "",
        snapshot.active_requests,
    )
    try:
        yield snapshot
    finally:
        with _STATE_LOCK:
            _STATE.active_requests = max(0, _STATE.active_requests - 1)
            snapshot = _snapshot_unlocked()
        logger.info(
            "runtime_request_exited kind={} provider={} model={} active_requests={}",
            request_kind,
            provider or "",
            model or "",
            snapshot.active_requests,
        )
