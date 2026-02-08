"""Pomocnicze funkcje opisujące aktualnie skonfigurowane runtime LLM."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Optional, Tuple
from urllib.parse import urlparse, urlunparse

import httpx

from venom_core.config import SETTINGS
from venom_core.utils.url_policy import apply_http_policy_to_url, build_http_url


@dataclass
class LLMRuntimeInfo:
    """Opisuje aktualnie używane runtime LLM (provider, model, endpoint)."""

    provider: str
    model_name: str
    endpoint: Optional[str]
    service_type: str
    mode: str
    config_hash: Optional[str] = None
    runtime_id: Optional[str] = None

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
            "config_hash": self.config_hash,
            "runtime_id": self.runtime_id,
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


def compute_llm_config_hash(
    provider: Optional[str], endpoint: Optional[str], model: Optional[str]
) -> str:
    """Stabilny hash konfiguracji LLM do wykrywania driftu."""
    source = f"{provider or ''}|{endpoint or ''}|{model or ''}".lower()
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:12]


def compute_runtime_id(provider: Optional[str], endpoint: Optional[str]) -> str:
    """Identyfikator runtime oparty o providera i endpoint."""
    return f"{provider or 'local'}@{endpoint or 'local'}"


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
        endpoint = apply_http_policy_to_url(endpoint)
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

    config_hash = compute_llm_config_hash(provider, endpoint, model_name)
    runtime_id = compute_runtime_id(provider, endpoint)

    return LLMRuntimeInfo(
        provider=provider,
        model_name=model_name,
        endpoint=endpoint,
        service_type=service_type,
        mode=mode,
        config_hash=config_hash,
        runtime_id=runtime_id,
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


def _build_health_url(runtime: LLMRuntimeInfo) -> Optional[str]:
    """Tworzy URL do health-checka na podstawie providera."""
    if not runtime.endpoint:
        return None

    parsed = urlparse(runtime.endpoint)
    if runtime.provider == "ollama":
        base = urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))
        return (
            f"{base}/api/tags"
            if base
            else build_http_url("localhost", 11434, "/api/tags")
        )

    endpoint = runtime.endpoint.rstrip("/")
    if endpoint.endswith("/models"):
        return endpoint
    if endpoint.endswith("/v1"):
        return f"{endpoint}/models"
    if endpoint.endswith("/v1/"):
        return f"{endpoint}models"
    return f"{endpoint}/models"


def _build_chat_completions_url(runtime: LLMRuntimeInfo) -> Optional[str]:
    """Buduje URL do /chat/completions na bazie endpointu runtime."""
    if not runtime.endpoint:
        return None
    parsed = urlparse(runtime.endpoint)
    base = urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))
    path = parsed.path.rstrip("/")
    if path.endswith("/chat/completions"):
        return runtime.endpoint
    if path.endswith("/v1"):
        return f"{base}{path}/chat/completions"
    if path:
        return f"{base}{path}/v1/chat/completions"
    return f"{base}/v1/chat/completions"


async def probe_runtime_status(runtime: LLMRuntimeInfo) -> Tuple[str, Optional[str]]:
    """
    Sprawdza rzeczywisty stan runtime i zwraca status + ewentualny błąd.
    """

    if runtime.service_type != "local":
        # Zakładamy poprawny stan dla zewnętrznych providerów
        return "ready", None

    health_url = _build_health_url(runtime)
    if not health_url:
        return "offline", "Brak endpointu runtime"

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(health_url)
        if response.status_code < 400:
            return "online", None
        return "degraded", f"HTTP {response.status_code}"
    except httpx.HTTPError as exc:
        return "offline", str(exc)
    except Exception as exc:  # pragma: no cover - defensywnie
        return "offline", str(exc)


async def warmup_local_runtime(
    runtime: LLMRuntimeInfo,
    prompt: str,
    timeout_seconds: float,
    max_tokens: int,
) -> bool:
    """
    Wysyła krótki request do lokalnego runtime aby podnieść model (best-effort).
    """
    if runtime.service_type != "local":
        return False
    warmup_url = _build_chat_completions_url(runtime)
    if not warmup_url:
        return False

    payload = {
        "model": runtime.model_name,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.0,
        "stream": False,
    }
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(warmup_url, json=payload)
        return response.status_code < 400
    except Exception:
        return False
