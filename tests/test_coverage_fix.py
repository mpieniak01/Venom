from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from venom_core.agents.analyst import AnalystAgent, TaskMetrics
from venom_core.agents.unsupported import UnsupportedAgent

# Import modules to test
from venom_core.api.routes import agents as agents_routes
from venom_core.api.routes import calendar as calendar_routes
from venom_core.api.routes import memory_projection as memory_projection_routes
from venom_core.api.routes import nodes as nodes_routes
from venom_core.api.routes import queue as queue_routes
from venom_core.api.routes import system_status as system_status_routes
from venom_core.core.model_router import ComplexityScore, ServiceId
from venom_core.execution.skills.chrono_skill import ChronoSkill
from venom_core.execution.skills.complexity_skill import ComplexitySkill

# --- Agents & Skills Tests ---


@pytest.mark.asyncio
async def test_analyst_agent():
    mock_kernel = MagicMock()
    agent = AnalystAgent(mock_kernel)

    # Test process
    res = await agent.process("analyze")
    assert "RAPORT ANALITYCZNY" in res

    # Test record_task
    metrics = TaskMetrics(
        task_id="t1",
        complexity=ComplexityScore.LOW,
        selected_service=ServiceId.LOCAL,
        success=True,
        cost_usd=0.01,
    )
    agent.record_task(metrics)
    assert agent.total_tasks == 1

    # Test generate_report
    report = agent.generate_report()
    assert "STATYSTYKI OGÓLNE" in report


@pytest.mark.asyncio
async def test_unsupported_agent():
    mock_kernel = MagicMock()
    agent = UnsupportedAgent(mock_kernel)
    res = await agent.process("unknown")
    assert "Nie mam jeszcze umiejętności" in res


@pytest.mark.asyncio
async def test_chrono_skill():
    mock_engine = MagicMock()
    skill = ChronoSkill(chronos_engine=mock_engine)

    # Test create_checkpoint
    mock_engine.create_checkpoint.return_value = "cp-123"
    res = await skill.create_checkpoint(name="test", description="desc")
    assert "cp-123" in res

    # Test list_checkpoints
    mock_engine.list_checkpoints.return_value = []
    res = await skill.list_checkpoints()
    assert "Brak checkpointów" in res


def test_complexity_skill():
    skill = ComplexitySkill()

    # Test estimate_time
    res = skill.estimate_time("napisz prostą funkcję hello world")
    assert "estimated_minutes" in res

    # Test estimate_complexity
    res = skill.estimate_complexity("zaprojektuj system mikroserwisów enterprise")
    assert "EPIC" in res or "HIGH" in res

    # Test suggest_subtasks
    res = skill.suggest_subtasks("zaprojektuj system")
    assert "1." in res

    # Test flag_risks
    res = skill.flag_risks("zrób to szybko na wczoraj wszystkie funkcje")
    assert "Ryzyko" in res or "Presja" in res


# --- API Routes Tests ---


class MockApp:
    def __init__(self):
        self.app = FastAPI()
        self.client = TestClient(self.app)


@pytest.fixture
def mock_app():
    return MockApp()


def test_agents_routes(mock_app):
    # Mock dependencies
    mock_gardener = MagicMock()
    mock_gardener.get_status.return_value = "idle"
    mock_shadow = MagicMock()
    mock_shadow.get_status.return_value = {"enabled": True}
    mock_watcher = MagicMock()
    mock_watcher.get_status.return_value = "watching"
    mock_documenter = MagicMock()
    mock_documenter.get_status.return_value = "ready"

    agents_routes.set_dependencies(
        gardener_agent=mock_gardener,
        shadow_agent=mock_shadow,
        file_watcher=mock_watcher,
        documenter_agent=mock_documenter,
        orchestrator=MagicMock(),
    )

    mock_app.app.include_router(agents_routes.router)

    # Test endpoints
    resp = mock_app.client.get("/api/v1/gardener/status")
    assert resp.status_code == 200
    assert resp.json()["gardener"] == "idle"

    resp = mock_app.client.get("/api/v1/watcher/status")
    assert resp.status_code == 200
    assert resp.json()["watcher"] == "watching"

    resp = mock_app.client.get("/api/v1/documenter/status")
    assert resp.status_code == 200
    assert resp.json()["documenter"] == "ready"

    resp = mock_app.client.get("/api/v1/shadow/status")
    assert resp.status_code == 200
    assert resp.json()["shadow_agent"]["enabled"] is True


def test_calendar_routes(mock_app):
    mock_skill = MagicMock()
    # Mocking read_agenda to return a string as per code
    mock_skill.read_agenda.return_value = "Brak wydarzeń\n"
    mock_skill.credentials_available = True
    calendar_routes.set_dependencies(google_calendar_skill=mock_skill)

    mock_app.app.include_router(calendar_routes.router)

    resp = mock_app.client.get("/api/v1/calendar/events")
    assert resp.status_code == 200


def test_memory_projection_routes(mock_app):
    mock_store = MagicMock()
    mock_store.list_entries.return_value = []
    # Mock embedding service
    mock_store.embedding_service = MagicMock()

    memory_projection_routes.set_dependencies(vector_store=mock_store)

    mock_app.app.include_router(memory_projection_routes.router)

    # Should return 'updated': 0 since we mock empty entries
    resp = mock_app.client.post("/api/v1/memory/embedding-project?limit=10")
    assert resp.status_code == 200
    assert resp.json()["updated"] == 0


def test_nodes_routes(mock_app):
    mock_manager = MagicMock()
    mock_manager.list_nodes.return_value = []
    nodes_routes.set_dependencies(node_manager=mock_manager)

    mock_app.app.include_router(nodes_routes.router)

    resp = mock_app.client.get("/api/v1/nodes")
    assert resp.status_code == 200
    assert resp.json()["count"] == 0


def test_queue_routes(mock_app):
    mock_orch = MagicMock()
    mock_orch.get_queue_status.return_value = {"size": 0, "status": "idle"}
    queue_routes.set_dependencies(orchestrator=mock_orch)

    # We also need to clear cache or mock it to ensure get_queue_status is called
    queue_routes._queue_cache.clear()

    mock_app.app.include_router(queue_routes.router)

    resp = mock_app.client.get("/api/v1/queue/status")
    assert resp.status_code == 200
    assert resp.json()["size"] == 0


def test_system_status_routes(mock_app):
    mock_monitor = MagicMock()
    mock_monitor.get_memory_metrics.return_value = {
        "memory_usage_mb": 100,
        "memory_total_mb": 1000,
        "memory_usage_percent": 10,
        "vram_usage_mb": 0,
        "vram_total_mb": 0,
        "vram_usage_percent": 0,
    }
    mock_monitor.get_summary.return_value = {"system_healthy": True}

    # patch get_service_monitor in system_deps
    with patch(
        "venom_core.api.routes.system_deps.get_service_monitor",
        return_value=mock_monitor,
    ):
        mock_app.app.include_router(system_status_routes.router)
        resp = mock_app.client.get("/api/v1/system/status")
        assert resp.status_code == 200
        assert resp.json()["system_healthy"] is True
