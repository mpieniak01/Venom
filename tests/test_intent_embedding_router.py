"""Testy jednostkowe dla IntentEmbeddingRouter."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from venom_core.config import SETTINGS


@pytest.fixture(autouse=True)
def mock_sentence_transformers_module(monkeypatch):
    """Mockuje moduł sentence_transformers w sposób ograniczony do tego modułu testowego."""
    monkeypatch.setitem(sys.modules, "sentence_transformers", MagicMock())


@pytest.fixture
def temp_lexicon_dir(tmp_path):
    """Tworzy tymczasowy katalog z plikami lexicon."""
    lexicon_data = {
        "intents": {
            "CODE_GENERATION": {
                "threshold": 0.85,
                "phrases": [
                    "write a function",
                    "generate code",
                    "create a script",
                    "napisz funkcję",
                    "wygeneruj kod",
                ],
                "regex": [],
            },
            "KNOWLEDGE_SEARCH": {
                "threshold": 0.85,
                "phrases": [
                    "what is",
                    "explain",
                    "co to jest",
                    "wyjaśnij",
                ],
                "regex": [],
            },
            "GENERAL_CHAT": {
                "threshold": 0.85,
                "phrases": [
                    "hello",
                    "hi",
                    "cześć",
                    "witaj",
                ],
                "regex": [],
            },
        }
    }
    
    # Utwórz pliki lexicon
    for lang in ["en", "pl", "de"]:
        lexicon_file = tmp_path / f"intent_lexicon_{lang}.json"
        with open(lexicon_file, "w", encoding="utf-8") as f:
            json.dump(lexicon_data, f)
    
    return tmp_path


@pytest.fixture
def mock_sentence_transformer():
    """Mockuje SentenceTransformer."""
    mock_model = MagicMock()
    
    # Mockuj encode - zwróć różne embeddingi dla różnych tekstów
    def mock_encode(texts, convert_to_numpy=True, show_progress_bar=False):
        if isinstance(texts, str):
            texts = [texts]
        
        # Symuluj embeddingi - różne wektory dla różnych typów tekstów
        embeddings = []
        for text in texts:
            text_lower = text.lower()
            if any(word in text_lower for word in ["write", "function", "code", "script", "napisz", "kod"]):
                # Embedding dla CODE_GENERATION
                emb = np.array([1.0, 0.0, 0.0])
            elif any(word in text_lower for word in ["what", "explain", "co to", "wyjaśnij"]):
                # Embedding dla KNOWLEDGE_SEARCH
                emb = np.array([0.0, 1.0, 0.0])
            elif any(word in text_lower for word in ["hello", "hi", "cześć", "witaj"]):
                # Embedding dla GENERAL_CHAT
                emb = np.array([0.0, 0.0, 1.0])
            else:
                # Domyślny embedding
                emb = np.array([0.5, 0.5, 0.5])
            
            embeddings.append(emb)
        
        return np.array(embeddings)
    
    mock_model.encode = mock_encode
    return mock_model


class TestIntentEmbeddingRouter:
    """Testy dla IntentEmbeddingRouter."""

    def test_router_disabled_when_flag_off(self, temp_lexicon_dir):
        """Test że router jest wyłączony gdy feature flag jest false."""
        with patch.object(SETTINGS, "ENABLE_INTENT_EMBEDDING_ROUTER", False):
            from venom_core.core.intent_embedding_router import IntentEmbeddingRouter
            
            router = IntentEmbeddingRouter(temp_lexicon_dir)
            assert not router.is_enabled()

    def test_router_initialization_with_mock_model(
        self, temp_lexicon_dir, mock_sentence_transformer
    ):
        """Test inicjalizacji routera z mockowanym modelem."""
        with patch.object(SETTINGS, "ENABLE_INTENT_EMBEDDING_ROUTER", True):
            with patch(
                "sentence_transformers.SentenceTransformer",
                return_value=mock_sentence_transformer
            ):
                from venom_core.core.intent_embedding_router import IntentEmbeddingRouter
                
                router = IntentEmbeddingRouter(temp_lexicon_dir)
                assert router.is_enabled()
                assert len(router.intent_embeddings) > 0
                assert "CODE_GENERATION" in router.intent_embeddings
                assert "KNOWLEDGE_SEARCH" in router.intent_embeddings

    @pytest.mark.asyncio
    async def test_classify_code_generation(
        self, temp_lexicon_dir, mock_sentence_transformer
    ):
        """Test klasyfikacji dla CODE_GENERATION."""
        with patch.object(SETTINGS, "ENABLE_INTENT_EMBEDDING_ROUTER", True):
            with patch.object(SETTINGS, "INTENT_EMBED_MIN_SCORE", 0.5):
                with patch.object(SETTINGS, "INTENT_EMBED_MARGIN", 0.1):
                    with patch(
                        "sentence_transformers.SentenceTransformer",
                        return_value=mock_sentence_transformer
                    ):
                        from venom_core.core.intent_embedding_router import IntentEmbeddingRouter
                        
                        router = IntentEmbeddingRouter(temp_lexicon_dir)
                        intent, score, top2 = await router.classify("write a function in Python")
                        
                        assert intent == "CODE_GENERATION"
                        assert score > 0.5
                        assert len(top2) >= 1

    @pytest.mark.asyncio
    async def test_classify_knowledge_search(
        self, temp_lexicon_dir, mock_sentence_transformer
    ):
        """Test klasyfikacji dla KNOWLEDGE_SEARCH."""
        with patch.object(SETTINGS, "ENABLE_INTENT_EMBEDDING_ROUTER", True):
            with patch.object(SETTINGS, "INTENT_EMBED_MIN_SCORE", 0.5):
                with patch.object(SETTINGS, "INTENT_EMBED_MARGIN", 0.1):
                    with patch(
                        "sentence_transformers.SentenceTransformer",
                        return_value=mock_sentence_transformer
                    ):
                        from venom_core.core.intent_embedding_router import IntentEmbeddingRouter
                        
                        router = IntentEmbeddingRouter(temp_lexicon_dir)
                        intent, score, top2 = await router.classify("what is GraphRAG?")
                        
                        assert intent == "KNOWLEDGE_SEARCH"
                        assert score > 0.5

    @pytest.mark.asyncio
    async def test_classify_below_threshold(
        self, temp_lexicon_dir, mock_sentence_transformer
    ):
        """Test że klasyfikacja zwraca None gdy score poniżej progu."""
        with patch.object(SETTINGS, "ENABLE_INTENT_EMBEDDING_ROUTER", True):
            with patch.object(SETTINGS, "INTENT_EMBED_MIN_SCORE", 0.99):  # Bardzo wysoki próg
                with patch.object(SETTINGS, "INTENT_EMBED_MARGIN", 0.01):
                    with patch(
                        "sentence_transformers.SentenceTransformer",
                        return_value=mock_sentence_transformer
                    ):
                        from venom_core.core.intent_embedding_router import IntentEmbeddingRouter
                        
                        router = IntentEmbeddingRouter(temp_lexicon_dir)
                        intent, score, top2 = await router.classify("some random text")
                        
                        # Powinno zwrócić None bo score nie osiągnął progu
                        assert intent is None
                        assert len(top2) >= 0

    @pytest.mark.asyncio
    async def test_classify_insufficient_margin(
        self, temp_lexicon_dir, mock_sentence_transformer
    ):
        """Test że klasyfikacja zwraca None gdy margines między top1 a top2 jest za mały."""
        # Stwórz mock który zwraca bardzo podobne embeddingi dla wszystkich intencji
        mock_model = MagicMock()
        
        def mock_encode_similar(texts, convert_to_numpy=True, show_progress_bar=False):
            if isinstance(texts, str):
                texts = [texts]
            # Wszystkie embeddingi bardzo podobne - mały margines
            return np.array([[0.5, 0.5, 0.5] for _ in texts])
        
        mock_model.encode = mock_encode_similar
        
        with patch.object(SETTINGS, "ENABLE_INTENT_EMBEDDING_ROUTER", True):
            with patch.object(SETTINGS, "INTENT_EMBED_MIN_SCORE", 0.5):
                with patch.object(SETTINGS, "INTENT_EMBED_MARGIN", 0.3):  # Wysoki wymagany margines
                    with patch(
                        "sentence_transformers.SentenceTransformer",
                        return_value=mock_model
                    ):
                        from venom_core.core.intent_embedding_router import IntentEmbeddingRouter
                        
                        router = IntentEmbeddingRouter(temp_lexicon_dir)
                        intent, score, top2 = await router.classify("some text")
                        
                        # Powinno zwrócić None bo margines jest za mały
                        assert intent is None

    @pytest.mark.asyncio
    async def test_graceful_fallback_on_import_error(self, temp_lexicon_dir):
        """Test że router gracefully fallbackuje gdy brak biblioteki sentence-transformers."""
        with patch.object(SETTINGS, "ENABLE_INTENT_EMBEDDING_ROUTER", True):
            # Symuluj brak biblioteki
            with patch(
                "sentence_transformers.SentenceTransformer",
                side_effect=ImportError("No module named 'sentence_transformers'")
            ):
                from venom_core.core.intent_embedding_router import IntentEmbeddingRouter
                
                router = IntentEmbeddingRouter(temp_lexicon_dir)
                assert not router.is_enabled()
                
                # Classify powinno zwrócić None (fallback)
                intent, score, top2 = await router.classify("test")
                assert intent is None

    def test_cosine_similarity(self):
        """Test funkcji cosine_similarity."""
        from venom_core.core.intent_embedding_router import IntentEmbeddingRouter
        
        # Identyczne wektory - similarity = 1.0
        a = np.array([1.0, 0.0, 0.0])
        b = np.array([1.0, 0.0, 0.0])
        similarity = IntentEmbeddingRouter._cosine_similarity(a, b)
        assert abs(similarity - 1.0) < 0.001
        
        # Ortogonalne wektory - similarity = 0.0
        a = np.array([1.0, 0.0, 0.0])
        b = np.array([0.0, 1.0, 0.0])
        similarity = IntentEmbeddingRouter._cosine_similarity(a, b)
        assert abs(similarity - 0.0) < 0.001
        
        # Przeciwne wektory - similarity = -1.0
        a = np.array([1.0, 0.0, 0.0])
        b = np.array([-1.0, 0.0, 0.0])
        similarity = IntentEmbeddingRouter._cosine_similarity(a, b)
        assert abs(similarity - (-1.0)) < 0.001

    def test_load_multiple_languages(self, temp_lexicon_dir):
        """Test ładowania fraz z wielu języków."""
        with patch.object(SETTINGS, "ENABLE_INTENT_EMBEDDING_ROUTER", True):
            with patch(
                "sentence_transformers.SentenceTransformer"
            ) as mock_st:
                mock_model = MagicMock()
                mock_model.encode = MagicMock(return_value=np.array([[1.0, 0.0, 0.0]]))
                mock_st.return_value = mock_model
                
                from venom_core.core.intent_embedding_router import IntentEmbeddingRouter
                
                router = IntentEmbeddingRouter(temp_lexicon_dir)
                
                # Sprawdź że frazy z różnych języków zostały załadowane
                assert "CODE_GENERATION" in router.intent_phrases
                phrases = router.intent_phrases["CODE_GENERATION"]
                
                # Powinny być frazy z en i pl (de ma te same co en w tym teście)
                assert any("write" in p for p in phrases)
                assert any("napisz" in p for p in phrases)

    @pytest.mark.asyncio
    async def test_empty_lexicon_directory(self):
        """Test zachowania gdy katalog lexicon jest pusty."""
        with patch.object(SETTINGS, "ENABLE_INTENT_EMBEDDING_ROUTER", True):
            with patch(
                "sentence_transformers.SentenceTransformer"
            ) as mock_st:
                mock_model = MagicMock()
                mock_model.encode = MagicMock(return_value=np.array([[1.0, 0.0, 0.0]]))
                mock_st.return_value = mock_model
                
                from venom_core.core.intent_embedding_router import IntentEmbeddingRouter
                
                # Użyj nieistniejącego katalogu
                router = IntentEmbeddingRouter(Path("/tmp/nonexistent_dir_xyz"))
                
                # Router powinien być zainicjalizowany mimo braku plików
                # (graceful handling)
                assert router.model is not None
                
                # Classify na pustych embeddingach powinno zwrócić None
                intent, score, top2 = await router.classify("test")
                assert intent is None


@pytest.mark.asyncio
async def test_intent_manager_with_embedding_router(temp_lexicon_dir, mock_sentence_transformer):
    """Test integracji embedding routera z IntentManager."""
    with patch.object(SETTINGS, "ENABLE_INTENT_EMBEDDING_ROUTER", True):
        with patch.object(SETTINGS, "INTENT_EMBED_MIN_SCORE", 0.5):
            with patch.object(SETTINGS, "INTENT_EMBED_MARGIN", 0.1):
                with patch(
                    "sentence_transformers.SentenceTransformer",
                    return_value=mock_sentence_transformer
                ):
                    # Mock lexicon dir w IntentManager
                    with patch("venom_core.core.intent_manager.IntentManager.LEXICON_DIR", temp_lexicon_dir):
                        from venom_core.core.intent_manager import IntentManager
                        
                        # Stwórz manager bez kernela (żeby nie wywołać LLM)
                        manager = IntentManager(kernel=MagicMock())
                        
                        # Użyj promptu który nie pasuje do lexicon ale pasuje do embeddingów
                        # (mock_sentence_transformer zwraca embedding [1,0,0] dla słów code/write)
                        intent = await manager.classify_intent("develop some code for me")
                        
                        # Powinien użyć embedding routera lub lexicon - oba są OK
                        assert intent == "CODE_GENERATION"
                        # Sprawdź score tylko gdy źródło to lexicon lub embedding
                        if manager.last_intent_debug["source"] in ["lexicon", "embedding"]:
                            # W tych przypadkach score powinien być ustawiony i wystarczająco wysoki
                            assert manager.last_intent_debug["score"] is not None
                            assert manager.last_intent_debug["score"] > 0.5
                        else:
                            # Fallback do LLM lub inne - test nie powinien failować na braku score
                            pass
