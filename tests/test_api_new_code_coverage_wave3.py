"""Coverage-oriented tests for API route branches used by Sonar new-code gate."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from venom_core.api.routes import queue as queue_routes
from venom_core.api.routes import strategy as strategy_routes
from venom_core.api.routes import system_deps
from venom_core.api.routes import system_iot as iot_routes
from venom_core.api.routes import system_metrics as metrics_routes
from venom_core.api.routes import system_runtime as runtime_routes
from venom_core.api.routes import system_scheduler as scheduler_routes
from venom_core.utils.ttl_cache import TTLCache


def _client(router) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_queue_status_cache_and_503(monkeypatch: pytest.MonkeyPatch) -> None:
    queue_routes._queue_cache = TTLCache(ttl_seconds=60.0)
    queue_routes.set_dependencies(None)
    client = _client(queue_routes.router)
    assert client.get("/api/v1/queue/status").status_code == 503

    orchestrator = MagicMock()
    orchestrator.get_queue_status.return_value = {"paused": False, "active": 1}
    queue_routes.set_dependencies(orchestrator)

    first = client.get("/api/v1/queue/status")
    second = client.get("/api/v1/queue/status")
    assert first.status_code == 200
    assert second.status_code == 200
    assert orchestrator.get_queue_status.call_count == 1


@pytest.mark.asyncio
async def test_queue_abort_and_action_errors() -> None:
    orchestrator = MagicMock()
    orchestrator.abort_task = AsyncMock(return_value={"success": False, "message": "x"})
    queue_routes.set_dependencies(orchestrator)

    with pytest.raises(HTTPException) as exc:
        await queue_routes.abort_task(uuid4())
    assert exc.value.status_code == 404

    orchestrator.pause_queue = AsyncMock(side_effect=RuntimeError("pause boom"))
    with pytest.raises(HTTPException) as exc:
        await queue_routes.pause_queue()
    assert exc.value.status_code == 500

    orchestrator.resume_queue = AsyncMock(side_effect=RuntimeError("resume boom"))
    with pytest.raises(HTTPException) as exc:
        await queue_routes.resume_queue()
    assert exc.value.status_code == 500

    orchestrator.purge_queue = AsyncMock(side_effect=RuntimeError("purge boom"))
    with pytest.raises(HTTPException) as exc:
        await queue_routes.purge_queue()
    assert exc.value.status_code == 500

    orchestrator.emergency_stop = AsyncMock(side_effect=RuntimeError("stop boom"))
    with pytest.raises(HTTPException) as exc:
        await queue_routes.emergency_stop()
    assert exc.value.status_code == 500


def test_strategy_routes_success_and_errors() -> None:
    client = _client(strategy_routes.router)
    strategy_routes.set_dependencies(None)
    assert client.get("/api/roadmap").status_code == 503
    assert client.post("/api/roadmap/create", json={"vision": "x"}).status_code == 503
    assert client.get("/api/roadmap/status").status_code == 503
    assert client.post("/api/campaign/start").status_code == 503

    vision = SimpleNamespace(
        title="Vision", description="Desc", status=SimpleNamespace(value="ACTIVE")
    )
    vision.get_progress = lambda: 42.0
    milestone = SimpleNamespace(
        goal_id="m1",
        title="M1",
        description="Milestone",
        status=SimpleNamespace(value="COMPLETED"),
        priority=1,
    )
    milestone.get_progress = lambda: 100.0
    task = SimpleNamespace(
        title="Task",
        description="Task desc",
        status=SimpleNamespace(value="COMPLETED"),
        priority=2,
    )

    goal_store = MagicMock()
    goal_store.get_vision.return_value = vision
    goal_store.get_milestones.return_value = [milestone]
    goal_store.get_tasks.return_value = [task]
    goal_store.generate_roadmap_report.return_value = "ok"

    executive_agent = MagicMock()
    executive_agent.create_roadmap = AsyncMock(return_value={"steps": 1})
    executive_agent.generate_status_report = AsyncMock(return_value={"status": "ok"})

    orchestrator = MagicMock()
    orchestrator.task_dispatcher = MagicMock(
        goal_store=goal_store, executive_agent=executive_agent
    )
    orchestrator.execute_campaign_mode = AsyncMock(return_value={"campaign": "started"})
    strategy_routes.set_dependencies(orchestrator)

    assert client.get("/api/roadmap").status_code == 200
    assert (
        client.post("/api/roadmap/create", json={"vision": "Ship v2"}).status_code
        == 200
    )
    assert client.get("/api/roadmap/status").status_code == 200
    assert client.post("/api/campaign/start").status_code == 200


def test_scheduler_status_jobs_pause_resume_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(scheduler_routes.router)
    monkeypatch.setattr(system_deps, "get_background_scheduler", lambda: None)
    assert client.get("/api/v1/scheduler/status").status_code == 503
    assert client.get("/api/v1/scheduler/jobs").status_code == 503
    assert client.post("/api/v1/scheduler/pause").status_code == 503
    assert client.post("/api/v1/scheduler/resume").status_code == 503

    scheduler = MagicMock()
    scheduler.get_status.return_value = {"running": True}
    scheduler.get_jobs.return_value = [{"id": "j1"}]
    scheduler.pause_all_jobs = AsyncMock(return_value=None)
    scheduler.resume_all_jobs = AsyncMock(return_value=None)
    monkeypatch.setattr(system_deps, "get_background_scheduler", lambda: scheduler)

    assert client.get("/api/v1/scheduler/status").status_code == 200
    assert client.get("/api/v1/scheduler/jobs").status_code == 200
    assert client.post("/api/v1/scheduler/pause").status_code == 200
    assert client.post("/api/v1/scheduler/resume").status_code == 200

    scheduler.get_status.side_effect = RuntimeError("boom")
    assert client.get("/api/v1/scheduler/status").status_code == 500


def test_metrics_root_cache_and_system_error(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(metrics_routes.router)
    metrics_routes._metrics_cache.clear()
    metrics_routes._token_metrics_cache.clear()

    monkeypatch.setattr(metrics_routes.metrics_module, "metrics_collector", None)
    assert client.get("/api/v1/metrics").status_code == 503

    class Collector:
        def __init__(self):
            self.calls = 0

        def get_metrics(self):
            self.calls += 1
            if self.calls == 3:
                raise RuntimeError("system metrics failed")
            return {"tokens_used_session": 10}

    collector = Collector()
    monkeypatch.setattr(metrics_routes.metrics_module, "metrics_collector", collector)

    # root endpoint should be cached
    assert client.get("/api/v1/metrics").status_code == 200
    assert client.get("/api/v1/metrics").status_code == 200
    assert collector.calls == 1

    # force next path through /system error
    assert client.get("/api/v1/metrics/system").status_code == 200
    assert client.get("/api/v1/metrics/system").status_code == 500


@pytest.mark.asyncio
async def test_iot_status_disconnected_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(iot_routes.SETTINGS, "ENABLE_IOT_BRIDGE", True, raising=False)
    monkeypatch.setattr(system_deps, "get_hardware_bridge", lambda: None)
    status = await iot_routes.get_iot_status()
    assert status.connected is False
    assert "Brak połączenia" in (status.message or "")


def test_runtime_action_and_history_error_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(runtime_routes.router)

    controller = MagicMock()
    controller.start_service.side_effect = RuntimeError("cannot start")
    controller.get_history.side_effect = RuntimeError("history failed")
    monkeypatch.setattr(runtime_routes, "runtime_controller", controller)

    assert client.post("/api/v1/runtime/backend/start").status_code == 500
    assert client.get("/api/v1/runtime/history").status_code == 500
