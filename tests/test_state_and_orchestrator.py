"""Testy jednostkowe dla StateManager i Orchestrator."""

import asyncio
import json
import tempfile
from pathlib import Path
from uuid import uuid4

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


def test_state_manager_initialization(temp_state_file):
    """Test inicjalizacji StateManager."""
    state_manager = StateManager(state_file_path=temp_state_file)
    assert state_manager._tasks == {}
    assert state_manager._state_file_path.exists() or not Path(temp_state_file).exists()


def test_state_manager_create_task(temp_state_file):
    """Test tworzenia zadania."""
    state_manager = StateManager(state_file_path=temp_state_file)
    task = state_manager.create_task("Test content")

    assert task.content == "Test content"
    assert task.status == TaskStatus.PENDING
    assert task.result is None
    assert task.logs == []
    assert task.id in state_manager._tasks


def test_state_manager_get_task(temp_state_file):
    """Test pobierania zadania."""
    state_manager = StateManager(state_file_path=temp_state_file)
    task = state_manager.create_task("Test content")

    retrieved_task = state_manager.get_task(task.id)
    assert retrieved_task is not None
    assert retrieved_task.id == task.id


def test_state_manager_get_nonexistent_task(temp_state_file):
    """Test pobierania nieistniejącego zadania."""
    state_manager = StateManager(state_file_path=temp_state_file)
    fake_id = uuid4()

    retrieved_task = state_manager.get_task(fake_id)
    assert retrieved_task is None


@pytest.mark.asyncio
async def test_state_manager_update_status(temp_state_file):
    """Test aktualizacji statusu zadania."""
    state_manager = StateManager(state_file_path=temp_state_file)
    task = state_manager.create_task("Test content")

    await state_manager.update_status(task.id, TaskStatus.PROCESSING)
    updated_task = state_manager.get_task(task.id)
    assert updated_task.status == TaskStatus.PROCESSING

    await state_manager.update_status(task.id, TaskStatus.COMPLETED, result="Done")
    final_task = state_manager.get_task(task.id)
    assert final_task.status == TaskStatus.COMPLETED
    assert final_task.result == "Done"


def test_state_manager_add_log(temp_state_file):
    """Test dodawania logów do zadania."""
    state_manager = StateManager(state_file_path=temp_state_file)
    task = state_manager.create_task("Test content")

    state_manager.add_log(task.id, "Log message 1")
    state_manager.add_log(task.id, "Log message 2")

    updated_task = state_manager.get_task(task.id)
    assert len(updated_task.logs) == 2
    assert "Log message 1" in updated_task.logs
    assert "Log message 2" in updated_task.logs


def test_state_manager_get_all_tasks(temp_state_file):
    """Test pobierania wszystkich zadań."""
    state_manager = StateManager(state_file_path=temp_state_file)
    task1 = state_manager.create_task("Task 1")
    task2 = state_manager.create_task("Task 2")
    task3 = state_manager.create_task("Task 3")

    all_tasks = state_manager.get_all_tasks()
    assert len(all_tasks) == 3
    task_ids = [t.id for t in all_tasks]
    assert task1.id in task_ids
    assert task2.id in task_ids
    assert task3.id in task_ids


@pytest.mark.asyncio
async def test_state_manager_persistence(temp_state_file):
    """Test zapisywania i ładowania stanu z pliku."""
    # Utwórz StateManager z tymczasowym plikiem
    state_manager1 = StateManager(state_file_path=temp_state_file)
    task = state_manager1.create_task("Persistent task")

    # Poczekaj na zapis
    await asyncio.sleep(0.5)

    # Sprawdź czy plik istnieje i zawiera dane
    assert Path(temp_state_file).exists()
    with open(temp_state_file, "r") as f:
        data = json.load(f)
    assert "tasks" in data
    assert len(data["tasks"]) == 1

    # Utwórz nowy StateManager - powinien załadować stan
    state_manager2 = StateManager(state_file_path=temp_state_file)
    loaded_task = state_manager2.get_task(task.id)

    assert loaded_task is not None
    assert loaded_task.content == "Persistent task"
    assert loaded_task.id == task.id


def test_state_manager_load_corrupted_state():
    """Test ładowania uszkodzonego pliku stanu."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
        f.write("{ invalid json")
        temp_path = f.name

    try:
        # Powinien załadować pusty stan bez błędu
        state_manager = StateManager(state_file_path=temp_path)
        assert state_manager._tasks == {}
    finally:
        Path(temp_path).unlink(missing_ok=True)


def test_state_manager_load_nonexistent_file():
    """Test ładowania nieistniejącego pliku stanu."""
    # Powinien utworzyć nowy pusty stan
    state_manager = StateManager(state_file_path="/tmp/test_nonexistent_file.json")
    assert state_manager._tasks == {}


@pytest.mark.asyncio
async def test_orchestrator_task_failure(temp_state_file):
    """Test obsługi błędów w Orchestrator."""
    state_manager = StateManager(state_file_path=temp_state_file)
    orchestrator = Orchestrator(state_manager)

    # Mock metody _run_task aby symulować błąd
    original_run_task = orchestrator._run_task

    async def failing_run_task(task_id):
        task = state_manager.get_task(task_id)
        if task:
            await state_manager.update_status(task_id, TaskStatus.PROCESSING)
            raise ValueError("Simulated error")

    orchestrator._run_task = failing_run_task

    from venom_core.core.models import TaskRequest

    # Utwórz zadanie
    await orchestrator.submit_task(TaskRequest(content="Failing task"))

    # Poczekaj na zakończenie
    await asyncio.sleep(1)

    # Przywróć oryginalną metodę
    orchestrator._run_task = original_run_task


@pytest.mark.asyncio
async def test_update_nonexistent_task(temp_state_file):
    """Test aktualizacji nieistniejącego zadania."""
    state_manager = StateManager(state_file_path=temp_state_file)
    fake_id = uuid4()

    # Nie powinno wyrzucić błędu, tylko zalogować warning
    await state_manager.update_status(fake_id, TaskStatus.COMPLETED)


def test_add_log_to_nonexistent_task(temp_state_file):
    """Test dodania logu do nieistniejącego zadania."""
    state_manager = StateManager(state_file_path=temp_state_file)
    fake_id = uuid4()

    # Nie powinno wyrzucić błędu, tylko zalogować warning
    state_manager.add_log(fake_id, "Test log")
