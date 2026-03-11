"""Federated knowledge entry read-model (session + lessons + vector + graph)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from venom_core.api.schemas.knowledge import (
    KnowledgeEntry,
    KnowledgeEntryScope,
    KnowledgeSourceMeta,
    KnowledgeSourceOrigin,
)
from venom_core.core.knowledge_adapters import from_lesson, from_vector_entry
from venom_core.core.knowledge_contract import KnowledgeRecordV1
from venom_core.core.knowledge_ttl import parse_iso_datetime
from venom_core.services.knowledge_context_service import (
    read_lesson_records,
    read_memory_records,
    read_session_records,
)
from venom_core.utils.helpers import get_utc_now_iso


@dataclass(slots=True)
class KnowledgeEntriesQuery:
    session_id: str | None = None
    scope: KnowledgeEntryScope | None = None
    source: KnowledgeSourceOrigin | None = None
    tags: list[str] | None = None
    created_from: str | None = None
    created_to: str | None = None
    limit: int = 200


def _origin_for_record(record: KnowledgeRecordV1) -> KnowledgeSourceOrigin:
    source_name = record.provenance.source.value
    if source_name == "session_store":
        return KnowledgeSourceOrigin.SESSION
    if source_name == "lessons_store":
        return KnowledgeSourceOrigin.LESSON
    if source_name == "vector_store":
        return KnowledgeSourceOrigin.VECTOR
    return KnowledgeSourceOrigin.EXTERNAL


def _scope_for_record(record: KnowledgeRecordV1) -> KnowledgeEntryScope:
    scope = record.retention.scope
    if scope == "session":
        return KnowledgeEntryScope.SESSION
    if scope == "task":
        return KnowledgeEntryScope.TASK
    return KnowledgeEntryScope.GLOBAL


def _to_entry(record: KnowledgeRecordV1) -> KnowledgeEntry:
    metadata = dict(record.metadata or {})
    tags_raw = metadata.get("tags")
    tags = [str(tag).strip() for tag in tags_raw] if isinstance(tags_raw, list) else []
    tags = [tag for tag in tags if tag]
    source_name = record.provenance.source.value
    reason_code = metadata.get("reason_code")
    if reason_code is not None:
        reason_code = str(reason_code)

    provenance = record.provenance.model_dump(exclude_none=True)
    return KnowledgeEntry(
        entry_id=record.record_id,
        entry_type=record.kind.value,
        scope=_scope_for_record(record),
        source=source_name,
        content=record.content,
        summary=metadata.get("summary"),
        tags=tags,
        session_id=record.session_id,
        task_id=record.task_id,
        request_id=record.provenance.request_id,
        created_at=record.created_at,
        updated_at=metadata.get("updated_at"),
        ttl_at=record.retention.expires_at,
        confidence=_as_optional_float(metadata.get("confidence")),
        quality_score=_as_optional_float(metadata.get("quality_score")),
        version=str(metadata.get("knowledge_contract_version") or "v1"),
        source_meta=KnowledgeSourceMeta(
            origin=_origin_for_record(record),
            provenance=provenance,
            reason_code=reason_code,
        ),
        metadata=metadata,
    )


def _as_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _collect_session_ids(
    session_store: Any, selected_session_id: str | None
) -> list[str]:
    if selected_session_id:
        return [selected_session_id]
    sessions = getattr(session_store, "_sessions", None)
    if isinstance(sessions, dict):
        return [sid for sid in sessions.keys() if isinstance(sid, str) and sid.strip()]
    return []


def _append_graph_entry(entries: list[KnowledgeEntry], graph_store: Any) -> None:
    if graph_store is None:
        return
    summary_getter = getattr(graph_store, "get_graph_summary", None)
    if not callable(summary_getter):
        return
    try:
        summary = summary_getter() or {}
    except Exception:
        return
    if not isinstance(summary, dict):
        return
    nodes = int(summary.get("total_nodes") or 0)
    edges = int(summary.get("total_edges") or 0)
    created_at = get_utc_now_iso()
    entries.append(
        KnowledgeEntry(
            entry_id="graph:summary",
            entry_type="graph_summary",
            scope=KnowledgeEntryScope.GLOBAL,
            source="graph_store",
            content=f"Graph summary: nodes={nodes}, edges={edges}",
            summary="Snapshot of current knowledge graph.",
            created_at=created_at,
            updated_at=created_at,
            source_meta=KnowledgeSourceMeta(
                origin=KnowledgeSourceOrigin.GRAPH,
                provenance={"source": "graph_store"},
            ),
            metadata=summary,
        )
    )


def _matches_time_window(
    entry: KnowledgeEntry, created_from: datetime | None, created_to: datetime | None
) -> bool:
    created_at = parse_iso_datetime(entry.created_at)
    if created_at is None:
        return created_from is None and created_to is None
    if created_from and created_at < created_from:
        return False
    if created_to and created_at > created_to:
        return False
    return True


def _matches_tags(entry: KnowledgeEntry, expected_tags: set[str]) -> bool:
    if not expected_tags:
        return True
    entry_tags = {tag.strip().lower() for tag in entry.tags if tag.strip()}
    return bool(entry_tags.intersection(expected_tags))


def _filter_entries(
    entries: list[KnowledgeEntry], query: KnowledgeEntriesQuery
) -> list[KnowledgeEntry]:
    created_from = (
        parse_iso_datetime(query.created_from) if query.created_from else None
    )
    created_to = parse_iso_datetime(query.created_to) if query.created_to else None
    expected_tags = {
        tag.strip().lower()
        for tag in (query.tags or [])
        if isinstance(tag, str) and tag.strip()
    }
    filtered: list[KnowledgeEntry] = []
    for entry in entries:
        if query.scope and entry.scope != query.scope:
            continue
        if query.source and entry.source_meta.origin != query.source:
            continue
        if query.session_id and entry.session_id != query.session_id:
            continue
        if not _matches_tags(entry, expected_tags):
            continue
        if not _matches_time_window(entry, created_from, created_to):
            continue
        filtered.append(entry)
    filtered.sort(key=lambda item: item.created_at, reverse=True)
    return filtered[: query.limit]


def list_federated_knowledge_entries(
    *,
    session_store: Any,
    lessons_store: Any,
    vector_store: Any,
    graph_store: Any,
    query: KnowledgeEntriesQuery,
) -> list[KnowledgeEntry]:
    records: list[KnowledgeRecordV1] = []
    for session_id in _collect_session_ids(session_store, query.session_id):
        records.extend(read_session_records(session_id, session_store))

    if lessons_store is not None:
        if query.session_id:
            records.extend(
                read_lesson_records(
                    lessons_store=lessons_store,
                    session_id=query.session_id,
                    related_task_ids=set(),
                    limit=query.limit,
                )
            )
        else:
            for lesson in lessons_store.get_all_lessons(limit=query.limit):
                records.append(from_lesson(lesson))

    if vector_store is not None:
        if query.session_id:
            records.extend(
                read_memory_records(vector_store, query.session_id, query.limit)
            )
        else:
            for entry in vector_store.list_entries(limit=query.limit):
                if isinstance(entry, dict):
                    records.append(from_vector_entry(entry))

    entries = [_to_entry(record) for record in records]
    _append_graph_entry(entries, graph_store)
    return _filter_entries(entries, query)
