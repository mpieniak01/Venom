from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from venom_core.services.knowledge_context_service import build_knowledge_context_map


@dataclass
class _Lesson:
    situation: str = "s"
    action: str = "a"
    result: str = "r"
    feedback: str = "f"
    metadata: dict[str, object] | None = None


class _LessonsStore:
    def __init__(self, lessons):
        self._lessons = lessons

    def get_all_lessons(self, limit: int):
        return self._lessons[:limit]


class _VectorStore:
    def list_entries(
        self, limit: int, metadata_filters: dict[str, object]
    ) -> list[dict[str, object]]:
        session_id = metadata_filters.get("session_id")
        return [
            {
                "id": "m1",
                "text": "memory",
                "metadata": {
                    "session_id": session_id,
                    "provenance_source": "vector_store",
                },
            }
        ][:limit]


def test_build_knowledge_context_map_includes_session_lesson_memory() -> None:
    session_store = SimpleNamespace(
        get_history=lambda _sid: [
            {
                "role": "user",
                "content": "hello",
                "request_id": "task-1",
                "timestamp": "2026-01-01T00:00:00+00:00",
            }
        ],
        get_summary_entry=lambda _sid: {
            "content": "summary",
            "request_id": "task-1",
            "timestamp": "2026-01-01T00:00:01+00:00",
            "knowledge_metadata": {},
        },
    )
    lessons_store = _LessonsStore(
        [
            _Lesson(metadata={"session_id": "sess-1", "task_id": "task-1"}),
            _Lesson(metadata={"session_id": "other", "task_id": "task-2"}),
        ]
    )
    vector_store = _VectorStore()

    payload = build_knowledge_context_map(
        session_id="sess-1",
        session_store=session_store,
        lessons_store=lessons_store,
        vector_store=vector_store,
        limit=20,
    )

    relations = {link.relation for link in payload.links}
    assert payload.session_id == "sess-1"
    assert "session->lesson" in relations
    assert "session->memory_entry" in relations
