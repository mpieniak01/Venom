"""Testy kontraktowe routera benchmark_coding."""

from __future__ import annotations

from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from venom_core.api.routes import benchmark_coding as benchmark_coding_routes
from venom_core.services.runtime_exclusive_guard import (
    RuntimeExclusiveConflictError,
    RuntimeExclusivePreflightError,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_app(service=None):
    """Tworzy testową instancję FastAPI z zarejestrowanym routerem."""
    # Reset module-level service before each test
    benchmark_coding_routes.set_dependencies(service)
    app = FastAPI()
    app.include_router(benchmark_coding_routes.router)
    return app


class _ConflictGuard:
    def acquire_lock(self, _owner):
        raise RuntimeExclusiveConflictError("lock busy")

    def release_lock(self, _owner):
        return None


class _PassGuard:
    def acquire_lock(self, _owner):
        return None

    def release_lock(self, _owner):
        return None

    async def preflight_for_benchmark(self, **_kwargs):
        return None


class _PreflightConflictGuard(_PassGuard):
    async def preflight_for_benchmark(self, **_kwargs):
        raise RuntimeExclusiveConflictError("active benchmark")


class _PreflightErrorGuard(_PassGuard):
    async def preflight_for_benchmark(self, **_kwargs):
        raise RuntimeExclusivePreflightError("runtime down")


def _mock_service(
    run_id="test-run-uuid-0000-0000000000001",
    status_dict=None,
    list_result=None,
):
    svc = MagicMock()
    svc.start_run.return_value = run_id
    default_status = {
        "run_id": run_id,
        "status": "pending",
        "config": {
            "models": ["llama3:latest"],
            "tasks": ["python_sanity"],
            "loop_task": "python_complex_bugfix",
            "first_sieve_task": "",
            "timeout": 180,
            "max_rounds": 3,
            "endpoint": "http://127.0.0.1:11434",
            "stop_on_failure": False,
        },
        "jobs": [],
        "summary": {
            "total_jobs": 0,
            "completed": 0,
            "failed": 0,
            "pending": 0,
            "skipped": 0,
            "success_rate": 0.0,
        },
        "created_at": "2024-01-01T00:00:00+00:00",
        "started_at": None,
        "finished_at": None,
        "error_message": None,
    }
    svc.get_run_status.return_value = status_dict or default_status
    svc.list_runs.return_value = list_result or []
    svc.delete_run.return_value = True
    svc.clear_all_runs.return_value = 0
    return svc


# ---------------------------------------------------------------------------
# POST /start
# ---------------------------------------------------------------------------


def test_start_endpoint_success():
    """POST /start z poprawnymi danymi zwraca 200 i run_id."""
    svc = _mock_service()
    client = TestClient(_make_app(svc))
    payload = {"models": ["llama3:latest"], "tasks": ["python_sanity"]}
    resp = client.post("/api/v1/benchmark/coding/start", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "run_id" in data
    assert "message" in data


def test_start_endpoint_no_service():
    """POST /start bez skonfigurowanego serwisu zwraca 503."""
    client = TestClient(_make_app(None))
    payload = {"models": ["llama3:latest"], "tasks": ["python_sanity"]}
    resp = client.post("/api/v1/benchmark/coding/start", json=payload)
    assert resp.status_code == 503


def test_start_endpoint_validation_error():
    """POST /start z nieprawidłowymi danymi zwraca 400."""
    svc = _mock_service()
    svc.start_run.side_effect = ValueError("Lista modeli nie może być pusta")
    client = TestClient(_make_app(svc))
    payload = {"models": [], "tasks": ["python_sanity"]}
    resp = client.post("/api/v1/benchmark/coding/start", json=payload)
    # FastAPI waliduje min_length=1 i zwróci 422
    assert resp.status_code in (400, 422)


def test_start_endpoint_default_tasks():
    """POST /start z domyślnymi parametrami jest akceptowane."""
    svc = _mock_service()
    client = TestClient(_make_app(svc))
    payload = {"models": ["llama3:latest"]}
    resp = client.post("/api/v1/benchmark/coding/start", json=payload)
    assert resp.status_code == 200


def test_start_endpoint_returns_409_when_guard_lock_busy():
    svc = _mock_service()
    benchmark_coding_routes.set_dependencies(
        svc,
        runtime_exclusive_guard=_ConflictGuard(),
    )
    app = FastAPI()
    app.include_router(benchmark_coding_routes.router)
    client = TestClient(app)
    payload = {"models": ["llama3:latest"], "tasks": ["python_sanity"]}
    resp = client.post("/api/v1/benchmark/coding/start", json=payload)
    assert resp.status_code == 409


def test_start_endpoint_calls_guard_preflight():
    svc = _mock_service()
    guard = _PassGuard()
    benchmark_coding_routes.set_dependencies(
        svc,
        runtime_exclusive_guard=guard,
    )
    app = FastAPI()
    app.include_router(benchmark_coding_routes.router)
    client = TestClient(app)
    payload = {"models": ["llama3:latest"], "tasks": ["python_sanity"]}
    resp = client.post("/api/v1/benchmark/coding/start", json=payload)
    assert resp.status_code == 200


def test_start_endpoint_returns_409_when_guard_preflight_conflicts():
    svc = _mock_service()
    benchmark_coding_routes.set_dependencies(
        svc,
        runtime_exclusive_guard=_PreflightConflictGuard(),
    )
    app = FastAPI()
    app.include_router(benchmark_coding_routes.router)
    client = TestClient(app)
    payload = {"models": ["llama3:latest"], "tasks": ["python_sanity"]}
    resp = client.post("/api/v1/benchmark/coding/start", json=payload)
    assert resp.status_code == 409


def test_start_endpoint_returns_503_when_guard_preflight_fails():
    svc = _mock_service()
    benchmark_coding_routes.set_dependencies(
        svc,
        runtime_exclusive_guard=_PreflightErrorGuard(),
    )
    app = FastAPI()
    app.include_router(benchmark_coding_routes.router)
    client = TestClient(app)
    payload = {"models": ["llama3:latest"], "tasks": ["python_sanity"]}
    resp = client.post("/api/v1/benchmark/coding/start", json=payload)
    assert resp.status_code == 503


def test_start_endpoint_returns_500_for_unexpected_error():
    svc = _mock_service()
    svc.start_run.side_effect = RuntimeError("boom")
    client = TestClient(_make_app(svc))
    payload = {"models": ["llama3:latest"], "tasks": ["python_sanity"]}
    resp = client.post("/api/v1/benchmark/coding/start", json=payload)
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# GET /list
# ---------------------------------------------------------------------------


def test_list_endpoint_empty():
    """GET /list zwraca pustą listę gdy brak benchmarków."""
    svc = _mock_service()
    svc.list_runs.return_value = []
    client = TestClient(_make_app(svc))
    resp = client.get("/api/v1/benchmark/coding/list")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 0
    assert data["runs"] == []


def test_list_endpoint_no_service():
    """GET /list bez serwisu zwraca 503."""
    client = TestClient(_make_app(None))
    resp = client.get("/api/v1/benchmark/coding/list")
    assert resp.status_code == 503


def test_list_endpoint_limit_query():
    """GET /list z parametrem limit=5."""
    svc = _mock_service()
    client = TestClient(_make_app(svc))
    resp = client.get("/api/v1/benchmark/coding/list?limit=5")
    assert resp.status_code == 200
    svc.list_runs.assert_called_once_with(limit=5)


def test_list_endpoint_returns_500_when_service_raises():
    svc = _mock_service()
    svc.list_runs.side_effect = RuntimeError("db fail")
    client = TestClient(_make_app(svc))
    resp = client.get("/api/v1/benchmark/coding/list")
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# GET /{run_id}/status
# ---------------------------------------------------------------------------


def test_status_endpoint_success():
    """GET /{run_id}/status zwraca status run."""
    run_id = "12345678-1234-1234-1234-123456789abc"
    svc = _mock_service(run_id=run_id)
    client = TestClient(_make_app(svc))
    resp = client.get(f"/api/v1/benchmark/coding/{run_id}/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["run_id"] == run_id


def test_status_endpoint_not_found():
    """GET /{run_id}/status zwraca 404 dla nieistniejącego run."""
    svc = _mock_service()
    svc.get_run_status.return_value = None
    client = TestClient(_make_app(svc))
    resp = client.get("/api/v1/benchmark/coding/nonexistent-id/status")
    assert resp.status_code == 404


def test_status_endpoint_no_service():
    """GET /{run_id}/status bez serwisu zwraca 503."""
    client = TestClient(_make_app(None))
    resp = client.get("/api/v1/benchmark/coding/some-id/status")
    assert resp.status_code == 503


def test_status_endpoint_returns_500_for_unexpected_error():
    svc = _mock_service()
    svc.get_run_status.side_effect = RuntimeError("status fail")
    client = TestClient(_make_app(svc))
    resp = client.get("/api/v1/benchmark/coding/some-id/status")
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# DELETE /all
# ---------------------------------------------------------------------------


def test_delete_all_endpoint():
    """DELETE /all usuwa wszystkie benchmarki."""
    svc = _mock_service()
    svc.clear_all_runs.return_value = 3
    client = TestClient(_make_app(svc))
    resp = client.delete("/api/v1/benchmark/coding/all")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 3


def test_delete_all_endpoint_no_service():
    """DELETE /all bez serwisu zwraca 503."""
    client = TestClient(_make_app(None))
    resp = client.delete("/api/v1/benchmark/coding/all")
    assert resp.status_code == 503


def test_delete_all_endpoint_returns_500_when_service_raises():
    svc = _mock_service()
    svc.clear_all_runs.side_effect = RuntimeError("clear fail")
    client = TestClient(_make_app(svc))
    resp = client.delete("/api/v1/benchmark/coding/all")
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# DELETE /{run_id}
# ---------------------------------------------------------------------------


def test_delete_run_endpoint_success():
    """DELETE /{run_id} usuwa run i zwraca 200."""
    run_id = "12345678-1234-1234-1234-123456789abc"
    svc = _mock_service(run_id=run_id)
    client = TestClient(_make_app(svc))
    resp = client.delete(f"/api/v1/benchmark/coding/{run_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert "message" in data


def test_delete_run_endpoint_not_found():
    """DELETE /{run_id} zwraca 404 dla nieistniejącego run."""
    svc = _mock_service()
    svc.delete_run.return_value = False
    client = TestClient(_make_app(svc))
    resp = client.delete("/api/v1/benchmark/coding/nonexistent-id")
    assert resp.status_code == 404


def test_delete_run_endpoint_no_service():
    """DELETE /{run_id} bez serwisu zwraca 503."""
    client = TestClient(_make_app(None))
    resp = client.delete("/api/v1/benchmark/coding/some-id")
    assert resp.status_code == 503


def test_delete_run_endpoint_returns_500_for_unexpected_error():
    svc = _mock_service()
    svc.delete_run.side_effect = RuntimeError("delete fail")
    client = TestClient(_make_app(svc))
    resp = client.delete("/api/v1/benchmark/coding/some-id")
    assert resp.status_code == 500
