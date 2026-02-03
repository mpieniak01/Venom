"""Testy API dla endpointów pamięci wektorowej."""

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

# Not importing lancedb anymore!


@pytest.fixture
def client(mock_lifespan_deps):
    """Fixture dla klienta testowego FastAPI z mockami."""

    # Używamy instancji z mock_lifespan_deps
    fake_vs = mock_lifespan_deps["vector_store"]
    mock_ls = mock_lifespan_deps["lessons_store"]

    # Ważne: override'y dependency injection w FastAPI (dla endpointów)
    app.dependency_overrides[get_vector_store] = lambda: fake_vs
    app.dependency_overrides[get_lessons_store] = lambda: mock_ls

    mock_session_store = MagicMock()
    mock_session_store.get_history.return_value = []
    mock_session_store.get_summary.return_value = "Mock summary"

    mock_state_manager = MagicMock()
    mock_state_manager.clear_session_context.return_value = 0
    # Create task needs to return a dummy
    mock_task = MagicMock()
    mock_task.id = "mock-task-id"
    mock_state_manager.create_task.return_value = mock_task
    mock_state_manager._tasks = {}

    app.dependency_overrides[get_session_store] = lambda: mock_session_store
    app.dependency_overrides[get_state_manager] = lambda: mock_state_manager

    with TestClient(app) as c:
        yield c

    app.dependency_overrides = {}


class TestMemoryIngestAPI:
    """Testy dla endpointu /api/v1/memory/ingest."""

    def test_ingest_simple_text(self, client):
        """Test zapisywania prostego tekstu przez API."""
        response = client.post(
            "/api/v1/memory/ingest",
            json={
                "text": "To jest testowa informacja do zapamiętania",
                "category": "test",
                "collection": "test_collection",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "success"
        assert "chunks_count" in data
        assert data["chunks_count"] >= 1
        assert "message" in data

    def test_ingest_long_text_chunks(self, client):
        """Test zapisywania długiego tekstu (chunking)."""
        long_text = "To jest bardzo długi tekst testowy. " * 100  # ~4000 znaków

        response = client.post(
            "/api/v1/memory/ingest",
            json={
                "text": long_text,
                "category": "test",
                "collection": "test_collection",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "success"
        # FakeVectorStore returns 1
        assert data["chunks_count"] >= 1

    def test_ingest_empty_text(self, client):
        """Test próby zapisania pustego tekstu."""
        response = client.post(
            "/api/v1/memory/ingest",
            json={"text": "", "category": "test", "collection": "test_collection"},
        )

        assert response.status_code == 400
        assert "pusty" in response.json()["detail"].lower()

    def test_ingest_whitespace_only(self, client):
        """Test próby zapisania tekstu składającego się tylko ze spacji."""
        response = client.post(
            "/api/v1/memory/ingest",
            json={
                "text": "   \n\t  ",
                "category": "test",
                "collection": "test_collection",
            },
        )

        assert response.status_code == 400

    def test_ingest_default_collection(self, client):
        """Test zapisywania do domyślnej kolekcji."""
        response = client.post(
            "/api/v1/memory/ingest",
            json={"text": "Test domyślnej kolekcji", "category": "test"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "success"

    def test_ingest_default_category(self, client):
        """Test zapisywania z domyślną kategorią."""
        response = client.post(
            "/api/v1/memory/ingest", json={"text": "Test domyślnej kategorii"}
        )

        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "success"

    def test_ingest_missing_text_field(self, client):
        """Test próby ingestion bez pola text."""
        response = client.post("/api/v1/memory/ingest", json={"category": "test"})

        assert response.status_code == 422  # Validation error

    def test_ingest_invalid_json(self, client):
        """Test z niepoprawnym JSON."""
        response = client.post(
            "/api/v1/memory/ingest",
            content="not a json",
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 422


class TestMemorySearchAPI:
    """Testy dla endpointu /api/v1/memory/search."""

    def test_search_after_ingest(self, client):
        """Test wyszukiwania po wcześniejszym zapisie."""
        # Najpierw zapisz dane
        client.post(
            "/api/v1/memory/ingest",
            json={
                "text": "Python jest językiem programowania używanym w projekcie Venom",
                "category": "technical",
                "collection": "search_test",
            },
        )

        # Następnie wyszukaj
        # Note: FakeVectorStore has basic substring search
        response = client.post(
            "/api/v1/memory/search",
            json={
                "query": "Jaki język programowania używamy?",
                "limit": 3,
                "collection": "search_test",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "results" in data
        assert "count" in data

    def test_search_after_ingest_fake_friendly(self, client):
        # Replaces test_search_after_ingest but with substring friendly query
        client.post(
            "/api/v1/memory/ingest",
            json={
                "text": "Python jest językiem programowania używanym w projekcie Venom",
                "category": "technical",
                "collection": "search_test",
            },
        )
        response = client.post(
            "/api/v1/memory/search",
            json={
                "query": "Python",  # direct match
                "limit": 3,
                "collection": "search_test",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) > 0

    def test_search_empty_query(self, client):
        """Test próby wyszukiwania z pustym zapytaniem."""
        response = client.post(
            "/api/v1/memory/search",
            json={"query": "", "limit": 3, "collection": "test_collection"},
        )

        assert response.status_code == 400
        assert "pusty" in response.json()["detail"].lower()

    def test_search_nonexistent_collection(self, client):
        """Test wyszukiwania w nieistniejącej kolekcji."""
        response = client.post(
            "/api/v1/memory/search",
            json={
                "query": "test query",
                "limit": 3,
                "collection": "nonexistent_collection_xyz",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["count"] == 0
        assert len(data["results"]) == 0

    def test_search_with_limit(self, client):
        """Test wyszukiwania z limitem wyników."""
        # Zapisz kilka różnych informacji
        for i in range(5):
            client.post(
                "/api/v1/memory/ingest",
                json={
                    "text": f"Informacja testowa numer {i}",
                    "category": "test",
                    "collection": "limit_test",
                },
            )

        # Wyszukaj z limitem 2
        # Use query matching all
        response = client.post(
            "/api/v1/memory/search",
            json={"query": "Informacja", "limit": 2, "collection": "limit_test"},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) <= 2

    def test_search_default_limit(self, client):
        """Test wyszukiwania z domyślnym limitem."""
        response = client.post("/api/v1/memory/search", json={"query": "test query"})

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_search_missing_query_field(self, client):
        """Test próby wyszukiwania bez pola query."""
        response = client.post("/api/v1/memory/search", json={"limit": 3})

        assert response.status_code == 422  # Validation error

    def test_search_result_structure(self, client):
        """Test struktury wyniku wyszukiwania."""
        # Zapisz dane
        client.post(
            "/api/v1/memory/ingest",
            json={
                "text": "Test struktury wyniku",
                "category": "test_category",
                "collection": "structure_test",
            },
        )

        # Wyszukaj
        response = client.post(
            "/api/v1/memory/search",
            json={"query": "struktura", "limit": 1, "collection": "structure_test"},
        )

        assert response.status_code == 200
        data = response.json()

        # Sprawdź strukturę odpowiedzi
        assert "status" in data
        assert "query" in data
        assert "results" in data
        assert "count" in data

        # Jeśli są wyniki, sprawdź ich strukturę
        if len(data["results"]) > 0:
            result = data["results"][0]
            assert "text" in result
            assert "metadata" in result
            assert "score" in result


class TestMemoryAPIIntegration:
    """Testy integracyjne workflow ingest → search."""

    def test_full_workflow(self, client):
        """Test pełnego workflow: zapis → wyszukiwanie → weryfikacja."""
        collection = "integration_test"

        # Krok 1: Zapisz kilka informacji
        texts = [
            "FastAPI jest frameworkiem webowym dla Pythona",
            "Venom używa LanceDB jako bazy wektorowej",
            "Semantic Kernel to framework dla AI agentów",
        ]

        for text in texts:
            response = client.post(
                "/api/v1/memory/ingest",
                json={
                    "text": text,
                    "category": "documentation",
                    "collection": collection,
                },
            )
            assert response.status_code == 201

        # Krok 2: Wyszukaj informację o FastAPI (Substring match)
        response = client.post(
            "/api/v1/memory/search",
            json={"query": "FastAPI", "limit": 3, "collection": collection},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["count"] > 0

        # Sprawdź czy znalazł informację o FastAPI
        results_text = " ".join([r["text"] for r in data["results"]])
        assert "FastAPI" in results_text

        # Krok 3: Wyszukaj informację o bazie danych (Substring match need adjustment for Fake)
        # "Venom używa LanceDB..." query "baza danych" -> FAIL on Fake (no semantic).
        # Adjust query to "LanceDB"
        response = client.post(
            "/api/v1/memory/search",
            json={"query": "LanceDB", "limit": 3, "collection": collection},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["count"] > 0

        # Sprawdź czy znalazł informację o LanceDB
        results_text = " ".join([r["text"] for r in data["results"]])
        assert "LanceDB" in results_text

    def test_persistence_simulation(self, client):
        """Test persystencji danych (symulowany restart przez nową kolekcję)."""
        # With fake vector store, persistence is just memory. This tests logic correctness.
        collection = "persistence_test"
        test_text = "Informacja która powinna przetrwać"

        # Zapisz
        response = client.post(
            "/api/v1/memory/ingest",
            json={"text": test_text, "collection": collection},
        )
        assert response.status_code == 201

        # Wyszukaj natychmiast
        response = client.post(
            "/api/v1/memory/search",
            json={"query": "przetrwać", "collection": collection},
        )
        assert response.status_code == 200
        assert response.json()["count"] > 0

        # Wyszukaj ponownie (symulacja po "restarcie")
        response = client.post(
            "/api/v1/memory/search",
            json={"query": "informacja przetrwać", "collection": collection},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["count"] > 0
        assert any("przetrwać" in r["text"] for r in data["results"])


class TestMemoryCleanupAPI:
    """Testy czyszczenia pamięci sesyjnej i globalnej."""

    def test_clear_session_memory(self, client, mock_lifespan_deps):
        """Powinno usunąć wpisy z wektorów i kontekst w StateManagerze."""
        # Note: client fixture already configured overrides.
        fake_vector_store = mock_lifespan_deps["vector_store"]

        session_id = "test-session-clean"

        # Populate Fake
        fake_vector_store.upsert(
            text="Fakt do usunięcia",
            metadata={"session_id": session_id, "user_id": "user_default"},
        )

        response = client.delete(f"/api/v1/memory/session/{session_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["deleted_vectors"] >= 1
        # cleared_tasks depends on state_manager mock return value
        assert data["cleared_tasks"] == 0  # Mock returns 0

    def test_clear_global_memory(self, client, mock_lifespan_deps):
        """Powinno czyścić globalne fakty/preferencje."""
        fake_vector_store = mock_lifespan_deps["vector_store"]
        fake_vector_store.upsert(
            text="Globalny wpis",
            metadata={"user_id": "user_default", "type": "preference"},
        )
        response = client.delete("/api/v1/memory/global")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["deleted_vectors"] >= 1


class TestMemoryGraphAPI:
    """Testy dla /api/v1/memory/graph (fakty + lekcje)."""

    def test_graph_filters_and_lessons(self, client, mock_lifespan_deps):
        """Powinno filtrować po session_id/pinned oraz dołączać lekcje na żądanie."""
        fake_vector_store = mock_lifespan_deps["vector_store"]
        # Prepopulate
        fake_vector_store.upsert(
            text="pinned fact",
            metadata={
                "session_id": "s1",
                "user_id": "user_default",
                "pinned": True,
                "type": "fact",
            },
            id_override="mem-pinned",
            chunk_text=False,
        )
        fake_vector_store.upsert(
            text="other fact",
            metadata={"session_id": "s2", "user_id": "user_default"},
            id_override="mem-other",
            chunk_text=False,
        )

        # Override lessons store for this test
        from types import SimpleNamespace

        lessons_mock = SimpleNamespace(
            lessons={
                "lesson-1": SimpleNamespace(
                    title="Lekcja 1",
                    tags=["tag1"],
                    timestamp="2025-01-01T00:00:00",
                )
            }
        )
        # Override the override...
        app.dependency_overrides[get_lessons_store] = lambda: lessons_mock

        try:
            resp = client.get(
                "/api/v1/memory/graph",
                params={"limit": 50, "session_id": "s1", "only_pinned": True},
            )
            assert resp.status_code == 200
            data = resp.json()
            node_ids = {n["data"]["id"] for n in data["elements"]["nodes"]}
            assert "mem-pinned" in node_ids
            assert "mem-other" not in node_ids
            assert not any(
                n["data"]["id"].startswith("lesson:") for n in data["elements"]["nodes"]
            )

            resp_with_lessons = client.get(
                "/api/v1/memory/graph",
                params={
                    "limit": 50,
                    "session_id": "s1",
                    "only_pinned": True,
                    "include_lessons": True,
                },
            )
            assert resp_with_lessons.status_code == 200
            data_with_lessons = resp_with_lessons.json()
            lesson_ids = {
                n["data"]["id"] for n in data_with_lessons["elements"]["nodes"]
            }
            assert "lesson:lesson-1" in lesson_ids

        finally:
            pass
