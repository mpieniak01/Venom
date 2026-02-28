"""Knowledge context-map use case extracted from API router."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from venom_core.core.knowledge_adapters import (
    from_lesson,
    from_session_store_entry,
    from_vector_entry,
)
from venom_core.core.knowledge_contract import (
    KnowledgeContextMapV1,
    KnowledgeLinkV1,
    KnowledgeRecordV1,
)
from venom_core.memory.lessons_store import LessonsStore


def read_session_records(
    session_id: str, session_store: Any
) -> list[KnowledgeRecordV1]:
    records: list[KnowledgeRecordV1] = []
    history = session_store.get_history(session_id) if session_store else []
    for entry in history or []:
        if isinstance(entry, dict):
            records.append(from_session_store_entry(session_id, entry))

    if session_store and hasattr(session_store, "get_summary_entry"):
        summary_entry = session_store.get_summary_entry(session_id)
        if isinstance(summary_entry, dict):
            summary_record = {
                "role": "summary",
                "content": summary_entry.get("content"),
                "session_id": session_id,
                "request_id": summary_entry.get("request_id"),
                "timestamp": summary_entry.get("timestamp")
                or datetime.now(timezone.utc).isoformat(),
                "knowledge_metadata": summary_entry.get("knowledge_metadata") or {},
            }
            records.append(from_session_store_entry(session_id, summary_record))
    return records


def read_lesson_records(
    lessons_store: LessonsStore,
    session_id: str,
    related_task_ids: set[str],
    limit: int,
) -> list[KnowledgeRecordV1]:
    records: list[KnowledgeRecordV1] = []
    all_lessons = lessons_store.get_all_lessons(limit=limit)
    for lesson in all_lessons:
        lesson_record = from_lesson(lesson)
        lesson_session_id = lesson_record.session_id
        lesson_task_id = lesson_record.task_id
        if lesson_session_id == session_id or (
            lesson_task_id and lesson_task_id in related_task_ids
        ):
            records.append(lesson_record)
    return records


def read_memory_records(
    vector_store: Any, session_id: str, limit: int
) -> list[KnowledgeRecordV1]:
    entries = vector_store.list_entries(
        limit=limit,
        metadata_filters={"session_id": session_id},
    )
    records: list[KnowledgeRecordV1] = []
    for entry in entries:
        if isinstance(entry, dict):
            records.append(from_vector_entry(entry))
    return records


def build_context_links(
    session_id: str,
    records: list[KnowledgeRecordV1],
    related_task_ids: set[str],
) -> list[KnowledgeLinkV1]:
    links: list[KnowledgeLinkV1] = []
    session_node = f"session:{session_id}"
    for record in records:
        if record.kind.value == "lesson":
            if record.session_id == session_id:
                links.append(
                    KnowledgeLinkV1(
                        relation="session->lesson",
                        source_id=session_node,
                        target_id=record.record_id,
                    )
                )
            if record.task_id and record.task_id in related_task_ids:
                links.append(
                    KnowledgeLinkV1(
                        relation="task->lesson",
                        source_id=f"task:{record.task_id}",
                        target_id=record.record_id,
                    )
                )
        if record.kind.value == "memory_entry" and record.session_id == session_id:
            links.append(
                KnowledgeLinkV1(
                    relation="session->memory_entry",
                    source_id=session_node,
                    target_id=record.record_id,
                )
            )
    return links


def build_knowledge_context_map(
    *,
    session_id: str,
    session_store: Any,
    lessons_store: LessonsStore,
    vector_store: Any,
    limit: int,
) -> KnowledgeContextMapV1:
    session_records = read_session_records(session_id, session_store)
    related_task_ids = {
        rec.task_id for rec in session_records if rec.task_id and rec.task_id.strip()
    }
    lesson_records = read_lesson_records(
        lessons_store=lessons_store,
        session_id=session_id,
        related_task_ids=related_task_ids,
        limit=limit,
    )
    memory_records = read_memory_records(vector_store, session_id, limit)
    records = session_records + lesson_records + memory_records
    links = build_context_links(session_id, records, related_task_ids)
    return KnowledgeContextMapV1(session_id=session_id, records=records, links=links)
