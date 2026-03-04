"""Route tests for Academy self-learning API."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from venom_core.api.routes import academy_self_learning as routes


@pytest.fixture
def mock_service():
    service = MagicMock()
    service.start_run.return_value = "6de0cc81-77db-4bbf-a598-b66c7a8d45e8"
    service.get_status.return_value = {
        "run_id": "6de0cc81-77db-4bbf-a598-b66c7a8d45e8",
        "status": "running",
        "mode": "rag_index",
        "sources": ["docs"],
        "created_at": "2026-03-04T10:00:00+00:00",
        "started_at": "2026-03-04T10:00:01+00:00",
        "finished_at": None,
        "progress": {
            "files_discovered": 10,
            "files_processed": 3,
            "chunks_created": 5,
            "records_created": 0,
            "indexed_vectors": 2,
        },
        "artifacts": {},
        "logs": ["started"],
        "error_message": None,
    }
    service.list_runs.return_value = [service.get_status.return_value]
    service.delete_run.return_value = True
    service.clear_all_runs.return_value = 1
    service.get_capabilities = AsyncMock(
        return_value={
            "trainable_models": [
                {
                    "model_id": "qwen2.5-coder:3b",
                    "label": "qwen2.5-coder:3b",
                    "provider": "ollama",
                    "recommended": True,
                    "runtime_compatibility": {"ollama": True},
                    "recommended_runtime": "ollama",
                }
            ],
            "embedding_profiles": [
                {
                    "profile_id": "local:default",
                    "provider": "local",
                    "model": "sentence-transformers/all-MiniLM-L6-v2",
                    "dimension": 384,
                    "healthy": True,
                    "fallback_active": False,
                    "details": {},
                }
            ],
            "default_base_model": "qwen2.5-coder:3b",
            "default_embedding_profile_id": "local:default",
        }
    )
    return service


@pytest.fixture
def client(mock_service):
    app = FastAPI()
    routes.set_dependencies(self_learning_service=mock_service)
    app.include_router(routes.router)
    yield TestClient(app)
    routes.set_dependencies(self_learning_service=None)


def test_start_self_learning(client: TestClient, mock_service: MagicMock):
    response = client.post(
        "/api/v1/academy/self-learning/start",
        json={
            "mode": "rag_index",
            "sources": ["docs"],
            "limits": {
                "max_file_size_kb": 256,
                "max_files": 500,
                "max_total_size_mb": 50,
            },
            "dry_run": False,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["run_id"] == mock_service.start_run.return_value
    assert data["message"]


def test_get_self_learning_status(client: TestClient):
    response = client.get(
        "/api/v1/academy/self-learning/6de0cc81-77db-4bbf-a598-b66c7a8d45e8/status"
    )
    assert response.status_code == 200
    assert response.json()["status"] == "running"


def test_get_self_learning_capabilities(client: TestClient):
    response = client.get("/api/v1/academy/self-learning/capabilities")
    assert response.status_code == 200
    payload = response.json()
    assert payload["default_base_model"] == "qwen2.5-coder:3b"
    assert payload["embedding_profiles"][0]["profile_id"] == "local:default"


def test_get_self_learning_status_not_found(
    client: TestClient, mock_service: MagicMock
):
    mock_service.get_status.return_value = None
    response = client.get(
        "/api/v1/academy/self-learning/6de0cc81-77db-4bbf-a598-b66c7a8d45e8/status"
    )
    assert response.status_code == 404


def test_start_self_learning_validation_error(
    client: TestClient, mock_service: MagicMock
):
    mock_service.start_run.side_effect = ValueError("bad request")
    response = client.post(
        "/api/v1/academy/self-learning/start",
        json={
            "mode": "rag_index",
            "sources": ["docs"],
            "limits": {
                "max_file_size_kb": 256,
                "max_files": 500,
                "max_total_size_mb": 50,
            },
            "rag_config": {"embedding_profile_id": "local:default"},
            "dry_run": False,
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "bad request"


def test_start_self_learning_internal_error(
    client: TestClient, mock_service: MagicMock
):
    mock_service.start_run.side_effect = RuntimeError("boom")
    response = client.post(
        "/api/v1/academy/self-learning/start",
        json={
            "mode": "rag_index",
            "sources": ["docs"],
            "limits": {
                "max_file_size_kb": 256,
                "max_files": 500,
                "max_total_size_mb": 50,
            },
            "rag_config": {"embedding_profile_id": "local:default"},
            "dry_run": False,
        },
    )
    assert response.status_code == 500


def test_list_self_learning_runs(client: TestClient):
    response = client.get("/api/v1/academy/self-learning/list?limit=20")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    assert len(data["runs"]) == 1


def test_get_self_learning_capabilities_internal_error(
    client: TestClient, mock_service: MagicMock
):
    mock_service.get_capabilities = AsyncMock(side_effect=RuntimeError("boom"))
    response = client.get("/api/v1/academy/self-learning/capabilities")
    assert response.status_code == 500


def test_list_self_learning_runs_internal_error(
    client: TestClient, mock_service: MagicMock
):
    mock_service.list_runs.side_effect = RuntimeError("boom")
    response = client.get("/api/v1/academy/self-learning/list?limit=20")
    assert response.status_code == 500


def test_delete_self_learning_run(client: TestClient):
    response = client.delete(
        "/api/v1/academy/self-learning/6de0cc81-77db-4bbf-a598-b66c7a8d45e8"
    )
    assert response.status_code == 200


def test_delete_self_learning_run_internal_error(
    client: TestClient, mock_service: MagicMock
):
    mock_service.delete_run.side_effect = RuntimeError("boom")
    response = client.delete(
        "/api/v1/academy/self-learning/6de0cc81-77db-4bbf-a598-b66c7a8d45e8"
    )
    assert response.status_code == 500


def test_clear_all_self_learning_runs(client: TestClient):
    response = client.delete("/api/v1/academy/self-learning/all")
    assert response.status_code == 200
    assert response.json()["count"] == 1


def test_clear_all_self_learning_runs_internal_error(
    client: TestClient, mock_service: MagicMock
):
    mock_service.clear_all_runs.side_effect = RuntimeError("boom")
    response = client.delete("/api/v1/academy/self-learning/all")
    assert response.status_code == 500


def test_service_unavailable_returns_503(mock_service: MagicMock):
    app = FastAPI()
    routes.set_dependencies(self_learning_service=None)
    app.include_router(routes.router)
    client = TestClient(app)

    response = client.post(
        "/api/v1/academy/self-learning/start",
        json={
            "mode": "rag_index",
            "sources": ["docs"],
            "limits": {
                "max_file_size_kb": 256,
                "max_files": 100,
                "max_total_size_mb": 20,
            },
            "dry_run": True,
        },
    )
    assert response.status_code == 503


def test_service_unavailable_returns_503_for_other_endpoints():
    app = FastAPI()
    routes.set_dependencies(self_learning_service=None)
    app.include_router(routes.router)
    client = TestClient(app)

    status_response = client.get(
        "/api/v1/academy/self-learning/6de0cc81-77db-4bbf-a598-b66c7a8d45e8/status"
    )
    list_response = client.get("/api/v1/academy/self-learning/list?limit=20")
    caps_response = client.get("/api/v1/academy/self-learning/capabilities")
    delete_response = client.delete(
        "/api/v1/academy/self-learning/6de0cc81-77db-4bbf-a598-b66c7a8d45e8"
    )
    clear_response = client.delete("/api/v1/academy/self-learning/all")

    assert status_response.status_code == 503
    assert list_response.status_code == 503
    assert caps_response.status_code == 503
    assert delete_response.status_code == 503
    assert clear_response.status_code == 503


def test_delete_self_learning_run_not_found(
    client: TestClient, mock_service: MagicMock
):
    mock_service.delete_run.return_value = False
    response = client.delete(
        "/api/v1/academy/self-learning/6de0cc81-77db-4bbf-a598-b66c7a8d45e8"
    )
    assert response.status_code == 404
