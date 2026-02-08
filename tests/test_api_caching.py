from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from venom_core.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_git_status_caching():
    # Reset cache before test
    from venom_core.api.routes.git import _git_status_cache

    _git_status_cache.set(None)

    with patch(
        "venom_core.api.routes.git._get_git_status_impl", new_callable=AsyncMock
    ) as mock_impl:
        mock_impl.return_value = {"status": "success", "branch": "test-branch"}

        client = TestClient(app)

        # First call - should call impl
        response1 = client.get("/api/v1/git/status")
        assert response1.status_code == 200
        assert response1.json()["branch"] == "test-branch"
        assert mock_impl.call_count == 1

        # Second call - should use cache
        response2 = client.get("/api/v1/git/status")
        assert response2.status_code == 200
        assert response2.json()["branch"] == "test-branch"
        assert mock_impl.call_count == 1  # Still 1

        # Wait for TTL (git cache has 5s, but we can mock/shorten it or just check it's not 0)
        # For the sake of test speed, we just verified it stays at 1.


def test_models_usage_caching():
    from venom_core.api.routes.models_usage import _models_usage_cache

    _models_usage_cache.set(None)

    # We need to mock the model_manager or the result of usage_metrics
    with patch(
        "venom_core.api.routes.models_usage.get_model_manager"
    ) as mock_get_manager:
        mock_manager = AsyncMock()
        mock_manager.get_usage_metrics.return_value = {"vram": 1024}
        mock_get_manager.return_value = mock_manager

        client = TestClient(app)

        # First
        client.get("/api/v1/models/usage")
        assert mock_manager.get_usage_metrics.call_count == 1

        # Second
        client.get("/api/v1/models/usage")
        assert mock_manager.get_usage_metrics.call_count == 1
