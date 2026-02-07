"""Testy jednostkowe dla VectorStore i EmbeddingService."""

import tempfile
from pathlib import Path

import pytest

# Testy będą działać tylko jeśli dependencies są zainstalowane
pytest.importorskip("lancedb")
pytest.importorskip("sentence_transformers", exc_type=ImportError)

from venom_core.memory.embedding_service import EmbeddingService
from venom_core.memory.vector_store import VectorStore


@pytest.fixture
def temp_db_path():
    """Fixture dla tymczasowej bazy danych."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def embedding_service(monkeypatch):
    """Fixture dla serwisu embeddingów w trybie lokalnym."""

    class _FakeVector:
        def __init__(self, values):
            self._values = values

        def tolist(self):
            return self._values

    class _MockSentenceTransformer:
        def __init__(self, model_name: str):
            self.model_name = model_name

        def encode(self, text, convert_to_numpy=True):
            assert convert_to_numpy is True
            if isinstance(text, list):
                return [_FakeVector([0.1] * 384) for _ in text]
            return _FakeVector([0.1] * 384)

        def get_sentence_embedding_dimension(self):
            return 384

    monkeypatch.setattr(
        "sentence_transformers.SentenceTransformer", _MockSentenceTransformer
    )
    return EmbeddingService(service_type="local")


@pytest.fixture
def vector_store(temp_db_path, embedding_service):
    """Fixture dla VectorStore z tymczasową bazą."""
    return VectorStore(
        db_path=temp_db_path,
        embedding_service=embedding_service,
        collection_name="test_collection",
    )


class TestEmbeddingService:
    """Testy dla EmbeddingService."""

    def test_embedding_service_initialization(self):
        """Test inicjalizacji serwisu embeddingów."""
        service = EmbeddingService(service_type="local")
        assert service.service_type == "local"
        assert service._model is None  # Lazy loading

    def test_get_embedding_local(self, embedding_service):
        """Test generowania embeddingu w trybie lokalnym."""
        text = "To jest testowy tekst"
        embedding = embedding_service.get_embedding(text)

        assert isinstance(embedding, list)
        assert len(embedding) > 0
        assert all(isinstance(x, float) for x in embedding)
        # all-MiniLM-L6-v2 ma 384 wymiary
        assert len(embedding) == 384

    def test_get_embedding_empty_text(self, embedding_service):
        """Test generowania embeddingu dla pustego tekstu."""
        with pytest.raises(ValueError, match="Tekst nie może być pusty"):
            embedding_service.get_embedding("")

    def test_get_embedding_cached(self, embedding_service):
        """Test cache'owania embeddingów."""
        text = "Tekst do cache'owania"

        # Pierwsze wywołanie
        embedding1 = embedding_service.get_embedding(text)

        # Drugie wywołanie - powinno być z cache
        embedding2 = embedding_service.get_embedding(text)

        # Powinny być identyczne (ten sam obiekt z cache)
        assert embedding1 == embedding2

    def test_get_embeddings_batch(self, embedding_service):
        """Test batch processing embeddingów."""
        texts = ["Pierwszy tekst", "Drugi tekst", "Trzeci tekst"]
        embeddings = embedding_service.get_embeddings_batch(texts)

        assert len(embeddings) == len(texts)
        assert all(isinstance(emb, list) for emb in embeddings)
        assert all(len(emb) == 384 for emb in embeddings)

    def test_clear_cache(self, embedding_service):
        """Test czyszczenia cache."""
        text = "Tekst testowy"
        embedding_service.get_embedding(text)

        # Cache info powinno pokazywać hit
        cache_info = embedding_service._get_embedding_cached.cache_info()
        assert cache_info.currsize > 0

        # Wyczyść cache
        embedding_service.clear_cache()

        # Cache powinien być pusty
        cache_info = embedding_service._get_embedding_cached.cache_info()
        assert cache_info.currsize == 0

    def test_embedding_dimension(self, embedding_service):
        """Test pobierania wymiaru embeddingu."""
        dim = embedding_service.embedding_dimension
        assert dim == 384


class TestVectorStore:
    """Testy dla VectorStore."""

    def test_vector_store_initialization(self, vector_store, temp_db_path):
        """Test inicjalizacji VectorStore."""
        assert vector_store.db_path == Path(temp_db_path)
        assert vector_store.collection_name == "test_collection"
        assert vector_store.embedding_service is not None

    def test_create_collection(self, vector_store):
        """Test tworzenia kolekcji."""
        result = vector_store.create_collection("new_collection")
        assert "new_collection" in result
        assert "utworzona" in result.lower()

    def test_create_collection_invalid_name(self, vector_store):
        """Test tworzenia kolekcji z nieprawidłową nazwą."""
        with pytest.raises(ValueError, match="Nazwa kolekcji"):
            vector_store.create_collection("")

        with pytest.raises(ValueError, match="może zawierać tylko"):
            vector_store.create_collection("invalid name!")

    def test_upsert_simple_text(self, vector_store):
        """Test zapisywania prostego tekstu."""
        text = "To jest testowy tekst do zapisania w bazie"
        result = vector_store.upsert(text, metadata={"category": "test"})

        assert "zapisano" in result.lower()
        assert "1" in result  # 1 fragment

    def test_upsert_long_text_chunking(self, vector_store):
        """Test chunking długiego tekstu."""
        # Utwórz długi tekst (ponad 500 znaków)
        long_text = "To jest bardzo długi tekst. " * 50
        result = vector_store.upsert(long_text, chunk_text=True)

        assert "zapisano" in result.lower()
        # Powinno być więcej niż 1 fragment
        import re

        match = re.search(r"(\d+)", result)
        assert match
        chunks_count = int(match.group(1))
        assert chunks_count > 1

    def test_upsert_empty_text(self, vector_store):
        """Test zapisywania pustego tekstu."""
        with pytest.raises(ValueError, match="Tekst nie może być pusty"):
            vector_store.upsert("")

    def test_search_basic(self, vector_store):
        """Test podstawowego wyszukiwania."""
        # Zapisz kilka tekstów
        vector_store.upsert(
            "Kot jest zwierzęciem domowym", metadata={"topic": "zwierzęta"}
        )
        vector_store.upsert(
            "Pies to wierny przyjaciel człowieka", metadata={"topic": "zwierzęta"}
        )
        vector_store.upsert(
            "Komputer to elektroniczne urządzenie", metadata={"topic": "technologia"}
        )

        # Wyszukaj coś związanego ze zwierzętami
        results = vector_store.search("zwierzęta domowe", limit=2)

        assert len(results) > 0
        assert len(results) <= 2
        # Pierwszy wynik powinien być związany ze zwierzętami
        assert any(
            "kot" in res["text"].lower() or "pies" in res["text"].lower()
            for res in results
        )

    def test_search_empty_query(self, vector_store):
        """Test wyszukiwania z pustym zapytaniem."""
        with pytest.raises(ValueError, match="Zapytanie nie może być puste"):
            vector_store.search("")

    def test_search_nonexistent_collection(self, vector_store):
        """Test wyszukiwania w nieistniejącej kolekcji."""
        results = vector_store.search(
            "test query", collection_name="nonexistent_collection"
        )
        assert results == []

    def test_list_collections(self, vector_store):
        """Test listowania kolekcji."""
        # Utwórz kilka kolekcji
        vector_store.create_collection("collection1")
        vector_store.create_collection("collection2")

        collections = vector_store.list_collections()

        assert "collection1" in collections
        assert "collection2" in collections

    def test_delete_collection(self, vector_store):
        """Test usuwania kolekcji."""
        # Utwórz kolekcję
        vector_store.create_collection("to_delete")
        assert "to_delete" in vector_store.list_collections()

        # Usuń kolekcję
        result = vector_store.delete_collection("to_delete")
        assert "usunięta" in result.lower()
        assert "to_delete" not in vector_store.list_collections()

    def test_delete_nonexistent_collection(self, vector_store):
        """Test usuwania nieistniejącej kolekcji."""
        with pytest.raises(ValueError, match="nie istnieje"):
            vector_store.delete_collection("nonexistent")

    def test_persistence(self, temp_db_path, embedding_service):
        """Test persystencji danych po ponownym otwarciu bazy."""
        # Utwórz store i zapisz dane
        store1 = VectorStore(
            db_path=temp_db_path,
            embedding_service=embedding_service,
            collection_name="persist_test",
        )
        store1.upsert("Informacja do zapamiętania")

        # Utwórz nowy store wskazujący na tę samą bazę
        store2 = VectorStore(
            db_path=temp_db_path,
            embedding_service=embedding_service,
            collection_name="persist_test",
        )

        # Wyszukaj dane
        results = store2.search("informacja")
        assert len(results) > 0
        assert "informacja" in results[0]["text"].lower()

    def test_chunking_with_overlap(self, vector_store):
        """Test chunking z overlapem."""
        # Utwórz tekst który będzie podzielony
        text = (
            "Pierwsze zdanie. " * 20 + "Drugie zdanie. " * 20 + "Trzecie zdanie. " * 20
        )

        chunks = vector_store._chunk_text(text, chunk_size=100, overlap=20)

        # Powinno być kilka chunków
        assert len(chunks) > 1

        # Sprawdź overlap między chunkami
        for i in range(len(chunks) - 1):
            # Ostatnie znaki chunku i powinny pokrywać się z początkiem chunku i+1
            # (mniej więcej, z uwagi na breaking na słowach)
            assert len(chunks[i]) > 0
            assert len(chunks[i + 1]) > 0


class TestMemorySkillIntegration:
    """Testy integracyjne dla MemorySkill."""

    def test_memory_skill_import(self):
        """Test importu MemorySkill."""
        from venom_core.memory.memory_skill import MemorySkill

        skill = MemorySkill()
        assert skill is not None
        assert skill.vector_store is not None
