"""Adapter layer from legacy memory/session/lesson records to Knowledge Contract v1."""

from __future__ import annotations

from typing import Any, Literal, cast

from venom_core.core.knowledge_contract import (
    KnowledgeKind,
    KnowledgeRecordV1,
    KnowledgeSource,
    ProvenanceV1,
    RetentionV1,
)
from venom_core.core.knowledge_ttl import (
    compute_expires_at,
    parse_iso_datetime,
    resolve_ttl_days,
)
from venom_core.utils.helpers import get_utc_now_iso


def _normalize_source(value: Any, fallback: KnowledgeSource) -> KnowledgeSource:
    if isinstance(value, KnowledgeSource):
        return value
    if isinstance(value, str):
        try:
            return KnowledgeSource(value)
        except ValueError:
            return fallback
    return fallback


def _provenance_from_metadata(
    metadata: dict[str, Any],
    *,
    fallback_source: KnowledgeSource,
    origin_id: str | None = None,
    pipeline_stage: str | None = None,
) -> ProvenanceV1:
    return ProvenanceV1(
        source=_normalize_source(
            metadata.get("provenance_source") or metadata.get("source"), fallback_source
        ),
        origin_id=origin_id or _as_optional_str(metadata.get("origin_id")),
        request_id=_as_optional_str(
            metadata.get("provenance_request_id") or metadata.get("request_id")
        ),
        intent=_as_optional_str(
            metadata.get("provenance_intent") or metadata.get("intent")
        ),
        agent=_as_optional_str(metadata.get("agent")),
        pipeline_stage=_as_optional_str(metadata.get("pipeline_stage"))
        or pipeline_stage,
    )


def _as_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _build_retention(
    *,
    kind: KnowledgeKind,
    scope: str,
    metadata: dict[str, Any],
    created_at: str | None,
) -> RetentionV1:
    retention_scope: Literal["session", "global", "task"] = cast(
        Literal["session", "global", "task"],
        scope if scope in {"session", "global", "task"} else "global",
    )
    ttl_days = resolve_ttl_days(kind, scope)
    expires_at = metadata.get("retention_expires_at") or compute_expires_at(
        created_at, ttl_days
    )
    return RetentionV1(
        ttl_days=ttl_days if ttl_days > 0 else None,
        expires_at=_as_optional_str(expires_at),
        pinned=bool(metadata.get("pinned")),
        scope=retention_scope,
    )


def from_session_store_entry(
    session_id: str, entry: dict[str, Any]
) -> KnowledgeRecordV1:
    metadata = dict(entry.get("knowledge_metadata") or {})
    role = _as_optional_str(entry.get("role")) or "unknown"
    content = _as_optional_str(entry.get("content")) or ""
    request_id = _as_optional_str(entry.get("request_id"))
    timestamp = _as_optional_str(entry.get("timestamp")) or get_utc_now_iso()

    if role == "summary":
        kind = KnowledgeKind.SESSION_SUMMARY
    else:
        kind = KnowledgeKind.SESSION_MESSAGE

    record_id = (
        _as_optional_str(entry.get("record_id"))
        or f"session:{session_id}:{request_id or timestamp}:{role}"
    )
    scope = _as_optional_str(metadata.get("retention_scope")) or "session"

    return KnowledgeRecordV1(
        record_id=record_id,
        kind=kind,
        session_id=session_id,
        task_id=request_id,
        user_id=_as_optional_str(entry.get("user_id")),
        content=content,
        metadata={**metadata, "role": role},
        provenance=_provenance_from_metadata(
            metadata,
            fallback_source=KnowledgeSource.SESSION_STORE,
            origin_id=record_id,
            pipeline_stage="session_history",
        ),
        retention=_build_retention(
            kind=kind,
            scope=scope,
            metadata=metadata,
            created_at=timestamp,
        ),
        created_at=timestamp,
    )


def from_lesson(lesson: Any) -> KnowledgeRecordV1:
    if isinstance(lesson, dict):
        lesson_data = dict(lesson)
    elif hasattr(lesson, "to_dict"):
        lesson_data = dict(lesson.to_dict())
    elif hasattr(lesson, "__dict__"):
        lesson_data = dict(vars(lesson))
    else:
        lesson_data = {}

    metadata = dict(lesson_data.get("metadata") or {})
    lesson_id = (
        _as_optional_str(lesson_data.get("lesson_id") or lesson_data.get("id"))
        or "lesson:unknown"
    )
    timestamp = _as_optional_str(lesson_data.get("timestamp")) or get_utc_now_iso()
    scope = _as_optional_str(metadata.get("retention_scope")) or "task"

    content = (
        f"Sytuacja: {_as_optional_str(lesson_data.get('situation')) or ''}\n"
        f"Akcja: {_as_optional_str(lesson_data.get('action')) or ''}\n"
        f"Rezultat: {_as_optional_str(lesson_data.get('result')) or ''}\n"
        f"Lekcja: {_as_optional_str(lesson_data.get('feedback')) or ''}"
    ).strip()

    return KnowledgeRecordV1(
        record_id=f"lesson:{lesson_id}",
        kind=KnowledgeKind.LESSON,
        session_id=_as_optional_str(metadata.get("session_id")),
        task_id=_as_optional_str(metadata.get("task_id")),
        user_id=_as_optional_str(metadata.get("user_id")),
        content=content,
        metadata={
            **metadata,
            "tags": lesson_data.get("tags") or [],
        },
        provenance=_provenance_from_metadata(
            metadata,
            fallback_source=KnowledgeSource.LESSONS_STORE,
            origin_id=lesson_id,
            pipeline_stage="lessons",
        ),
        retention=_build_retention(
            kind=KnowledgeKind.LESSON,
            scope=scope,
            metadata=metadata,
            created_at=timestamp,
        ),
        created_at=timestamp,
    )


def from_vector_entry(entry: dict[str, Any]) -> KnowledgeRecordV1:
    metadata = dict(entry.get("metadata") or {})
    record_id = _as_optional_str(entry.get("id")) or "memory:unknown"
    text = _as_optional_str(entry.get("text")) or ""
    created_at = (
        _as_optional_str(metadata.get("timestamp"))
        or _as_optional_str(metadata.get("created_at"))
        or get_utc_now_iso()
    )
    scope = _as_optional_str(metadata.get("retention_scope"))
    if not scope:
        scope = "session" if metadata.get("session_id") else "global"

    provenance = _provenance_from_metadata(
        metadata,
        fallback_source=KnowledgeSource.VECTOR_STORE,
        origin_id=record_id,
        pipeline_stage="vector_memory",
    )

    # Ensure timestamps stay valid ISO when old records carry malformed values.
    created_parsed = parse_iso_datetime(created_at)
    normalized_created_at = (
        created_parsed.isoformat() if created_parsed else get_utc_now_iso()
    )

    return KnowledgeRecordV1(
        record_id=f"memory:{record_id}",
        kind=KnowledgeKind.MEMORY_ENTRY,
        session_id=_as_optional_str(metadata.get("session_id")),
        task_id=_as_optional_str(metadata.get("task_id"))
        or _as_optional_str(metadata.get("request_id")),
        user_id=_as_optional_str(metadata.get("user_id")),
        content=text,
        metadata=metadata,
        provenance=provenance,
        retention=_build_retention(
            kind=KnowledgeKind.MEMORY_ENTRY,
            scope=scope,
            metadata=metadata,
            created_at=normalized_created_at,
        ),
        created_at=normalized_created_at,
    )
