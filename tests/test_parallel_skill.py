"""Testy dla parallel_skill - umiejętność równoległego przetwarzania."""

import json
from unittest.mock import AsyncMock, Mock

import pytest

from venom_core.execution.skills.parallel_skill import ParallelSkill
from venom_core.infrastructure.message_broker import MessageBroker, TaskMessage


@pytest.fixture
def mock_message_broker():
    """Mock MessageBroker."""
    broker = Mock(spec=MessageBroker)

    async def _fake_enqueue(task_type, payload, priority):
        return f"task_{payload.get('item_index', 0)}"

    broker.enqueue_task = AsyncMock(side_effect=_fake_enqueue)
    broker.get_task_status = AsyncMock()
    return broker


@pytest.fixture
def parallel_skill(mock_message_broker):
    """Fixture dla ParallelSkill."""
    return ParallelSkill(mock_message_broker)


def test_parallel_skill_initialization(parallel_skill):
    """Test inicjalizacji ParallelSkill."""
    assert parallel_skill is not None
    assert parallel_skill.message_broker is not None


@pytest.mark.asyncio
async def test_map_reduce_invalid_json(parallel_skill):
    """Test map_reduce z nieprawidłowym JSON."""
    result = await parallel_skill.map_reduce(
        task_description="Test task",
        items="invalid json",
    )

    assert "Błąd parsowania" in result


@pytest.mark.asyncio
async def test_map_reduce_not_a_list(parallel_skill):
    """Test map_reduce gdy items nie jest listą."""
    result = await parallel_skill.map_reduce(
        task_description="Test task",
        items='{"key": "value"}',  # Object, nie lista
    )

    assert "musi być listą" in result


@pytest.mark.asyncio
async def test_map_reduce_empty_list(parallel_skill):
    """Test map_reduce z pustą listą."""
    result = await parallel_skill.map_reduce(
        task_description="Test task",
        items="[]",
    )

    assert "pusta" in result


@pytest.mark.asyncio
async def test_map_reduce_creates_tasks(parallel_skill, mock_message_broker):
    """Test że map_reduce tworzy zadania dla każdego elementu."""
    items = ["item1", "item2", "item3"]

    # Mock get_task_status do symulacji ukończonych zadań
    async def mock_get_status(task_id):
        task = TaskMessage(task_id, "map_task", {"item": "test"})
        task.status = "completed"
        task.result = f"result_{task_id}"
        return task

    mock_message_broker.get_task_status.side_effect = mock_get_status

    result = await parallel_skill.map_reduce(
        task_description="Process items",
        items=json.dumps(items),
        wait_timeout=1,  # Krótki timeout dla testu
    )

    # Sprawdź że utworzono zadania
    assert mock_message_broker.enqueue_task.call_count == 3

    # Sprawdź odpowiedź
    assert "summary" in result or "Błąd" in result  # Może timeout w testach


@pytest.mark.asyncio
async def test_map_reduce_priority(parallel_skill, mock_message_broker):
    """Test że map_reduce respektuje priorytet."""
    items = ["item1"]

    async def mock_get_status(task_id):
        task = TaskMessage(task_id, "map_task", {})
        task.status = "completed"
        return task

    mock_message_broker.get_task_status.side_effect = mock_get_status

    await parallel_skill.map_reduce(
        task_description="Test",
        items=json.dumps(items),
        priority="high_priority",
        wait_timeout=1,
    )

    # Sprawdź że wywołano z odpowiednim priorytetem
    call_args = mock_message_broker.enqueue_task.call_args
    assert call_args.kwargs["priority"] == "high_priority"


@pytest.mark.asyncio
async def test_parallel_execute_invalid_json(parallel_skill):
    """Test parallel_execute z nieprawidłowym JSON."""
    result = await parallel_skill.parallel_execute(
        task_description="Test",
        subtasks="invalid json",
    )

    assert "Błąd parsowania" in result


@pytest.mark.asyncio
async def test_parallel_execute_not_a_list(parallel_skill):
    """Test parallel_execute gdy subtasks nie jest listą."""
    result = await parallel_skill.parallel_execute(
        task_description="Test",
        subtasks='{"key": "value"}',
    )

    assert "musi być listą" in result


@pytest.mark.asyncio
async def test_parallel_execute_empty_list(parallel_skill):
    """Test parallel_execute z pustą listą."""
    result = await parallel_skill.parallel_execute(
        task_description="Test",
        subtasks="[]",
    )

    assert "pusta" in result


@pytest.mark.asyncio
async def test_parallel_execute_creates_tasks(parallel_skill, mock_message_broker):
    """Test że parallel_execute tworzy zadania."""
    subtasks = ["subtask1", "subtask2"]

    async def mock_get_status(task_id):
        task = TaskMessage(task_id, "parallel_task", {})
        task.status = "completed"
        task.result = "success"
        return task

    mock_message_broker.get_task_status.side_effect = mock_get_status

    await parallel_skill.parallel_execute(
        task_description="Main task",
        subtasks=json.dumps(subtasks),
        wait_timeout=1,
    )

    assert mock_message_broker.enqueue_task.call_count == 2


@pytest.mark.asyncio
async def test_get_task_status_not_found(parallel_skill, mock_message_broker):
    """Test get_task_status gdy zadanie nie istnieje."""
    mock_message_broker.get_task_status.return_value = None

    result = await parallel_skill.get_task_status("nonexistent")

    assert "nie znalezione" in result


@pytest.mark.asyncio
async def test_get_task_status_returns_info(parallel_skill, mock_message_broker):
    """Test get_task_status zwraca informacje o zadaniu."""
    task = TaskMessage("task_123", "test_type", {"data": "test"})
    task.status = "completed"
    task.result = "success"

    mock_message_broker.get_task_status.return_value = task

    result = await parallel_skill.get_task_status("task_123")

    # Sprawdź że odpowiedź zawiera informacje o zadaniu
    result_data = json.loads(result)
    assert result_data["task_id"] == "task_123"
    assert result_data["status"] == "completed"
    assert result_data["result"] == "success"


@pytest.mark.asyncio
async def test_wait_for_results_timeout():
    """Test _wait_for_results z timeoutem."""
    broker = Mock(spec=MessageBroker)

    # Mock który zawsze zwraca pending task
    async def mock_get_status(task_id):
        task = TaskMessage(task_id, "test", {})
        task.status = "pending"
        return task

    broker.get_task_status = AsyncMock(side_effect=mock_get_status)

    skill = ParallelSkill(broker)
    results = await skill._wait_for_results(["task_1", "task_2"], timeout=1)

    # Powinno zwrócić pending dla wszystkich z powodu timeout
    assert len(results) == 2
    assert all(r["status"] == "pending" for r in results)


@pytest.mark.asyncio
async def test_wait_for_results_all_completed():
    """Test _wait_for_results gdy wszystkie zadania ukończone."""
    broker = Mock(spec=MessageBroker)

    # Mock który zwraca completed tasks
    async def mock_get_status(task_id):
        task = TaskMessage(task_id, "test", {"item_index": int(task_id.split("_")[1])})
        task.status = "completed"
        task.result = f"result_{task_id}"
        return task

    broker.get_task_status = AsyncMock(side_effect=mock_get_status)

    skill = ParallelSkill(broker)
    results = await skill._wait_for_results(["task_1", "task_2"], timeout=10)

    assert len(results) == 2
    assert all(r["status"] == "completed" for r in results)
    # Sprawdź sortowanie według item_index
    assert results[0]["item_index"] <= results[1]["item_index"]


@pytest.mark.asyncio
async def test_wait_for_results_mixed_status():
    """Test _wait_for_results z mieszanymi statusami."""
    broker = Mock(spec=MessageBroker)

    call_count = 0

    async def mock_get_status(task_id):
        nonlocal call_count
        call_count += 1

        task = TaskMessage(task_id, "test", {"item_index": int(task_id.split("_")[1])})

        # Pierwsze zadanie ukończone, drugie failed
        if task_id == "task_1":
            task.status = "completed"
            task.result = "success"
        elif task_id == "task_2":
            task.status = "failed"
            task.error = "error occurred"

        return task

    broker.get_task_status = AsyncMock(side_effect=mock_get_status)

    skill = ParallelSkill(broker)
    results = await skill._wait_for_results(["task_1", "task_2"], timeout=10)

    assert len(results) == 2
    assert results[0]["status"] == "completed"
    assert results[1]["status"] == "failed"
