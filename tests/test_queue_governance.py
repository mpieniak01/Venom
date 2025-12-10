"""Test dla Dashboard v2.3 - Queue Governance."""

import asyncio
import tempfile
from pathlib import Path
from uuid import UUID

import pytest

from venom_core.core.models import TaskStatus
from venom_core.core.orchestrator import Orchestrator
from venom_core.core.state_manager import StateManager


@pytest.fixture
def temp_state_file():
    """Fixture dla tymczasowego pliku stanu."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
        temp_path = f.name
    yield temp_path
    # Cleanup
    Path(temp_path).unlink(missing_ok=True)


@pytest.fixture
def orchestrator(temp_state_file):
    """Fixture dla Orchestratora."""
    state_manager = StateManager(state_file_path=temp_state_file)
    orch = Orchestrator(state_manager)
    return orch


@pytest.mark.asyncio
async def test_pause_resume_queue(orchestrator):
    """Test wstrzymywania i wznawiania kolejki."""
    # Sprawdź początkowy stan
    assert not orchestrator.is_paused

    # Wstrzymaj kolejkę
    result = await orchestrator.pause_queue()
    assert result["success"]
    assert result["paused"]
    assert orchestrator.is_paused

    # Wznów kolejkę
    result = await orchestrator.resume_queue()
    assert result["success"]
    assert not result["paused"]
    assert not orchestrator.is_paused


@pytest.mark.asyncio
async def test_queue_status(orchestrator):
    """Test pobierania statusu kolejki."""
    status = orchestrator.get_queue_status()

    assert "paused" in status
    assert "pending" in status
    assert "active" in status
    assert "processing" in status
    assert isinstance(status["paused"], bool)
    assert isinstance(status["pending"], int)
    assert isinstance(status["active"], int)


@pytest.mark.asyncio
async def test_purge_queue(orchestrator):
    """Test czyszczenia kolejki."""
    # Utwórz zadania
    task1 = orchestrator.state_manager.create_task("Task 1")
    task2 = orchestrator.state_manager.create_task("Task 2")
    task3 = orchestrator.state_manager.create_task("Task 3")

    # Zmień status jednego zadania na PROCESSING (nie powinno być usunięte)
    await orchestrator.state_manager.update_status(task2.id, TaskStatus.PROCESSING)

    # Purge
    result = await orchestrator.purge_queue()

    assert result["success"]
    assert result["removed"] == 2  # task1 i task3

    # Sprawdź statusy
    task1_updated = orchestrator.state_manager.get_task(task1.id)
    task2_updated = orchestrator.state_manager.get_task(task2.id)
    task3_updated = orchestrator.state_manager.get_task(task3.id)

    assert task1_updated.status == TaskStatus.FAILED
    assert task2_updated.status == TaskStatus.PROCESSING  # Nie zmieniony
    assert task3_updated.status == TaskStatus.FAILED


@pytest.mark.asyncio
async def test_abort_task(orchestrator):
    """Test przerywania zadania."""
    # Utwórz zadanie
    task = orchestrator.state_manager.create_task("Test task")

    # Symuluj aktywne zadanie (dodaj do active_tasks)
    mock_task_handle = asyncio.create_task(asyncio.sleep(10))
    orchestrator.active_tasks[task.id] = mock_task_handle

    # Zmień status na PROCESSING
    await orchestrator.state_manager.update_status(task.id, TaskStatus.PROCESSING)

    # Abort
    result = await orchestrator.abort_task(task.id)

    assert result["success"]
    assert str(task.id) in result["task_id"]

    # Sprawdź czy task został usunięty z active_tasks
    assert task.id not in orchestrator.active_tasks

    # Sprawdź status
    task_updated = orchestrator.state_manager.get_task(task.id)
    assert task_updated.status == TaskStatus.FAILED

    # Cleanup
    try:
        await mock_task_handle
    except asyncio.CancelledError:
        # Oczekiwane anulowanie taska podczas czyszczenia po teście.
        pass


@pytest.mark.asyncio
async def test_abort_nonexistent_task(orchestrator):
    """Test przerywania nieistniejącego zadania."""
    fake_id = UUID("00000000-0000-0000-0000-000000000000")

    result = await orchestrator.abort_task(fake_id)

    assert not result["success"]
    assert "nie istnieje" in result["message"]


@pytest.mark.asyncio
async def test_abort_non_processing_task(orchestrator):
    """Test przerywania zadania które nie jest w trakcie wykonywania."""
    task = orchestrator.state_manager.create_task("Test task")

    # Zadanie ma status PENDING
    result = await orchestrator.abort_task(task.id)

    assert not result["success"]
    assert "nie jest aktywne" in result["message"]


@pytest.mark.asyncio
async def test_emergency_stop(orchestrator):
    """Test awaryjnego zatrzymania systemu."""
    # Utwórz kilka zadań
    task1 = orchestrator.state_manager.create_task("Task 1")
    task2 = orchestrator.state_manager.create_task("Task 2")
    task3 = orchestrator.state_manager.create_task("Task 3")

    # Symuluj aktywne zadania
    mock_task1 = asyncio.create_task(asyncio.sleep(10))
    mock_task2 = asyncio.create_task(asyncio.sleep(10))
    orchestrator.active_tasks[task1.id] = mock_task1
    orchestrator.active_tasks[task2.id] = mock_task2

    # Zmień statusy
    await orchestrator.state_manager.update_status(task1.id, TaskStatus.PROCESSING)
    await orchestrator.state_manager.update_status(task2.id, TaskStatus.PROCESSING)
    # task3 pozostaje PENDING

    # Emergency stop
    result = await orchestrator.emergency_stop()

    assert result["success"]
    assert result["paused"] is True
    assert result["cancelled"] == 2  # task1 i task2
    assert result["purged"] == 1  # task3
    assert orchestrator.is_paused is True
    assert len(orchestrator.active_tasks) == 0

    # Sprawdź statusy zadań
    task1_updated = orchestrator.state_manager.get_task(task1.id)
    task2_updated = orchestrator.state_manager.get_task(task2.id)
    task3_updated = orchestrator.state_manager.get_task(task3.id)

    assert task1_updated.status == TaskStatus.FAILED
    assert task2_updated.status == TaskStatus.FAILED
    assert task3_updated.status == TaskStatus.FAILED

    # Cleanup
    try:
        await mock_task1
    except asyncio.CancelledError:
        # Oczekiwane anulowanie taska podczas czyszczenia po teście.
        pass
    try:
        await mock_task2
    except asyncio.CancelledError:
        # Oczekiwane anulowanie taska podczas czyszczenia po teście.
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
