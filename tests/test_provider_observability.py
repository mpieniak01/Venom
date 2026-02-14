"""Tests for provider observability: metrics, SLO, and alerting."""

import pytest
from datetime import datetime, timedelta

from venom_core.core.provider_observability import (
    Alert,
    AlertSeverity,
    AlertType,
    HealthStatus,
    ProviderObservability,
    SLOStatus,
    SLOTarget,
)


class TestSLOTarget:
    """Tests for SLOTarget dataclass."""

    def test_slo_target_defaults(self):
        """Test default SLO target values."""
        target = SLOTarget(provider="test")
        
        assert target.provider == "test"
        assert target.availability_target == 0.99
        assert target.latency_p99_ms == 1000.0
        assert target.error_rate_target == 0.01
        assert target.cost_budget_usd == 50.0
        assert isinstance(target.period_start, datetime)

    def test_slo_target_custom_values(self):
        """Test custom SLO target values."""
        target = SLOTarget(
            provider="openai",
            availability_target=0.999,
            latency_p99_ms=500.0,
            error_rate_target=0.001,
            cost_budget_usd=100.0,
        )
        
        assert target.provider == "openai"
        assert target.availability_target == 0.999
        assert target.latency_p99_ms == 500.0
        assert target.error_rate_target == 0.001
        assert target.cost_budget_usd == 100.0


class TestAlert:
    """Tests for Alert dataclass."""

    def test_alert_creation_with_fingerprint(self):
        """Test alert creation with automatic fingerprint generation."""
        alert = Alert(
            id="test_1",
            severity=AlertSeverity.WARNING,
            alert_type=AlertType.HIGH_LATENCY,
            provider="openai",
            message="test.alert.message",
        )
        
        assert alert.id == "test_1"
        assert alert.severity == AlertSeverity.WARNING
        assert alert.alert_type == AlertType.HIGH_LATENCY
        assert alert.provider == "openai"
        assert alert.fingerprint != ""  # Should be auto-generated
        assert alert.expires_at is not None

    def test_alert_fingerprint_consistency(self):
        """Test that alerts with same params get same fingerprint."""
        timestamp = datetime.now()
        
        alert1 = Alert(
            id="test_1",
            severity=AlertSeverity.WARNING,
            alert_type=AlertType.HIGH_LATENCY,
            provider="openai",
            message="test",
            timestamp=timestamp,
        )
        
        alert2 = Alert(
            id="test_2",
            severity=AlertSeverity.WARNING,
            alert_type=AlertType.HIGH_LATENCY,
            provider="openai",
            message="test",
            timestamp=timestamp,
        )
        
        assert alert1.fingerprint == alert2.fingerprint

    def test_alert_expiry_based_on_severity(self):
        """Test alert expiry times based on severity."""
        now = datetime.now()
        
        info_alert = Alert(
            id="info",
            severity=AlertSeverity.INFO,
            alert_type=AlertType.HIGH_LATENCY,
            provider="test",
            message="test",
            timestamp=now,
        )
        
        warning_alert = Alert(
            id="warning",
            severity=AlertSeverity.WARNING,
            alert_type=AlertType.ERROR_SPIKE,
            provider="test",
            message="test",
            timestamp=now,
        )
        
        critical_alert = Alert(
            id="critical",
            severity=AlertSeverity.CRITICAL,
            alert_type=AlertType.BUDGET_CRITICAL,
            provider="test",
            message="test",
            timestamp=now,
        )
        
        # Info expires in 1 hour
        assert info_alert.expires_at == now + timedelta(hours=1)
        # Warning expires in 3 hours
        assert warning_alert.expires_at == now + timedelta(hours=3)
        # Critical expires in 6 hours
        assert critical_alert.expires_at == now + timedelta(hours=6)


class TestProviderObservability:
    """Tests for ProviderObservability class."""

    def test_initialization(self):
        """Test observability initialization."""
        obs = ProviderObservability()
        
        assert isinstance(obs.slo_targets, dict)
        assert isinstance(obs.active_alerts, dict)
        assert isinstance(obs.alert_history, list)
        
        # Check default SLO targets
        assert "openai" in obs.slo_targets
        assert "google" in obs.slo_targets
        assert "ollama" in obs.slo_targets
        assert "vllm" in obs.slo_targets
        assert "huggingface" in obs.slo_targets

    def test_set_slo_target(self):
        """Test setting custom SLO target."""
        obs = ProviderObservability()
        
        custom_target = SLOTarget(
            provider="custom",
            availability_target=0.95,
            latency_p99_ms=2000.0,
        )
        
        obs.set_slo_target("custom", custom_target)
        
        assert "custom" in obs.slo_targets
        assert obs.slo_targets["custom"].availability_target == 0.95
        assert obs.slo_targets["custom"].latency_p99_ms == 2000.0

    def test_calculate_slo_status_no_metrics(self):
        """Test SLO calculation with no metrics."""
        obs = ProviderObservability()
        
        slo_status = obs.calculate_slo_status("openai", None)
        
        assert slo_status.provider == "openai"
        assert slo_status.availability == 0.0
        assert slo_status.latency_p99_ms is None
        assert slo_status.error_rate == 0.0
        assert slo_status.health_status == HealthStatus.UNKNOWN
        assert slo_status.health_score == 0.0

    def test_calculate_slo_status_healthy(self):
        """Test SLO calculation with healthy metrics."""
        obs = ProviderObservability()
        
        metrics = {
            "success_rate": 99.5,
            "error_rate": 0.5,
            "latency": {"p99_ms": 500.0},
            "cost": {"total_usd": 10.0},
        }
        
        slo_status = obs.calculate_slo_status("openai", metrics)
        
        assert slo_status.provider == "openai"
        assert slo_status.availability == 0.995
        assert slo_status.latency_p99_ms == 500.0
        assert slo_status.error_rate == 0.005
        assert slo_status.health_status == HealthStatus.HEALTHY
        assert slo_status.health_score == 100.0
        assert len(slo_status.breaches) == 0

    def test_calculate_slo_status_degraded_latency(self):
        """Test SLO calculation with high latency."""
        obs = ProviderObservability()
        
        metrics = {
            "success_rate": 99.5,
            "error_rate": 0.5,
            "latency": {"p99_ms": 2500.0},  # Above 2000ms threshold for OpenAI
            "cost": {"total_usd": 10.0},
        }
        
        slo_status = obs.calculate_slo_status("openai", metrics)
        
        assert slo_status.health_status == HealthStatus.DEGRADED
        assert slo_status.health_score == 75.0  # 100 - 25 for latency
        assert len(slo_status.breaches) == 1
        assert "latency_p99" in slo_status.breaches[0]

    def test_calculate_slo_status_critical_multiple_breaches(self):
        """Test SLO calculation with multiple breaches."""
        obs = ProviderObservability()
        
        metrics = {
            "success_rate": 90.0,  # Low availability
            "error_rate": 10.0,  # High error rate
            "latency": {"p99_ms": 3000.0},  # High latency
            "cost": {"total_usd": 60.0},  # Over budget
        }
        
        slo_status = obs.calculate_slo_status("openai", metrics)
        
        assert slo_status.health_status == HealthStatus.CRITICAL
        assert slo_status.health_score == 0.0  # 100 - 30 - 25 - 25 - 20 = 0
        assert len(slo_status.breaches) == 4

    def test_emit_alert_new(self):
        """Test emitting a new alert."""
        obs = ProviderObservability()
        
        alert = Alert(
            id="test_1",
            severity=AlertSeverity.WARNING,
            alert_type=AlertType.HIGH_LATENCY,
            provider="openai",
            message="test",
        )
        
        result = obs.emit_alert(alert)
        
        assert result is True
        assert alert.fingerprint in obs.active_alerts
        assert alert in obs.alert_history

    def test_emit_alert_deduplication(self):
        """Test alert deduplication."""
        obs = ProviderObservability()
        
        timestamp = datetime.now()
        
        alert1 = Alert(
            id="test_1",
            severity=AlertSeverity.WARNING,
            alert_type=AlertType.HIGH_LATENCY,
            provider="openai",
            message="test",
            timestamp=timestamp,
        )
        
        alert2 = Alert(
            id="test_2",
            severity=AlertSeverity.WARNING,
            alert_type=AlertType.HIGH_LATENCY,
            provider="openai",
            message="test",
            timestamp=timestamp,
        )
        
        result1 = obs.emit_alert(alert1)
        result2 = obs.emit_alert(alert2)
        
        assert result1 is True
        assert result2 is False  # Should be deduplicated
        assert len(obs.active_alerts) == 1
        assert len(obs.alert_history) == 1  # Only first one added

    def test_get_active_alerts_no_filter(self):
        """Test getting all active alerts."""
        obs = ProviderObservability()
        
        alert1 = Alert(
            id="test_1",
            severity=AlertSeverity.WARNING,
            alert_type=AlertType.HIGH_LATENCY,
            provider="openai",
            message="test",
        )
        
        alert2 = Alert(
            id="test_2",
            severity=AlertSeverity.CRITICAL,
            alert_type=AlertType.ERROR_SPIKE,
            provider="google",
            message="test",
        )
        
        obs.emit_alert(alert1)
        obs.emit_alert(alert2)
        
        active = obs.get_active_alerts()
        
        assert len(active) == 2

    def test_get_active_alerts_with_provider_filter(self):
        """Test getting alerts filtered by provider."""
        obs = ProviderObservability()
        
        alert1 = Alert(
            id="test_1",
            severity=AlertSeverity.WARNING,
            alert_type=AlertType.HIGH_LATENCY,
            provider="openai",
            message="test",
        )
        
        alert2 = Alert(
            id="test_2",
            severity=AlertSeverity.CRITICAL,
            alert_type=AlertType.ERROR_SPIKE,
            provider="google",
            message="test",
        )
        
        obs.emit_alert(alert1)
        obs.emit_alert(alert2)
        
        openai_alerts = obs.get_active_alerts(provider="openai")
        
        assert len(openai_alerts) == 1
        assert openai_alerts[0].provider == "openai"

    def test_get_active_alerts_expired_cleanup(self):
        """Test that expired alerts are cleaned up."""
        obs = ProviderObservability()
        
        # Create expired alert
        past_time = datetime.now() - timedelta(hours=10)
        alert = Alert(
            id="test_1",
            severity=AlertSeverity.WARNING,
            alert_type=AlertType.HIGH_LATENCY,
            provider="openai",
            message="test",
            timestamp=past_time,
        )
        alert.expires_at = past_time + timedelta(hours=1)  # Already expired
        
        obs.active_alerts[alert.fingerprint] = alert
        
        active = obs.get_active_alerts()
        
        assert len(active) == 0
        assert alert.fingerprint not in obs.active_alerts

    def test_get_alert_summary(self):
        """Test alert summary generation."""
        obs = ProviderObservability()
        
        obs.emit_alert(
            Alert(
                id="test_1",
                severity=AlertSeverity.WARNING,
                alert_type=AlertType.HIGH_LATENCY,
                provider="openai",
                message="test",
            )
        )
        
        obs.emit_alert(
            Alert(
                id="test_2",
                severity=AlertSeverity.CRITICAL,
                alert_type=AlertType.ERROR_SPIKE,
                provider="openai",
                message="test",
            )
        )
        
        obs.emit_alert(
            Alert(
                id="test_3",
                severity=AlertSeverity.INFO,
                alert_type=AlertType.BUDGET_WARNING,
                provider="google",
                message="test",
            )
        )
        
        summary = obs.get_alert_summary()
        
        assert summary["total_active"] == 3
        assert summary["by_severity"]["warning"] == 1
        assert summary["by_severity"]["critical"] == 1
        assert summary["by_severity"]["info"] == 1
        assert summary["by_provider"]["openai"] == 2
        assert summary["by_provider"]["google"] == 1

    def test_check_and_emit_alerts_high_latency(self):
        """Test alerting for high latency."""
        obs = ProviderObservability()
        
        metrics = {
            "success_rate": 99.5,
            "error_rate": 0.5,
            "latency": {"p99_ms": 2500.0},
            "cost": {"total_usd": 10.0},
        }
        
        slo_status = obs.calculate_slo_status("openai", metrics)
        emitted = obs.check_and_emit_alerts("openai", slo_status, metrics)
        
        assert len(emitted) >= 1
        assert any(a.alert_type == AlertType.HIGH_LATENCY for a in emitted)

    def test_check_and_emit_alerts_error_spike(self):
        """Test alerting for error spike."""
        obs = ProviderObservability()
        
        metrics = {
            "success_rate": 95.0,
            "error_rate": 5.0,  # Above 1% threshold
            "latency": {"p99_ms": 500.0},
            "cost": {"total_usd": 10.0},
        }
        
        slo_status = obs.calculate_slo_status("openai", metrics)
        emitted = obs.check_and_emit_alerts("openai", slo_status, metrics)
        
        assert len(emitted) >= 1
        assert any(a.alert_type == AlertType.ERROR_SPIKE for a in emitted)

    def test_check_and_emit_alerts_budget_warning(self):
        """Test alerting for budget warnings."""
        obs = ProviderObservability()
        
        metrics = {
            "success_rate": 99.5,
            "error_rate": 0.5,
            "latency": {"p99_ms": 500.0},
            "cost": {"total_usd": 45.0},  # 90% of $50 budget
        }
        
        slo_status = obs.calculate_slo_status("openai", metrics)
        emitted = obs.check_and_emit_alerts("openai", slo_status, metrics)
        
        assert len(emitted) >= 1
        assert any(a.alert_type == AlertType.BUDGET_WARNING for a in emitted)

    def test_check_and_emit_alerts_availability_drop(self):
        """Test alerting for availability drop."""
        obs = ProviderObservability()
        
        metrics = {
            "success_rate": 95.0,  # Below 99% threshold
            "error_rate": 5.0,
            "latency": {"p99_ms": 500.0},
            "cost": {"total_usd": 10.0},
        }
        
        slo_status = obs.calculate_slo_status("openai", metrics)
        emitted = obs.check_and_emit_alerts("openai", slo_status, metrics)
        
        assert len(emitted) >= 1
        assert any(a.alert_type == AlertType.AVAILABILITY_DROP for a in emitted)
