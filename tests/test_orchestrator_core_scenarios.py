"""Unit tests for Orchestrator core scenarios (Queue, Emergency, Kernel)."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from venom_core.core.models import TaskRequest, TaskStatus
from venom_core.core.orchestrator import Orchestrator
from venom_core.core.state_manager import StateManager
from venom_core.utils.llm_runtime import LLMRuntimeInfo


@pytest.fixture
def mock_runtime_info():
    """Mock for get_active_llm_runtime."""
    return LLMRuntimeInfo(
        provider="local",
        model_name="mock-model",
        endpoint="http://mock",
        service_type="local",
        mode="LOCAL",
        config_hash="initial_hash",
        runtime_id="local@http://mock",
    )


@pytest.fixture(autouse=True)
def patch_runtime(mock_runtime_info):
    """Automatically patch runtime for all tests."""
    with (
        patch(
            "venom_core.utils.llm_runtime.get_active_llm_runtime",
            return_value=mock_runtime_info,
        ),
    ):
        with (
            patch("venom_core.config.SETTINGS") as mock_settings,
            patch(
                "venom_core.core.orchestrator.orchestrator_dispatch.SETTINGS",
                new=mock_settings,
            ),
        ):
            mock_settings.LLM_CONFIG_HASH = "initial_hash"
            yield


@pytest.fixture
def temp_state_file():
    """Fixture for temporary state file."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
        temp_path = f.name
    yield temp_path
    Path(temp_path).unlink(missing_ok=True)


@pytest.fixture
def orchestrator_deps(temp_state_file):
    """Fixture with common dependencies."""
    state_manager = StateManager(state_file_path=temp_state_file)
    intent_manager = MagicMock()
    intent_manager.classify_intent = AsyncMock(return_value="GENERAL_CHAT")
    intent_manager.requires_tool = MagicMock(return_value=False)

    task_dispatcher = MagicMock()
    task_dispatcher.dispatch = AsyncMock(return_value="Mocked response")

    return {
        "state_manager": state_manager,
        "intent_manager": intent_manager,
        "task_dispatcher": task_dispatcher,
    }


# --- Queue Management Tests ---


@pytest.mark.asyncio
async def test_pause_and_resume_queue(orchestrator_deps):
    """Test pausing and resuming the task queue."""
    orchestrator = Orchestrator(**orchestrator_deps)

    # 1. Initial State: running
    assert not orchestrator.is_paused

    # 2. Pause Queue
    # pause_queue is async
    result = await orchestrator.pause_queue()
    assert result["paused"] is True
    assert orchestrator.is_paused

    # 3. Submit task while paused
    request = TaskRequest(content="Task while paused")
    response = await orchestrator.submit_task(request)

    # Verify status
    task = orchestrator_deps["state_manager"].get_task(response.task_id)
    assert task.status == TaskStatus.PENDING

    # 4. Resume Queue
    # resume_queue is async
    result = await orchestrator.resume_queue()
    assert result["paused"] is False
    assert not orchestrator.is_paused


@pytest.mark.asyncio
async def test_purge_queue(orchestrator_deps):
    """Test purging pending tasks from the queue."""
    orchestrator = Orchestrator(**orchestrator_deps)
    state_manager = orchestrator_deps["state_manager"]

    # Create valid Tasks
    state_manager.create_task("Task 1")
    state_manager.create_task("Task 2")

    # Mock task_manager behavior
    orchestrator.task_manager = MagicMock()
    # Mock return of async method
    orchestrator.task_manager.purge = AsyncMock(return_value={"purged": 2})

    # purge_queue is async
    result = await orchestrator.purge_queue()

    assert result["purged"] == 2
    orchestrator.task_manager.purge.assert_called_once()


# --- Emergency Procedures Tests ---


@pytest.mark.asyncio
async def test_emergency_stop(orchestrator_deps):
    """Test emergency stop procedure."""
    orchestrator = Orchestrator(**orchestrator_deps)

    orchestrator.task_manager = MagicMock()
    orchestrator.task_manager.emergency_stop = AsyncMock(
        return_value={"status": "emergency_stopped"}
    )

    # emergency_stop is async
    result = await orchestrator.emergency_stop()

    assert result["status"] == "emergency_stopped"
    orchestrator.task_manager.emergency_stop.assert_called_once()


# --- Kernel Management Tests ---


@pytest.mark.asyncio
async def test_kernel_refresh_on_drift(orchestrator_deps):
    """Test that kernel is refreshed when runtime config changes."""
    orchestrator = Orchestrator(**orchestrator_deps)

    # Mock kernel_manager
    orchestrator.kernel_manager = MagicMock()
    # Initial state tracking
    orchestrator.kernel_manager._kernel_config_hash = "initial_hash"
    # Mock refresh check to return True (simulating drift logic trigger)
    orchestrator.kernel_manager.refresh_kernel_if_needed = MagicMock(return_value=True)

    # Trigger check
    orchestrator._refresh_kernel_if_needed()

    # Verify manager method was called
    orchestrator.kernel_manager.refresh_kernel_if_needed.assert_called_once()


# --- Event Broadcasting Tests ---


@pytest.mark.asyncio
async def test_broadcast_event_structure(orchestrator_deps):
    """Verify detailed structure of broadcasted events."""
    mock_broadcaster = MagicMock()
    mock_broadcaster.broadcast_event = AsyncMock()

    orchestrator = Orchestrator(**orchestrator_deps, event_broadcaster=mock_broadcaster)

    test_data = {"key": "value"}
    # _broadcast_event is async
    await orchestrator._broadcast_event(
        "TEST_EVENT", "Test message", agent="TestAgent", data=test_data
    )

    # Verify call arguments
    args, kwargs = mock_broadcaster.broadcast_event.call_args

    # Expected structure passed to broadcaster
    assert kwargs["event_type"] == "TEST_EVENT"
    assert kwargs["message"] == "Test message"
    assert kwargs["agent"] == "TestAgent"
    assert kwargs["data"] == test_data
