"""Canonical audit stream shared by core and optional modules."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Any
from uuid import uuid4

from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


def _env_int(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class AuditStreamEntry:
    id: str
    timestamp: datetime
    source: str
    action: str
    actor: str
    status: str
    context: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


class AuditStream:
    """Thread-safe in-memory audit stream."""

    def __init__(self, max_entries: int = 5000):
        self._entries: list[AuditStreamEntry] = []
        self._lock = Lock()
        self._max_entries = max(100, max_entries)

    def publish(
        self,
        *,
        source: str,
        action: str,
        actor: str,
        status: str,
        context: str | None = None,
        details: dict[str, Any] | None = None,
        timestamp: datetime | None = None,
        entry_id: str | None = None,
    ) -> AuditStreamEntry:
        entry = AuditStreamEntry(
            id=entry_id or f"audit-{uuid4().hex[:12]}",
            timestamp=timestamp or datetime.now(timezone.utc),
            source=(source or "unknown").strip() or "unknown",
            action=(action or "unknown").strip() or "unknown",
            actor=(actor or "unknown").strip() or "unknown",
            status=(status or "unknown").strip() or "unknown",
            context=(context or "").strip() or None,
            details=details or {},
        )
        with self._lock:
            self._entries.append(entry)
            if len(self._entries) > self._max_entries:
                self._entries = self._entries[-self._max_entries :]
        return entry

    def get_entries(
        self,
        *,
        source: str | None = None,
        action: str | None = None,
        actor: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[AuditStreamEntry]:
        with self._lock:
            entries = list(self._entries)

        if source:
            source_l = source.lower()
            entries = [entry for entry in entries if entry.source.lower() == source_l]
        if action:
            action_l = action.lower()
            entries = [entry for entry in entries if entry.action.lower() == action_l]
        if actor:
            actor_l = actor.lower()
            entries = [entry for entry in entries if entry.actor.lower() == actor_l]
        if status:
            status_l = status.lower()
            entries = [entry for entry in entries if entry.status.lower() == status_l]

        entries.sort(key=lambda entry: entry.timestamp, reverse=True)
        return entries[: max(1, min(limit, 500))]

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


_audit_stream: AuditStream | None = None
_audit_stream_lock = Lock()


def get_audit_stream() -> AuditStream:
    global _audit_stream
    if _audit_stream is None:
        with _audit_stream_lock:
            if _audit_stream is None:
                _audit_stream = AuditStream(
                    max_entries=max(
                        100,
                        _env_int("VENOM_AUDIT_STREAM_MAX_ENTRIES", default=5000),
                    )
                )
                logger.info("Initialized canonical audit stream")
    return _audit_stream
