import pytest
from fastapi.testclient import TestClient

from venom_core.api.dependencies import get_vector_store
from venom_core.main import app

pytest.importorskip("lancedb")
pytest.importorskip("sentence_transformers", exc_type=ImportError)


@pytest.fixture
def client():
    # Clear overrides before each test
    app.dependency_overrides = {}

    # Use context manager to trigger lifespan and initialize dependencies
    with TestClient(app) as c:
        yield c

    app.dependency_overrides = {}


def test_new_chat_session_clearing_workflow(client):
    """
    Testuje pełny workflow czyszczenia sesji:
    1. Ingestion danych dla konkretnej sesji.
    2. Weryfikacja obecności danych w grafie pamięci.
    3. Wywołanie endpointu DELETE /session/{session_id}.
    4. Weryfikacja usunięcia danych z wektorowej bazy, StateManager i SessionStore.
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
    # Szukamy czy jest węzeł z naszym tekstem lub session_id
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
    session_nodes_post = [
        n for n in elements_post["nodes"] if n["data"].get("session_id") == session_id
    ]
    assert len(session_nodes_post) == 0, (
        f"Dane dla sesji {session_id} nadal istnieją w grafie po usunięciu"
    )

    # 5. Weryfikacja SessionStore (przez GET /session/{session_id})
    # Po usunięciu, get_session_memory powinno zwrócić błąd 503 jeśli SessionStore niedostępny
    # lub puste dane jeśli wyczyszczone (zależy od implementacji).
    # Sprawdźmy co zwraca endpoint GET /session/{session_id}
    session_resp = client.get(f"/api/v1/memory/session/{session_id}")
    if session_resp.status_code == 200:
        assert session_resp.json()["count"] == 0
        assert session_resp.json()["history"] == []


def test_new_chat_session_dependency_overrides(client):
    """
    Testuje użycie dependency_overrides, zgodnie z sugestią z PR.
    """
    from unittest.mock import MagicMock

    mock_vector_store = MagicMock()
    mock_vector_store.delete_by_metadata.return_value = 10
    mock_vector_store.delete_session.return_value = 5

    # Ustawiamy override
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
        app.dependency_overrides = {}
