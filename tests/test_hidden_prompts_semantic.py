from unittest.mock import patch

import pytest

from venom_core.core import hidden_prompts


# Mock VectorStore to avoid real DB interactions
@pytest.fixture
def mock_vector_store():
    with patch("venom_core.memory.vector_store.VectorStore") as MockVectorStore:
        mock_instance = MockVectorStore.return_value
        yield mock_instance


def test_get_cached_hidden_response_exact_match_hit(tmp_path, monkeypatch):
    """Test that exact match returns immediately without querying semantic cache."""
    # Setup exact match via JSONL mocks (reusing logic from existing tests or mocking implementation)
    # Here we mock the internal helper _load_hidden_prompts or the list directly if possible.
    # But since we want to test the flow, we'll spy on VectorStore.

    with patch("venom_core.core.hidden_prompts.aggregate_hidden_prompts") as mock_agg:
        mock_agg.return_value = [
            {
                "prompt": "exact prompt",
                "approved_response": "exact response",
                "score": 5,
            }
        ]

        # Call function
        resp = hidden_prompts.get_cached_hidden_response("exact prompt", intent="qa")

        assert resp == "exact response"

        # Verify VectorStore was NOT imported/used
        # Note: We can't easily check import, but we can check if we mocked it at module level.
        # But for this test, result verification is sufficient.


def test_get_cached_hidden_response_semantic_hit(mock_vector_store):
    """Test semantic cache hit when exact match fails."""

    # 1. Mock exact match to return empty
    with patch("venom_core.core.hidden_prompts.aggregate_hidden_prompts") as mock_agg:
        mock_agg.return_value = []

        # 2. Mock VectorStore search result (HIT)
        # Distance 0.1 means Similarity 0.9 (assuming threshold 0.85)
        mock_vector_store.search.return_value = [
            {
                "text": "similar prompt",
                "score": 0.1,  # distance
                "metadata": {"response": "semantic response", "intent": "qa"},
            }
        ]

        # 3. Call function
        resp = hidden_prompts.get_cached_hidden_response(
            "semantically similar prompt", intent="qa"
        )

        # 4. Assert
        assert resp == "semantic response"
        mock_vector_store.search.assert_called_once()


def test_get_cached_hidden_response_semantic_miss_low_score(mock_vector_store):
    """Test semantic cache miss (score too low/distance too high)."""

    # Exact match empty
    with patch(
        "venom_core.core.hidden_prompts.aggregate_hidden_prompts", return_value=[]
    ):
        # VectorStore returns a match but with high distance (low similarity)
        # Distance 0.5 means Similarity 0.5 < 0.85
        mock_vector_store.search.return_value = [
            {
                "text": "vaguely related",
                "score": 0.5,
                "metadata": {"response": "bad response"},
            }
        ]

        resp = hidden_prompts.get_cached_hidden_response("prompt", intent="qa")

        assert resp is None


def test_get_cached_hidden_response_semantic_error(mock_vector_store, caplog):
    """Test graceful failure when VectorStore raises exception."""

    with patch(
        "venom_core.core.hidden_prompts.aggregate_hidden_prompts", return_value=[]
    ):
        mock_vector_store.search.side_effect = Exception("DB Connection Failed")

    resp = hidden_prompts.get_cached_hidden_response("prompt")

    assert resp is None


def test_cache_hidden_prompt_semantic_upsert(mock_vector_store):
    """Test saving to semantic cache."""

    hidden_prompts.cache_hidden_prompt_semantic(
        "prompt to save", "response", intent="qa"
    )

    # Verify upsert call
    mock_vector_store.upsert.assert_called_once()
    args, kwargs = mock_vector_store.upsert.call_args
    assert kwargs["text"] == "prompt to save"
    assert kwargs["metadata"]["response"] == "response"
    assert kwargs["metadata"]["intent"] == "qa"
    assert kwargs["chunk_text"] is False
