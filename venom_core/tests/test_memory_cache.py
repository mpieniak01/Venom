from unittest.mock import patch

from fastapi.testclient import TestClient

from venom_core.core.orchestrator.constants import SEMANTIC_CACHE_COLLECTION_NAME
from venom_core.main import app

client = TestClient(app)


def test_flush_semantic_cache():
    # Patchujemy klasę VectorStore u źródła, bo w routes/memory jest importowana lokalnie
    with patch("venom_core.memory.vector_store.VectorStore") as MockVectorStore:
        # Konfiguracja mocka
        instance = MockVectorStore.return_value
        instance.wipe_collection.return_value = 5  # Simulujemy usunięcie 5 wpisów

        # Wywołanie endpointu
        response = client.delete("/api/v1/memory/cache/semantic")

        # Weryfikacja response
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["deleted"] == 5

        # Weryfikacja inizjalizacji VectorStore z dobrą kolekcją
        MockVectorStore.assert_called_with(
            collection_name=SEMANTIC_CACHE_COLLECTION_NAME
        )
        # Weryfikacja wywołania metody
        instance.wipe_collection.assert_called_once()
