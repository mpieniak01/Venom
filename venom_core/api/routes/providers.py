"""Provider management API endpoints."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from venom_core.api.routes.models_dependencies import get_model_registry
from venom_core.config import SETTINGS
from venom_core.core.model_registry import ModelProvider
from venom_core.services.config_manager import config_manager
from venom_core.utils.llm_runtime import get_active_llm_runtime
from venom_core.utils.logger import get_logger
from venom_core.utils.url_policy import build_http_url

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["providers"])


class ProviderCapability(BaseModel):
    """Provider capabilities."""

    install: bool = Field(default=False, description="Supports model installation")
    search: bool = Field(default=False, description="Supports model search")
    activate: bool = Field(default=False, description="Supports runtime activation")
    inference: bool = Field(default=False, description="Supports inference")
    trainable: bool = Field(default=False, description="Supports model training")


class ProviderStatus(BaseModel):
    """Provider connection status."""

    status: str = Field(
        ...,
        description="Connection status: connected, degraded, offline, unknown",
    )
    reason_code: Optional[str] = Field(
        default=None, description="Reason code for non-connected status"
    )
    message: Optional[str] = Field(
        default=None, description="Human-readable status message"
    )
    latency_ms: Optional[float] = Field(
        default=None, description="Connection latency in milliseconds"
    )


class ProviderInfo(BaseModel):
    """Provider information."""

    name: str = Field(..., description="Provider name")
    display_name: str = Field(..., description="Display name")
    provider_type: str = Field(
        ..., description="Type: cloud_provider, catalog_integrator, local_runtime"
    )
    runtime: str = Field(..., description="Runtime identifier")
    capabilities: ProviderCapability
    connection_status: ProviderStatus
    is_active: bool = Field(default=False, description="Is currently active")
    endpoint: Optional[str] = Field(default=None, description="Provider endpoint")


class ProviderActivateRequest(BaseModel):
    """Request to activate a provider."""

    provider: str = Field(..., description="Provider to activate")
    runtime: Optional[str] = Field(
        default=None, description="Optional runtime override"
    )
    model: Optional[str] = Field(default=None, description="Optional model name")


def _get_provider_type(provider: str) -> str:
    """Determine provider type."""
    if provider in ("openai", "google"):
        return "cloud_provider"
    if provider in ("huggingface", "ollama"):
        return "catalog_integrator"
    if provider in ("vllm", "local"):
        return "local_runtime"
    return "unknown"


def _get_provider_capabilities(provider: str) -> ProviderCapability:
    """Get provider capabilities."""
    if provider == "huggingface":
        return ProviderCapability(
            install=True, search=True, activate=False, inference=False, trainable=True
        )
    elif provider == "ollama":
        return ProviderCapability(
            install=True, search=True, activate=True, inference=True, trainable=False
        )
    elif provider == "vllm":
        return ProviderCapability(
            install=True, search=False, activate=True, inference=True, trainable=False
        )
    elif provider == "openai":
        return ProviderCapability(
            install=False, search=False, activate=True, inference=True, trainable=False
        )
    elif provider == "google":
        return ProviderCapability(
            install=False, search=False, activate=True, inference=True, trainable=False
        )
    elif provider == "local":
        return ProviderCapability(
            install=False, search=False, activate=True, inference=True, trainable=False
        )
    else:
        return ProviderCapability()


async def _check_provider_connection(provider: str) -> ProviderStatus:
    """Check provider connection status."""
    # Check local runtimes
    if provider == "ollama":
        return await _check_ollama_status()
    elif provider == "vllm":
        return await _check_vllm_status()
    # Cloud providers - check API keys
    elif provider == "openai":
        return _check_openai_status()
    elif provider == "google":
        return _check_google_status()
    # Catalog integrators - always available
    elif provider == "huggingface":
        return ProviderStatus(
            status="connected",
            message="HuggingFace catalog available",
        )
    else:
        return ProviderStatus(
            status="unknown",
            reason_code="unsupported_provider",
            message=f"Unknown provider: {provider}",
        )


async def _check_ollama_status() -> ProviderStatus:
    """Check Ollama server status."""
    endpoint = build_http_url("localhost", 11434)
    health_url = f"{endpoint}/api/tags"
    
    try:
        start = time.perf_counter()
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(health_url)
        latency_ms = (time.perf_counter() - start) * 1000
        
        if response.status_code == 200:
            return ProviderStatus(
                status="connected",
                message="Ollama server is running",
                latency_ms=latency_ms,
            )
        else:
            return ProviderStatus(
                status="degraded",
                reason_code="http_error",
                message=f"HTTP {response.status_code}",
                latency_ms=latency_ms,
            )
    except Exception as exc:
        return ProviderStatus(
            status="offline",
            reason_code="connection_failed",
            message=str(exc),
        )


async def _check_vllm_status() -> ProviderStatus:
    """Check vLLM server status."""
    endpoint = SETTINGS.VLLM_ENDPOINT
    if not endpoint:
        return ProviderStatus(
            status="offline",
            reason_code="no_endpoint",
            message="VLLM_ENDPOINT not configured",
        )
    
    health_url = f"{endpoint}/health"
    
    try:
        start = time.perf_counter()
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(health_url)
        latency_ms = (time.perf_counter() - start) * 1000
        
        if response.status_code == 200:
            return ProviderStatus(
                status="connected",
                message="vLLM server is running",
                latency_ms=latency_ms,
            )
        else:
            return ProviderStatus(
                status="degraded",
                reason_code="http_error",
                message=f"HTTP {response.status_code}",
                latency_ms=latency_ms,
            )
    except Exception as exc:
        return ProviderStatus(
            status="offline",
            reason_code="connection_failed",
            message=str(exc),
        )


def _check_openai_status() -> ProviderStatus:
    """Check OpenAI configuration."""
    if SETTINGS.OPENAI_API_KEY:
        return ProviderStatus(
            status="connected",
            message="OpenAI API key configured",
        )
    else:
        return ProviderStatus(
            status="offline",
            reason_code="missing_api_key",
            message="OPENAI_API_KEY not configured",
        )


def _check_google_status() -> ProviderStatus:
    """Check Google Gemini configuration."""
    if SETTINGS.GOOGLE_API_KEY:
        return ProviderStatus(
            status="connected",
            message="Google API key configured",
        )
    else:
        return ProviderStatus(
            status="offline",
            reason_code="missing_api_key",
            message="GOOGLE_API_KEY not configured",
        )


def _get_provider_endpoint(provider: str) -> Optional[str]:
    """Get provider endpoint if applicable."""
    if provider == "ollama":
        return build_http_url("localhost", 11434)
    elif provider == "vllm":
        return SETTINGS.VLLM_ENDPOINT
    return None


@router.get("/providers")
async def list_providers() -> dict[str, Any]:
    """
    List all available providers with their capabilities and status.
    
    Returns information about cloud providers, catalog integrators, and local runtimes.
    """
    # Get active runtime info
    active_runtime = get_active_llm_runtime()
    active_provider = active_runtime.provider.lower() if active_runtime.provider else None
    
    # Define all providers
    provider_names = [
        "huggingface",
        "ollama",
        "vllm",
        "openai",
        "google",
    ]
    
    # Check status for all providers in parallel
    status_tasks = [_check_provider_connection(p) for p in provider_names]
    statuses = await asyncio.gather(*status_tasks)
    
    providers = []
    for provider_name, status in zip(provider_names, statuses):
        provider_info = ProviderInfo(
            name=provider_name,
            display_name=provider_name.title(),
            provider_type=_get_provider_type(provider_name),
            runtime=provider_name,
            capabilities=_get_provider_capabilities(provider_name),
            connection_status=status,
            is_active=(provider_name == active_provider),
            endpoint=_get_provider_endpoint(provider_name),
        )
        providers.append(provider_info.model_dump())
    
    return {
        "status": "success",
        "providers": providers,
        "active_provider": active_provider,
        "count": len(providers),
    }


@router.get("/providers/{provider_name}")
async def get_provider_info(provider_name: str) -> dict[str, Any]:
    """
    Get detailed information about a specific provider.
    
    Args:
        provider_name: Provider identifier (huggingface, ollama, vllm, openai, google)
    """
    provider_name = provider_name.lower()
    
    # Validate provider
    valid_providers = {"huggingface", "ollama", "vllm", "openai", "google"}
    if provider_name not in valid_providers:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown provider: {provider_name}",
        )
    
    # Get active runtime
    active_runtime = get_active_llm_runtime()
    is_active = (
        active_runtime.provider.lower() == provider_name
        if active_runtime.provider
        else False
    )
    
    # Check connection status
    status = await _check_provider_connection(provider_name)
    
    provider_info = ProviderInfo(
        name=provider_name,
        display_name=provider_name.title(),
        provider_type=_get_provider_type(provider_name),
        runtime=provider_name,
        capabilities=_get_provider_capabilities(provider_name),
        connection_status=status,
        is_active=is_active,
        endpoint=_get_provider_endpoint(provider_name),
    )
    
    return {
        "status": "success",
        "provider": provider_info.model_dump(),
    }


@router.post("/providers/{provider_name}/activate")
async def activate_provider(
    provider_name: str,
    request: Optional[ProviderActivateRequest] = None,
) -> dict[str, Any]:
    """
    Activate a provider/runtime.
    
    Args:
        provider_name: Provider to activate (huggingface, ollama, vllm, openai, google)
        request: Optional activation parameters
    """
    provider_name = provider_name.lower()
    
    # Validate provider
    valid_providers = {"huggingface", "ollama", "vllm", "openai", "google"}
    if provider_name not in valid_providers:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown provider: {provider_name}",
        )
    
    # Check if provider supports activation
    capabilities = _get_provider_capabilities(provider_name)
    if not capabilities.activate:
        raise HTTPException(
            status_code=400,
            detail=f"Provider {provider_name} does not support activation",
        )
    
    # Check provider status
    status = await _check_provider_connection(provider_name)
    if status.status == "offline":
        raise HTTPException(
            status_code=503,
            detail=f"Provider {provider_name} is offline: {status.message}",
        )
    
    # Activate based on provider type
    if provider_name in ("openai", "google"):
        # Cloud providers - update runtime config
        try:
            if provider_name == "openai":
                model = (
                    request.model if request and request.model else SETTINGS.OPENAI_GPT4O_MODEL
                )
                SETTINGS.LLM_SERVICE_TYPE = "openai"
                SETTINGS.LLM_MODEL_NAME = model
                SETTINGS.ACTIVE_LLM_SERVER = "openai"
                config_manager.update_config({
                    "LLM_SERVICE_TYPE": "openai",
                    "LLM_MODEL_NAME": model,
                    "ACTIVE_LLM_SERVER": "openai",
                })
            else:  # google
                model = (
                    request.model if request and request.model else SETTINGS.GOOGLE_GEMINI_PRO_MODEL
                )
                SETTINGS.LLM_SERVICE_TYPE = "google"
                SETTINGS.LLM_MODEL_NAME = model
                SETTINGS.ACTIVE_LLM_SERVER = "google"
                config_manager.update_config({
                    "LLM_SERVICE_TYPE": "google",
                    "LLM_MODEL_NAME": model,
                    "ACTIVE_LLM_SERVER": "google",
                })
            
            return {
                "status": "success",
                "message": f"Provider {provider_name} activated successfully",
                "provider": provider_name,
                "model": model,
            }
        except Exception as exc:
            logger.exception(f"Failed to activate provider {provider_name}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to activate provider: {str(exc)}",
            ) from exc
    
    elif provider_name in ("ollama", "vllm"):
        # Local runtimes - delegate to system_llm endpoint
        # This is handled by /system/llm-servers/active endpoint
        raise HTTPException(
            status_code=400,
            detail=f"Local runtime {provider_name} activation should use /system/llm-servers/active endpoint",
        )
    
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Provider {provider_name} activation not implemented",
        )


@router.get("/providers/{provider_name}/status")
async def get_provider_status(provider_name: str) -> dict[str, Any]:
    """
    Get connection status for a specific provider.
    
    Args:
        provider_name: Provider identifier
    """
    provider_name = provider_name.lower()
    
    # Validate provider
    valid_providers = {"huggingface", "ollama", "vllm", "openai", "google"}
    if provider_name not in valid_providers:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown provider: {provider_name}",
        )
    
    status = await _check_provider_connection(provider_name)
    
    return {
        "status": "success",
        "provider": provider_name,
        "connection_status": status.model_dump(),
    }
