from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from venom_core.agents.analyst import AnalystAgent, TaskMetrics
from venom_core.agents.unsupported import UnsupportedAgent
from venom_core.api.routes import agents as agents_routes
from venom_core.api.routes import calendar as calendar_routes
from venom_core.api.routes import memory_projection as memory_projection_routes
from venom_core.api.routes import models_install as models_install_routes
from venom_core.api.routes import nodes as nodes_routes
from venom_core.api.routes import queue as queue_routes
from venom_core.api.routes import strategy as strategy_routes
from venom_core.api.routes import (
    system_config,
    system_deps,
    system_governance,
    system_runtime,
    system_scheduler,
    system_services,
    system_status,
)
from venom_core.core.model_router import ComplexityScore, ServiceId
from venom_core.core.models import TaskStatus
from venom_core.core.queue_manager import QueueManager
from venom_core.execution.skills.chrono_skill import ChronoSkill
from venom_core.execution.skills.complexity_skill import ComplexitySkill
from venom_core.memory.lessons_store import Lesson, LessonsStore
from venom_core.simulation.director import SimulationDirector
from venom_core.utils.ttl_cache import TTLCache


def _client_with_router(router) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app, client=("127.0.0.1", 50000))


def test_routes_agents_calendar_memory_projection_nodes_queue_strategy() -> None:
    # agents routes
    shadow_agent = MagicMock()
    shadow_agent.get_status.return_value = {"enabled": True}
    agents_routes.set_dependencies(
        gardener_agent=MagicMock(get_status=MagicMock(return_value="idle")),
        shadow_agent=shadow_agent,
        file_watcher=MagicMock(get_status=MagicMock(return_value="watching")),
        documenter_agent=MagicMock(get_status=MagicMock(return_value="ready")),
        orchestrator=MagicMock(),
    )
    client = _client_with_router(agents_routes.router)
    assert client.get("/api/v1/gardener/status").status_code == 200
    assert client.get("/api/v1/watcher/status").status_code == 200
    assert client.get("/api/v1/documenter/status").status_code == 200
    assert client.get("/api/v1/shadow/status").status_code == 200
    assert (
        client.post("/api/v1/shadow/reject", json={"content": "not now"}).status_code
        == 200
    )

    # calendar routes
    calendar_skill = MagicMock()
    calendar_skill.credentials_available = True
    calendar_skill.read_agenda.return_value = "Brak wydarzeń"
    calendar_skill.schedule_task.return_value = (
        "✅ Zaplanowano\n🔗 Link: https://calendar"
    )
    calendar_routes.set_dependencies(calendar_skill)
    calendar_client = _client_with_router(calendar_routes.router)
    assert calendar_client.get("/api/v1/calendar/events").status_code == 200
    assert (
        calendar_client.post(
            "/api/v1/calendar/event",
            json={
                "title": "Standup",
                "start_time": "2025-01-01T10:00:00",
                "duration_minutes": 30,
                "description": "Daily",
            },
        ).status_code
        == 201
    )

    # memory projection route
    class _FakePCA:
        def __init__(self, n_components: int):
            self.n_components = n_components

        def fit_transform(self, vectors):
            return np.array([[0.1, 0.2] for _ in vectors], dtype=float)

    vector_store = MagicMock()
    vector_store.embedding_service = MagicMock(
        get_embeddings_batch=MagicMock(return_value=[[1.0, 2.0], [3.0, 4.0]])
    )
    vector_store.list_entries.return_value = [
        {"id": "a", "text": "alpha"},
        {"id": "b", "text": "beta"},
    ]
    vector_store.update_metadata.return_value = True
    memory_projection_routes.PCA = _FakePCA
    memory_projection_routes.set_dependencies(vector_store)
    projection_client = _client_with_router(memory_projection_routes.router)
    assert projection_client.post("/api/v1/memory/embedding-project").status_code == 200

    # nodes routes
    node_online = SimpleNamespace(
        is_online=True, to_dict=lambda: {"id": "n1", "is_online": True}
    )
    node_manager = MagicMock()
    node_manager.list_nodes.return_value = [node_online]
    node_manager.get_node.return_value = node_online
    nodes_routes.set_dependencies(node_manager)
    nodes_client = _client_with_router(nodes_routes.router)
    assert nodes_client.get("/api/v1/nodes").status_code == 200
    assert nodes_client.get("/api/v1/nodes/n1").status_code == 200

    # queue route
    queue_routes._queue_cache = TTLCache(ttl_seconds=1.0)
    queue_routes.set_dependencies(
        MagicMock(get_queue_status=MagicMock(return_value={"paused": False}))
    )
    queue_client = _client_with_router(queue_routes.router)
    assert queue_client.get("/api/v1/queue/status").status_code == 200

    # strategy route
    goal_store = MagicMock()
    goal_store.get_vision.return_value = None
    goal_store.get_milestones.return_value = []
    goal_store.generate_roadmap_report.return_value = "ok"
    orchestrator = MagicMock()
    orchestrator.task_dispatcher = MagicMock(goal_store=goal_store)
    strategy_routes.set_dependencies(orchestrator)
    strategy_client = _client_with_router(strategy_routes.router)
    assert strategy_client.get("/api/roadmap").status_code == 200


def test_routes_system_config_governance_runtime_scheduler_services_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # system config
    config_mgr = MagicMock()
    config_mgr.get_effective_config_with_sources.return_value = (
        {"mode": "local"},
        {"mode": "env"},
    )
    config_mgr.update_config.return_value = {"status": "updated"}
    config_mgr.get_backup_list.return_value = ["b1.env"]
    config_mgr.restore_backup.return_value = {"status": "restored"}
    monkeypatch.setattr(system_config, "config_manager", config_mgr)
    cfg_client = _client_with_router(system_config.router)
    assert cfg_client.get("/api/v1/config/runtime").status_code == 200
    assert (
        cfg_client.post(
            "/api/v1/config/runtime", json={"updates": {"AI_MODE": "LOCAL"}}
        ).status_code
        == 200
    )
    assert cfg_client.get("/api/v1/config/backups").status_code == 200
    assert (
        cfg_client.post(
            "/api/v1/config/restore", json={"backup_filename": "b1.env"}
        ).status_code
        == 200
    )

    # shared system_deps mocks
    monitor = MagicMock()
    monitor.check_health = AsyncMock(return_value=None)
    monitor.get_all_services.return_value = [
        SimpleNamespace(
            name="svc1",
            service_type="core",
            status=SimpleNamespace(value="online"),
            latency_ms=1.0,
            last_check="now",
            is_critical=False,
            error_message=None,
            description="Service 1",
            endpoint="http://127.0.0.1",
        )
    ]
    monitor.get_memory_metrics.return_value = {
        "memory_usage_mb": 100,
        "memory_total_mb": 1000,
        "memory_usage_percent": 10,
        "vram_usage_mb": 0,
        "vram_total_mb": 0,
        "vram_usage_percent": 0,
    }
    monitor.get_summary.return_value = {"system_healthy": True}
    monkeypatch.setattr(system_deps, "get_service_monitor", lambda: None)

    state_manager = MagicMock()
    state_manager.is_paid_mode_enabled.return_value = True
    monkeypatch.setattr(system_deps, "get_state_manager", lambda: state_manager)

    scheduler = MagicMock()
    scheduler.get_status.return_value = {"running": True}
    scheduler.get_jobs.return_value = []
    monkeypatch.setattr(system_deps, "get_background_scheduler", lambda: scheduler)

    # system governance
    level_info = SimpleNamespace(
        name="L1",
        color="blue",
        color_name="Blue",
        description="desc",
        permissions={},
        risk_level="low",
        examples=[],
        id=10,
    )
    guard = MagicMock()
    guard.get_current_level.return_value = 10
    guard.get_level_info.return_value = level_info
    guard.set_level.return_value = True
    guard.get_all_levels.return_value = {10: level_info}
    monkeypatch.setattr(system_governance, "permission_guard", guard)
    gov_client = _client_with_router(system_governance.router)
    assert gov_client.get("/api/v1/system/cost-mode").status_code == 200
    assert (
        gov_client.post("/api/v1/system/cost-mode", json={"enable": True}).status_code
        == 200
    )
    assert gov_client.get("/api/v1/system/autonomy").status_code == 200
    assert (
        gov_client.post("/api/v1/system/autonomy", json={"level": 10}).status_code
        == 200
    )
    assert gov_client.get("/api/v1/system/autonomy/levels").status_code == 200

    # system runtime
    runtime_service = SimpleNamespace(
        name="backend",
        service_type=SimpleNamespace(value="core"),
        status=SimpleNamespace(value="running"),
        pid=123,
        port=8000,
        cpu_percent=0.1,
        memory_mb=64,
        uptime_seconds=12,
        last_log=None,
        error_message=None,
        runtime_version=None,
        actionable=True,
    )
    runtime_ctrl = MagicMock()
    runtime_ctrl.get_all_services_status.return_value = [runtime_service]
    runtime_ctrl.apply_profile.return_value = {"status": "ok"}
    runtime_ctrl.start_service.return_value = {"status": "started"}
    runtime_ctrl.get_history.return_value = []
    monkeypatch.setattr(system_runtime, "runtime_controller", runtime_ctrl)
    runtime_client = _client_with_router(system_runtime.router)
    assert runtime_client.get("/api/v1/runtime/status").status_code == 200
    assert runtime_client.post("/api/v1/runtime/profile/light").status_code == 200
    assert runtime_client.post("/api/v1/runtime/backend/start").status_code == 200
    assert runtime_client.get("/api/v1/runtime/history").status_code == 200

    # system scheduler
    sched_client = _client_with_router(system_scheduler.router)
    assert sched_client.get("/api/v1/scheduler/status").status_code == 200
    assert sched_client.get("/api/v1/scheduler/jobs").status_code == 200

    # system services and system status
    monkeypatch.setattr(system_deps, "get_service_monitor", lambda: monitor)
    system_services._services_cache = TTLCache(ttl_seconds=1.0)
    svc_client = _client_with_router(system_services.router)
    assert svc_client.get("/api/v1/system/services/svc1").status_code == 200
    status_client = _client_with_router(system_status.router)
    assert status_client.get("/api/v1/system/status").status_code == 200


@pytest.mark.asyncio
async def test_agents_and_skills_new_code_paths() -> None:
    analyst = AnalystAgent(MagicMock())
    result = await analyst.process("analyze")
    assert "RAPORT ANALITYCZNY" in result
    analyst.record_task(
        TaskMetrics(
            task_id="t1",
            complexity=ComplexityScore.LOW,
            selected_service=ServiceId.LOCAL,
            success=True,
        )
    )
    assert analyst.total_tasks == 1

    unsupported = UnsupportedAgent(MagicMock())
    unsupported_result = await unsupported.process("unknown")
    assert "Nie mam jeszcze umiejętności" in unsupported_result

    chronos_engine = MagicMock()
    chronos_engine.create_checkpoint.return_value = "cp-1"
    chronos_engine.restore_checkpoint.return_value = True
    chronos_engine.list_checkpoints.return_value = []
    chronos_engine.delete_checkpoint.return_value = True
    chronos_engine.create_timeline.return_value = True
    chronos_engine.list_timelines.return_value = ["main"]
    chrono = ChronoSkill(chronos_engine=chronos_engine)

    assert "cp-1" in await chrono.create_checkpoint(name="n")
    assert "przywrócony" in await chrono.restore_checkpoint("cp-1")
    assert "Brak checkpointów" in await chrono.list_checkpoints()
    assert "usunięty" in await chrono.delete_checkpoint("cp-1")
    assert "utworzona" in await chrono.branch_timeline("exp")
    assert "Dostępne linie" in await chrono.list_timelines()
    assert "zaawansowana funkcja" in await chrono.merge_timeline("exp", "main")


@pytest.mark.asyncio
async def test_complexity_skill_new_code_paths() -> None:
    skill = ComplexitySkill()
    assert "estimated_minutes" in await skill.estimate_time("prosty test")
    assert "Złożoność" in await skill.estimate_complexity("api i baza danych")
    assert "podział" in await skill.suggest_subtasks(
        "zaprojektuj system api i integrację"
    )
    assert "ryzyka" in await skill.flag_risks("zrób to szybko, pełny system i migracja")


@pytest.mark.asyncio
async def test_models_install_marks_active_model_by_basename(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = MagicMock()
    manager.list_local_models = AsyncMock(
        return_value=[
            {"name": "custom", "path": "/models/gemma3:1b"},
            {"name": "other", "path": "/models/other:1b"},
        ]
    )
    monkeypatch.setattr(models_install_routes, "get_model_manager", lambda: manager)
    monkeypatch.setattr(
        models_install_routes,
        "get_active_llm_runtime",
        lambda: SimpleNamespace(
            provider="ollama", to_payload=lambda: {"provider": "ollama"}
        ),
    )
    monkeypatch.setattr(
        models_install_routes,
        "probe_runtime_status",
        AsyncMock(return_value=("ok", None)),
    )
    monkeypatch.setattr(models_install_routes.SETTINGS, "LLM_MODEL_NAME", "gemma3:1b")
    monkeypatch.setattr(models_install_routes.SETTINGS, "HYBRID_LOCAL_MODEL", None)

    payload = await models_install_routes.list_models()

    assert payload["success"] is True
    active_models = [model for model in payload["models"] if model.get("active")]
    assert len(active_models) == 1
    assert active_models[0]["name"] == "custom"
    assert active_models[0]["source"] == "ollama"


@pytest.mark.asyncio
async def test_queue_manager_emergency_stop_iterates_active_tasks() -> None:
    state_manager = MagicMock()
    state_manager.update_status = AsyncMock()
    state_manager.get_all_tasks.return_value = []

    manager = QueueManager(state_manager=state_manager)
    task_id = uuid4()
    fake_task = MagicMock()
    manager.active_tasks[task_id] = fake_task

    result = await manager.emergency_stop()

    fake_task.cancel.assert_called_once()
    state_manager.update_status.assert_awaited_once_with(
        task_id,
        TaskStatus.FAILED,
        result="🚨 Zadanie przerwane przez Emergency Stop",
    )
    assert result["cancelled"] == 1
    assert result["paused"] is True


@pytest.mark.asyncio
async def test_simulation_director_cleanup_closes_sessions_and_stack() -> None:
    director = SimulationDirector.__new__(SimulationDirector)
    ok_agent = SimpleNamespace(browser_skill=SimpleNamespace(close_browser=AsyncMock()))
    err_agent = SimpleNamespace(
        browser_skill=SimpleNamespace(close_browser=AsyncMock(side_effect=RuntimeError))
    )
    director.active_simulations = {"s1": ok_agent, "s2": err_agent}
    director.stack_manager = MagicMock(
        destroy_stack=MagicMock(return_value=(True, "ok"))
    )

    await director.cleanup(stack_name="demo-stack")

    ok_agent.browser_skill.close_browser.assert_awaited_once()
    err_agent.browser_skill.close_browser.assert_awaited_once()
    director.stack_manager.destroy_stack.assert_called_once()
    assert director.active_simulations == {}


def test_lessons_store_delete_and_prune_iterate_over_snapshot(tmp_path) -> None:
    store = LessonsStore(storage_path=str(tmp_path / "lessons.json"), auto_save=False)
    now = datetime.now(timezone.utc)
    lesson_old = Lesson(
        situation="old",
        action="act",
        result="res",
        feedback="fb",
        tags=["a"],
        timestamp=(now - timedelta(days=7)).isoformat(),
    )
    lesson_new = Lesson(
        situation="new",
        action="act",
        result="res",
        feedback="fb",
        tags=["keep"],
        timestamp=now.isoformat(),
    )
    store.add_lesson(lesson_old)
    store.add_lesson(lesson_new)

    assert store.delete_by_tag("a") == 1
    assert store.prune_by_ttl(3) == 0
    assert len(store.lessons) == 1
