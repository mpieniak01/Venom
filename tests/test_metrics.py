"""Testy dla modułu metrics - zbieranie metryk systemowych."""

import threading

from venom_core.core.metrics import MetricsCollector


class TestMetricsCollector:
    """Testy dla MetricsCollector."""

    def test_initialization(self):
        """Test inicjalizacji collectora."""
        # Arrange & Act
        collector = MetricsCollector()

        # Assert
        assert collector.metrics["tasks_created"] == 0
        assert collector.metrics["tasks_completed"] == 0
        assert collector.metrics["tasks_failed"] == 0
        assert isinstance(collector.tool_usage, dict)
        assert isinstance(collector.agent_usage, dict)

    def test_increment_task_created(self):
        """Test inkrementacji licznika utworzonych zadań."""
        # Arrange
        collector = MetricsCollector()

        # Act
        collector.increment_task_created()
        collector.increment_task_created()

        # Assert
        assert collector.metrics["tasks_created"] == 2

    def test_increment_task_completed(self):
        """Test inkrementacji licznika ukończonych zadań."""
        # Arrange
        collector = MetricsCollector()

        # Act
        collector.increment_task_completed()

        # Assert
        assert collector.metrics["tasks_completed"] == 1

    def test_increment_task_failed(self):
        """Test inkrementacji licznika nieudanych zadań."""
        # Arrange
        collector = MetricsCollector()

        # Act
        collector.increment_task_failed()
        collector.increment_task_failed()
        collector.increment_task_failed()

        # Assert
        assert collector.metrics["tasks_failed"] == 3

    def test_add_tokens_used(self):
        """Test dodawania użytych tokenów."""
        # Arrange
        collector = MetricsCollector()

        # Act
        collector.add_tokens_used(100)
        collector.add_tokens_used(250)

        # Assert
        assert collector.metrics["tokens_used_session"] == 350

    def test_concurrent_increments(self):
        """Test wielowątkowej inkrementacji (thread safety)."""
        # Arrange
        collector = MetricsCollector()

        def increment_multiple_times():
            for _ in range(100):
                collector.increment_task_created()

        # Act
        threads = [threading.Thread(target=increment_multiple_times) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Assert
        assert collector.metrics["tasks_created"] == 500
