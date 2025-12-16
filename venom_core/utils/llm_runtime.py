"""Pomocnicze funkcje opisujące aktualnie skonfigurowane runtime LLM."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

from venom_core.config import SETTINGS


@dataclass
class LLMRuntimeInfo:
    """Opisuje aktualnie używane runtime LLM (provider, model, endpoint)."""

    provider: str
    model_name: str
    endpoint: Optional[str]
    service_type: str
    mode: str

    def to_payload(self) -> dict:
        """Wygodny format do serializacji JSON."""
        label = format_runtime_label(self)
        parsed = urlparse(self.endpoint or "")
        endpoint_host = parsed.hostname
        endpoint_port = parsed.port
        return {
            "provider": self.provider,
            "model": self.model_name,
            "endpoint": self.endpoint,
            "endpoint_host": endpoint_host,
            "endpoint_port": endpoint_port,
            "service_type": self.service_type,
            "mode": self.mode,
            "label": label,
        }


def infer_local_provider(endpoint: Optional[str]) -> str:
    """Próbuje określić typ lokalnego serwera na podstawie endpointu."""
    endpoint_lower = (endpoint or "").lower()
    if not endpoint_lower:
        return "local"
    if "ollama" in endpoint_lower or "11434" in endpoint_lower:
        return "ollama"
    if "vllm" in endpoint_lower:
        return "vllm"
    if "lmstudio" in endpoint_lower:
        return "lmstudio"
    if ":8000" in endpoint_lower or ":8001" in endpoint_lower:
        # Najczęstsze porty nowych instancji vLLM w tym projekcie
        return "vllm"
    return "local"


def get_active_llm_runtime(settings=None) -> LLMRuntimeInfo:
    """
    Buduje obiekt opisujący aktualnie używane runtime LLM na podstawie konfiguracji.
    """

    settings = settings or SETTINGS
    service_type = (settings.LLM_SERVICE_TYPE or "local").lower()
    mode = (settings.AI_MODE or "LOCAL").upper()
    model_name = settings.LLM_MODEL_NAME
    endpoint = settings.LLM_LOCAL_ENDPOINT

    if service_type == "local":
        provider = infer_local_provider(endpoint)
    elif service_type == "openai":
        provider = "openai"
        endpoint = endpoint or "https://api.openai.com/v1"
    elif service_type == "google":
        provider = "google-gemini"
        endpoint = endpoint or "https://generativelanguage.googleapis.com"
    elif service_type == "azure":
        provider = "azure-openai"
        endpoint = endpoint or getattr(settings, "AZURE_OPENAI_ENDPOINT", None)
    else:
        provider = service_type

    return LLMRuntimeInfo(
        provider=provider,
        model_name=model_name,
        endpoint=endpoint,
        service_type=service_type,
        mode=mode,
    )


def format_runtime_label(runtime: LLMRuntimeInfo) -> str:
    """
    Tworzy przyjazną etykietę np. 'Gemma 3 · vLLM @ 8001'.
    """

    model_display = runtime.model_name.split("/")[-1] if runtime.model_name else "?"
    parsed = urlparse(runtime.endpoint or "")
    if parsed.port:
        endpoint_display = f"{parsed.hostname or 'localhost'}:{parsed.port}"
    elif runtime.endpoint:
        endpoint_display = runtime.endpoint
    else:
        endpoint_display = "local"

    provider_display = runtime.provider or runtime.service_type

    return f"{model_display} · {provider_display} @ {endpoint_display}"
