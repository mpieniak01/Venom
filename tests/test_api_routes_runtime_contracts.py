"""Solid API route coverage tests for queue, metrics and runtime modules."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from venom_core.api.routes import queue as queue_routes
from venom_core.api.routes import system_deps
from venom_core.api.routes import system_metrics as metrics_routes
from venom_core.api.routes import system_runtime as runtime_routes
from venom_core.utils.ttl_cache import TTLCache


def _client(router) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_queue_status_internal_error_returns_500() -> None:
    queue_routes._queue_cache = TTLCache(ttl_seconds=10.0)
    orchestrator = MagicMock()
    orchestrator.get_queue_status.side_effect = RuntimeError("db unavailable")
    queue_routes.set_dependencies(orchestrator)

    response = _client(queue_routes.router).get("/api/v1/queue/status")
    assert response.status_code == 500
    assert "statusu kolejki" in response.json()["detail"]


def test_queue_mutation_endpoints_success_paths_clear_cache() -> None:
    queue_routes._queue_cache = TTLCache(ttl_seconds=60.0)

    orchestrator = MagicMock()
    orchestrator.pause_queue = AsyncMock(return_value={"success": True, "paused": True})
    orchestrator.resume_queue = AsyncMock(
        return_value={"success": True, "paused": False}
    )
    orchestrator.purge_queue = AsyncMock(return_value={"success": True, "removed": 2})
    orchestrator.emergency_stop = AsyncMock(
        return_value={"success": True, "cancelled": 1}
    )
    queue_routes.set_dependencies(orchestrator)
    queue_routes._queue_cache.set({"paused": False, "active": 99})

    client = _client(queue_routes.router)
    assert client.post("/api/v1/queue/pause").status_code == 200
    assert client.post("/api/v1/queue/resume").status_code == 200
    assert client.post("/api/v1/queue/purge").status_code == 200
    assert client.post("/api/v1/queue/emergency-stop").status_code == 200
    assert queue_routes._queue_cache.get() is None


def test_queue_abort_paths_success_404_and_500() -> None:
    client = _client(queue_routes.router)
    task_id = str(uuid4())

    orchestrator = MagicMock()
    orchestrator.abort_task = AsyncMock(
        return_value={"success": True, "task_id": task_id}
    )
    queue_routes.set_dependencies(orchestrator)
    ok = client.post(f"/api/v1/queue/task/{task_id}/abort")
    assert ok.status_code == 200
    assert ok.json()["success"] is True

    orchestrator.abort_task = AsyncMock(
        return_value={"success": False, "message": "nope"}
    )
    queue_routes.set_dependencies(orchestrator)
    not_found = client.post(f"/api/v1/queue/task/{task_id}/abort")
    assert not_found.status_code == 404
    assert "nope" in not_found.json()["detail"]

    orchestrator.abort_task = AsyncMock(side_effect=RuntimeError("boom"))
    queue_routes.set_dependencies(orchestrator)
    error = client.post(f"/api/v1/queue/task/{task_id}/abort")
    assert error.status_code == 500
    assert "przerywania zadania" in error.json()["detail"]


def test_metrics_tokens_cache_and_error_paths(monkeypatch) -> None:
    metrics_routes._token_metrics_cache.clear()
    metrics_routes._metrics_cache.clear()

    class Collector:
        def __init__(self):
            self.calls = 0

        def get_metrics(self):
            self.calls += 1
            return {"tokens_used_session": 200}

    collector = Collector()
    monkeypatch.setattr(metrics_routes.metrics_module, "metrics_collector", collector)
    metrics_routes.set_dependencies(token_economist=None)

    client = _client(metrics_routes.router)
    first = client.get("/api/v1/metrics/tokens")
    second = client.get("/api/v1/metrics/tokens")
    assert first.status_code == 200
    assert second.status_code == 200
    assert collector.calls == 1

    class FailingEconomist:
        def calculate_cost(self, *_args, **_kwargs):
            raise RuntimeError("cost backend unavailable")

    metrics_routes._token_metrics_cache.clear()
    metrics_routes.set_dependencies(token_economist=FailingEconomist())
    failed = client.get("/api/v1/metrics/tokens")
    assert failed.status_code == 500
    assert "metryk tokenów" in failed.json()["detail"]


def test_metrics_system_and_root_collector_none_and_root_cache(monkeypatch) -> None:
    metrics_routes._metrics_cache.clear()
    metrics_routes._token_metrics_cache.clear()
    client = _client(metrics_routes.router)

    monkeypatch.setattr(metrics_routes.metrics_module, "metrics_collector", None)
    assert client.get("/api/v1/metrics/system").status_code == 503
    assert client.get("/api/v1/metrics").status_code == 503

    class Collector:
        def __init__(self):
            self.calls = 0

        def get_metrics(self):
            self.calls += 1
            return {"uptime": 10}

    collector = Collector()
    monkeypatch.setattr(metrics_routes.metrics_module, "metrics_collector", collector)
    first = client.get("/api/v1/metrics")
    second = client.get("/api/v1/metrics")
    assert first.status_code == 200
    assert second.status_code == 200
    assert collector.calls == 1


def test_runtime_status_enriches_with_service_monitor(monkeypatch) -> None:
    runtime_service = SimpleNamespace(
        name="Backend",
        service_type=SimpleNamespace(value="core"),
        status=SimpleNamespace(value="running"),
        pid=123,
        port=8000,
        cpu_percent=2.0,
        memory_mb=128.0,
        uptime_seconds=50,
        last_log="ok",
        error_message=None,
        runtime_version=None,
        actionable=True,
    )
    controller = MagicMock()
    controller.get_all_services_status.return_value = [runtime_service]
    controller.get_aux_runtime_version.return_value = None
    monkeypatch.setattr(runtime_routes, "runtime_controller", controller)

    monitor = MagicMock()
    monitor.check_health = AsyncMock(return_value=[])
    monitor.get_all_services.return_value = [
        # skipped: api
        SimpleNamespace(
            name="Api Gateway",
            service_type="api",
            status=SimpleNamespace(value="online"),
            error_message=None,
            latency_ms=1.0,
            endpoint="http://127.0.0.1",
        ),
        # skipped: local llm alias
        SimpleNamespace(
            name="local llm",
            service_type="llm",
            status=SimpleNamespace(value="online"),
            error_message=None,
            latency_ms=1.0,
            endpoint=None,
        ),
        # added
        SimpleNamespace(
            name="Redis",
            service_type="database",
            status=SimpleNamespace(value="offline"),
            error_message="conn refused",
            latency_ms=10.5,
            endpoint="redis://localhost",
        ),
    ]
    monkeypatch.setattr(system_deps, "get_service_monitor", lambda: monitor)

    response = _client(runtime_routes.router).get("/api/v1/runtime/status")
    assert response.status_code == 200
    data = response.json()
    names = [service["name"] for service in data["services"]]
    assert "Backend" in names
    assert "Redis" in names
    redis = next(service for service in data["services"] if service["name"] == "Redis")
    assert redis["status"] == "stopped"
    assert redis["actionable"] is False


def test_runtime_actions_stop_restart_and_error_paths(monkeypatch) -> None:
    controller = MagicMock()
    controller.stop_service.return_value = {"success": True, "action": "stop"}
    controller.restart_service.return_value = {"success": True, "action": "restart"}
    controller.apply_profile.side_effect = RuntimeError("profile failed")
    controller.get_history.side_effect = RuntimeError("history failed")
    controller.get_aux_runtime_version.return_value = None
    monkeypatch.setattr(runtime_routes, "runtime_controller", controller)

    client = _client(runtime_routes.router)
    assert client.post("/api/v1/runtime/backend/stop").status_code == 200
    assert client.post("/api/v1/runtime/backend/restart").status_code == 200
    assert client.post("/api/v1/runtime/profile/light").status_code == 500
    assert client.get("/api/v1/runtime/history").status_code == 500
