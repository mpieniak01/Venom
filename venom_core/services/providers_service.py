"""Domain helpers for provider metadata and cloud activation flows."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import Request

from venom_core.api.schemas.providers import ProviderCapability, ProviderStatus
from venom_core.config import SETTINGS
from venom_core.services.config_manager import config_manager


def extract_user_from_request(request: Request, *, logger: Any = None) -> str:
    """Extract best-effort user identifier for audit logging."""
    try:
        if hasattr(request, "state") and hasattr(request.state, "user"):
            user = request.state.user
            if user:
                return str(user)

        if hasattr(request, "headers"):
            for header_name in ("X-Authenticated-User", "X-User", "X-Admin-User"):
                header_value = request.headers.get(header_name)
                if header_value:
                    return header_value
    except Exception as exc:
        if logger is not None:
            logger.warning(f"Failed to extract user from request: {exc}")

    return "unknown"


def get_provider_type(provider: str) -> str:
    if provider in ("openai", "google"):
        return "cloud_provider"
    if provider in ("huggingface", "ollama"):
        return "catalog_integrator"
    if provider in ("vllm", "local"):
        return "local_runtime"
    return "unknown"


def get_provider_capabilities(provider: str) -> ProviderCapability:
    if provider == "huggingface":
        return ProviderCapability(
            install=True, search=True, activate=False, inference=False, trainable=True
        )
    if provider == "ollama":
        return ProviderCapability(
            install=True, search=True, activate=True, inference=True, trainable=False
        )
    if provider == "vllm":
        return ProviderCapability(
            install=True, search=False, activate=True, inference=True, trainable=False
        )
    if provider in {"openai", "google", "local"}:
        return ProviderCapability(
            install=False, search=False, activate=True, inference=True, trainable=False
        )
    return ProviderCapability()


def resolve_cloud_model(provider_name: str, request: Optional[Any]) -> str:
    if provider_name == "openai":
        return (
            request.model if request and request.model else SETTINGS.OPENAI_GPT4O_MODEL
        )
    return (
        request.model if request and request.model else SETTINGS.GOOGLE_GEMINI_PRO_MODEL
    )


def activate_cloud_provider(
    provider_name: str, request: Optional[Any]
) -> dict[str, Any]:
    model = resolve_cloud_model(provider_name, request)
    provider_config = {
        "LLM_SERVICE_TYPE": provider_name,
        "LLM_MODEL_NAME": model,
        "ACTIVE_LLM_SERVER": provider_name,
    }
    config_manager.update_config(provider_config)
    return {
        "status": "success",
        "message": f"Provider {provider_name} activated successfully",
        "provider": provider_name,
        "model": model,
    }


def check_openai_status() -> ProviderStatus:
    if SETTINGS.OPENAI_API_KEY:
        return ProviderStatus(
            status="connected",
            message="OpenAI API key configured",
        )
    return ProviderStatus(
        status="offline",
        reason_code="missing_api_key",
        message="OPENAI_API_KEY not configured",
    )


def check_google_status() -> ProviderStatus:
    if SETTINGS.GOOGLE_API_KEY:
        return ProviderStatus(
            status="connected",
            message="Google Gemini API key configured",
        )
    return ProviderStatus(
        status="offline",
        reason_code="missing_api_key",
        message="GOOGLE_API_KEY not configured",
    )


def get_provider_endpoint(provider: str) -> Optional[str]:
    if provider == "ollama":
        return "http://localhost:11434"
    if provider == "vllm":
        return SETTINGS.VLLM_ENDPOINT
    return None
