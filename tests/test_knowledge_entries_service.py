from __future__ import annotations

from venom_core.api.schemas.knowledge import KnowledgeEntryScope, KnowledgeSourceOrigin
from venom_core.services.knowledge_entries_service import (
    KnowledgeEntriesQuery,
    list_federated_knowledge_entries,
)
from venom_core.services.session_store import SessionStore


class _VectorStore:
    def list_entries(
        self, limit=200, metadata_filters=None, collection_name=None, entry_id=None
    ):
        del collection_name, entry_id
        entry = {
            "id": "vec-1",
            "text": "v-text",
            "metadata": {"session_id": "s-1", "retention_scope": "session"},
        }
        if metadata_filters and metadata_filters.get("session_id") != "s-1":
            return []
        return [entry][:limit]


class _Lesson:
    def to_dict(self):
        return {
            "lesson_id": "lesson-1",
            "timestamp": "2026-03-01T10:00:00+00:00",
            "situation": "s",
            "action": "a",
            "result": "r",
            "feedback": "f",
            "tags": ["ops"],
            "metadata": {"session_id": "s-1", "task_id": "req-1"},
        }


class _LessonsStore:
    def get_all_lessons(self, limit=None):
        del limit
        return [_Lesson()]


class _GraphStore:
    def get_graph_summary(self):
        return {"total_nodes": 5, "total_edges": 7}


def test_list_federated_knowledge_entries_contains_graph_and_respects_scope(tmp_path):
    session_store = SessionStore(store_path=str(tmp_path / "session_store.json"))
    session_store.append_message(
        "s-1",
        {
            "role": "user",
            "content": "hello",
            "request_id": "req-1",
            "timestamp": "2026-03-01T09:00:00+00:00",
        },
    )
    entries = list_federated_knowledge_entries(
        session_store=session_store,
        lessons_store=_LessonsStore(),
        vector_store=_VectorStore(),
        graph_store=_GraphStore(),
        query=KnowledgeEntriesQuery(limit=20),
    )
    origins = {entry.source_meta.origin for entry in entries}
    assert KnowledgeSourceOrigin.SESSION in origins
    assert KnowledgeSourceOrigin.LESSON in origins
    assert KnowledgeSourceOrigin.VECTOR in origins
    assert KnowledgeSourceOrigin.GRAPH in origins


def test_list_federated_knowledge_entries_filter_scope_task(tmp_path):
    session_store = SessionStore(store_path=str(tmp_path / "session_store.json"))
    entries = list_federated_knowledge_entries(
        session_store=session_store,
        lessons_store=_LessonsStore(),
        vector_store=_VectorStore(),
        graph_store=_GraphStore(),
        query=KnowledgeEntriesQuery(scope=KnowledgeEntryScope.TASK, limit=20),
    )
    assert entries
    assert all(entry.scope == KnowledgeEntryScope.TASK for entry in entries)
