import pytest
from fastapi.testclient import TestClient

# Testy będą działać tylko jeśli dependencies są zainstalowane
pytest.importorskip("lancedb")
pytest.importorskip("sentence_transformers", exc_type=ImportError)

from venom_core.api.routes import memory as memory_routes
from venom_core.core.state_manager import StateManager
from venom_core.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_new_chat_session_clearing_workflow(client):
    """
    Test logic corresponding to 'New Chat' button:
    1. Populate session vectors.
    2. Populate session history in StateManager.
    3. Call DELETE /api/v1/memory/session/{id}.
    4. Verify cleanup.
    """
    session_id = "new-chat-test-session"
    vector_store = memory_routes._ensure_vector_store()
    state_manager = StateManager()
    memory_routes.set_dependencies(vector_store, state_manager)

    # 1. Ingest vector
    vector_store.upsert(
        text="Background context for new chat",
        metadata={"session_id": session_id, "user_id": "user_default"},
    )

    # 2. Add history to StateManager
    task = state_manager.create_task("Sample prompt for new chat")
    task.context_history = {
        "session": {"session_id": session_id},
        "session_history": [{"role": "user", "content": "Hello"}],
        "session_summary": "Active session",
    }

    # 3. Call the API (linked to New Chat button)
    response = client.delete(f"/api/v1/memory/session/{session_id}")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "success"
    assert data["cleared_tasks"] >= 1

    # 4. Verify History is cleared in StateManager
    # Note: StateManager is a singleton or managed by routes,
    # we verify via getting the task context.
    ctx = state_manager.get_task(task.id).context_history
    assert ctx["session_history"] == []
    assert ctx["session_summary"] is None

    # 5. Verify Vectors are cleared (optional but good)
    # Search should return 0 results for this session
    search_resp = client.post(
        "/api/v1/memory/search",
        json={"query": "chat", "collection": "default", "session_id": session_id},
    )
    # The search API filter by session_id might still find global if not careful,
    # but specifically for this session it should be empty if our logic works.
    search_data = search_resp.json()
    # Depending on implementation, it might return 0 or results without the session bits.
    # Our DELETE specifically removes where session_id == id.
    for res in search_data.get("results", []):
        assert res["metadata"].get("session_id") != session_id
