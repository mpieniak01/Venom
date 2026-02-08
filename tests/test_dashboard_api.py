"""Testy dla modułu API - WebSocket i metryki."""

from typing import cast

import pytest
from fastapi import WebSocket

from venom_core.api.stream import ConnectionManager, Event, EventBroadcaster, EventType
from venom_core.core.metrics import MetricsCollector


class MockWebSocket:
    """Mock WebSocket object for testing."""

    def __init__(self, should_fail=False):
        self.should_fail = should_fail
        self.messages_sent = []
        self.closed = False

    async def accept(self):
        """Mock accept method."""
        pass

    async def send_text(self, message):
        """Mock send_text method."""
        if self.should_fail:
            raise Exception("WebSocket send failed")
        self.messages_sent.append(message)


class TestConnectionManager:
    """Testy dla ConnectionManager."""

    @pytest.mark.asyncio
    async def test_broadcast_empty_connections(self):
        """Test broadcastu gdy brak połączeń."""
        manager = ConnectionManager()

        event = Event(
            type=EventType.SYSTEM_LOG,
            message="Test message",
            timestamp="2023-01-01T00:00:00",
        )

        # Nie powinno rzucić wyjątku
        await manager.broadcast(event)

        assert len(manager.active_connections) == 0

    @pytest.mark.asyncio
    async def test_connect_websocket(self):
        """Test dodawania połączenia WebSocket."""
        manager = ConnectionManager()
        mock_ws = MockWebSocket()

        await manager.connect(cast(WebSocket, mock_ws))

        assert len(manager.active_connections) == 1
        assert mock_ws in manager.active_connections

    @pytest.mark.asyncio
    async def test_disconnect_websocket(self):
        """Test usuwania połączenia WebSocket."""
        manager = ConnectionManager()
        mock_ws = MockWebSocket()

        await manager.connect(cast(WebSocket, mock_ws))
        assert len(manager.active_connections) == 1

        await manager.disconnect(cast(WebSocket, mock_ws))
        assert len(manager.active_connections) == 0

    @pytest.mark.asyncio
    async def test_broadcast_to_connected_clients(self):
        """Test broadcastu do podłączonych klientów."""
        manager = ConnectionManager()
        mock_ws1 = MockWebSocket()
        mock_ws2 = MockWebSocket()

        await manager.connect(cast(WebSocket, mock_ws1))
        await manager.connect(cast(WebSocket, mock_ws2))

        event = Event(
            type=EventType.AGENT_ACTION,
            message="Test broadcast",
            timestamp="2023-01-01T00:00:00",
        )

        await manager.broadcast(event)

        # Oba WebSockety powinny otrzymać wiadomość
        assert len(mock_ws1.messages_sent) == 1
        assert len(mock_ws2.messages_sent) == 1

    @pytest.mark.asyncio
    async def test_broadcast_handles_failed_connections(self):
        """Test obsługi błędów podczas broadcastu."""
        manager = ConnectionManager()
        mock_ws_good = MockWebSocket()
        mock_ws_bad = MockWebSocket(should_fail=True)

        await manager.connect(cast(WebSocket, mock_ws_good))
        await manager.connect(cast(WebSocket, mock_ws_bad))

        assert len(manager.active_connections) == 2

        event = Event(
            type=EventType.SYSTEM_LOG,
            message="Test message",
            timestamp="2023-01-01T00:00:00",
        )

        await manager.broadcast(event)

        # Zepsute połączenie powinno zostać usunięte
        assert len(manager.active_connections) == 1
        assert mock_ws_bad not in manager.active_connections
        assert mock_ws_good in manager.active_connections
        # Dobre połączenie powinno otrzymać wiadomość
        assert len(mock_ws_good.messages_sent) == 1


class TestEventBroadcaster:
    """Testy dla EventBroadcaster."""

    @pytest.mark.asyncio
    async def test_broadcast_event(self):
        """Test wysyłania zdarzenia."""
        manager = ConnectionManager()
        broadcaster = EventBroadcaster(manager)

        # Nie powinno rzucić wyjątku gdy brak połączeń
        await broadcaster.broadcast_event(
            event_type=EventType.AGENT_ACTION,
            message="Test action",
            agent="TestAgent",
        )

    @pytest.mark.asyncio
    async def test_broadcast_log(self):
        """Test wysyłania loga systemowego."""
        manager = ConnectionManager()
        broadcaster = EventBroadcaster(manager)

        # Nie powinno rzucić wyjątku
        await broadcaster.broadcast_log(level="INFO", message="Test log")


class TestMetricsCollector:
    """Testy dla MetricsCollector."""

    def test_initial_state(self):
        """Test początkowego stanu collectora."""
        collector = MetricsCollector()

        metrics = collector.get_metrics()

        assert metrics["status"] == "ok"
        assert metrics["tasks"]["created"] == 0
        assert metrics["tasks"]["completed"] == 0
        assert metrics["tasks"]["failed"] == 0

    def test_increment_task_created(self):
        """Test inkrementacji zadań utworzonych."""
        collector = MetricsCollector()

        collector.increment_task_created()
        collector.increment_task_created()

        metrics = collector.get_metrics()
        assert metrics["tasks"]["created"] == 2

    def test_increment_task_completed(self):
        """Test inkrementacji zadań ukończonych."""
        collector = MetricsCollector()

        collector.increment_task_created()
        collector.increment_task_completed()

        metrics = collector.get_metrics()
        assert metrics["tasks"]["completed"] == 1
        assert metrics["tasks"]["success_rate"] == 100.0

    def test_increment_task_failed(self):
        """Test inkrementacji zadań nieudanych."""
        collector = MetricsCollector()

        collector.increment_task_created()
        collector.increment_task_created()
        collector.increment_task_failed()

        metrics = collector.get_metrics()
        assert metrics["tasks"]["failed"] == 1
        assert metrics["tasks"]["success_rate"] == 0.0

    def test_tool_usage(self):
        """Test śledzenia użycia narzędzi."""
        collector = MetricsCollector()

        collector.increment_tool_usage("FileSkill")
        collector.increment_tool_usage("FileSkill")
        collector.increment_tool_usage("WebSkill")

        metrics = collector.get_metrics()
        assert metrics["tool_usage"]["FileSkill"] == 2
        assert metrics["tool_usage"]["WebSkill"] == 1

    def test_agent_usage(self):
        """Test śledzenia użycia agentów."""
        collector = MetricsCollector()

        collector.increment_agent_usage("ResearcherAgent")
        collector.increment_agent_usage("CoderAgent")
        collector.increment_agent_usage("ResearcherAgent")

        metrics = collector.get_metrics()
        assert metrics["agent_usage"]["ResearcherAgent"] == 2
        assert metrics["agent_usage"]["CoderAgent"] == 1

    def test_success_rate_calculation(self):
        """Test obliczania wskaźnika sukcesu."""
        collector = MetricsCollector()

        # 3 zadania: 2 ukończone, 1 nieudane
        collector.increment_task_created()
        collector.increment_task_created()
        collector.increment_task_created()

        collector.increment_task_completed()
        collector.increment_task_completed()
        collector.increment_task_failed()

        metrics = collector.get_metrics()
        assert metrics["tasks"]["success_rate"] == pytest.approx(66.67, rel=0.01)
