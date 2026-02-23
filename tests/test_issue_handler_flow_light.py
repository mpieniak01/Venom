"""Testy jednostkowe dla IssueHandlerFlow."""

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, Mock
from uuid import uuid4

import pytest

from venom_core.core.flows.issue_handler import IssueHandlerFlow


@dataclass
class FakeTask:
    """Fake Task for testing."""

    id: str
    content: str = ""


@pytest.fixture
def mock_state_manager():
    """Fixture dla mockowego StateManager."""
    manager = MagicMock()
    manager.create_task = MagicMock(
        return_value=FakeTask(id="task-123", content="Test")
    )
    manager.add_log = MagicMock()
    manager.update_status = AsyncMock()  # Must be AsyncMock for await
    return manager


@pytest.fixture
def mock_task_dispatcher():
    """Fixture dla mockowego TaskDispatcher."""
    dispatcher = MagicMock()
    dispatcher.agent_map = {}
    return dispatcher


@pytest.fixture
def mock_event_broadcaster():
    """Fixture dla mockowego EventBroadcaster."""
    broadcaster = MagicMock()
    broadcaster.broadcast_event = AsyncMock()
    return broadcaster


@pytest.fixture
def issue_handler_flow(
    mock_state_manager, mock_task_dispatcher, mock_event_broadcaster
):
    """Fixture dla IssueHandlerFlow."""
    return IssueHandlerFlow(
        state_manager=mock_state_manager,
        task_dispatcher=mock_task_dispatcher,
        event_broadcaster=mock_event_broadcaster,
    )


def test_issue_handler_flow_initialization(
    mock_state_manager, mock_task_dispatcher, mock_event_broadcaster
):
    """Test inicjalizacji IssueHandlerFlow."""
    flow = IssueHandlerFlow(
        state_manager=mock_state_manager,
        task_dispatcher=mock_task_dispatcher,
        event_broadcaster=mock_event_broadcaster,
    )

    assert flow.state_manager == mock_state_manager
    assert flow.task_dispatcher == mock_task_dispatcher
    assert flow.event_broadcaster == mock_event_broadcaster


@pytest.mark.asyncio
async def test_execute_without_integrator(issue_handler_flow):
    """Test wykonania gdy brak IntegratorAgent."""
    result = await issue_handler_flow.execute(issue_number=123)

    assert result["success"] is False
    assert "nie jest dostępny" in result["message"]


@pytest.mark.asyncio
async def test_execute_with_integrator_error(issue_handler_flow, mock_task_dispatcher):
    """Test wykonania gdy Integrator zwraca błąd."""
    # Mock integrator agent
    mock_integrator = MagicMock()
    mock_integrator.handle_issue = AsyncMock(return_value="❌ Issue not found")
    mock_task_dispatcher.agent_map["GIT_OPERATIONS"] = mock_integrator

    result = await issue_handler_flow.execute(issue_number=999)

    assert result["success"] is False
    mock_integrator.handle_issue.assert_called_once_with(999)


@pytest.mark.asyncio
async def test_execute_success_path(issue_handler_flow, mock_task_dispatcher):
    """Test pomyślnego wykonania flow."""
    # Mock integrator agent
    mock_integrator = MagicMock()
    mock_integrator.handle_issue = AsyncMock(
        return_value="✓ Issue #123: Fix bug in auth"
    )
    mock_integrator.process = AsyncMock(return_value="✓ PR created")
    mock_integrator.finalize_issue = AsyncMock(return_value="✓ Issue finalized")
    mock_task_dispatcher.agent_map["GIT_OPERATIONS"] = mock_integrator

    # Mock architect agent
    mock_architect = MagicMock()
    mock_architect.process = AsyncMock(return_value="Plan: Fix auth bug")
    mock_task_dispatcher.agent_map["ARCHITECT"] = mock_architect

    # Mock coder agent
    mock_coder = MagicMock()
    mock_coder.process = AsyncMock(return_value="Code implemented")
    mock_task_dispatcher.agent_map["CODER"] = mock_coder

    result = await issue_handler_flow.execute(issue_number=123)

    # Check that integrator was called
    mock_integrator.handle_issue.assert_called_once_with(123)


@pytest.mark.asyncio
async def test_broadcast_event_called(issue_handler_flow, mock_event_broadcaster):
    """Test że eventy są broadcastowane."""
    result = await issue_handler_flow.execute(issue_number=123)

    # Verify event broadcasting was called
    mock_event_broadcaster.broadcast_event.assert_called()


def test_issue_handler_flow_without_event_broadcaster(
    mock_state_manager, mock_task_dispatcher
):
    """Test inicjalizacji bez event broadcastera."""
    flow = IssueHandlerFlow(
        state_manager=mock_state_manager,
        task_dispatcher=mock_task_dispatcher,
        event_broadcaster=None,
    )

    assert flow.event_broadcaster is None


@pytest.mark.asyncio
async def test_execute_with_invalid_issue_number(issue_handler_flow):
    """Test z niepoprawnym numerem issue."""
    result = await issue_handler_flow.execute(issue_number=-1)

    # Should still attempt to process even with negative number
    assert isinstance(result, dict)
    assert "success" in result


@pytest.mark.asyncio
async def test_execute_creates_task(issue_handler_flow, mock_state_manager):
    """Test że execute tworzy zadanie w state managerze."""
    await issue_handler_flow.execute(issue_number=123)

    # Verify that create_task was called
    mock_state_manager.create_task.assert_called_once()
    call_args = mock_state_manager.create_task.call_args[1]
    assert "Issue #123" in call_args["content"]


@pytest.mark.asyncio
async def test_execute_logs_progress(issue_handler_flow, mock_state_manager):
    """Test że execute loguje postęp."""
    await issue_handler_flow.execute(issue_number=123)

    # Verify that add_log was called
    assert mock_state_manager.add_log.call_count > 0


@pytest.mark.asyncio
async def test_execute_with_exception(issue_handler_flow, mock_task_dispatcher):
    """Test obsługi wyjątku podczas wykonania."""
    # Mock integrator that raises exception
    mock_integrator = MagicMock()
    mock_integrator.handle_issue = AsyncMock(side_effect=Exception("Network error"))
    mock_task_dispatcher.agent_map["GIT_OPERATIONS"] = mock_integrator

    result = await issue_handler_flow.execute(issue_number=123)

    # Should handle exception gracefully
    assert isinstance(result, dict)
