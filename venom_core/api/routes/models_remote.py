"""Remote Models API endpoints - remote provider status, catalog, and connectivity."""

from __future__ import annotations

from datetime import datetime
from threading import Lock
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from venom_core.config import SETTINGS
from venom_core.services import remote_models_service
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

# Compatibility aliases for tests/monkeypatching while keeping router free from
# direct infrastructure/http-client imports.
TrafficControlledHttpClient = remote_models_service.traffic_controlled_http_client_cls()
httpx = remote_models_service.httpx_module()


def _env_int(name: str, default: int) -> int:
    return remote_models_service.env_int(name, default)


def _catalog_ttl_seconds() -> int:
    return remote_models_service.catalog_ttl_seconds()


def _provider_probe_ttl_seconds() -> int:
    return remote_models_service.provider_probe_ttl_seconds()


def _remote_timeout_seconds() -> float:
    return remote_models_service.remote_timeout_seconds(
        openai_api_timeout=getattr(
            SETTINGS,
            "OPENAI_API_TIMEOUT",
            _DEFAULT_REMOTE_TIMEOUT_SECONDS,
        )
    )


def _check_openai_configured() -> bool:
    """Check if OpenAI API key is configured."""
    return remote_models_service.is_api_key_configured(SETTINGS.OPENAI_API_KEY)


def _check_google_configured() -> bool:
    """Check if Google API key is configured."""
    return remote_models_service.is_api_key_configured(SETTINGS.GOOGLE_API_KEY)


def _now_iso() -> str:
    return datetime.now().isoformat()


def _openai_models_url() -> str:
    return remote_models_service.openai_models_url(
        chat_completions_endpoint=(
            getattr(SETTINGS, "OPENAI_CHAT_COMPLETIONS_ENDPOINT", "") or ""
        )
    )


def _openai_model_url(model_id: str) -> str:
    return remote_models_service.openai_model_url(
        models_url=_openai_models_url(),
        model_id=model_id,
    )


def _google_models_url() -> str:
    return remote_models_service.google_models_url()


def _google_model_url(model_id: str) -> str:
    return remote_models_service.google_model_url(model_id)


def _map_openai_capabilities(model_id: str) -> list[str]:
    return remote_models_service.map_openai_capabilities(model_id)


def _map_google_capabilities(item: dict[str, Any]) -> list[str]:
    return remote_models_service.map_google_capabilities(item)


def _cache_get(
    cache: dict[str, dict[str, Any]], lock: Lock, key: str, ttl_seconds: int
) -> dict[str, Any] | None:
    return remote_models_service.cache_get(cache, lock, key, ttl_seconds)


def _cache_put(
    cache: dict[str, dict[str, Any]],
    lock: Lock,
    key: str,
    *,
    payload: dict[str, Any],
) -> None:
    remote_models_service.cache_put(cache, lock, key, payload=payload)


async def _fetch_openai_models_catalog_live() -> list[RemoteModelInfo]:
    models_payload = await remote_models_service.fetch_openai_models_catalog_live(
        api_key=(SETTINGS.OPENAI_API_KEY or "").strip(),
        timeout_seconds=_remote_timeout_seconds(),
        models_url=_openai_models_url(),
        traffic_client_factory=TrafficControlledHttpClient,
        map_openai_capabilities_fn=_map_openai_capabilities,
    )
    return [RemoteModelInfo(**item) for item in models_payload]


async def _fetch_openai_models_catalog_live_payload() -> list[dict[str, Any]]:
    models = await _fetch_openai_models_catalog_live()
    return [model.model_dump() for model in models]


async def _fetch_google_models_catalog_live() -> list[RemoteModelInfo]:
    models_payload = await remote_models_service.fetch_google_models_catalog_live(
        api_key=(SETTINGS.GOOGLE_API_KEY or "").strip(),
        timeout_seconds=_remote_timeout_seconds(),
        models_url=_google_models_url(),
        traffic_client_factory=TrafficControlledHttpClient,
        map_google_capabilities_fn=_map_google_capabilities,
    )
    return [RemoteModelInfo(**item) for item in models_payload]


async def _fetch_google_models_catalog_live_payload() -> list[dict[str, Any]]:
    models = await _fetch_google_models_catalog_live()
    return [model.model_dump() for model in models]


async def _validate_openai_connection(
    *, model: str | None = None
) -> tuple[bool, str, float | None]:
    return await remote_models_service.validate_openai_connection(
        api_key=(SETTINGS.OPENAI_API_KEY or "").strip(),
        model=model,
        timeout_seconds=_remote_timeout_seconds(),
        openai_models_url=_openai_models_url(),
        openai_model_url_fn=_openai_model_url,
        traffic_client_factory=TrafficControlledHttpClient,
        http_error_type=httpx.HTTPError,
    )


async def _validate_google_connection(
    *, model: str | None = None
) -> tuple[bool, str, float | None]:
    return await remote_models_service.validate_google_connection(
        api_key=(SETTINGS.GOOGLE_API_KEY or "").strip(),
        model=model,
        timeout_seconds=_remote_timeout_seconds(),
        google_models_url=_google_models_url(),
        google_model_url_fn=_google_model_url,
        traffic_client_factory=TrafficControlledHttpClient,
        http_error_type=httpx.HTTPError,
    )


async def _probe_provider_cached(provider: str) -> tuple[str, str | None, float | None]:
    return await remote_models_service.probe_provider_cached(
        provider=provider,
        cache=_provider_probe_cache,
        lock=_provider_probe_cache_lock,
        provider_probe_ttl_seconds=_provider_probe_ttl_seconds(),
        cache_get_fn=_cache_get,
        cache_put_fn=_cache_put,
        validate_openai_connection_fn=_validate_openai_connection,
        validate_google_connection_fn=_validate_google_connection,
    )


async def _catalog_for_provider(
    provider: str,
) -> tuple[list[RemoteModelInfo], str, str | None]:
    (
        models_payload,
        source,
        live_error,
    ) = await remote_models_service.catalog_for_provider(
        provider=provider,
        cache=_catalog_cache,
        lock=_catalog_cache_lock,
        catalog_ttl_seconds=_catalog_ttl_seconds(),
        deps=remote_models_service.CatalogProviderDeps(
            cache_get_fn=_cache_get,
            cache_put_fn=_cache_put,
            fetch_openai_models_catalog_live_fn=(
                lambda: _fetch_openai_models_catalog_live_payload()
            ),
            fetch_google_models_catalog_live_fn=(
                lambda: _fetch_google_models_catalog_live_payload()
            ),
            openai_static_catalog_payload_fn=remote_models_service.openai_static_catalog_payload,
            google_static_catalog_payload_fn=remote_models_service.google_static_catalog_payload,
            check_openai_configured_fn=_check_openai_configured,
            check_google_configured_fn=_check_google_configured,
            now_iso_fn=_now_iso,
            logger=logger,
        ),
    )
    models = [RemoteModelInfo(**item) for item in models_payload]
    return models, source, live_error


def _get_service_model_bindings() -> list[ServiceModelBinding]:
    """Get service-to-model bindings from config manager."""
    return [
        ServiceModelBinding(**item)
        for item in remote_models_service.service_model_bindings_payload(
            settings=SETTINGS
        )
    ]


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
