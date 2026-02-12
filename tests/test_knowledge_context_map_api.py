from pathlib import Path

from fastapi.testclient import TestClient

from venom_core.api.dependencies import (
    get_lessons_store,
    get_session_store,
    get_vector_store,
)
from venom_core.main import app
from venom_core.memory.lessons_store import Lesson, LessonsStore
from venom_core.services.session_store import SessionStore


class DummyVectorStore:
    def __init__(self) -> None:
        self.entries: list[dict] = []

    def upsert(
        self,
        text,
        metadata=None,
        collection_name=None,
        chunk_text=True,
        id_override=None,
    ):
        self.entries.append(
            {
                "id": id_override or f"id-{len(self.entries) + 1}",
                "text": text,
                "metadata": metadata or {},
                "collection": collection_name or "default",
            }
        )
        return {"message": "ok", "chunks_count": 1}

    def list_entries(
        self, limit=200, metadata_filters=None, collection_name=None, entry_id=None
    ):
        del collection_name
        filtered = []
        for entry in self.entries:
            if entry_id and entry["id"] != entry_id:
                continue
            ok = True
            for key, value in (metadata_filters or {}).items():
                if entry["metadata"].get(key) != value:
                    ok = False
                    break
            if ok:
                filtered.append(entry)
        return filtered[:limit]


def _build_client(
    tmp_path: Path,
) -> tuple[TestClient, DummyVectorStore, LessonsStore, SessionStore]:
    vector_store = DummyVectorStore()
    lessons_store = LessonsStore(
        storage_path=str(tmp_path / "lessons.json"),
        vector_store=None,
        auto_save=True,
    )
    session_store = SessionStore(store_path=str(tmp_path / "session_store.json"))

    app.dependency_overrides[get_vector_store] = lambda: vector_store
    app.dependency_overrides[get_lessons_store] = lambda: lessons_store
    app.dependency_overrides[get_session_store] = lambda: session_store
    client = TestClient(app)
    return client, vector_store, lessons_store, session_store


def test_memory_ingest_stores_contract_metadata(tmp_path: Path):
    client, vector_store, _, _ = _build_client(tmp_path)
    try:
        response = client.post(
            "/api/v1/memory/ingest",
            json={
                "text": "abc",
                "category": "test",
                "session_id": "s1",
                "scope": "session",
            },
        )
        assert response.status_code == 201
        assert vector_store.entries
        metadata = vector_store.entries[0]["metadata"]
        assert metadata["knowledge_contract_version"] == "v1"
        assert metadata["provenance_source"] == "vector_store"
        assert metadata["retention_scope"] == "session"
    finally:
        client.close()
        app.dependency_overrides = {}


def test_knowledge_context_map_returns_session_lesson_and_memory(tmp_path: Path):
    client, vector_store, lessons_store, session_store = _build_client(tmp_path)
    try:
        session_store.append_message(
            "sess-1",
            {
                "role": "user",
                "content": "hello",
                "request_id": "task-1",
                "timestamp": "2026-02-12T00:00:00+00:00",
            },
        )
        session_store.set_summary("sess-1", "summary")

        lesson = Lesson(
            situation="s",
            action="a",
            result="r",
            feedback="f",
            metadata={"session_id": "sess-1", "task_id": "task-1"},
        )
        lessons_store.add_lesson(lesson)

        vector_store.upsert(
            text="memory for session",
            metadata={"session_id": "sess-1", "provenance_source": "vector_store"},
            collection_name="default",
        )

        response = client.get("/api/v1/knowledge/context-map/sess-1")
        assert response.status_code == 200
        payload = response.json()
        assert payload["session_id"] == "sess-1"
        assert len(payload["records"]) >= 3
        relations = {link["relation"] for link in payload["links"]}
        assert "session->lesson" in relations
        assert "session->memory_entry" in relations
    finally:
        client.close()
        app.dependency_overrides = {}
