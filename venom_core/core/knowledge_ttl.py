"""Knowledge Contract v1 retention utilities."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from venom_core.config import SETTINGS
from venom_core.core.knowledge_contract import KnowledgeKind


def _to_aware_utc(created_at: datetime) -> datetime:
    if created_at.tzinfo is None:
        return created_at.replace(tzinfo=timezone.utc)
    return created_at.astimezone(timezone.utc)


def parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return _to_aware_utc(parsed)
    except Exception:
        return None


def resolve_ttl_days(kind: KnowledgeKind, scope: str) -> int:
    if kind == KnowledgeKind.LESSON:
        return int(getattr(SETTINGS, "LESSONS_TTL_DAYS", 0) or 0)
    if kind == KnowledgeKind.MEMORY_ENTRY:
        return int(getattr(SETTINGS, "MEMORY_TTL_DAYS", 0) or 0)
    if kind in {KnowledgeKind.SESSION_MESSAGE, KnowledgeKind.SESSION_SUMMARY}:
        return int(getattr(SETTINGS, "SESSION_TTL_DAYS", 0) or 0)
    # Retrieval context and other transient kinds default to disabled retention.
    _ = scope
    return 0


def compute_expires_at(
    created_at: datetime | str | None, ttl_days: Optional[int]
) -> str | None:
    ttl = int(ttl_days or 0)
    if ttl <= 0:
        return None

    created: datetime | None
    if isinstance(created_at, datetime):
        created = _to_aware_utc(created_at)
    elif isinstance(created_at, str):
        created = parse_iso_datetime(created_at)
    else:
        created = None

    if created is None:
        return None
    return (created + timedelta(days=ttl)).isoformat()
