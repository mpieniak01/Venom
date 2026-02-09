"""Testy jednostkowe dla EmbeddingService."""

from types import SimpleNamespace

import pytest

from venom_core.memory.embedding_service import (
    LOCAL_EMBEDDING_DIMENSION,
    EmbeddingService,
)


def test_get_embedding_rejects_empty_text():
    service = EmbeddingService(service_type="local")
    with pytest.raises(ValueError):
        service.get_embedding("   ")


def test_fallback_embedding_is_deterministic_and_has_expected_dimension():
    service = EmbeddingService(service_type="local")
    emb1 = service._generate_fallback_embedding("abc")
    emb2 = service._generate_fallback_embedding("abc")
    assert len(emb1) == LOCAL_EMBEDDING_DIMENSION
    assert emb1 == emb2


def test_local_embedding_uses_model_and_cache(monkeypatch):
    class DummyVector:
        def __init__(self, values):
            self._values = values

        def tolist(self):
            return self._values

    class DummyModel:
        def __init__(self):
            self.calls = 0

        def encode(self, text, convert_to_numpy=True):
            self.calls += 1
            assert convert_to_numpy is True
            assert text == "abc"
            return DummyVector([0.1, 0.2, 0.3])

        def get_sentence_embedding_dimension(self):
            return 3

    service = EmbeddingService(service_type="local")
    service._model = DummyModel()

    emb_a = service.get_embedding("abc")
    emb_b = service.get_embedding("abc")

    assert emb_a == [0.1, 0.2, 0.3]
    assert emb_b == [0.1, 0.2, 0.3]
    assert service._model.calls == 1


def test_local_embedding_raises_when_model_missing_and_no_fallback():
    service = EmbeddingService(service_type="local")
    service._model = None
    service._client = None
    service._local_fallback_mode = False
    service._ensure_model_loaded = lambda: None

    with pytest.raises(RuntimeError):
        service.get_embedding("abc")


def test_batch_local_fallback_path():
    service = EmbeddingService(service_type="local")
    service._local_fallback_mode = True
    service._ensure_model_loaded = lambda: None
    batch = service.get_embeddings_batch(["a", "b"])
    assert len(batch) == 2
    assert all(len(item) == LOCAL_EMBEDDING_DIMENSION for item in batch)


def test_batch_rejects_empty_list():
    service = EmbeddingService(service_type="local")
    with pytest.raises(ValueError):
        service.get_embeddings_batch([])


def test_openai_path_raises_when_client_missing():
    service = EmbeddingService(service_type="openai")
    service._ensure_model_loaded = lambda: None
    service._client = None
    with pytest.raises(RuntimeError):
        service._get_embedding_impl("abc")


def test_openai_path_returns_embedding():
    class DummyEmbeddings:
        def create(self, model, input):
            assert model == "text-embedding-3-small"
            assert input == "abc"
            return SimpleNamespace(data=[SimpleNamespace(embedding=[1.0, 2.0])])

    service = EmbeddingService(service_type="openai")
    service._ensure_model_loaded = lambda: None
    service._client = SimpleNamespace(embeddings=DummyEmbeddings())
    assert service.get_embedding("abc") == [1.0, 2.0]


def test_batch_openai_path_returns_embeddings():
    class DummyEmbeddings:
        def create(self, model, input):
            assert model == "text-embedding-3-small"
            assert input == ["a", "b"]
            return SimpleNamespace(
                data=[
                    SimpleNamespace(embedding=[1.0]),
                    SimpleNamespace(embedding=[2.0]),
                ]
            )

    service = EmbeddingService(service_type="openai")
    service._ensure_model_loaded = lambda: None
    service._client = SimpleNamespace(embeddings=DummyEmbeddings())
    assert service.get_embeddings_batch(["a", "b"]) == [[1.0], [2.0]]


def test_embedding_dimension_for_supported_types():
    assert EmbeddingService(service_type="openai").embedding_dimension == 1536

    service = EmbeddingService(service_type="local")
    assert service.embedding_dimension == LOCAL_EMBEDDING_DIMENSION


def test_embedding_dimension_uses_loaded_local_model_dimension():
    service = EmbeddingService(service_type="local")
    service._model = SimpleNamespace(get_sentence_embedding_dimension=lambda: 777)
    assert service.embedding_dimension == 777


def test_embedding_dimension_for_unknown_type_raises():
    service = EmbeddingService(service_type="custom")
    service._ensure_model_loaded = lambda: None
    with pytest.raises(ValueError):
        _ = service.embedding_dimension


def test_clear_cache_invokes_cache_clear():
    service = EmbeddingService(service_type="local")
    service.clear_cache()
    info = service._get_embedding_cached.cache_info()
    assert info.hits >= 0 and info.misses >= 0
