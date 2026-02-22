"""Remote Models API endpoints - remote provider status, catalog, and connectivity."""

from __future__ import annotations

import os
import time
from datetime import datetime
from threading import Lock
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from venom_core.config import SETTINGS
from venom_core.infrastructure.traffic_control import TrafficControlledHttpClient
from venom_core.services.audit_stream import get_audit_stream
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/models/remote", tags=["models", "remote"])
PROVIDER_NAME_DESCRIPTION = "Provider name"

# ============================================================================
# Pydantic Response Models
# ============================================================================


class RemoteProviderStatus(BaseModel):
    """Remote provider status information."""

    provider: str = Field(
        ..., description=f"{PROVIDER_NAME_DESCRIPTION} (openai, google)"
    )
    status: str = Field(
        ...,
        description="Status: configured, reachable, degraded, disabled",
    )
    last_check: datetime = Field(..., description="Last check timestamp")
    error: str | None = Field(default=None, description="Error message if any")
    latency_ms: float | None = Field(
        default=None, description="Latency in milliseconds"
    )


class RemoteModelInfo(BaseModel):
    """Remote model information."""

    id: str = Field(..., description="Model ID")
    name: str = Field(..., description="Model display name")
    provider: str = Field(..., description=PROVIDER_NAME_DESCRIPTION)
    capabilities: list[str] = Field(
        default_factory=list, description="Model capabilities"
    )
    model_alias: str | None = Field(default=None, description="Model alias/variant")


class ServiceModelBinding(BaseModel):
    """Service to model binding information."""

    service_id: str = Field(..., description="Service identifier")
    endpoint: str = Field(..., description="Endpoint path")
    http_method: str = Field(..., description="HTTP method")
    provider: str = Field(..., description=PROVIDER_NAME_DESCRIPTION)
    model: str = Field(..., description="Model name")
    routing_mode: str = Field(..., description="Routing mode: direct, fallback, hybrid")
    fallback_order: list[str] | None = Field(
        default=None, description="Fallback order if any"
    )
    status: str = Field(..., description="Binding status")


class ValidationRequest(BaseModel):
    """Request to validate provider/model connection."""

    provider: str = Field(..., description=f"{PROVIDER_NAME_DESCRIPTION} to validate")
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

_DEFAULT_CATALOG_TTL_SECONDS = 300
_DEFAULT_PROVIDER_PROBE_TTL_SECONDS = 60
_DEFAULT_REMOTE_TIMEOUT_SECONDS = 6.0

_catalog_cache_lock = Lock()
_catalog_cache: dict[str, dict[str, Any]] = {}
_provider_probe_cache_lock = Lock()
_provider_probe_cache: dict[str, dict[str, Any]] = {}


def _env_int(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _catalog_ttl_seconds() -> int:
    return max(
        30,
        _env_int(
            "VENOM_REMOTE_MODELS_CATALOG_TTL_SECONDS", _DEFAULT_CATALOG_TTL_SECONDS
        ),
    )


def _provider_probe_ttl_seconds() -> int:
    return max(
        10,
        _env_int(
            "VENOM_REMOTE_MODELS_PROVIDER_PROBE_TTL_SECONDS",
            _DEFAULT_PROVIDER_PROBE_TTL_SECONDS,
        ),
    )


def _remote_timeout_seconds() -> float:
    return max(
        1.0,
        min(
            float(
                getattr(SETTINGS, "OPENAI_API_TIMEOUT", _DEFAULT_REMOTE_TIMEOUT_SECONDS)
            ),
            20.0,
        ),
    )


def _check_openai_configured() -> bool:
    """Check if OpenAI API key is configured."""
    return bool(SETTINGS.OPENAI_API_KEY and SETTINGS.OPENAI_API_KEY.strip())


def _check_google_configured() -> bool:
    """Check if Google API key is configured."""
    return bool(SETTINGS.GOOGLE_API_KEY and SETTINGS.GOOGLE_API_KEY.strip())


def _now_iso() -> str:
    return datetime.now().isoformat()


def _openai_models_url() -> str:
    endpoint = (getattr(SETTINGS, "OPENAI_CHAT_COMPLETIONS_ENDPOINT", "") or "").strip()
    if endpoint.endswith("/chat/completions"):
        return f"{endpoint[: -len('/chat/completions')]}/models"
    if endpoint.endswith("/v1"):
        return f"{endpoint}/models"
    if "/v1/" in endpoint:
        root, _, _ = endpoint.partition("/v1/")
        return f"{root}/v1/models"
    return "https://api.openai.com/v1/models"


def _openai_model_url(model_id: str) -> str:
    return f"{_openai_models_url().rstrip('/')}/{model_id}"


def _google_models_url() -> str:
    return "https://generativelanguage.googleapis.com/v1beta/models"


def _google_model_url(model_id: str) -> str:
    normalized = model_id if model_id.startswith("models/") else f"models/{model_id}"
    return f"https://generativelanguage.googleapis.com/v1beta/{normalized}"


def _map_openai_capabilities(model_id: str) -> list[str]:
    model = model_id.lower()
    capabilities = ["chat", "text-generation"]
    if "gpt-4" in model or "gpt-5" in model or "o1" in model or "o3" in model:
        capabilities.append("function-calling")
    if "gpt-4o" in model or "vision" in model:
        capabilities.append("vision")
    return capabilities


def _map_google_capabilities(item: dict[str, Any]) -> list[str]:
    methods = item.get("supportedGenerationMethods") or []
    mapped: set[str] = set()
    for method in methods:
        method_l = str(method).lower()
        if "generatecontent" in method_l:
            mapped.update({"chat", "text-generation"})
        if "streamgeneratecontent" in method_l:
            mapped.update({"chat", "text-generation"})
        if "counttokens" in method_l:
            mapped.add("token-counting")
        if "embedcontent" in method_l:
            mapped.add("embeddings")
    model_name = str(item.get("name") or "").lower()
    if (
        "vision" in model_name
        or "multimodal" in model_name
        or "gemini-1.5" in model_name
    ):
        mapped.add("vision")
    return sorted(mapped) if mapped else ["chat", "text-generation"]


def _cache_get(
    cache: dict[str, dict[str, Any]], lock: Lock, key: str, ttl_seconds: int
) -> dict[str, Any] | None:
    now = time.monotonic()
    with lock:
        entry = cache.get(key)
        if not entry:
            return None
        if now - float(entry.get("ts_monotonic", 0.0)) > ttl_seconds:
            cache.pop(key, None)
            return None
        return dict(entry)


def _cache_put(
    cache: dict[str, dict[str, Any]],
    lock: Lock,
    key: str,
    *,
    payload: dict[str, Any],
) -> None:
    with lock:
        cache[key] = {**payload, "ts_monotonic": time.monotonic()}


def _get_openai_models_catalog_static() -> list[RemoteModelInfo]:
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


def _get_google_models_catalog_static() -> list[RemoteModelInfo]:
    """Get static Google models catalog."""
    return [
        RemoteModelInfo(
            id="gemini-1.5-pro",
            name="Gemini 1.5 Pro",
            provider="google",
            capabilities=[
                "chat",
                "text-generation",
                "function-calling",
                "vision",
                "multimodal",
            ],
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


async def _fetch_openai_models_catalog_live() -> list[RemoteModelInfo]:
    api_key = (SETTINGS.OPENAI_API_KEY or "").strip()
    if not api_key:
        return []
    headers = {"Authorization": f"Bearer {api_key}"}
    timeout = _remote_timeout_seconds()
    async with TrafficControlledHttpClient(
        provider="openai",
        timeout=timeout,
    ) as client:
        response = await client.aget(_openai_models_url(), headers=headers)
        payload = response.json()
    raw_items = payload.get("data") if isinstance(payload, dict) else []
    items = raw_items if isinstance(raw_items, list) else []
    models: list[RemoteModelInfo] = []
    for item in items:
        model_id = str(item.get("id") or "").strip()
        if not model_id:
            continue
        models.append(
            RemoteModelInfo(
                id=model_id,
                name=model_id,
                provider="openai",
                capabilities=_map_openai_capabilities(model_id),
                model_alias=None,
            )
        )
    models.sort(key=lambda m: m.id.lower())
    return models


async def _fetch_google_models_catalog_live() -> list[RemoteModelInfo]:
    api_key = (SETTINGS.GOOGLE_API_KEY or "").strip()
    if not api_key:
        return []
    timeout = _remote_timeout_seconds()
    async with TrafficControlledHttpClient(
        provider="google",
        timeout=timeout,
    ) as client:
        response = await client.aget(_google_models_url(), params={"key": api_key})
        payload = response.json()
    raw_items = payload.get("models") if isinstance(payload, dict) else []
    items = raw_items if isinstance(raw_items, list) else []
    models: list[RemoteModelInfo] = []
    for item in items:
        raw_name = str(item.get("name") or "").strip()
        model_id = raw_name.removeprefix("models/")
        if not model_id:
            continue
        models.append(
            RemoteModelInfo(
                id=model_id,
                name=model_id,
                provider="google",
                capabilities=_map_google_capabilities(item),
                model_alias=raw_name if raw_name != model_id else None,
            )
        )
    models.sort(key=lambda m: m.id.lower())
    return models


async def _validate_openai_connection(
    *, model: str | None = None
) -> tuple[bool, str, float | None]:
    api_key = (SETTINGS.OPENAI_API_KEY or "").strip()
    if not api_key:
        return False, "OPENAI_API_KEY not configured", None
    url = _openai_model_url(model) if model else _openai_models_url()
    headers = {"Authorization": f"Bearer {api_key}"}
    timeout = _remote_timeout_seconds()
    start = time.perf_counter()
    try:
        async with TrafficControlledHttpClient(
            provider="openai",
            timeout=timeout,
        ) as client:
            response = await client.aget(
                url,
                headers=headers,
                raise_for_status=False,
            )
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        if response.status_code == 200:
            return True, "OpenAI API reachable", elapsed_ms
        if response.status_code == 401:
            return False, "OpenAI API key unauthorized", elapsed_ms
        if response.status_code == 404 and model:
            return False, f"Model not found: {model}", elapsed_ms
        return (
            False,
            f"OpenAI validation failed (HTTP {response.status_code})",
            elapsed_ms,
        )
    except httpx.HTTPError as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return False, f"OpenAI validation error: {exc}", elapsed_ms
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return False, f"OpenAI validation error: {exc}", elapsed_ms


async def _validate_google_connection(
    *, model: str | None = None
) -> tuple[bool, str, float | None]:
    api_key = (SETTINGS.GOOGLE_API_KEY or "").strip()
    if not api_key:
        return False, "GOOGLE_API_KEY not configured", None
    url = _google_model_url(model) if model else _google_models_url()
    timeout = _remote_timeout_seconds()
    start = time.perf_counter()
    try:
        async with TrafficControlledHttpClient(
            provider="google",
            timeout=timeout,
        ) as client:
            response = await client.aget(
                url,
                params={"key": api_key},
                raise_for_status=False,
            )
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        if response.status_code == 200:
            return True, "Google API reachable", elapsed_ms
        if response.status_code in (401, 403):
            return False, "Google API key unauthorized", elapsed_ms
        if response.status_code == 404 and model:
            return False, f"Model not found: {model}", elapsed_ms
        return (
            False,
            f"Google validation failed (HTTP {response.status_code})",
            elapsed_ms,
        )
    except httpx.HTTPError as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return False, f"Google validation error: {exc}", elapsed_ms
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return False, f"Google validation error: {exc}", elapsed_ms


async def _probe_provider_cached(provider: str) -> tuple[str, str | None, float | None]:
    cached = _cache_get(
        _provider_probe_cache,
        _provider_probe_cache_lock,
        provider,
        _provider_probe_ttl_seconds(),
    )
    if cached:
        return (
            str(cached.get("status") or "degraded"),
            cached.get("error"),
            cached.get("latency_ms"),
        )

    if provider == "openai":
        valid, message, latency = await _validate_openai_connection()
    else:
        valid, message, latency = await _validate_google_connection()

    status = "reachable" if valid else "degraded"
    error = None if valid else message
    _cache_put(
        _provider_probe_cache,
        _provider_probe_cache_lock,
        provider,
        payload={"status": status, "error": error, "latency_ms": latency},
    )
    return status, error, latency


async def _catalog_for_provider(
    provider: str,
) -> tuple[list[RemoteModelInfo], str, str | None]:
    cached = _cache_get(
        _catalog_cache,
        _catalog_cache_lock,
        provider,
        _catalog_ttl_seconds(),
    )
    if cached:
        cached_models = [RemoteModelInfo(**item) for item in cached.get("models", [])]
        return cached_models, str(cached.get("source") or "cache"), cached.get("error")

    fetch_live = (
        _fetch_openai_models_catalog_live
        if provider == "openai"
        else _fetch_google_models_catalog_live
    )
    static_models = (
        _get_openai_models_catalog_static()
        if provider == "openai"
        else _get_google_models_catalog_static()
    )
    live_error: str | None = None
    models: list[RemoteModelInfo]
    source: str
    if (provider == "openai" and _check_openai_configured()) or (
        provider == "google" and _check_google_configured()
    ):
        try:
            models = await fetch_live()
            source = f"{provider}_api"
            if not models:
                models = static_models
                source = "static_fallback_empty_live"
                live_error = "live catalog empty"
        except Exception as exc:
            logger.warning("Remote catalog live fetch failed for %s: %s", provider, exc)
            models = static_models
            source = "static_fallback_error"
            live_error = str(exc)
    else:
        models = static_models
        source = "static_fallback_unconfigured"
        live_error = f"{provider.upper()}_API_KEY not configured"

    _cache_put(
        _catalog_cache,
        _catalog_cache_lock,
        provider,
        payload={
            "models": [m.model_dump() for m in models],
            "source": source,
            "error": live_error,
            "refreshed_at": _now_iso(),
        },
    )
    return models, source, live_error


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
    if openai_configured:
        openai_status, openai_error, openai_latency = await _probe_provider_cached(
            "openai"
        )
    else:
        openai_status, openai_error, openai_latency = (
            "disabled",
            "OPENAI_API_KEY not configured",
            None,
        )
    providers_status.append(
        RemoteProviderStatus(
            provider="openai",
            status=openai_status,
            last_check=now,
            error=openai_error,
            latency_ms=openai_latency,
        ).model_dump()
    )

    # Check Google
    google_configured = _check_google_configured()
    if google_configured:
        google_status, google_error, google_latency = await _probe_provider_cached(
            "google"
        )
    else:
        google_status, google_error, google_latency = (
            "disabled",
            "GOOGLE_API_KEY not configured",
            None,
        )
    providers_status.append(
        RemoteProviderStatus(
            provider="google",
            status=google_status,
            last_check=now,
            error=google_error,
            latency_ms=google_latency,
        ).model_dump()
    )

    return {
        "status": "success",
        "providers": providers_status,
        "count": len(providers_status),
    }


@router.get(
    "/catalog",
    responses={
        400: {"description": "Invalid provider. Allowed values: openai, google."}
    },
)
async def get_remote_catalog(
    provider: Annotated[
        str, Query(..., description=f"{PROVIDER_NAME_DESCRIPTION}: openai or google")
    ],
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

    models, source, error = await _catalog_for_provider(provider)

    now = datetime.now()

    return {
        "status": "success",
        "provider": provider,
        "models": [m.model_dump() for m in models],
        "count": len(models),
        "refreshed_at": now.isoformat(),
        "source": source,
        "error": error,
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


@router.post(
    "/validate",
    responses={
        400: {"description": "Invalid provider. Allowed values: openai, google."}
    },
)
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

    model = (request.model or "").strip() or None
    if provider == "openai":
        valid, message, latency = await _validate_openai_connection(model=model)
    else:
        valid, message, latency = await _validate_google_connection(model=model)

    result = ValidationResult(
        provider=provider,
        valid=valid,
        message=message,
        details={
            "configured": _check_openai_configured()
            if provider == "openai"
            else _check_google_configured(),
            "model": model,
            "latency_ms": latency,
            "validation_mode": "live_api_call",
        },
    )
    get_audit_stream().publish(
        source="models.remote",
        action="validate_provider",
        actor="operator",
        status="success" if valid else "error",
        context=provider,
        details={
            "model": model,
            "message": message,
            "latency_ms": latency,
            "valid": valid,
        },
    )

    return {
        "status": "success",
        "validation": result.model_dump(),
    }
