"""Testy dla message_broker - infrastruktura kolejkowania zadań."""

import json
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from venom_core.infrastructure.message_broker import MessageBroker, TaskMessage


@pytest.fixture
def task_message():
    """Fixture dla TaskMessage."""
    return TaskMessage(
        task_id="test_task_123",
        task_type="test_type",
        payload={"data": "test"},
        priority="background",
    )


def test_task_message_creation(task_message):
    """Test tworzenia TaskMessage."""
    assert task_message.task_id == "test_task_123"
    assert task_message.task_type == "test_type"
    assert task_message.payload == {"data": "test"}
    assert task_message.priority == "background"
    assert task_message.status == "pending"
    assert task_message.attempt == 0


def test_task_message_to_dict(task_message):
    """Test konwersji TaskMessage do dict."""
    data = task_message.to_dict()
    assert data["task_id"] == "test_task_123"
    assert data["task_type"] == "test_type"
    assert data["status"] == "pending"
    assert isinstance(data["created_at"], str)


def test_task_message_from_dict():
    """Test tworzenia TaskMessage z dict."""
    data = {
        "task_id": "test_123",
        "task_type": "test",
        "payload": {"key": "value"},
        "priority": "high_priority",
        "created_at": datetime.now().isoformat(),
        "status": "completed",
        "attempt": 2,
    }

    task = TaskMessage.from_dict(data)
    assert task.task_id == "test_123"
    assert task.task_type == "test"
    assert task.status == "completed"
    assert task.attempt == 2


@pytest.fixture
def message_broker():
    """Fixture dla MessageBroker (bez połączenia)."""
    return MessageBroker()


def test_message_broker_initialization(message_broker):
    """Test inicjalizacji MessageBroker."""
    assert message_broker is not None
    assert message_broker._is_connected is False
    assert message_broker.redis_client is None
    assert message_broker.arq_pool is None


def test_message_broker_is_connected(message_broker):
    """Test sprawdzania połączenia."""
    assert message_broker.is_connected() is False
    message_broker._is_connected = True
    assert message_broker.is_connected() is True


@pytest.mark.asyncio
async def test_message_broker_connect_failure():
    """Test nieudanego połączenia z Redis."""
    broker = MessageBroker()

    with patch("redis.asyncio.Redis") as mock_redis:
        mock_redis_instance = AsyncMock()
        mock_redis_instance.ping = AsyncMock(side_effect=Exception("Connection failed"))
        mock_redis.return_value = mock_redis_instance

        result = await broker.connect()

        assert result is False
        assert broker.is_connected() is False


@pytest.mark.asyncio
async def test_enqueue_task_not_connected():
    """Test dodawania zadania gdy brak połączenia."""
    broker = MessageBroker()

    with pytest.raises(RuntimeError, match="nie jest połączony"):
        await broker.enqueue_task("test_task", {"data": "test"})


@pytest.mark.asyncio
async def test_get_task_status_from_registry():
    """Test pobierania statusu zadania z rejestru."""
    broker = MessageBroker()
    task = TaskMessage("task_123", "test", {"data": "test"})
    broker._task_registry["task_123"] = task

    # Mock redis_client aby get_task_status działało
    broker.redis_client = AsyncMock()
    broker.redis_client.get = AsyncMock(
        return_value=None
    )  # Nie ma w Redis, będzie z rejestru

    result = await broker.get_task_status("task_123")

    assert result is not None
    assert result.task_id == "task_123"


@pytest.mark.asyncio
async def test_get_task_status_not_found():
    """Test pobierania nieistniejącego zadania."""
    broker = MessageBroker()
    broker.redis_client = None  # Upewnij się że redis_client jest None

    result = await broker.get_task_status("nonexistent")

    assert result is None


@pytest.mark.asyncio
async def test_update_task_status():
    """Test aktualizacji statusu zadania."""
    broker = MessageBroker()
    broker._is_connected = True
    broker.redis_client = AsyncMock()

    task = TaskMessage("task_123", "test", {"data": "test"})
    broker._task_registry["task_123"] = task

    await broker.update_task_status(
        "task_123", status="running", assigned_node="node_1"
    )

    assert task.status == "running"
    assert task.assigned_node == "node_1"
    assert task.started_at is not None


@pytest.mark.asyncio
async def test_broadcast_control_not_connected():
    """Test broadcast gdy brak połączenia."""
    broker = MessageBroker()

    with pytest.raises(RuntimeError, match="nie jest połączony"):
        await broker.broadcast_control("TEST_COMMAND")


@pytest.mark.asyncio
async def test_get_queue_stats():
    """Test pobierania statystyk kolejek."""
    broker = MessageBroker()

    # Dodaj kilka zadań do rejestru - użyj prawidłowej inicjalizacji
    task1 = TaskMessage("task_1", "test", {})
    task1.status = "pending"
    broker._task_registry["task_1"] = task1

    task2 = TaskMessage("task_2", "test", {})
    task2.status = "running"
    broker._task_registry["task_2"] = task2

    task3 = TaskMessage("task_3", "test", {})
    task3.status = "completed"
    broker._task_registry["task_3"] = task3

    task4 = TaskMessage("task_4", "test", {})
    task4.status = "failed"
    broker._task_registry["task_4"] = task4

    stats = await broker.get_queue_stats()

    assert stats["tasks_pending"] == 1
    assert stats["tasks_running"] == 1
    assert stats["tasks_completed"] == 1
    assert stats["tasks_failed"] == 1
    assert stats["connected"] is False


@pytest.mark.asyncio
async def test_detect_zombie_tasks():
    """Test wykrywania zombie tasks."""
    from datetime import timedelta

    broker = MessageBroker()

    # Utwórz zombie task (stary running task)
    old_task = TaskMessage("zombie_1", "test", {})
    old_task.status = "running"
    old_task.started_at = datetime.now() - timedelta(seconds=700)  # Starszy niż timeout

    # Utwórz normalny task
    normal_task = TaskMessage("normal_1", "test", {})
    normal_task.status = "running"
    normal_task.started_at = datetime.now()

    broker._task_registry["zombie_1"] = old_task
    broker._task_registry["normal_1"] = normal_task

    zombies = await broker.detect_zombie_tasks()

    assert len(zombies) == 1
    assert zombies[0].task_id == "zombie_1"


@pytest.mark.asyncio
async def test_retry_task_not_found():
    """Test retry nieistniejącego zadania."""
    broker = MessageBroker()

    result = await broker.retry_task("nonexistent")

    assert result is False


@pytest.mark.asyncio
async def test_retry_task_max_retries():
    """Test retry zadania które osiągnęło max retries."""
    broker = MessageBroker()

    task = TaskMessage("task_123", "test", {}, max_retries=3)
    task.attempt = 3  # Osiągnięto max
    broker._task_registry["task_123"] = task

    result = await broker.retry_task("task_123")

    assert result is False


@pytest.mark.asyncio
async def test_store_task_info_uses_json_serialization():
    """Task info powinien byc zapisywany jako jawny JSON (bez pickle)."""
    broker = MessageBroker()
    broker.redis_client = AsyncMock()
    task = TaskMessage("task_json_1", "test", {"k": "v"})

    await broker._store_task_info(task)

    broker.redis_client.setex.assert_awaited_once()
    args, _ = broker.redis_client.setex.await_args
    assert args[0] == "venom:task:task_json_1"
    assert args[1] == 86400
    raw = args[2]
    assert isinstance(raw, bytes)
    payload = json.loads(raw.decode("utf-8"))
    assert payload["task_id"] == "task_json_1"
    assert payload["payload"] == {"k": "v"}


@pytest.mark.asyncio
async def test_get_task_status_from_redis_json_payload():
    """Broker powinien poprawnie odczytywac TaskMessage z JSON z Redis."""
    broker = MessageBroker()
    broker.redis_client = AsyncMock()
    encoded = json.dumps(
        {
            "task_id": "redis_task_1",
            "task_type": "test",
            "payload": {"k": "v"},
            "priority": "background",
            "created_at": datetime.now().isoformat(),
            "timeout": 30,
            "max_retries": 2,
            "attempt": 0,
            "assigned_node": None,
            "started_at": None,
            "completed_at": None,
            "result": None,
            "error": None,
            "status": "pending",
        }
    ).encode("utf-8")
    broker.redis_client.get = AsyncMock(return_value=encoded)

    task = await broker.get_task_status("redis_task_1")

    assert task is not None
    assert task.task_id == "redis_task_1"
    assert task.payload == {"k": "v"}


@pytest.mark.asyncio
async def test_get_task_status_returns_none_for_invalid_redis_payload():
    """Uszkodzony payload z Redis nie powinien crashowac brokera."""
    broker = MessageBroker()
    broker.redis_client = AsyncMock()
    broker.redis_client.get = AsyncMock(return_value=b"not-json")

    task = await broker.get_task_status("broken_task")

    assert task is None
