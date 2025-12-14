"""Testy API dla endpointów pamięci wektorowej."""

import pytest
from fastapi.testclient import TestClient

# Testy będą działać tylko jeśli dependencies są zainstalowane
pytest.importorskip("lancedb")
pytest.importorskip("sentence_transformers", exc_type=ImportError)

from venom_core.main import app


@pytest.fixture
def client():
    """Fixture dla klienta testowego FastAPI."""
    return TestClient(app)


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
        assert data["chunks_count"] > 1  # Powinno być podzielone na fragmenty

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
            data="not a json",
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
        assert len(data["results"]) > 0

        # Sprawdź czy wynik zawiera słowo "Python"
        results_text = " ".join([r["text"] for r in data["results"]])
        assert "Python" in results_text or "python" in results_text.lower()

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
        response = client.post(
            "/api/v1/memory/search",
            json={"query": "informacja", "limit": 2, "collection": "limit_test"},
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

        # Krok 2: Wyszukaj informację o FastAPI
        response = client.post(
            "/api/v1/memory/search",
            json={"query": "framework webowy", "limit": 3, "collection": collection},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["count"] > 0

        # Sprawdź czy znalazł informację o FastAPI
        results_text = " ".join([r["text"] for r in data["results"]])
        assert "FastAPI" in results_text

        # Krok 3: Wyszukaj informację o bazie danych
        response = client.post(
            "/api/v1/memory/search",
            json={"query": "baza danych", "limit": 3, "collection": collection},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["count"] > 0

        # Sprawdź czy znalazł informację o LanceDB
        results_text = " ".join([r["text"] for r in data["results"]])
        assert "LanceDB" in results_text

    def test_persistence_simulation(self, client):
        """Test persystencji danych (symulowany restart przez nową kolekcję)."""
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
