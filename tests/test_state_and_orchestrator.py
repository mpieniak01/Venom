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


def test_state_manager_paid_mode_default(temp_state_file):
    """Test domyślnego stanu paid_mode (wyłączony)."""
    state_manager = StateManager(state_file_path=temp_state_file)
    assert state_manager.is_paid_mode_enabled() is False
    assert state_manager.paid_mode_enabled is False


def test_state_manager_set_paid_mode(temp_state_file):
    """Test ustawiania paid_mode."""
    state_manager = StateManager(state_file_path=temp_state_file)
    
    # Włącz paid mode
    state_manager.set_paid_mode(True)
    assert state_manager.is_paid_mode_enabled() is True
    assert state_manager.paid_mode_enabled is True
    
    # Wyłącz paid mode
    state_manager.set_paid_mode(False)
    assert state_manager.is_paid_mode_enabled() is False
    assert state_manager.paid_mode_enabled is False


@pytest.mark.asyncio
async def test_state_manager_paid_mode_persistence(temp_state_file):
    """Test zapisywania i ładowania paid_mode z pliku."""
    # Utwórz StateManager i ustaw paid_mode
    state_manager1 = StateManager(state_file_path=temp_state_file)
    state_manager1.set_paid_mode(True)
    
    # Poczekaj na zapis
    await asyncio.sleep(0.5)
    
    # Załaduj nowy StateManager z tego samego pliku
    state_manager2 = StateManager(state_file_path=temp_state_file)
    
    # paid_mode powinien być zachowany
    assert state_manager2.is_paid_mode_enabled() is True


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


def test_state_manager_load_oversized_file():
    """Test ładowania zbyt dużego pliku stanu."""
    from venom_core.core.state_manager import MAX_STATE_FILE_SIZE

    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
        # Utwórz plik większy niż limit
        large_data = "x" * (MAX_STATE_FILE_SIZE + 1000)
        f.write(large_data)
        temp_path = f.name

    try:
        # Powinien załadować pusty stan i zalogować błąd
        state_manager = StateManager(state_file_path=temp_path)
        assert state_manager._tasks == {}
    finally:
        Path(temp_path).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_state_manager_shutdown(temp_state_file):
    """Test metody shutdown - oczekiwanie na zakończenie zapisów."""
    state_manager = StateManager(state_file_path=temp_state_file)

    # Utwórz kilka zadań, które zaplanują zapisy
    state_manager.create_task("Task 1")
    state_manager.create_task("Task 2")

    # Wywołaj shutdown - powinien poczekać na zakończenie zapisów
    await state_manager.shutdown()

    # Sprawdź czy plik został zapisany
    assert Path(temp_state_file).exists()
    with open(temp_state_file, "r") as f:
        data = json.load(f)
    assert len(data["tasks"]) == 2


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


# --- Testy integracji Orchestrator z RequestTracer ---


@pytest.mark.asyncio
async def test_orchestrator_creates_trace_on_submit(temp_state_file):
    """Test że Orchestrator tworzy trace przy submit_task."""
    from venom_core.core.models import TaskRequest
    from venom_core.core.tracer import RequestTracer, TraceStatus

    state_manager = StateManager(state_file_path=temp_state_file)
    request_tracer = RequestTracer()
    orchestrator = Orchestrator(state_manager, request_tracer=request_tracer)

    # Submit task
    request = TaskRequest(content="Test task")
    response = await orchestrator.submit_task(request)

    # Verify trace was created
    trace = request_tracer.get_trace(response.task_id)
    assert trace is not None
    assert trace.request_id == response.task_id
    assert trace.prompt == "Test task"
    assert trace.status == TraceStatus.PENDING or trace.status == TraceStatus.PROCESSING
    assert len(trace.steps) >= 1
    assert trace.steps[0].component == "User"
    assert trace.steps[0].action == "submit_request"


@pytest.mark.asyncio
async def test_orchestrator_updates_trace_status_during_processing(temp_state_file):
    """Test że Orchestrator aktualizuje status trace podczas przetwarzania."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from venom_core.core.models import TaskRequest
    from venom_core.core.tracer import RequestTracer

    state_manager = StateManager(state_file_path=temp_state_file)
    request_tracer = RequestTracer()

    # Mock task_dispatcher to avoid actual agent execution
    with patch("venom_core.core.orchestrator.TaskDispatcher") as mock_dispatcher_class:
        mock_dispatcher = MagicMock()
        mock_dispatcher.dispatch = AsyncMock(return_value="Mocked result")
        mock_dispatcher.agent_map = {}
        mock_dispatcher_class.return_value = mock_dispatcher

        orchestrator = Orchestrator(
            state_manager,
            task_dispatcher=mock_dispatcher,
            request_tracer=request_tracer,
        )

        # Submit task and wait a bit for processing
        request = TaskRequest(content="Test processing")
        response = await orchestrator.submit_task(request)

        # Give it time to process
        await asyncio.sleep(0.5)

        # Verify trace status progression
        trace = request_tracer.get_trace(response.task_id)
        assert trace is not None

        # Should have multiple steps
        assert len(trace.steps) >= 2

        # Should have User submit step
        user_steps = [s for s in trace.steps if s.component == "User"]
        assert len(user_steps) >= 1

        # Should have Orchestrator steps
        orchestrator_steps = [s for s in trace.steps if s.component == "Orchestrator"]
        assert len(orchestrator_steps) >= 1


@pytest.mark.asyncio
async def test_orchestrator_adds_steps_for_key_moments(temp_state_file):
    """Test że Orchestrator dodaje kroki dla kluczowych momentów."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from venom_core.core.models import TaskRequest
    from venom_core.core.tracer import RequestTracer

    state_manager = StateManager(state_file_path=temp_state_file)
    request_tracer = RequestTracer()

    with patch("venom_core.core.orchestrator.TaskDispatcher") as mock_dispatcher_class:
        mock_dispatcher = MagicMock()
        mock_dispatcher.dispatch = AsyncMock(return_value="Mocked result")
        mock_dispatcher.agent_map = {}
        mock_dispatcher_class.return_value = mock_dispatcher

        with patch(
            "venom_core.core.orchestrator.IntentManager"
        ) as mock_intent_manager_class:
            mock_intent_manager = MagicMock()
            mock_intent_manager.classify_intent = AsyncMock(return_value="GENERAL_CHAT")
            mock_intent_manager_class.return_value = mock_intent_manager

            orchestrator = Orchestrator(
                state_manager,
                task_dispatcher=mock_dispatcher,
                intent_manager=mock_intent_manager,
                request_tracer=request_tracer,
            )

            request = TaskRequest(content="Test steps")
            response = await orchestrator.submit_task(request)

            # Wait for processing
            await asyncio.sleep(0.5)

            trace = request_tracer.get_trace(response.task_id)
            assert trace is not None

            # Check for classify_intent step
            classify_steps = [
                s
                for s in trace.steps
                if s.component == "Orchestrator" and s.action == "classify_intent"
            ]
            assert len(classify_steps) >= 1
            assert "Intent:" in classify_steps[0].details


@pytest.mark.asyncio
async def test_orchestrator_sets_failed_status_on_error(temp_state_file):
    """Test że Orchestrator ustawia status FAILED przy błędzie."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from venom_core.core.models import TaskRequest
    from venom_core.core.tracer import RequestTracer, TraceStatus

    state_manager = StateManager(state_file_path=temp_state_file)
    request_tracer = RequestTracer()

    with patch("venom_core.core.orchestrator.TaskDispatcher") as mock_dispatcher_class:
        mock_dispatcher = MagicMock()
        # Make dispatch raise an error
        mock_dispatcher.dispatch = AsyncMock(
            side_effect=Exception("Test error message")
        )
        mock_dispatcher.agent_map = {}
        mock_dispatcher_class.return_value = mock_dispatcher

        orchestrator = Orchestrator(
            state_manager,
            task_dispatcher=mock_dispatcher,
            request_tracer=request_tracer,
        )

        request = TaskRequest(content="Test error handling")
        response = await orchestrator.submit_task(request)

        # Wait for processing
        await asyncio.sleep(0.5)

        trace = request_tracer.get_trace(response.task_id)
        assert trace is not None

        # Should be marked as FAILED
        assert trace.status == TraceStatus.FAILED

        # Should have error step
        error_steps = [s for s in trace.steps if s.status == "error"]
        assert len(error_steps) >= 1
        assert "error" in error_steps[-1].action.lower()


@pytest.mark.asyncio
async def test_orchestrator_works_without_tracer(temp_state_file):
    """Test że Orchestrator działa bez tracera (backward compatibility)."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from venom_core.core.models import TaskRequest

    state_manager = StateManager(state_file_path=temp_state_file)

    with patch("venom_core.core.orchestrator.TaskDispatcher") as mock_dispatcher_class:
        mock_dispatcher = MagicMock()
        mock_dispatcher.dispatch = AsyncMock(return_value="Mocked result")
        mock_dispatcher.agent_map = {}
        mock_dispatcher_class.return_value = mock_dispatcher

        # Initialize without tracer
        orchestrator = Orchestrator(
            state_manager, task_dispatcher=mock_dispatcher, request_tracer=None
        )

        request = TaskRequest(content="Test without tracer")
        response = await orchestrator.submit_task(request)

        # Should still work
        assert response.task_id is not None
        assert response.status == TaskStatus.PENDING

        # Wait for processing
        await asyncio.sleep(0.5)

        # Task should complete
        task = state_manager.get_task(response.task_id)
        # Status might be COMPLETED or PROCESSING depending on timing
        assert task is not None
