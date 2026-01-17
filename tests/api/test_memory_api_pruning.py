from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from venom_core.api.dependencies import get_lessons_store
from venom_core.main import app


# Mock store config
def get_mock_lessons_store():
    mock = MagicMock()
    # Configure return values for primitive types (int)
    mock.prune_by_ttl.return_value = 5
    mock.delete_by_time_range.return_value = 3
    mock.delete_by_tag.return_value = 0
    mock.delete_last_n.return_value = 2
    mock.dedupe_lessons.return_value = 1
    return mock


# Dependency override
app.dependency_overrides[get_lessons_store] = get_mock_lessons_store

client = TestClient(app)


# Dummy test data injector
def inject_dummy_lessons(client):
    pass


def test_prune_lessons_latest_endpoint():
    # DELETE /api/v1/memory/lessons/prune/latest?count=1
    response = client.delete("/api/v1/memory/lessons/prune/latest?count=1")
    # Even if empty, should return 200 OK with deleted_count
    assert response.status_code == 200
    data = response.json()
    assert "deleted" in data
    assert data["deleted"] == 2


def test_prune_lessons_by_range_endpoint():
    # DELETE /api/v1/memory/lessons/prune/range
    # Use Z suffix to avoid URL encoding issues with +
    now = datetime.now(timezone.utc)
    end_date = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    start_date = (now - timedelta(days=365)).strftime("%Y-%m-%dT%H:%M:%SZ")

    response = client.delete(
        f"/api/v1/memory/lessons/prune/range?start={start_date}&end={end_date}"
    )
    assert response.status_code == 200
    assert "deleted" in response.json()
    assert response.json()["deleted"] == 3


def test_prune_lessons_by_tag_endpoint():
    # DELETE /api/v1/memory/lessons/prune/tag
    response = client.delete("/api/v1/memory/lessons/prune/tag?tag=nonexistent_tag_123")
    assert response.status_code == 200
    assert response.json()["deleted"] == 0


def test_prune_lessons_by_ttl_endpoint():
    # DELETE /api/v1/memory/lessons/prune/ttl
    response = client.delete("/api/v1/memory/lessons/prune/ttl?days=30")
    assert response.status_code == 200
    assert "deleted" in response.json()
    assert response.json()["deleted"] == 5
