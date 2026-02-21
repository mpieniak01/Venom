"""Remote Models API endpoints - remote provider status, catalog, and connectivity."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from venom_core.config import SETTINGS
from venom_core.services.config_manager import config_manager
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/models/remote", tags=["models", "remote"])

# ============================================================================
# Pydantic Response Models
# ============================================================================


class RemoteProviderStatus(BaseModel):
    """Remote provider status information."""

    provider: str = Field(..., description="Provider name (openai, google)")
    status: str = Field(
        ...,
        description="Status: configured, reachable, degraded, disabled",
    )
    last_check: datetime = Field(..., description="Last check timestamp")
    error: str | None = Field(default=None, description="Error message if any")
    latency_ms: float | None = Field(default=None, description="Latency in milliseconds")


class RemoteModelInfo(BaseModel):
    """Remote model information."""

    id: str = Field(..., description="Model ID")
    name: str = Field(..., description="Model display name")
    provider: str = Field(..., description="Provider name")
    capabilities: list[str] = Field(
        default_factory=list, description="Model capabilities"
    )
    model_alias: str | None = Field(default=None, description="Model alias/variant")


class ServiceModelBinding(BaseModel):
    """Service to model binding information."""

    service_id: str = Field(..., description="Service identifier")
    endpoint: str = Field(..., description="Endpoint path")
    http_method: str = Field(..., description="HTTP method")
    provider: str = Field(..., description="Provider name")
    model: str = Field(..., description="Model name")
    routing_mode: str = Field(..., description="Routing mode: direct, fallback, hybrid")
    fallback_order: list[str] | None = Field(
        default=None, description="Fallback order if any"
    )
    status: str = Field(..., description="Binding status")


class ValidationRequest(BaseModel):
    """Request to validate provider/model connection."""

    provider: str = Field(..., description="Provider name to validate")
    model: str | None = Field(default=None, description="Optional model name")


class ValidationResult(BaseModel):
    """Result of provider/model validation."""

    provider: str = Field(..., description="Provider name")
    valid: bool = Field(..., description="Whether validation passed")
    message: str = Field(..., description="Validation message")
    details: dict[str, Any] | None = Field(
        default=None, description="Additional details"
    )


# ============================================================================
# Helper Functions
# ============================================================================


def _check_openai_configured() -> bool:
    """Check if OpenAI API key is configured."""
    return bool(SETTINGS.OPENAI_API_KEY and SETTINGS.OPENAI_API_KEY.strip())


def _check_google_configured() -> bool:
    """Check if Google API key is configured."""
    return bool(SETTINGS.GOOGLE_API_KEY and SETTINGS.GOOGLE_API_KEY.strip())


def _get_openai_models_catalog() -> list[RemoteModelInfo]:
    """Get static OpenAI models catalog."""
    return [
        RemoteModelInfo(
            id="gpt-4o",
            name="GPT-4o",
            provider="openai",
            capabilities=["chat", "text-generation", "function-calling", "vision"],
            model_alias="gpt-4o-2024-08-06",
        ),
        RemoteModelInfo(
            id="gpt-4o-mini",
            name="GPT-4o Mini",
            provider="openai",
            capabilities=["chat", "text-generation", "function-calling"],
            model_alias="gpt-4o-mini-2024-07-18",
        ),
        RemoteModelInfo(
            id="gpt-4-turbo",
            name="GPT-4 Turbo",
            provider="openai",
            capabilities=["chat", "text-generation", "function-calling", "vision"],
            model_alias="gpt-4-turbo-2024-04-09",
        ),
        RemoteModelInfo(
            id="gpt-3.5-turbo",
            name="GPT-3.5 Turbo",
            provider="openai",
            capabilities=["chat", "text-generation", "function-calling"],
            model_alias="gpt-3.5-turbo-0125",
        ),
    ]


def _get_google_models_catalog() -> list[RemoteModelInfo]:
    """Get static Google models catalog."""
    return [
        RemoteModelInfo(
            id="gemini-1.5-pro",
            name="Gemini 1.5 Pro",
            provider="google",
            capabilities=["chat", "text-generation", "function-calling", "vision", "multimodal"],
            model_alias="gemini-1.5-pro-latest",
        ),
        RemoteModelInfo(
            id="gemini-1.5-flash",
            name="Gemini 1.5 Flash",
            provider="google",
            capabilities=["chat", "text-generation", "function-calling"],
            model_alias="gemini-1.5-flash-latest",
        ),
        RemoteModelInfo(
            id="gemini-pro",
            name="Gemini Pro",
            provider="google",
            capabilities=["chat", "text-generation"],
            model_alias="gemini-pro",
        ),
    ]


def _get_service_model_bindings() -> list[ServiceModelBinding]:
    """Get service-to-model bindings from config manager."""
    bindings = []
    
    # Get current LLM configuration
    llm_service_type = getattr(SETTINGS, "LLM_SERVICE_TYPE", "local")
    llm_model_name = getattr(SETTINGS, "LLM_MODEL_NAME", "phi3:latest")
    
    # Main LLM service binding
    if llm_service_type in ("openai", "google"):
        bindings.append(
            ServiceModelBinding(
                service_id="venom_llm_service",
                endpoint="/api/v1/llm/chat",
                http_method="POST",
                provider=llm_service_type,
                model=llm_model_name,
                routing_mode="direct",
                fallback_order=None,
                status="active",
            )
        )
    
    # Check if hybrid mode is enabled
    ai_mode = getattr(SETTINGS, "AI_MODE", "LOCAL")
    if ai_mode in ("HYBRID", "CLOUD"):
        hybrid_provider = getattr(SETTINGS, "HYBRID_CLOUD_PROVIDER", "google")
        hybrid_model = getattr(SETTINGS, "HYBRID_CLOUD_MODEL", "gemini-1.5-pro")
        
        bindings.append(
            ServiceModelBinding(
                service_id="venom_hybrid_service",
                endpoint="/api/v1/llm/chat",
                http_method="POST",
                provider=hybrid_provider,
                model=hybrid_model,
                routing_mode="hybrid" if ai_mode == "HYBRID" else "direct",
                fallback_order=(
                    [getattr(SETTINGS, "HYBRID_LOCAL_MODEL", "llama3"), hybrid_model]
                    if ai_mode == "HYBRID"
                    else None
                ),
                status="active",
            )
        )
    
    return bindings


# ============================================================================
# API Endpoints
# ============================================================================


@router.get("/providers")
async def get_remote_providers() -> dict[str, Any]:
    """
    Get status of remote providers (OpenAI, Google).
    
    Returns provider configuration status, reachability, and last check time.
    """
    now = datetime.now()
    providers_status = []
    
    # Check OpenAI
    openai_configured = _check_openai_configured()
    providers_status.append(
        RemoteProviderStatus(
            provider="openai",
            status="configured" if openai_configured else "disabled",
            last_check=now,
            error="OPENAI_API_KEY not configured" if not openai_configured else None,
            latency_ms=None,
        ).model_dump()
    )
    
    # Check Google
    google_configured = _check_google_configured()
    providers_status.append(
        RemoteProviderStatus(
            provider="google",
            status="configured" if google_configured else "disabled",
            last_check=now,
            error="GOOGLE_API_KEY not configured" if not google_configured else None,
            latency_ms=None,
        ).model_dump()
    )
    
    return {
        "status": "success",
        "providers": providers_status,
        "count": len(providers_status),
    }


@router.get("/catalog")
async def get_remote_catalog(
    provider: str = Query(..., description="Provider name: openai or google")
) -> dict[str, Any]:
    """
    Get catalog of remote models for a specific provider.
    
    Args:
        provider: Provider name (openai or google)
        
    Returns:
        List of available models with capabilities
    """
    provider = provider.lower()
    
    if provider not in ("openai", "google"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid provider: {provider}. Must be 'openai' or 'google'",
        )
    
    # Get catalog based on provider
    if provider == "openai":
        models = _get_openai_models_catalog()
    else:
        models = _get_google_models_catalog()
    
    now = datetime.now()
    
    return {
        "status": "success",
        "provider": provider,
        "models": [m.model_dump() for m in models],
        "count": len(models),
        "refreshed_at": now.isoformat(),
        "source": "static_catalog",
    }


@router.get("/connectivity")
async def get_connectivity_map() -> dict[str, Any]:
    """
    Get service-to-model binding map.
    
    Returns mapping of Venom services to remote providers and models,
    including routing mode and fallback configuration.
    """
    bindings = _get_service_model_bindings()
    
    return {
        "status": "success",
        "bindings": [b.model_dump() for b in bindings],
        "count": len(bindings),
    }


@router.post("/validate")
async def validate_provider(request: ValidationRequest) -> dict[str, Any]:
    """
    Validate connection for a specific provider/model.
    
    Checks if API key is configured and returns validation result.
    Note: This does not perform actual API calls to avoid key usage.
    
    Args:
        request: Validation request with provider and optional model
        
    Returns:
        Validation result with status and message
    """
    provider = request.provider.lower()
    
    if provider not in ("openai", "google"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid provider: {provider}. Must be 'openai' or 'google'",
        )
    
    # Check configuration
    if provider == "openai":
        configured = _check_openai_configured()
        api_key_setting = "OPENAI_API_KEY"
    else:
        configured = _check_google_configured()
        api_key_setting = "GOOGLE_API_KEY"
    
    if not configured:
        result = ValidationResult(
            provider=provider,
            valid=False,
            message=f"{api_key_setting} not configured",
            details={
                "reason": "missing_api_key",
                "suggestion": f"Set {api_key_setting} environment variable",
            },
        )
    else:
        result = ValidationResult(
            provider=provider,
            valid=True,
            message=f"{provider.title()} API key is configured",
            details={
                "configured": True,
                "note": "Configuration check only - no API call performed",
            },
        )
    
    return {
        "status": "success",
        "validation": result.model_dump(),
    }
