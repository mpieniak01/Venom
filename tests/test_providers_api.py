"""Tests for provider management API endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import patch, MagicMock

from venom_core.main import app


@pytest.mark.asyncio
async def test_list_providers():
    """Test listing all providers."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/providers")
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "providers" in data
    assert "active_provider" in data
    assert "count" in data
    assert data["count"] > 0
    
    # Check that we have the expected providers
    provider_names = {p["name"] for p in data["providers"]}
    assert "huggingface" in provider_names
    assert "ollama" in provider_names
    assert "vllm" in provider_names


@pytest.mark.asyncio
async def test_get_provider_info_huggingface():
    """Test getting info for HuggingFace provider."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/providers/huggingface")
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "provider" in data
    
    provider = data["provider"]
    assert provider["name"] == "huggingface"
    assert provider["provider_type"] == "catalog_integrator"
    assert provider["capabilities"]["search"] is True
    assert provider["capabilities"]["install"] is True
    assert provider["connection_status"]["status"] == "connected"


@pytest.mark.asyncio
async def test_get_provider_info_ollama():
    """Test getting info for Ollama provider."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/providers/ollama")
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "provider" in data
    
    provider = data["provider"]
    assert provider["name"] == "ollama"
    assert provider["provider_type"] == "catalog_integrator"
    assert provider["capabilities"]["search"] is True
    assert provider["capabilities"]["activate"] is True
    assert provider["capabilities"]["inference"] is True
    # Status depends on whether Ollama is running
    assert provider["connection_status"]["status"] in ["connected", "offline", "degraded"]


@pytest.mark.asyncio
async def test_get_provider_info_vllm():
    """Test getting info for vLLM provider."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/providers/vllm")
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "provider" in data
    
    provider = data["provider"]
    assert provider["name"] == "vllm"
    assert provider["provider_type"] == "local_runtime"
    assert provider["capabilities"]["install"] is True
    assert provider["capabilities"]["activate"] is True
    assert provider["capabilities"]["inference"] is True
    # Status depends on vLLM configuration and availability
    assert provider["connection_status"]["status"] in ["connected", "offline", "degraded"]


@pytest.mark.asyncio
async def test_get_provider_info_openai():
    """Test getting info for OpenAI provider."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/providers/openai")
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "provider" in data
    
    provider = data["provider"]
    assert provider["name"] == "openai"
    assert provider["provider_type"] == "cloud_provider"
    assert provider["capabilities"]["activate"] is True
    assert provider["capabilities"]["inference"] is True
    assert provider["capabilities"]["install"] is False
    # Status depends on API key configuration
    assert provider["connection_status"]["status"] in ["connected", "offline"]


@pytest.mark.asyncio
async def test_get_provider_info_google():
    """Test getting info for Google provider."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/providers/google")
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "provider" in data
    
    provider = data["provider"]
    assert provider["name"] == "google"
    assert provider["provider_type"] == "cloud_provider"
    assert provider["capabilities"]["activate"] is True
    assert provider["capabilities"]["inference"] is True
    assert provider["capabilities"]["install"] is False
    # Status depends on API key configuration
    assert provider["connection_status"]["status"] in ["connected", "offline"]


@pytest.mark.asyncio
async def test_get_provider_info_unknown():
    """Test getting info for unknown provider."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/providers/unknown_provider")
    
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data
    assert "Unknown provider" in data["detail"]


@pytest.mark.asyncio
async def test_get_provider_status():
    """Test getting connection status for a provider."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/providers/huggingface/status")
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["provider"] == "huggingface"
    assert "connection_status" in data
    assert data["connection_status"]["status"] == "connected"


@pytest.mark.asyncio
async def test_get_provider_status_unknown():
    """Test getting status for unknown provider."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/providers/unknown_provider/status")
    
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data


@pytest.mark.asyncio
async def test_activate_cloud_provider_without_capabilities():
    """Test activating a provider that doesn't support activation."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/api/v1/providers/huggingface/activate")
    
    assert response.status_code == 400
    data = response.json()
    assert "does not support activation" in data["detail"]


@pytest.mark.asyncio
async def test_activate_local_runtime_returns_error():
    """Test activating local runtime through provider endpoint."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/api/v1/providers/ollama/activate")
    
    # Should return 400 directing to use system/llm-servers endpoint
    assert response.status_code in [400, 503]  # 503 if offline
    data = response.json()
    assert "detail" in data


@pytest.mark.asyncio
@pytest.mark.skip(reason="Requires model_registry initialization in test mode")
async def test_search_models_with_pagination():
    """Test model search with pagination support."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get(
            "/api/v1/models/search",
            params={"query": "llama", "provider": "huggingface", "limit": 5, "page": 1}
        )
    
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "models" in data
    assert "page" in data
    assert "limit" in data
    assert "total" in data
    assert data["page"] == 1
    assert data["limit"] == 5


@pytest.mark.asyncio
async def test_provider_capabilities():
    """Test that provider capabilities are correctly set."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/providers")
    
    assert response.status_code == 200
    data = response.json()
    providers = {p["name"]: p for p in data["providers"]}
    
    # HuggingFace: search + install + trainable
    hf = providers["huggingface"]
    assert hf["capabilities"]["search"] is True
    assert hf["capabilities"]["install"] is True
    assert hf["capabilities"]["trainable"] is True
    assert hf["capabilities"]["activate"] is False
    assert hf["capabilities"]["inference"] is False
    
    # Ollama: search + install + activate + inference
    ollama = providers["ollama"]
    assert ollama["capabilities"]["search"] is True
    assert ollama["capabilities"]["install"] is True
    assert ollama["capabilities"]["activate"] is True
    assert ollama["capabilities"]["inference"] is True
    assert ollama["capabilities"]["trainable"] is False
    
    # vLLM: install + activate + inference
    vllm = providers["vllm"]
    assert vllm["capabilities"]["install"] is True
    assert vllm["capabilities"]["activate"] is True
    assert vllm["capabilities"]["inference"] is True
    assert vllm["capabilities"]["search"] is False
    
    # OpenAI: activate + inference only
    openai = providers["openai"]
    assert openai["capabilities"]["activate"] is True
    assert openai["capabilities"]["inference"] is True
    assert openai["capabilities"]["install"] is False
    assert openai["capabilities"]["search"] is False


@pytest.mark.asyncio
async def test_provider_types():
    """Test that provider types are correctly classified."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/providers")
    
    assert response.status_code == 200
    data = response.json()
    providers = {p["name"]: p for p in data["providers"]}
    
    # Cloud providers
    assert providers["openai"]["provider_type"] == "cloud_provider"
    assert providers["google"]["provider_type"] == "cloud_provider"
    
    # Catalog integrators
    assert providers["huggingface"]["provider_type"] == "catalog_integrator"
    assert providers["ollama"]["provider_type"] == "catalog_integrator"
    
    # Local runtimes
    assert providers["vllm"]["provider_type"] == "local_runtime"


@pytest.mark.asyncio
async def test_connection_status_structure():
    """Test that connection status has correct structure."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/providers/huggingface")
    
    assert response.status_code == 200
    data = response.json()
    status = data["provider"]["connection_status"]
    
    # Must have status field
    assert "status" in status
    assert status["status"] in ["connected", "degraded", "offline", "unknown"]
    
    # Optional fields
    if status["status"] != "connected":
        # May have reason_code and message for non-connected states
        pass

