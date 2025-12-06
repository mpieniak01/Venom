"""Testy dla modułu API - WebSocket i metryki."""

import asyncio

import pytest

from venom_core.api.stream import ConnectionManager, Event, EventBroadcaster, EventType
from venom_core.core.metrics import MetricsCollector


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
