from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from venom_core.api.dependencies import (
    get_lessons_store,
    get_session_store,
    get_state_manager,
    get_vector_store,
)
from venom_core.main import app

# Refactored to use FakeVectorStore from conftest
# Not importing lancedb anymore!


@pytest.fixture
def client(mock_lifespan_deps):
    # overrides
    fake_vs = mock_lifespan_deps["vector_store"]
    mock_ls = mock_lifespan_deps["lessons_store"]

    app.dependency_overrides[get_vector_store] = lambda: fake_vs
    app.dependency_overrides[get_lessons_store] = lambda: mock_ls

    mock_session_store = MagicMock()
    mock_session_store.get_history.return_value = []
    mock_session_store.get_summary.return_value = "Mock summary"

    mock_state_manager = MagicMock()
    mock_state_manager.clear_session_context.return_value = 0

    app.dependency_overrides[get_session_store] = lambda: mock_session_store
    app.dependency_overrides[get_state_manager] = lambda: mock_state_manager

    with TestClient(app) as c:
        yield c

    app.dependency_overrides = {}


def test_new_chat_session_clearing_workflow(client):
    """
    Testuje pełny workflow czyszczenia sesji z użyciem FakeVectorStore.
    """
    session_id = "test-session-123"
    test_text = "Tajny protokół: Antigravity jest super agentem."

    # 1. Ingestion danych dla sesji
    ingest_resp = client.post(
        "/api/v1/memory/ingest",
        json={"text": test_text, "session_id": session_id, "collection": "default"},
    )
    assert ingest_resp.status_code == 201
    assert ingest_resp.json()["status"] == "success"

    # 2. Weryfikacja obecności w grafie pamięci
    graph_resp = client.get("/api/v1/memory/graph", params={"session_id": session_id})
    assert graph_resp.status_code == 200
    elements = graph_resp.json()["elements"]

    session_nodes = [
        n for n in elements["nodes"] if n["data"].get("session_id") == session_id
    ]
    assert len(session_nodes) > 0, (
        f"Nie znaleziono danych dla sesji {session_id} w grafie"
    )

    # 3. Wywołanie czyszczenia sesji
    delete_resp = client.delete(f"/api/v1/memory/session/{session_id}")
    assert delete_resp.status_code == 200
    data = delete_resp.json()
    assert data["status"] == "success"
    assert data["session_id"] == session_id
    assert data["deleted_vectors"] > 0
    assert "cleared_tasks" in data

    # 4. Weryfikacja usunięcia z wektorowej bazy (przez graph API)
    graph_resp_post = client.get(
        "/api/v1/memory/graph", params={"session_id": session_id}
    )
    assert graph_resp_post.status_code == 200
    elements_post = graph_resp_post.json()["elements"]

    # Should be empty now
    session_nodes_post = [
        n for n in elements_post["nodes"] if n["data"].get("session_id") == session_id
    ]
    assert len(session_nodes_post) == 0, (
        f"Dane dla sesji {session_id} nadal istnieją w grafie po usunięciu"
    )

    # 5. Weryfikacja SessionStore
    session_resp = client.get(f"/api/v1/memory/session/{session_id}")
    if session_resp.status_code == 200:
        assert session_resp.json()["count"] == 0
        assert session_resp.json()["history"] == []


def test_new_chat_session_dependency_overrides(client):
    """
    Testuje użycie dependency_overrides z MagicMock, aby upewnić się, że mechanizm override'ów działa.
    Ten test nadpisuje globalnego clienta swoim własnym overridem dla tego konkretnego test case.
    """
    mock_vector_store = MagicMock()
    mock_vector_store.delete_by_metadata.return_value = 10
    mock_vector_store.delete_session.return_value = 5

    # Nadpiszmy override, który dał fixtura 'client'
    app.dependency_overrides[get_vector_store] = lambda: mock_vector_store

    try:
        session_id = "mock-session"
        resp = client.delete(f"/api/v1/memory/session/{session_id}")

        assert resp.status_code == 200
        assert resp.json()["deleted_vectors"] == 15  # 10 + 5
        mock_vector_store.delete_by_metadata.assert_called_once_with(
            {"session_id": session_id}
        )
    finally:
        pass
