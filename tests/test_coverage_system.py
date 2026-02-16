import sys
from unittest.mock import AsyncMock, MagicMock, patch

# --- Mocks for Heavy Dependencies (only for imports in this module) ---
_module_backup: dict[str, object | None] = {}


def _set_mocked_module(name: str, module: object | None = None) -> object:
    _module_backup[name] = sys.modules.get(name)
    mocked = module if module is not None else MagicMock()
    sys.modules[name] = mocked  # type: ignore[assignment]
    return mocked


_set_mocked_module("semantic_kernel")
_set_mocked_module("semantic_kernel.kernel")
_set_mocked_module("semantic_kernel.contents")
_set_mocked_module("semantic_kernel.contents.chat_history")
_set_mocked_module("semantic_kernel.contents.chat_message_content")
_set_mocked_module("semantic_kernel.contents.function_result_content")
_set_mocked_module("semantic_kernel.contents.text_content")
_set_mocked_module("semantic_kernel.contents.utils")
_set_mocked_module("semantic_kernel.contents.utils.author_role")
_set_mocked_module("semantic_kernel.connectors")
_set_mocked_module("semantic_kernel.connectors.ai")
_set_mocked_module("semantic_kernel.connectors.ai.open_ai")

config_module = MagicMock()
config_module.SETTINGS = MagicMock()
config_module.SETTINGS.AI_MODE = "HYBRID"
_set_mocked_module("venom_core.config", config_module)

# Mock venom_core.services.config_manager
mock_config_manager = MagicMock()
config_manager_module = MagicMock()
config_manager_module.config_manager = mock_config_manager
_set_mocked_module("venom_core.services.config_manager", config_manager_module)

# Mock venom_core.core.permission_guard
mock_permission_guard = MagicMock()
permission_guard_module = MagicMock()
permission_guard_module.permission_guard = mock_permission_guard
_set_mocked_module("venom_core.core.permission_guard", permission_guard_module)

# Mock venom_core.api.routes.system_deps
mock_system_deps = MagicMock()
_set_mocked_module("venom_core.api.routes.system_deps", mock_system_deps)

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from venom_core.agents.unsupported import UnsupportedAgent  # noqa: E402

# Import modules to test
from venom_core.api.routes import nodes as nodes_routes  # noqa: E402
from venom_core.api.routes import queue as queue_routes  # noqa: E402
from venom_core.api.routes import strategy  # noqa: E402
from venom_core.api.routes import system_config  # noqa: E402
from venom_core.api.routes import system_governance  # noqa: E402
from venom_core.api.routes import system_runtime  # noqa: E402
from venom_core.api.routes import system_scheduler  # noqa: E402
from venom_core.api.routes import system_services  # noqa: E402
from venom_core.utils.ttl_cache import TTLCache  # noqa: E402

pytestmark = pytest.mark.integration

for _name, _original in _module_backup.items():
    if _original is None:
        sys.modules.pop(_name, None)
    else:
        sys.modules[_name] = _original  # type: ignore[assignment]

# --- App Fixture ---


class MockApp:
    def __init__(self):
        self.app = FastAPI()
        self.client = TestClient(self.app, client=("127.0.0.1", 50000))


@pytest.fixture
def mock_app():
    return MockApp()


# --- System Config Tests ---


def test_system_config_routes(mock_app):
    mock_app.app.include_router(system_config.router)

    # Test get_runtime_config
    mock_config_manager.get_config.return_value = {"key": "val"}
    resp = mock_app.client.get("/api/v1/config/runtime")
    assert resp.status_code == 200
    assert resp.json()["config"]["key"] == "val"

    # Test update_runtime_config
    mock_config_manager.update_config.return_value = {"status": "updated"}
    resp = mock_app.client.post(
        "/api/v1/config/runtime", json={"updates": {"key": "new"}}
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "updated"
    mock_config_manager.update_config.assert_called_with({"key": "new"})

    # Test get_config_backups
    mock_config_manager.get_backup_list.return_value = ["backup1.env"]
    resp = mock_app.client.get("/api/v1/config/backups")
    assert resp.status_code == 200
    assert "backup1.env" in resp.json()["backups"]

    # Test restore_config_backup
    mock_config_manager.restore_backup.return_value = {"status": "restored"}
    resp = mock_app.client.post(
        "/api/v1/config/restore", json={"backup_filename": "backup1.env"}
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "restored"
    mock_config_manager.restore_backup.assert_called_with("backup1.env")


# --- System Governance Tests ---


def test_system_governance_routes(mock_app):
    mock_app.app.include_router(system_governance.router)

    # Mock State Manager
    mock_state = MagicMock()
    mock_system_deps.get_state_manager.return_value = mock_state

    # Test get_cost_mode
    mock_state.is_paid_mode_enabled.return_value = True
    resp = mock_app.client.get("/api/v1/system/cost-mode")
    assert resp.status_code == 200
    assert resp.json()["enabled"] is True

    # Test set_cost_mode (Enable)
    resp = mock_app.client.post("/api/v1/system/cost-mode", json={"enable": True})
    assert resp.status_code == 200
    assert resp.json()["enabled"] is True
    mock_state.enable_paid_mode.assert_called_once()

    # Test set_cost_mode (Disable)
    resp = mock_app.client.post("/api/v1/system/cost-mode", json={"enable": False})
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False
    mock_state.disable_paid_mode.assert_called_once()

    # Test get_autonomy_level
    mock_permission_guard.get_current_level.return_value = 10
    mock_level_info = MagicMock()
    mock_level_info.name = "Test Level"
    mock_level_info.color = "blue"
    mock_level_info.description = "desc"
    mock_level_info.permissions = {}
    mock_level_info.risk_level = "low"
    mock_level_info.color_name = "Blue"
    mock_permission_guard.get_level_info.return_value = mock_level_info

    resp = mock_app.client.get("/api/v1/system/autonomy")
    assert resp.status_code == 200
    assert resp.json()["current_level"] == 10

    # Test set_autonomy_level
    mock_permission_guard.set_level.return_value = True
    resp = mock_app.client.post("/api/v1/system/autonomy", json={"level": 20})
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"

    # Test get_all_autonomy_levels
    mock_permission_guard.get_all_levels.return_value = {
        10: MagicMock(id=10, name="L1"),
        20: MagicMock(id=20, name="L2"),
    }
    resp = mock_app.client.get("/api/v1/system/autonomy/levels")
    assert resp.status_code == 200
    assert len(resp.json()["levels"]) == 2


# --- Strategy Routes Tests ---


@pytest.mark.asyncio
async def test_strategy_routes(mock_app):
    mock_app.app.include_router(strategy.router)

    # Mock Orchestrator and dependencies
    mock_orch = MagicMock()
    mock_dispatcher = MagicMock()
    mock_orch.task_dispatcher = mock_dispatcher

    # Goal Store
    mock_goal = MagicMock()
    mock_dispatcher.goal_store = mock_goal

    # Executive Agent
    mock_exec = AsyncMock()
    mock_dispatcher.executive_agent = mock_exec

    strategy.set_dependencies(orchestrator=mock_orch)

    # Test get_roadmap
    mock_goal.get_vision.return_value = MagicMock(
        title="Vision", status=MagicMock(value="PLANNED")
    )
    mock_goal.get_milestones.return_value = []
    mock_goal.generate_roadmap_report.return_value = "Report"

    resp = mock_app.client.get("/api/roadmap")
    assert resp.status_code == 200
    assert resp.json()["vision"]["title"] == "Vision"

    # Test create_roadmap
    mock_exec.create_roadmap.return_value = {"roadmap": "created"}
    resp = mock_app.client.post("/api/roadmap/create", json={"vision": "new vision"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"

    # Test get_roadmap_status
    mock_exec.generate_status_report.return_value = "Status Report"
    resp = mock_app.client.get("/api/roadmap/status")
    assert resp.status_code == 200
    assert resp.json()["report"] == "Status Report"

    # Test start_campaign
    mock_orch.execute_campaign_mode = AsyncMock(return_value="Campaign Started")
    resp = mock_app.client.post("/api/campaign/start")
    assert resp.status_code == 200
    assert resp.json()["result"] == "Campaign Started"


# --- System Runtime Tests ---


def test_system_runtime_routes(mock_app):
    mock_app.app.include_router(system_runtime.router)

    # Mock Runtime Controller
    mock_runtime_ctrl = MagicMock()
    sys.modules[
        "venom_core.services.runtime_controller"
    ].runtime_controller = mock_runtime_ctrl
    # Re-import or patch where it is used
    # system_runtime imports runtime_controller directly
    # We can patch it in the module
    with patch(
        "venom_core.api.routes.system_runtime.runtime_controller", mock_runtime_ctrl
    ):
        # Test get_runtime_status
        mock_service = MagicMock()
        mock_service.name = "backend"
        mock_service.service_type.value = "core"
        mock_service.status.value = "running"
        mock_service.pid = 123
        mock_service.port = 8000
        mock_service.cpu_percent = 1.0
        mock_service.memory_mb = 100
        mock_service.uptime_seconds = 1000
        mock_service.last_log = "log"
        mock_service.error_message = None
        mock_service.runtime_version = None
        mock_service.actionable = True

        mock_runtime_ctrl.get_all_services_status.return_value = [mock_service]

        # Mock Service Monitor via system_deps
        mock_monitor = MagicMock()
        mock_system_deps.get_service_monitor.return_value = mock_monitor
        mock_monitor.get_all_services.return_value = []  # Empty for simplicity

        resp = mock_app.client.get("/api/v1/runtime/status")
        assert resp.status_code == 200
        assert resp.json()["services"][0]["name"] == "backend"

        # Test apply_runtime_profile
        mock_runtime_ctrl.apply_profile.return_value = {"status": "applied"}
        resp = mock_app.client.post("/api/v1/runtime/profile/full")
        assert resp.status_code == 200
        assert resp.json()["status"] == "applied"

        # Test runtime_service_action
        mock_runtime_ctrl.restart_service.return_value = {"status": "restarted"}
        resp = mock_app.client.post("/api/v1/runtime/backend/restart")
        assert resp.status_code == 200
        assert resp.json()["status"] == "restarted"

        # Test runtime_service_action (Invalid action)
        resp = mock_app.client.post("/api/v1/runtime/backend/dance")
        assert resp.status_code == 400

        # Test get_runtime_history
        mock_runtime_ctrl.get_history.return_value = [{"action": "restart"}]
        resp = mock_app.client.get("/api/v1/runtime/history")
        assert resp.status_code == 200
        assert len(resp.json()["history"]) == 1


# --- System Scheduler Tests ---


@pytest.mark.asyncio
async def test_system_scheduler_routes(mock_app):
    mock_app.app.include_router(system_scheduler.router)

    mock_scheduler = MagicMock()  # Changed to MagicMock as methods are sync
    mock_system_deps.get_background_scheduler.return_value = mock_scheduler

    # Test get_scheduler_status
    mock_scheduler.get_status.return_value = {"running": True}
    resp = mock_app.client.get("/api/v1/scheduler/status")
    assert resp.status_code == 200
    assert resp.json()["scheduler"]["running"] is True

    # Test get_scheduler_jobs
    mock_scheduler.get_jobs.return_value = ["job1"]
    resp = mock_app.client.get("/api/v1/scheduler/jobs")
    assert resp.status_code == 200
    assert "job1" in resp.json()["jobs"]

    # Test pause_scheduler
    # pause_all_jobs is awaited in the route, so it MUST be async
    mock_scheduler.pause_all_jobs = AsyncMock()
    resp = mock_app.client.post("/api/v1/scheduler/pause")
    assert resp.status_code == 200
    assert "paused" in resp.json()["message"]
    mock_scheduler.pause_all_jobs.assert_called_once()

    # Test resume_scheduler
    # resume_all_jobs is awaited
    mock_scheduler.resume_all_jobs = AsyncMock()
    resp = mock_app.client.post("/api/v1/scheduler/resume")
    assert resp.status_code == 200
    assert "resumed" in resp.json()["message"]
    mock_scheduler.resume_all_jobs.assert_called_once()


# --- System Services Tests ---


@pytest.mark.asyncio
async def test_system_services_routes(mock_app):
    mock_app.app.include_router(system_services.router)

    mock_monitor = MagicMock()  # Changed to MagicMock
    mock_system_deps.get_service_monitor.return_value = mock_monitor

    # check_health is awaited in route
    mock_monitor.check_health = AsyncMock()

    # Clear cache
    system_services._services_cache = TTLCache(ttl_seconds=1.0)  # Reset cache

    # Mock Service objects
    mock_svc = MagicMock()
    mock_svc.name = "db"
    mock_svc.service_type = "database"
    mock_svc.status.value = "online"
    mock_svc.latency_ms = 10
    mock_svc.last_check = "now"
    mock_svc.is_critical = True
    mock_svc.error_message = None
    mock_svc.description = "Database"

    # get_all_services is NOT awaited in route, so it is sync
    mock_monitor.get_all_services.return_value = [mock_svc]

    # Test get_all_services
    resp = mock_app.client.get("/api/v1/system/services")
    assert resp.status_code == 200
    assert resp.json()["services"][0]["name"] == "db"
    mock_monitor.check_health.assert_called_once()

    # Test get_service_status
    resp = mock_app.client.get("/api/v1/system/services/db")
    assert resp.status_code == 200
    assert resp.json()["service"]["name"] == "db"

    # Test get_service_status (Not Found)
    resp = mock_app.client.get("/api/v1/system/services/missing")
    assert resp.status_code == 404


# --- Queue Routes Tests (Expanded) ---


@pytest.mark.asyncio
async def test_queue_routes_expanded(mock_app):
    mock_app.app.include_router(queue_routes.router)

    # Mock Orchestrator
    mock_orch = AsyncMock()
    queue_routes.set_dependencies(orchestrator=mock_orch)
    queue_routes._queue_cache.clear()

    # Test get_queue_status (Sync wrapper in route, but orchestrator method might be sync?)
    # The route is def list_queue... wait, queue.py: def get_queue_status(): ... status = _orchestrator.get_queue_status()
    # It assumes _orchestrator.get_queue_status() is sync if called from sync route?
    # Actually queue.py:39 def get_queue_status() is sync.
    # So we should mock get_queue_status as sync or value.
    mock_orch.get_queue_status = MagicMock(return_value={"status": "running"})

    resp = mock_app.client.get("/api/v1/queue/status")
    assert resp.status_code == 200
    assert resp.json()["status"] == "running"

    # Test pause_queue (Async route)
    mock_orch.pause_queue.return_value = {"status": "paused"}
    resp = mock_app.client.post("/api/v1/queue/pause")
    assert resp.status_code == 200
    mock_orch.pause_queue.assert_called_once()

    # Test resume_queue (Async route)
    mock_orch.resume_queue.return_value = {"status": "resumed"}
    resp = mock_app.client.post("/api/v1/queue/resume")
    assert resp.status_code == 200
    mock_orch.resume_queue.assert_called_once()

    # Test purge_queue
    mock_orch.purge_queue.return_value = {"removed": 5}
    resp = mock_app.client.post("/api/v1/queue/purge")
    assert resp.status_code == 200
    assert resp.json()["removed"] == 5

    # Test emergency_stop
    mock_orch.emergency_stop.return_value = {"status": "stopped"}
    resp = mock_app.client.post("/api/v1/queue/emergency-stop")
    assert resp.status_code == 200

    # Test abort_task
    task_id = "12345678-1234-5678-1234-567812345678"
    mock_orch.abort_task.return_value = {"success": True}
    resp = mock_app.client.post(f"/api/v1/queue/task/{task_id}/abort")
    assert resp.status_code == 200

    # Test abort_task failure
    mock_orch.abort_task.return_value = {"success": False, "message": "Not found"}
    resp = mock_app.client.post(f"/api/v1/queue/task/{task_id}/abort")
    assert resp.status_code == 404


# --- Nodes Routes Tests (Expanded) ---


@pytest.mark.asyncio
async def test_nodes_routes_expanded(mock_app):
    mock_app.app.include_router(nodes_routes.router)

    mock_manager = MagicMock()
    nodes_routes.set_dependencies(node_manager=mock_manager)

    # Mock Node object
    mock_node = MagicMock()
    mock_node.to_dict.return_value = {"id": "n1", "status": "online"}
    mock_node.is_online = True

    mock_manager.list_nodes.return_value = [mock_node]
    mock_manager.get_node.return_value = mock_node

    # Test list_nodes
    resp = mock_app.client.get("/api/v1/nodes")
    assert resp.status_code == 200
    assert len(resp.json()["nodes"]) == 1

    # Test get_node_info
    resp = mock_app.client.get("/api/v1/nodes/n1")
    assert resp.status_code == 200
    assert resp.json()["node"]["id"] == "n1"

    # Test get_node_info (Not Found)
    mock_manager.get_node.return_value = None
    resp = mock_app.client.get("/api/v1/nodes/missing")
    assert resp.status_code == 404

    # Test execute_on_node
    # Reset helper logic
    mock_manager.get_node.return_value = mock_node  # Found
    mock_manager.execute_on_node = AsyncMock(return_value={"result": "ok"})

    payload = {
        "skill_name": "TestSkill",
        "method_name": "test",
        "parameters": {},
        "timeout": 10,
    }
    resp = mock_app.client.post("/api/v1/nodes/n1/execute", json=payload)
    assert resp.status_code == 200
    assert resp.json()["result"]["result"] == "ok"

    # Test execute_on_node (Offline)
    mock_node.is_online = False
    resp = mock_app.client.post("/api/v1/nodes/n1/execute", json=payload)
    assert resp.status_code == 400


# --- Unsupported Agent Test ---


@pytest.mark.asyncio
async def test_unsupported_agent():
    mock_kernel = MagicMock()
    # Mock BaseAgent init if needed, but since we are testing the class directly
    # and we mocked semantic_kernel, it should be fine.

    agent = UnsupportedAgent(mock_kernel)

    res = await agent.process("help")
    assert "Nie mam jeszcze umiejętności" in res
