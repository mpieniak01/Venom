"""Provider management API endpoints."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from venom_core.config import SETTINGS
from venom_core.services.config_manager import config_manager
from venom_core.utils.llm_runtime import get_active_llm_runtime
from venom_core.utils.logger import get_logger
from venom_core.utils.url_policy import build_http_url

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["providers"])

# Valid provider names
VALID_PROVIDERS = {"huggingface", "ollama", "vllm", "openai", "google"}


def _extract_user_from_request(request: Request) -> str:
    """
    Extract user identifier from request for audit logging.

    Attempts to identify the user from:
    1. Authenticated user in request.state (set by auth middleware)
    2. Common identity headers (X-Authenticated-User, X-User, X-Admin-User)
    3. Falls back to "unknown" if no user can be determined

    Args:
        request: FastAPI request object

    Returns:
        User identifier string
    """
    try:
        # Try user set by authentication middleware on request.state
        if hasattr(request, "state") and hasattr(request.state, "user"):
            user = request.state.user
            if user:
                return str(user)

        # Fallback to common identity headers
        if hasattr(request, "headers"):
            for header_name in (
                "X-Authenticated-User",
                "X-User",
                "X-Admin-User",
            ):
                header_value = request.headers.get(header_name)
                if header_value:
                    return header_value

    except Exception as exc:
        # Never let user extraction errors break the endpoint
        logger.warning(f"Failed to extract user from request: {exc}")

    return "unknown"


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
        logger.warning(f"Failed to check Ollama status: {exc}")
        return ProviderStatus(
            status="offline",
            reason_code="connection_failed",
            message="Unable to connect to Ollama server",
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
        logger.warning(f"Failed to check vLLM status: {exc}")
        return ProviderStatus(
            status="offline",
            reason_code="connection_failed",
            message="Unable to connect to vLLM server",
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
    active_provider = (
        active_runtime.provider.lower() if active_runtime.provider else None
    )

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
    if provider_name not in VALID_PROVIDERS:
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
    if provider_name not in VALID_PROVIDERS:
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
                    request.model
                    if request and request.model
                    else SETTINGS.OPENAI_GPT4O_MODEL
                )
                # Update config atomically through config_manager only
                config_manager.update_config(
                    {
                        "LLM_SERVICE_TYPE": "openai",
                        "LLM_MODEL_NAME": model,
                        "ACTIVE_LLM_SERVER": "openai",
                    }
                )
            else:  # google
                model = (
                    request.model
                    if request and request.model
                    else SETTINGS.GOOGLE_GEMINI_PRO_MODEL
                )
                # Update config atomically through config_manager only
                config_manager.update_config(
                    {
                        "LLM_SERVICE_TYPE": "google",
                        "LLM_MODEL_NAME": model,
                        "ACTIVE_LLM_SERVER": "google",
                    }
                )

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
    if provider_name not in VALID_PROVIDERS:
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


@router.get("/providers/{provider_name}/metrics")
async def get_provider_metrics(provider_name: str) -> dict[str, Any]:
    """
    Get performance metrics for a specific provider.

    Returns latency percentiles, error rates, cost, and throughput.

    Args:
        provider_name: Provider identifier
    """
    from venom_core.core.metrics import get_metrics_collector

    provider_name = provider_name.lower()

    # Validate provider
    if provider_name not in VALID_PROVIDERS:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown provider: {provider_name}",
        )

    provider_metrics = get_metrics_collector().get_provider_metrics(provider_name)

    if not provider_metrics:
        # Return empty metrics structure
        return {
            "status": "success",
            "provider": provider_name,
            "metrics": {
                "total_requests": 0,
                "successful_requests": 0,
                "failed_requests": 0,
                "success_rate": 0.0,
                "error_rate": 0.0,
                "latency": {
                    "p50_ms": None,
                    "p95_ms": None,
                    "p99_ms": None,
                    "samples": 0,
                },
                "errors": {
                    "total": 0,
                    "timeouts": 0,
                    "auth_errors": 0,
                    "budget_errors": 0,
                    "by_code": {},
                },
                "cost": {
                    "total_usd": 0.0,
                    "total_tokens": 0,
                },
            },
        }

    return {
        "status": "success",
        "provider": provider_name,
        "metrics": provider_metrics,
    }


@router.get("/providers/{provider_name}/health")
async def get_provider_health(provider_name: str) -> dict[str, Any]:
    """
    Get SLO status and health score for a specific provider.

    Args:
        provider_name: Provider identifier
    """
    from venom_core.core.metrics import get_metrics_collector
    from venom_core.core.provider_observability import get_provider_observability

    provider_name = provider_name.lower()

    # Validate provider
    if provider_name not in VALID_PROVIDERS:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown provider: {provider_name}",
        )

    observability = get_provider_observability()
    provider_metrics = get_metrics_collector().get_provider_metrics(provider_name)
    slo_status = observability.calculate_slo_status(provider_name, provider_metrics)

    return {
        "status": "success",
        "provider": provider_name,
        "health": {
            "health_status": slo_status.health_status.value,
            "health_score": slo_status.health_score,
            "availability": slo_status.availability,
            "latency_p99_ms": slo_status.latency_p99_ms,
            "error_rate": slo_status.error_rate,
            "cost_usage_usd": slo_status.cost_usage_usd,
            "slo_target": {
                "availability_target": slo_status.slo_target.availability_target,
                "latency_p99_ms": slo_status.slo_target.latency_p99_ms,
                "error_rate_target": slo_status.slo_target.error_rate_target,
                "cost_budget_usd": slo_status.slo_target.cost_budget_usd,
            },
            "slo_breaches": slo_status.breaches,
        },
    }


@router.get("/alerts")
async def get_alerts(
    provider: Optional[str] = None,
    severity: Optional[str] = None,
) -> dict[str, Any]:
    """
    Get active alerts for providers.

    Args:
        provider: Optional provider filter
        severity: Optional severity filter (info, warning, critical)
    """
    from venom_core.core.provider_observability import get_provider_observability

    observability = get_provider_observability()

    # Get active alerts (optionally filtered by provider)
    if provider:
        provider = provider.lower()
        if provider not in VALID_PROVIDERS:
            raise HTTPException(
                status_code=404,
                detail=f"Unknown provider: {provider}",
            )

    active_alerts = observability.get_active_alerts(provider)

    # Filter by severity if specified
    if severity:
        severity = severity.lower()
        if severity not in ("info", "warning", "critical"):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid severity: {severity}. Must be info, warning, or critical",
            )
        active_alerts = [a for a in active_alerts if a.severity.value == severity]

    # Get summary
    summary = observability.get_alert_summary()

    # Convert alerts to dict
    alerts_data = [
        {
            "id": alert.id,
            "severity": alert.severity.value,
            "alert_type": alert.alert_type.value,
            "provider": alert.provider,
            "message": alert.message,
            "technical_details": alert.technical_details,
            "timestamp": alert.timestamp.isoformat(),
            "expires_at": alert.expires_at.isoformat() if alert.expires_at else None,
            "metadata": alert.metadata,
        }
        for alert in active_alerts
    ]

    return {
        "status": "success",
        "alerts": alerts_data,
        "summary": summary,
        "count": len(alerts_data),
    }


@router.post("/providers/{provider_name}/test-connection")
async def test_provider_connection(
    provider_name: str, request: Request
) -> dict[str, Any]:
    """
    Test connection to a provider (admin endpoint).

    This is an idempotent operation safe for retry.
    Performs a connection test and returns detailed diagnostics.

    Args:
        provider_name: Provider identifier
        request: FastAPI request object

    Returns:
        Connection test results with error mappings and runbook links
    """
    from venom_core.core.admin_audit import get_audit_trail
    from venom_core.core.error_mappings import (
        get_admin_message_key,
        get_recovery_hint_key,
        get_runbook_path,
        get_severity,
        get_user_message_key,
    )

    provider_name = provider_name.lower()

    # Validate provider
    if provider_name not in VALID_PROVIDERS:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown provider: {provider_name}",
        )

    # Audit the test
    audit_trail = get_audit_trail()
    user = _extract_user_from_request(request)

    try:
        # Perform connection test
        status = await _check_provider_connection(provider_name)

        # Build enriched response with error mappings
        response = {
            "status": "success" if status.status == "connected" else "failure",
            "provider": provider_name,
            "connection_status": status.status,
            "latency_ms": status.latency_ms,
            "message": status.message,
        }

        # Add error mapping if not connected
        if status.reason_code:
            response["error_info"] = {
                "reason_code": status.reason_code,
                "user_message_key": get_user_message_key(status.reason_code),
                "admin_message_key": get_admin_message_key(status.reason_code),
                "recovery_hint_key": get_recovery_hint_key(status.reason_code),
                "runbook_path": get_runbook_path(status.reason_code),
                "severity": get_severity(status.reason_code),
            }

        # Log to audit trail
        audit_trail.log_action(
            action="test_connection",
            user=user,
            provider=provider_name,
            details={"status": status.status, "latency_ms": status.latency_ms},
            result="success" if status.status == "connected" else "failure",
            error_message=status.message if status.status != "connected" else None,
        )

        return response

    except Exception as exc:
        logger.exception(f"Failed to test provider {provider_name} connection")
        audit_trail.log_action(
            action="test_connection",
            user=user,
            provider=provider_name,
            details={},
            result="failure",
            error_message=str(exc),
        )
        raise HTTPException(
            status_code=500,
            detail=f"Connection test failed: {str(exc)}",
        ) from exc


@router.post("/providers/{provider_name}/preflight")
async def provider_preflight_check(
    provider_name: str, request: Request
) -> dict[str, Any]:
    """
    Perform preflight validation for a provider (admin endpoint).

    Checks:
    - Connection status
    - Credentials configuration
    - Capabilities
    - Current metrics

    Args:
        provider_name: Provider identifier
        request: FastAPI request object

    Returns:
        Comprehensive preflight check results
    """
    from venom_core.core.admin_audit import get_audit_trail

    provider_name = provider_name.lower()

    # Validate provider
    if provider_name not in VALID_PROVIDERS:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown provider: {provider_name}",
        )

    audit_trail = get_audit_trail()
    user = _extract_user_from_request(request)

    try:
        # Gather all preflight checks
        checks = {}

        # 1. Connection check
        connection_status = await _check_provider_connection(provider_name)
        checks["connection"] = {
            "status": connection_status.status,
            "passed": connection_status.status == "connected",
            "message": connection_status.message,
            "reason_code": connection_status.reason_code,
        }

        # 2. Credentials check
        creds_ok = False
        creds_msg = "Not required"
        if provider_name == "openai":
            creds_ok = bool(SETTINGS.OPENAI_API_KEY)
            creds_msg = "Configured" if creds_ok else "Missing OPENAI_API_KEY"
        elif provider_name == "google":
            creds_ok = bool(SETTINGS.GOOGLE_API_KEY)
            creds_msg = "Configured" if creds_ok else "Missing GOOGLE_API_KEY"
        else:
            creds_ok = True  # Local runtimes don't need API keys

        checks["credentials"] = {
            "status": "configured" if creds_ok else "missing",
            "passed": creds_ok,
            "message": creds_msg,
        }

        # 3. Capabilities check
        capabilities = _get_provider_capabilities(provider_name)
        checks["capabilities"] = {
            "status": "available",
            "passed": True,
            "capabilities": capabilities.model_dump(),
        }

        # 4. Endpoint check
        endpoint = _get_provider_endpoint(provider_name)
        checks["endpoint"] = {
            "status": "configured" if endpoint else "not_required",
            "passed": True,
            "endpoint": endpoint,
        }

        # Overall result
        all_passed = all(check["passed"] for check in checks.values())
        overall_status = "ready" if all_passed else "not_ready"

        # Audit
        audit_trail.log_action(
            action="preflight_check",
            user=user,
            provider=provider_name,
            details={"overall_status": overall_status},
            result="success",
        )

        return {
            "status": "success",
            "provider": provider_name,
            "overall_status": overall_status,
            "checks": checks,
            "ready_for_activation": all_passed,
        }

    except Exception as exc:
        logger.exception(f"Preflight check failed for {provider_name}")
        audit_trail.log_action(
            action="preflight_check",
            user=user,
            provider=provider_name,
            details={},
            result="failure",
            error_message=str(exc),
        )
        raise HTTPException(
            status_code=500,
            detail=f"Preflight check failed: {str(exc)}",
        ) from exc


@router.get("/admin/audit")
async def get_admin_audit_log(
    action: Optional[str] = None,
    provider: Optional[str] = None,
    limit: int = 50,
) -> dict[str, Any]:
    """
    Get admin audit log (admin endpoint).

    Args:
        action: Filter by action type
        provider: Filter by provider
        limit: Maximum number of entries (default 50, max 200)

    Returns:
        Audit log entries
    """
    from venom_core.core.admin_audit import get_audit_trail

    # Cap limit
    limit = min(limit, 200)

    audit_trail = get_audit_trail()
    entries = audit_trail.get_entries(
        action=action,
        provider=provider,
        limit=limit,
    )

    # Convert to dict
    entries_data = [
        {
            "timestamp": entry.timestamp.isoformat(),
            "action": entry.action,
            "user": entry.user,
            "provider": entry.provider,
            "details": entry.details,
            "result": entry.result,
            "error_message": entry.error_message,
        }
        for entry in entries
    ]

    return {
        "status": "success",
        "entries": entries_data,
        "count": len(entries_data),
    }
