"""Tests for governance API endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import patch

from venom_core.main import app


@pytest.mark.asyncio
async def test_get_governance_status():
    """Test getting governance status."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/governance/status")
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "cost_limits" in data
    assert "rate_limits" in data
    assert "recent_fallbacks" in data
    assert "fallback_policy" in data


@pytest.mark.asyncio
async def test_get_limits_config():
    """Test getting limits configuration."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/governance/limits")
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "cost_limits" in data
    assert "rate_limits" in data
    
    # Check structure of cost limits
    if "global" in data["cost_limits"]:
        global_cost = data["cost_limits"]["global"]
        assert "soft_limit_usd" in global_cost
        assert "hard_limit_usd" in global_cost


@pytest.mark.asyncio
async def test_get_provider_credential_status_configured():
    """Test checking credential status for configured provider."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/governance/providers/ollama/credentials")
    
    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "ollama"
    assert data["credential_status"] == "configured"
    assert "message" in data


@pytest.mark.asyncio
async def test_get_provider_credential_status_missing():
    """Test checking credential status for provider with missing credentials."""
    with patch("venom_core.core.provider_governance.SETTINGS") as mock_settings:
        mock_settings.OPENAI_API_KEY = ""
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/api/v1/governance/providers/openai/credentials")
        
        assert response.status_code == 200
        data = response.json()
        assert data["provider"] == "openai"
        assert data["credential_status"] in ["configured", "missing_credentials"]


@pytest.mark.asyncio
async def test_update_cost_limit():
    """Test updating cost limit."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        payload = {
            "limit_type": "cost",
            "scope": "global",
            "soft_limit_usd": 20.0,
            "hard_limit_usd": 100.0,
        }
        response = await ac.post("/api/v1/governance/limits", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "limit" in data
    assert data["limit"]["soft_limit_usd"] == 20.0
    assert data["limit"]["hard_limit_usd"] == 100.0


@pytest.mark.asyncio
async def test_update_rate_limit():
    """Test updating rate limit."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        payload = {
            "limit_type": "rate",
            "scope": "global",
            "max_requests_per_minute": 200,
            "max_tokens_per_minute": 200000,
        }
        response = await ac.post("/api/v1/governance/limits", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "limit" in data
    assert data["limit"]["max_requests_per_minute"] == 200
    assert data["limit"]["max_tokens_per_minute"] == 200000


@pytest.mark.asyncio
async def test_update_provider_specific_limit():
    """Test updating provider-specific limit."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        payload = {
            "limit_type": "cost",
            "scope": "openai",
            "soft_limit_usd": 5.0,
            "hard_limit_usd": 25.0,
        }
        response = await ac.post("/api/v1/governance/limits", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    # Message is now an i18n key
    assert "governance.messages" in data["message"]


@pytest.mark.asyncio
async def test_update_limit_invalid_type():
    """Test updating limit with invalid type."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        payload = {
            "limit_type": "invalid",
            "scope": "global",
            "soft_limit_usd": 10.0,
        }
        response = await ac.post("/api/v1/governance/limits", json=payload)
    
    assert response.status_code == 400
    assert "invalid" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_reset_usage_all():
    """Test resetting all usage counters."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/api/v1/governance/reset-usage")
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    # Message is now an i18n key
    assert "governance.messages" in data["message"]


@pytest.mark.asyncio
async def test_reset_usage_specific_scope():
    """Test resetting usage for specific scope."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/api/v1/governance/reset-usage?scope=openai")
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    # Message is now an i18n key
    assert "governance.messages" in data["message"]


@pytest.mark.asyncio
async def test_governance_integration_with_usage():
    """Test governance status reflects usage updates."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # First, reset usage
        await ac.post("/api/v1/governance/reset-usage")
        
        # Get initial status
        response1 = await ac.get("/api/v1/governance/status")
        data1 = response1.json()
        initial_usage = data1["cost_limits"]["global"]["current_usage_usd"]
        
        # Simulate usage by directly calling governance (in real scenario would be via inference)
        from venom_core.core.provider_governance import get_provider_governance
        governance = get_provider_governance()
        governance.record_usage("openai", cost_usd=2.5, tokens=500, requests=1)
        
        # Get updated status
        response2 = await ac.get("/api/v1/governance/status")
        data2 = response2.json()
        updated_usage = data2["cost_limits"]["global"]["current_usage_usd"]
        
        # Usage should have increased
        assert updated_usage > initial_usage


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "override",
    [
        # Negative soft limit
        {"soft_limit_usd": -1.0, "hard_limit_usd": 10.0},
        # Zero soft limit
        {"soft_limit_usd": 0.0, "hard_limit_usd": 10.0},
        # Negative hard limit
        {"soft_limit_usd": 10.0, "hard_limit_usd": -1.0},
        # Zero hard limit
        {"soft_limit_usd": 10.0, "hard_limit_usd": 0.0},
    ],
)
async def test_update_cost_limit_invalid_values(override):
    """Test that invalid cost limit values are rejected."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        payload = {
            "limit_type": "cost",
            "scope": "global",
            "soft_limit_usd": 10.0,
            "hard_limit_usd": 20.0,
        }
        payload.update(override)
        response = await ac.post("/api/v1/governance/limits", json=payload)

    assert response.status_code == 422  # Pydantic validation error


@pytest.mark.asyncio
async def test_update_cost_limit_soft_greater_than_hard():
    """Test that soft limit greater than hard limit is rejected."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        payload = {
            "limit_type": "cost",
            "scope": "global",
            "soft_limit_usd": 20.0,
            "hard_limit_usd": 10.0,
        }
        response = await ac.post("/api/v1/governance/limits", json=payload)

    assert response.status_code == 400


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "override",
    [
        # Negative request rate limit
        {"max_requests_per_minute": -1, "max_tokens_per_minute": 1000},
        # Zero request rate limit
        {"max_requests_per_minute": 0, "max_tokens_per_minute": 1000},
        # Negative token rate limit
        {"max_requests_per_minute": 60, "max_tokens_per_minute": -1},
        # Zero token rate limit
        {"max_requests_per_minute": 60, "max_tokens_per_minute": 0},
    ],
)
async def test_update_rate_limit_invalid_values(override):
    """Test that invalid rate limit values are rejected."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        payload = {
            "limit_type": "rate",
            "scope": "global",
            "max_requests_per_minute": 60,
            "max_tokens_per_minute": 1000,
        }
        payload.update(override)
        response = await ac.post("/api/v1/governance/limits", json=payload)

    assert response.status_code == 422  # Pydantic validation error
