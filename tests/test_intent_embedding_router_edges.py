"""Additional edge-case tests for IntentEmbeddingRouter and embedding branches in IntentManager."""

from __future__ import annotations

import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from venom_core.config import SETTINGS


@pytest.fixture(autouse=True)
def mock_sentence_transformers_module(monkeypatch):
    monkeypatch.setitem(sys.modules, "sentence_transformers", MagicMock())


@pytest.fixture
def temp_lexicon_dir(tmp_path):
    data = {
        "intents": {
            "CODE_GENERATION": {"phrases": ["write code", "create script"]},
            "KNOWLEDGE_SEARCH": {"phrases": ["what is", "explain"]},
        }
    }
    for lang in ["en", "pl", "de"]:
        (tmp_path / f"intent_lexicon_{lang}.json").write_text(
            json.dumps(data), encoding="utf-8"
        )
    return tmp_path


def test_load_intent_phrases_handles_invalid_json_file(tmp_path):
    (tmp_path / "intent_lexicon_en.json").write_text("{broken", encoding="utf-8")
    # Missing pl/de is expected path too.
    with patch.object(SETTINGS, "ENABLE_INTENT_EMBEDDING_ROUTER", True):
        with patch(
            "sentence_transformers.SentenceTransformer", return_value=MagicMock()
        ):
            from venom_core.core.intent_embedding_router import IntentEmbeddingRouter

            router = IntentEmbeddingRouter(tmp_path)
            assert router.model is not None
            assert router.intent_phrases == {}


def test_build_intent_embeddings_skips_single_failing_intent(temp_lexicon_dir):
    mock_model = MagicMock()

    def _encode(phrases, **_kwargs):
        text = " ".join(phrases)
        if "write code" in text:
            raise RuntimeError("encode fail")
        return np.array([[0.0, 1.0, 0.0], [0.0, 1.0, 0.0]])

    mock_model.encode.side_effect = _encode

    with patch.object(SETTINGS, "ENABLE_INTENT_EMBEDDING_ROUTER", True):
        with patch(
            "sentence_transformers.SentenceTransformer", return_value=mock_model
        ):
            from venom_core.core.intent_embedding_router import IntentEmbeddingRouter

            router = IntentEmbeddingRouter(temp_lexicon_dir)
            assert "KNOWLEDGE_SEARCH" in router.intent_embeddings
            assert "CODE_GENERATION" not in router.intent_embeddings


@pytest.mark.asyncio
async def test_classify_returns_none_when_thread_pool_raises(temp_lexicon_dir):
    mock_model = MagicMock()
    mock_model.encode.return_value = np.array([[1.0, 0.0, 0.0]])

    with patch.object(SETTINGS, "ENABLE_INTENT_EMBEDDING_ROUTER", True):
        with patch(
            "sentence_transformers.SentenceTransformer", return_value=mock_model
        ):
            from venom_core.core.intent_embedding_router import IntentEmbeddingRouter

            router = IntentEmbeddingRouter(temp_lexicon_dir)
            with patch("anyio.to_thread.run_sync", side_effect=RuntimeError("boom")):
                intent, score, top2 = await router.classify("write code")
            assert intent is None
            assert score == 0.0
            assert top2 == []


@pytest.mark.asyncio
async def test_classify_returns_none_for_empty_similarities(temp_lexicon_dir):
    with patch.object(SETTINGS, "ENABLE_INTENT_EMBEDDING_ROUTER", False):
        from venom_core.core.intent_embedding_router import IntentEmbeddingRouter

        router = IntentEmbeddingRouter(temp_lexicon_dir)
        router._initialized = True
        router.model = MagicMock()
        router.intent_embeddings = {}
        intent, score, top2 = await router.classify("anything")
        assert intent is None
        assert score == 0.0
        assert top2 == []


def test_cosine_similarity_returns_zero_for_zero_vector():
    from venom_core.core.intent_embedding_router import IntentEmbeddingRouter

    a = np.array([0.0, 0.0, 0.0])
    b = np.array([1.0, 0.0, 0.0])
    assert IntentEmbeddingRouter._cosine_similarity(a, b) == 0.0


@pytest.mark.asyncio
async def test_intent_manager_embedding_hit_sets_debug(temp_lexicon_dir):
    with patch.object(SETTINGS, "ENABLE_INTENT_EMBEDDING_ROUTER", False):
        from venom_core.core.intent_manager import IntentManager

        manager = IntentManager(kernel=MagicMock())
        manager._classify_from_lexicon = MagicMock(return_value="")
        manager._classify_from_keywords = MagicMock(return_value="")
        router = MagicMock()
        router.is_enabled.return_value = True
        router.classify = AsyncMock(
            return_value=("RESEARCH", 0.88, [("RESEARCH", 0.88), ("GENERAL_CHAT", 0.2)])
        )
        manager.embedding_router = router

        intent = await manager.classify_intent("need deep research")
        assert intent == "RESEARCH"
        assert manager.last_intent_debug["source"] == "embedding"
        assert manager.last_intent_debug["score"] == 0.88


@pytest.mark.asyncio
async def test_intent_manager_embedding_miss_without_kernel_fallback(temp_lexicon_dir):
    with patch.object(SETTINGS, "ENABLE_INTENT_EMBEDDING_ROUTER", False):
        from venom_core.core.intent_manager import IntentManager

        manager = IntentManager(kernel=None)
        manager._classify_from_lexicon = MagicMock(return_value="")
        manager._classify_from_keywords = MagicMock(return_value="")
        manager.embedding_router = MagicMock(
            is_enabled=MagicMock(return_value=True),
            classify=AsyncMock(return_value=(None, 0.2, [("A", 0.2), ("B", 0.19)])),
        )
        manager._llm_disabled = True

        intent = await manager.classify_intent("ambiguous question")
        assert intent == "GENERAL_CHAT"
        assert manager.last_intent_debug["source"] == "fallback"


@pytest.mark.asyncio
async def test_intent_manager_llm_exception_uses_help_heuristic(temp_lexicon_dir):
    with patch.object(SETTINGS, "ENABLE_INTENT_EMBEDDING_ROUTER", False):
        from venom_core.core.intent_manager import IntentManager

        manager = IntentManager(kernel=MagicMock())
        manager._classify_from_lexicon = MagicMock(return_value="")
        manager._classify_from_keywords = MagicMock(return_value="")
        manager.embedding_router = None
        manager._classify_from_llm = AsyncMock(side_effect=RuntimeError("llm down"))

        intent = await manager.classify_intent("czy możesz pomóc z setupem?")
        assert intent == "HELP_REQUEST"
        assert manager.last_intent_debug["source"] == "fallback"


@pytest.mark.asyncio
async def test_release_reload_without_optional_dependency_falls_back_only_once(
    tmp_path, monkeypatch
):
    from unittest.mock import Mock

    from venom_core.core.intent_embedding_router import IntentEmbeddingRouter

    monkeypatch.setattr(SETTINGS, "ENABLE_INTENT_EMBEDDING_ROUTER", True)
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)
    router = IntentEmbeddingRouter(tmp_path)
    router.release_model_resource()
    original = router._initialize
    router._initialize = Mock(wraps=original)
    assert await router.classify("hello") == (None, 0.0, [])
    assert await router.classify("again") == (None, 0.0, [])
    assert router._initialize.call_count == 1
    assert router._resources_released is False


@pytest.mark.asyncio
async def test_release_reload_preserves_barrier_and_does_not_duplicate_phrases(
    temp_lexicon_dir, monkeypatch
):
    import asyncio

    from fastapi import HTTPException

    from venom_core.core.intent_embedding_router import IntentEmbeddingRouter
    from venom_core.services.model_resources import release_barrier

    monkeypatch.setattr(SETTINGS, "ENABLE_INTENT_EMBEDDING_ROUTER", True)
    model = MagicMock()
    model.encode.side_effect = lambda phrases, **_kw: np.array(
        [[1.0, 0.0] for _ in phrases]
    )
    constructor = sys.modules["sentence_transformers"].SentenceTransformer
    constructor.return_value = model
    router = IntentEmbeddingRouter(temp_lexicon_dir)
    initial = {key: list(value) for key, value in router.intent_phrases.items()}
    router.release_model_resource()
    with release_barrier():
        with pytest.raises(HTTPException, match="model_resources_releasing"):
            await router.classify("hello")
    assert router._resources_released is True
    await asyncio.gather(router.classify("hello"), router.classify("again"))
    assert constructor.call_count == 2
    assert router.intent_phrases == initial
