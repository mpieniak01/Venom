"""Tests for remote models API endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient

from venom_core.main import app


@pytest.mark.asyncio
async def test_get_remote_providers():
    """Test getting remote provider status."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/api/v1/models/remote/providers")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "providers" in data
    assert "count" in data
    assert data["count"] == 2  # OpenAI and Google

    # Check provider structure
    provider_names = {p["provider"] for p in data["providers"]}
    assert "openai" in provider_names
    assert "google" in provider_names

    # Check that each provider has required fields
    for provider in data["providers"]:
        assert "provider" in provider
        assert "status" in provider
        assert "last_check" in provider
        assert provider["status"] in ["configured", "disabled", "reachable", "degraded"]


@pytest.mark.asyncio
async def test_get_remote_catalog_openai():
    """Test getting OpenAI models catalog."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/api/v1/models/remote/catalog?provider=openai")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["provider"] == "openai"
    assert "models" in data
    assert "count" in data
    assert "refreshed_at" in data
    assert "source" in data
    assert data["source"] == "static_catalog"
    assert data["count"] > 0

    # Check model structure
    for model in data["models"]:
        assert "id" in model
        assert "name" in model
        assert "provider" in model
        assert model["provider"] == "openai"
        assert "capabilities" in model
        assert isinstance(model["capabilities"], list)


@pytest.mark.asyncio
async def test_get_remote_catalog_google():
    """Test getting Google models catalog."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/api/v1/models/remote/catalog?provider=google")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["provider"] == "google"
    assert "models" in data
    assert data["count"] > 0

    # Check model structure
    for model in data["models"]:
        assert model["provider"] == "google"
        assert "capabilities" in model


@pytest.mark.asyncio
async def test_get_remote_catalog_invalid_provider():
    """Test getting catalog with invalid provider."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/api/v1/models/remote/catalog?provider=invalid")

    assert response.status_code == 400
    data = response.json()
    assert "detail" in data
    assert "invalid" in data["detail"].lower()


@pytest.mark.asyncio
async def test_get_connectivity_map():
    """Test getting service-to-model connectivity map."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/api/v1/models/remote/connectivity")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "bindings" in data
    assert "count" in data
    assert isinstance(data["bindings"], list)

    # Check binding structure if any exist
    for binding in data["bindings"]:
        assert "service_id" in binding
        assert "endpoint" in binding
        assert "http_method" in binding
        assert "provider" in binding
        assert "model" in binding
        assert "routing_mode" in binding
        assert "status" in binding


@pytest.mark.asyncio
async def test_validate_provider_openai():
    """Test validating OpenAI provider."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.post(
            "/api/v1/models/remote/validate",
            json={"provider": "openai"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "validation" in data

    validation = data["validation"]
    assert validation["provider"] == "openai"
    assert "valid" in validation
    assert "message" in validation
    assert isinstance(validation["valid"], bool)


@pytest.mark.asyncio
async def test_validate_provider_google():
    """Test validating Google provider."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.post(
            "/api/v1/models/remote/validate",
            json={"provider": "google"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "validation" in data

    validation = data["validation"]
    assert validation["provider"] == "google"
    assert "valid" in validation
    assert "message" in validation


@pytest.mark.asyncio
async def test_validate_provider_invalid():
    """Test validating invalid provider."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.post(
            "/api/v1/models/remote/validate",
            json={"provider": "invalid"},
        )

    assert response.status_code == 400
    data = response.json()
    assert "detail" in data
    assert "invalid" in data["detail"].lower()


@pytest.mark.asyncio
async def test_validate_provider_with_model():
    """Test validating provider with specific model."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.post(
            "/api/v1/models/remote/validate",
            json={"provider": "openai", "model": "gpt-4o"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "validation" in data
