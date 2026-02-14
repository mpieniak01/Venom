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

    def test_increment_policy_blocked(self):
        """Test inkrementacji licznika zablokowanych żądań przez policy gate."""
        # Arrange
        collector = MetricsCollector()

        # Act
        collector.increment_policy_blocked()
        collector.increment_policy_blocked()

        # Assert
        assert collector.metrics["policy_blocked_count"] == 2

    def test_record_provider_request_success(self):
        """Test recording successful provider request."""
        # Arrange
        collector = MetricsCollector()

        # Act
        collector.record_provider_request(
            provider="openai",
            success=True,
            latency_ms=250.0,
            cost_usd=0.001,
            tokens=100,
        )

        # Assert
        pm = collector.get_provider_metrics("openai")
        assert pm is not None
        assert pm["total_requests"] == 1
        assert pm["successful_requests"] == 1
        assert pm["failed_requests"] == 0
        assert pm["success_rate"] == 100.0
        assert pm["error_rate"] == 0.0
        assert pm["latency"]["p50_ms"] == 250.0
        assert pm["cost"]["total_usd"] == 0.001
        assert pm["cost"]["total_tokens"] == 100

    def test_record_provider_request_failure(self):
        """Test recording failed provider request."""
        # Arrange
        collector = MetricsCollector()

        # Act
        collector.record_provider_request(
            provider="openai",
            success=False,
            latency_ms=5000.0,
            error_code="TIMEOUT",
            cost_usd=0.0,
            tokens=0,
        )

        # Assert
        pm = collector.get_provider_metrics("openai")
        assert pm is not None
        assert pm["total_requests"] == 1
        assert pm["successful_requests"] == 0
        assert pm["failed_requests"] == 1
        assert pm["success_rate"] == 0.0
        assert pm["error_rate"] == 100.0
        assert pm["errors"]["total"] == 1
        assert pm["errors"]["timeouts"] == 1
        assert "TIMEOUT" in pm["errors"]["by_code"]
        assert pm["errors"]["by_code"]["TIMEOUT"] == 1

    def test_record_provider_request_mixed(self):
        """Test recording mixed success/failure requests."""
        # Arrange
        collector = MetricsCollector()

        # Act - 7 successful, 3 failed
        for i in range(7):
            collector.record_provider_request(
                provider="openai",
                success=True,
                latency_ms=200.0 + i * 10,
                cost_usd=0.001,
                tokens=100,
            )

        for i in range(3):
            collector.record_provider_request(
                provider="openai",
                success=False,
                latency_ms=5000.0,
                error_code="AUTH_ERROR" if i < 2 else "TIMEOUT",
            )

        # Assert
        pm = collector.get_provider_metrics("openai")
        assert pm["total_requests"] == 10
        assert pm["successful_requests"] == 7
        assert pm["failed_requests"] == 3
        assert pm["success_rate"] == 70.0
        assert pm["error_rate"] == 30.0
        assert pm["errors"]["auth_errors"] == 2
        assert pm["errors"]["timeouts"] == 1
        assert pm["cost"]["total_usd"] == 0.007

    def test_calculate_percentile(self):
        """Test percentile calculation."""
        # Arrange
        collector = MetricsCollector()
        samples = [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000]

        # Act & Assert
        p50 = collector._calculate_percentile(samples, 0.50)
        p95 = collector._calculate_percentile(samples, 0.95)
        p99 = collector._calculate_percentile(samples, 0.99)

        assert p50 == 550.0  # Median
        assert p95 == 950.0  # 95th percentile
        assert p99 == 1000.0  # 99th percentile

    def test_calculate_percentile_empty(self):
        """Test percentile calculation with empty samples."""
        # Arrange
        collector = MetricsCollector()

        # Act & Assert
        result = collector._calculate_percentile([], 0.50)
        assert result is None

    def test_latency_percentiles_with_multiple_samples(self):
        """Test latency percentiles with realistic samples."""
        # Arrange
        collector = MetricsCollector()

        # Act - Add samples with varying latencies
        latencies = [100, 150, 200, 250, 300, 350, 400, 500, 1000, 2000]
        for latency in latencies:
            collector.record_provider_request(
                provider="openai",
                success=True,
                latency_ms=latency,
            )

        # Assert
        pm = collector.get_provider_metrics("openai")
        assert pm["latency"]["p50_ms"] == 325.0
        assert pm["latency"]["p95_ms"] == 1500.0
        assert pm["latency"]["p99_ms"] == 2000.0
        assert pm["latency"]["samples"] == 10

    def test_get_provider_metrics_nonexistent(self):
        """Test getting metrics for nonexistent provider."""
        # Arrange
        collector = MetricsCollector()

        # Act
        pm = collector.get_provider_metrics("nonexistent")

        # Assert
        assert pm is None

    def test_get_all_provider_metrics(self):
        """Test getting all provider metrics."""
        # Arrange
        collector = MetricsCollector()

        # Act - Add metrics for multiple providers
        collector.record_provider_request(
            provider="openai", success=True, latency_ms=200.0
        )
        collector.record_provider_request(
            provider="google", success=True, latency_ms=300.0
        )
        collector.record_provider_request(
            provider="ollama", success=False, latency_ms=1000.0, error_code="TIMEOUT"
        )

        # Assert
        all_metrics = collector.get_all_provider_metrics()
        assert len(all_metrics) == 3
        assert "openai" in all_metrics
        assert "google" in all_metrics
        assert "ollama" in all_metrics
        assert all_metrics["openai"]["total_requests"] == 1
        assert all_metrics["google"]["total_requests"] == 1
        assert all_metrics["ollama"]["total_requests"] == 1

    def test_provider_metrics_thread_safety(self):
        """Test thread safety for provider metrics."""
        # Arrange
        collector = MetricsCollector()

        def record_multiple_requests():
            for _ in range(100):
                collector.record_provider_request(
                    provider="openai", success=True, latency_ms=200.0
                )

        # Act
        threads = [threading.Thread(target=record_multiple_requests) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Assert
        pm = collector.get_provider_metrics("openai")
        assert pm["total_requests"] == 500

    def test_latency_sample_limit(self):
        """Test that latency samples are limited to 1000."""
        # Arrange
        collector = MetricsCollector()

        # Act - Add more than 1000 samples
        for i in range(1500):
            collector.record_provider_request(
                provider="openai", success=True, latency_ms=float(i)
            )

        # Assert
        pm = collector.get_provider_metrics("openai")
        assert pm["latency"]["samples"] == 1000  # Should be capped at 1000

    def test_error_code_tracking(self):
        """Test tracking of different error codes."""
        # Arrange
        collector = MetricsCollector()

        # Act
        collector.record_provider_request(
            provider="openai", success=False, latency_ms=100.0, error_code="TIMEOUT"
        )
        collector.record_provider_request(
            provider="openai", success=False, latency_ms=100.0, error_code="TIMEOUT"
        )
        collector.record_provider_request(
            provider="openai", success=False, latency_ms=100.0, error_code="AUTH_ERROR"
        )
        collector.record_provider_request(
            provider="openai",
            success=False,
            latency_ms=100.0,
            error_code="BUDGET_EXCEEDED",
        )

        # Assert
        pm = collector.get_provider_metrics("openai")
        assert pm["errors"]["by_code"]["TIMEOUT"] == 2
        assert pm["errors"]["by_code"]["AUTH_ERROR"] == 1
        assert pm["errors"]["by_code"]["BUDGET_EXCEEDED"] == 1
        assert pm["errors"]["timeouts"] == 2
        assert pm["errors"]["auth_errors"] == 1
        assert pm["errors"]["budget_errors"] == 1

    def test_policy_blocked_in_metrics_output(self):
        """Test czy policy metrics są w wyniku get_metrics()."""
        # Arrange
        collector = MetricsCollector()
        collector.increment_task_created()
        collector.increment_task_created()
        collector.increment_policy_blocked()

        # Act
        metrics = collector.get_metrics()

        # Assert
        assert "policy" in metrics
        assert metrics["policy"]["blocked_count"] == 1
        assert metrics["policy"]["block_rate"] == 50.0  # 1 blocked / 2 created * 100

    def test_policy_block_rate_calculation(self):
        """Test obliczania policy block rate."""
        # Arrange
        collector = MetricsCollector()

        # 10 tasks created, 3 blocked
        for _ in range(10):
            collector.increment_task_created()
        for _ in range(3):
            collector.increment_policy_blocked()

        # Act
        metrics = collector.get_metrics()

        # Assert
        assert metrics["policy"]["blocked_count"] == 3
        assert metrics["policy"]["block_rate"] == 30.0  # 3/10 * 100

    def test_policy_block_rate_zero_when_no_tasks(self):
        """Test że block rate jest 0 gdy brak tasków."""
        # Arrange
        collector = MetricsCollector()

        # Act
        metrics = collector.get_metrics()

        # Assert
        assert metrics["policy"]["block_rate"] == 0.0
