"""Tests for provider observability API endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import patch, MagicMock

from venom_core.main import app
from venom_core.core.metrics import MetricsCollector
from venom_core.core.provider_observability import (
    Alert,
    AlertSeverity,
    AlertType,
    ProviderObservability,
)


@pytest.mark.asyncio
async def test_get_provider_metrics_no_data():
    """Test getting metrics for provider with no data."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/providers/openai/metrics")
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["provider"] == "openai"
    assert "metrics" in data
    assert data["metrics"]["total_requests"] == 0


@pytest.mark.asyncio
async def test_get_provider_metrics_with_data():
    """Test getting metrics for provider with recorded data."""
    from venom_core.core.metrics import metrics_collector
    
    # Record some test data
    if metrics_collector:
        metrics_collector.record_provider_request(
            provider="openai",
            success=True,
            latency_ms=250.0,
            cost_usd=0.001,
            tokens=100,
        )
        metrics_collector.record_provider_request(
            provider="openai",
            success=True,
            latency_ms=300.0,
            cost_usd=0.002,
            tokens=150,
        )
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/providers/openai/metrics")
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["provider"] == "openai"
    
    metrics = data["metrics"]
    assert metrics["total_requests"] >= 2
    assert metrics["success_rate"] > 0
    assert "latency" in metrics
    assert "cost" in metrics


@pytest.mark.asyncio
async def test_get_provider_metrics_invalid_provider():
    """Test getting metrics for invalid provider."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/providers/invalid_provider/metrics")
    
    assert response.status_code == 404
    data = response.json()
    assert "Unknown provider" in data["detail"]


@pytest.mark.asyncio
async def test_get_provider_health_no_data():
    """Test getting health status for provider with no metrics."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/providers/openai/health")
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["provider"] == "openai"
    assert "health" in data
    
    health = data["health"]
    assert "health_status" in health
    assert "health_score" in health
    assert "slo_target" in health


@pytest.mark.asyncio
async def test_get_provider_health_healthy():
    """Test getting health status for healthy provider."""
    from venom_core.core.metrics import metrics_collector
    
    # Clear any existing data first
    if metrics_collector and "openai" in metrics_collector.provider_metrics:
        del metrics_collector.provider_metrics["openai"]
    
    # Record healthy metrics
    if metrics_collector:
        for _ in range(10):
            metrics_collector.record_provider_request(
                provider="openai",
                success=True,
                latency_ms=500.0,
                cost_usd=0.001,
                tokens=100,
            )
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/providers/openai/health")
    
    assert response.status_code == 200
    data = response.json()
    
    health = data["health"]
    assert health["health_status"] == "healthy"
    assert health["health_score"] >= 80.0
    assert health["availability"] >= 0.99


@pytest.mark.asyncio
async def test_get_provider_health_degraded():
    """Test getting health status for degraded provider."""
    from venom_core.core.metrics import metrics_collector
    
    # Clear any existing data
    if metrics_collector and "google" in metrics_collector.provider_metrics:
        del metrics_collector.provider_metrics["google"]
    
    # Record degraded metrics (high latency)
    if metrics_collector:
        for _ in range(10):
            metrics_collector.record_provider_request(
                provider="google",
                success=True,
                latency_ms=3000.0,  # High latency
                cost_usd=0.001,
                tokens=100,
            )
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/providers/google/health")
    
    assert response.status_code == 200
    data = response.json()
    
    health = data["health"]
    # Should be degraded due to high latency
    assert len(health["slo_breaches"]) > 0


@pytest.mark.asyncio
async def test_get_provider_health_invalid_provider():
    """Test getting health for invalid provider."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/providers/invalid_provider/health")
    
    assert response.status_code == 404
    data = response.json()
    assert "Unknown provider" in data["detail"]


@pytest.mark.asyncio
async def test_get_alerts_no_alerts():
    """Test getting alerts when none are active."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/alerts")
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "alerts" in data
    assert "summary" in data
    assert isinstance(data["alerts"], list)


@pytest.mark.asyncio
async def test_get_alerts_with_provider_filter():
    """Test getting alerts filtered by provider."""
    from venom_core.core.provider_observability import get_provider_observability
    
    obs = get_provider_observability()
    
    # Clear existing alerts
    obs.active_alerts.clear()
    
    # Add test alerts
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
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/alerts?provider=openai")
    
    assert response.status_code == 200
    data = response.json()
    assert data["count"] >= 1
    # All alerts should be for openai
    for alert in data["alerts"]:
        assert alert["provider"] == "openai"


@pytest.mark.asyncio
async def test_get_alerts_with_severity_filter():
    """Test getting alerts filtered by severity."""
    from venom_core.core.provider_observability import get_provider_observability
    
    obs = get_provider_observability()
    obs.active_alerts.clear()
    
    # Add test alerts with different severities
    alert1 = Alert(
        id="test_warn",
        severity=AlertSeverity.WARNING,
        alert_type=AlertType.HIGH_LATENCY,
        provider="openai",
        message="test",
    )
    alert2 = Alert(
        id="test_crit",
        severity=AlertSeverity.CRITICAL,
        alert_type=AlertType.ERROR_SPIKE,
        provider="openai",
        message="test",
    )
    
    obs.emit_alert(alert1)
    obs.emit_alert(alert2)
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/alerts?severity=critical")
    
    assert response.status_code == 200
    data = response.json()
    # All alerts should be critical
    for alert in data["alerts"]:
        assert alert["severity"] == "critical"


@pytest.mark.asyncio
async def test_get_alerts_invalid_provider():
    """Test getting alerts with invalid provider filter."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/alerts?provider=invalid_provider")
    
    assert response.status_code == 404
    data = response.json()
    assert "Unknown provider" in data["detail"]


@pytest.mark.asyncio
async def test_get_alerts_invalid_severity():
    """Test getting alerts with invalid severity filter."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/alerts?severity=invalid")
    
    assert response.status_code == 400
    data = response.json()
    assert "Invalid severity" in data["detail"]


@pytest.mark.asyncio
async def test_get_alerts_summary():
    """Test alert summary in response."""
    from venom_core.core.provider_observability import get_provider_observability
    
    obs = get_provider_observability()
    obs.active_alerts.clear()
    
    # Add multiple test alerts
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
            provider="google",
            message="test",
        )
    )
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/alerts")
    
    assert response.status_code == 200
    data = response.json()
    
    summary = data["summary"]
    assert "total_active" in summary
    assert "by_severity" in summary
    assert "by_provider" in summary
    assert summary["total_active"] >= 2
