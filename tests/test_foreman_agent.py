"""Testy dla foreman - agent zarządcy klastra."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from semantic_kernel import Kernel

from venom_core.agents.foreman import ForemanAgent, NodeMetrics
from venom_core.infrastructure.message_broker import MessageBroker, TaskMessage


@pytest.fixture
def mock_kernel():
    """Mock Semantic Kernel."""
    return Mock(spec=Kernel)


@pytest.fixture
def mock_message_broker():
    """Mock MessageBroker."""
    broker = Mock(spec=MessageBroker)
    broker.detect_zombie_tasks = AsyncMock(return_value=[])
    broker.update_task_status = AsyncMock()
    broker.retry_task = AsyncMock(return_value=True)
    broker.get_queue_stats = AsyncMock(
        return_value={
            "high_priority_queue": 0,
            "background_queue": 0,
            "tasks_pending": 0,
            "tasks_running": 0,
            "tasks_completed": 0,
            "tasks_failed": 0,
        }
    )
    return broker


@pytest.fixture
def foreman_agent(mock_kernel, mock_message_broker):
    """Fixture dla ForemanAgent."""
    return ForemanAgent(mock_kernel, mock_message_broker)


def test_node_metrics_creation():
    """Test tworzenia NodeMetrics."""
    metrics = NodeMetrics(
        node_id="node_1",
        node_name="Test Node",
        cpu_usage=50.0,
        memory_usage=60.0,
        active_tasks=3,
        gpu_available=True,
    )

    assert metrics.node_id == "node_1"
    assert metrics.node_name == "Test Node"
    assert metrics.cpu_usage == 50.0
    assert metrics.memory_usage == 60.0
    assert metrics.active_tasks == 3
    assert metrics.gpu_available is True
    assert metrics.is_online is True


def test_node_metrics_load_score():
    """Test obliczania load score."""
    # Węzeł bez obciążenia
    idle_node = NodeMetrics("node_1", "Idle", cpu_usage=0, memory_usage=0, active_tasks=0)
    assert idle_node.get_load_score() == 0.0

    # Węzeł z pełnym obciążeniem
    busy_node = NodeMetrics(
        "node_2", "Busy", cpu_usage=100, memory_usage=100, active_tasks=10
    )
    assert busy_node.get_load_score() == 100.0

    # Węzeł z średnim obciążeniem
    medium_node = NodeMetrics(
        "node_3", "Medium", cpu_usage=50, memory_usage=50, active_tasks=5
    )
    assert 40 < medium_node.get_load_score() < 60


def test_node_metrics_to_dict():
    """Test konwersji NodeMetrics do dict."""
    metrics = NodeMetrics("node_1", "Test", cpu_usage=25, memory_usage=30, active_tasks=2)
    data = metrics.to_dict()

    assert data["node_id"] == "node_1"
    assert data["node_name"] == "Test"
    assert data["cpu_usage"] == 25
    assert data["memory_usage"] == 30
    assert data["active_tasks"] == 2
    assert "load_score" in data


def test_foreman_initialization(foreman_agent):
    """Test inicjalizacji ForemanAgent."""
    assert foreman_agent is not None
    assert foreman_agent.message_broker is not None
    assert foreman_agent._is_running is False
    assert len(foreman_agent.nodes_metrics) == 0


@pytest.mark.asyncio
async def test_foreman_start_stop(foreman_agent):
    """Test uruchamiania i zatrzymywania Foreman."""
    await foreman_agent.start()
    assert foreman_agent._is_running is True
    assert foreman_agent._watchdog_task is not None
    assert foreman_agent._monitoring_task is not None

    await asyncio.sleep(0.1)  # Daj czas na uruchomienie tasków

    await foreman_agent.stop()
    assert foreman_agent._is_running is False


def test_select_best_node_no_nodes(foreman_agent):
    """Test wyboru węzła gdy brak dostępnych węzłów."""
    result = foreman_agent.select_best_node()
    assert result is None


def test_select_best_node_single_node(foreman_agent):
    """Test wyboru węzła gdy jest tylko jeden dostępny."""
    foreman_agent.nodes_metrics["node_1"] = NodeMetrics(
        "node_1", "Node 1", cpu_usage=30, memory_usage=40, active_tasks=1
    )

    result = foreman_agent.select_best_node()
    assert result == "node_1"


def test_select_best_node_multiple_nodes(foreman_agent):
    """Test wyboru najlepszego węzła z kilku dostępnych."""
    # Węzeł bardzo zajęty
    foreman_agent.nodes_metrics["node_1"] = NodeMetrics(
        "node_1", "Busy Node", cpu_usage=90, memory_usage=85, active_tasks=8
    )

    # Węzeł wolny (powinien zostać wybrany)
    foreman_agent.nodes_metrics["node_2"] = NodeMetrics(
        "node_2", "Idle Node", cpu_usage=10, memory_usage=20, active_tasks=1
    )

    # Węzeł średnio zajęty
    foreman_agent.nodes_metrics["node_3"] = NodeMetrics(
        "node_3", "Medium Node", cpu_usage=50, memory_usage=50, active_tasks=4
    )

    result = foreman_agent.select_best_node()
    assert result == "node_2"  # Powinien wybrać najmniej zajęty


def test_select_best_node_with_gpu_requirement(foreman_agent):
    """Test wyboru węzła z wymaganiem GPU."""
    # Węzeł bez GPU
    foreman_agent.nodes_metrics["node_1"] = NodeMetrics(
        "node_1", "CPU Node", cpu_usage=10, memory_usage=20, active_tasks=0, gpu_available=False
    )

    # Węzeł z GPU
    foreman_agent.nodes_metrics["node_2"] = NodeMetrics(
        "node_2", "GPU Node", cpu_usage=30, memory_usage=40, active_tasks=0, gpu_available=True
    )

    result = foreman_agent.select_best_node(task_requirements={"gpu": True})
    assert result == "node_2"


def test_select_best_node_offline_nodes_filtered(foreman_agent):
    """Test że offline węzły są filtrowane."""
    # Węzeł offline
    offline_node = NodeMetrics(
        "node_1", "Offline", cpu_usage=10, memory_usage=20, active_tasks=0
    )
    offline_node.is_online = False
    foreman_agent.nodes_metrics["node_1"] = offline_node

    # Węzeł online
    foreman_agent.nodes_metrics["node_2"] = NodeMetrics(
        "node_2", "Online", cpu_usage=30, memory_usage=40, active_tasks=0
    )

    result = foreman_agent.select_best_node()
    assert result == "node_2"


@pytest.mark.asyncio
async def test_assign_task(foreman_agent, mock_message_broker):
    """Test przypisywania zadania do węzła."""
    foreman_agent.nodes_metrics["node_1"] = NodeMetrics(
        "node_1", "Node 1", cpu_usage=20, memory_usage=30, active_tasks=0
    )

    result = await foreman_agent.assign_task("task_123")

    assert result == "node_1"
    mock_message_broker.update_task_status.assert_called_once()
    assert foreman_agent.nodes_metrics["node_1"].active_tasks == 1


@pytest.mark.asyncio
async def test_assign_task_no_available_nodes(foreman_agent, mock_message_broker):
    """Test przypisywania zadania gdy brak dostępnych węzłów."""
    result = await foreman_agent.assign_task("task_123")

    assert result is None


@pytest.mark.asyncio
async def test_complete_task(foreman_agent, mock_message_broker):
    """Test oznaczania zadania jako ukończone."""
    foreman_agent.nodes_metrics["node_1"] = NodeMetrics(
        "node_1", "Node 1", cpu_usage=20, memory_usage=30, active_tasks=3
    )

    await foreman_agent.complete_task("task_123", "node_1", {"result": "success"})

    mock_message_broker.update_task_status.assert_called_once()
    assert foreman_agent.nodes_metrics["node_1"].active_tasks == 2


@pytest.mark.asyncio
async def test_fail_task(foreman_agent, mock_message_broker):
    """Test oznaczania zadania jako nieudane."""
    foreman_agent.nodes_metrics["node_1"] = NodeMetrics(
        "node_1", "Node 1", cpu_usage=20, memory_usage=30, active_tasks=3
    )

    await foreman_agent.fail_task("task_123", "node_1", "Error occurred")

    mock_message_broker.update_task_status.assert_called_once()
    mock_message_broker.retry_task.assert_called_once_with("task_123")
    assert foreman_agent.nodes_metrics["node_1"].active_tasks == 2


def test_get_cluster_status(foreman_agent):
    """Test pobierania statusu klastra."""
    # Dodaj kilka węzłów
    foreman_agent.nodes_metrics["node_1"] = NodeMetrics(
        "node_1", "Node 1", cpu_usage=40, memory_usage=50, active_tasks=2
    )
    foreman_agent.nodes_metrics["node_2"] = NodeMetrics(
        "node_2", "Node 2", cpu_usage=60, memory_usage=70, active_tasks=3
    )

    status = foreman_agent.get_cluster_status()

    assert status["total_nodes"] == 2
    assert status["online_nodes"] == 2
    assert status["offline_nodes"] == 0
    assert status["avg_cpu_usage"] == 50.0
    assert status["avg_memory_usage"] == 60.0
    assert status["total_active_tasks"] == 5
    assert len(status["nodes"]) == 2


def test_get_cluster_status_empty(foreman_agent):
    """Test statusu klastra gdy brak węzłów."""
    status = foreman_agent.get_cluster_status()

    assert status["total_nodes"] == 0
    assert status["online_nodes"] == 0
    assert status["avg_cpu_usage"] == 0
    assert status["avg_memory_usage"] == 0
    assert status["total_active_tasks"] == 0


@pytest.mark.asyncio
async def test_process_returns_status(foreman_agent, mock_message_broker):
    """Test że process zwraca status Foreman."""
    foreman_agent.nodes_metrics["node_1"] = NodeMetrics(
        "node_1", "Node 1", cpu_usage=30, memory_usage=40, active_tasks=2
    )

    result = await foreman_agent.process("status")

    assert "Foreman Status" in result
    assert "Węzły:" in result
    assert "Kolejki:" in result
