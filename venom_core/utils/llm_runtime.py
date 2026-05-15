"""Pomocnicze funkcje opisujące aktualnie skonfigurowane runtime LLM."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple
from urllib.parse import urlparse, urlunparse

import httpx

from venom_core.config import SETTINGS
from venom_core.utils.runtime_names import MULTI_RUNTIME_ID, is_multi_runtime
from venom_core.utils.url_policy import apply_http_policy_to_url, build_http_url


class LifecycleStep(str, Enum):
    """Kroki lifecycle switch runtime — używane do śledzenia postępu przełączenia."""

    PROCESS_STOPPED = "process_stopped"
    RELEASE_DONE = "release_done"
    CACHE_INVALIDATED = "cache_invalidated"
    START_DONE = "start_done"
    HEALTH_READY = "health_ready"
    ENDPOINT_SWITCHED = "endpoint_switched"
    CONFIG_SAVED = "config_saved"


@dataclass
class LifecycleSwitchState:
    """Opisuje stan przełączenia runtime w danym momencie switch flow.

    Umożliwia diagnostykę i detekcję driftu: które kroki zostały wykonane,
    a które nie. W razie niepowodzenia pozwala określić, w którym miejscu
    switch się zatrzymał.
    """

    from_server: str
    to_server: str
    completed_steps: List[LifecycleStep] = field(default_factory=list)
    failed_step: Optional[LifecycleStep] = None
    error_message: Optional[str] = None

    def mark_done(self, step: LifecycleStep) -> None:
        if step not in self.completed_steps:
            self.completed_steps.append(step)

    def mark_failed(self, step: LifecycleStep, error: str) -> None:
        self.failed_step = step
        self.error_message = error

    @property
    def is_complete(self) -> bool:
        return (
            self.failed_step is None
            and LifecycleStep.CONFIG_SAVED in self.completed_steps
        )

    @property
    def is_in_partial_state(self) -> bool:
        return self.failed_step is not None and len(self.completed_steps) > 0

    def to_payload(self) -> dict:
        return {
            "from_server": self.from_server,
            "to_server": self.to_server,
            "completed_steps": [s.value for s in self.completed_steps],
            "failed_step": self.failed_step.value if self.failed_step else None,
            "error_message": self.error_message,
            "is_complete": self.is_complete,
            "is_in_partial_state": self.is_in_partial_state,
        }


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
    if "vllm" in endpoint_lower or ":8001" in endpoint_lower:
        return "vllm"
    if "gemma4" in endpoint_lower or "8014" in endpoint_lower:
        return MULTI_RUNTIME_ID
    if "onnx" in endpoint_lower:
        return "onnx"
    if "lmstudio" in endpoint_lower:
        return "lmstudio"
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
    active_server = (getattr(settings, "ACTIVE_LLM_SERVER", "") or "").strip().lower()

    if service_type == "local":
        provider, endpoint = _resolve_local_runtime(
            active_server=active_server,
            endpoint=endpoint,
            settings=settings,
        )
    else:
        provider, endpoint = _resolve_non_local_runtime(
            service_type=service_type,
            endpoint=endpoint,
            settings=settings,
        )

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


def _resolve_local_runtime(
    *, active_server: str, endpoint: Optional[str], settings
) -> Tuple[str, Optional[str]]:
    if is_multi_runtime(active_server):
        return (
            MULTI_RUNTIME_ID,
            apply_http_policy_to_url(
                getattr(settings, "GEMMA4_AUDIO_ENDPOINT", endpoint)
            ),
        )
    if active_server == "vllm":
        return (
            "vllm",
            apply_http_policy_to_url(getattr(settings, "VLLM_ENDPOINT", endpoint)),
        )
    if active_server == "ollama":
        candidate = apply_http_policy_to_url(endpoint)
        if infer_local_provider(candidate) != "ollama":
            candidate = apply_http_policy_to_url("http://localhost:11434/v1")
        return "ollama", candidate
    if active_server == "onnx":
        return "onnx", None
    normalized_endpoint = apply_http_policy_to_url(endpoint)
    return infer_local_provider(normalized_endpoint), normalized_endpoint


def _resolve_non_local_runtime(
    *, service_type: str, endpoint: Optional[str], settings
) -> Tuple[str, Optional[str]]:
    if service_type == "onnx":
        return "onnx", None
    if service_type == "openai":
        return "openai", endpoint or "https://api.openai.com/v1"
    if service_type == "google":
        return "google-gemini", endpoint or "https://generativelanguage.googleapis.com"
    if service_type == "azure":
        return "azure-openai", endpoint or getattr(
            settings, "AZURE_OPENAI_ENDPOINT", None
        )
    return service_type, endpoint


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
    if runtime.provider == "onnx":
        return None
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

    if is_multi_runtime(runtime.provider):
        base = urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))
        return (
            f"{base}/health" if base else build_http_url("localhost", 8014, "/health")
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

    if runtime.service_type == "onnx":
        return "ready", None

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


# ---------------------------------------------------------------------------
# Drift detection (Faza 4 PR 220A)
# ---------------------------------------------------------------------------


def detect_runtime_drift(settings=None) -> dict:
    """Detect inconsistency between ACTIVE_LLM_SERVER, endpoint, and model.

    Drift occurs when the config keys disagree with each other or with what
    get_active_llm_runtime() resolves — e.g. ACTIVE_LLM_SERVER says "ollama"
    but LLM_LOCAL_ENDPOINT points at a vLLM port, or the model name belongs
    to a different provider than the active server.

    Returns a dict with:
      - "drift_detected": bool
      - "active_server": the ACTIVE_LLM_SERVER value
      - "inferred_provider": what infer_local_provider() resolves from endpoint
      - "model_name": current LLM_MODEL_NAME
      - "endpoint": current LLM_LOCAL_ENDPOINT
      - "issues": list of human-readable inconsistency descriptions
    """
    settings = settings or SETTINGS
    active_server = (getattr(settings, "ACTIVE_LLM_SERVER", "") or "").strip().lower()
    endpoint = (getattr(settings, "LLM_LOCAL_ENDPOINT", "") or "").strip()
    model_name = (getattr(settings, "LLM_MODEL_NAME", "") or "").strip()
    service_type = (getattr(settings, "LLM_SERVICE_TYPE", "local") or "local").lower()

    inferred = _build_inferred_provider(
        service_type=service_type,
        endpoint=endpoint,
    )
    issues: List[str] = []
    endpoint_issue = _collect_endpoint_provider_issue(
        service_type=service_type,
        active_server=active_server,
        endpoint=endpoint,
        inferred_provider=inferred,
    )
    if endpoint_issue:
        issues.append(endpoint_issue)

    runtime = get_active_llm_runtime(settings)
    runtime_issue = _collect_runtime_provider_issue(
        service_type=service_type,
        active_server=active_server,
        runtime_provider=(runtime.provider or "").strip().lower(),
    )
    if runtime_issue:
        issues.append(runtime_issue)

    return {
        "drift_detected": len(issues) > 0,
        "active_server": active_server,
        "inferred_provider": inferred if service_type == "local" else service_type,
        "model_name": model_name,
        "endpoint": endpoint,
        "issues": issues,
    }


def _build_inferred_provider(*, service_type: str, endpoint: str) -> str:
    if service_type != "local":
        return service_type
    return infer_local_provider(endpoint) if endpoint else ""


def _collect_endpoint_provider_issue(
    *,
    service_type: str,
    active_server: str,
    endpoint: str,
    inferred_provider: str,
) -> str | None:
    if service_type != "local":
        return None
    if not active_server or not endpoint:
        return None
    if active_server == "onnx":
        return None
    if inferred_provider == active_server:
        return None
    if active_server == "ollama" and inferred_provider == "local":
        return None
    if is_multi_runtime(active_server) and is_multi_runtime(inferred_provider):
        return None
    return (
        f"Configured active server '{active_server}' conflicts with endpoint "
        f"provider '{inferred_provider}' for '{endpoint}'."
    )


def _should_skip_provider_mismatch(
    *, active_server: str, runtime_provider: str
) -> bool:
    if not active_server or not runtime_provider:
        return True
    if runtime_provider == active_server:
        return True
    if active_server == "local" or runtime_provider == "local":
        return True
    if active_server == "onnx" and runtime_provider == "onnx":
        return True
    if is_multi_runtime(active_server) or is_multi_runtime(runtime_provider):
        return True
    return False


def _collect_runtime_provider_issue(
    *,
    service_type: str,
    active_server: str,
    runtime_provider: str,
) -> str | None:
    if service_type != "local":
        return None
    if _should_skip_provider_mismatch(
        active_server=active_server,
        runtime_provider=runtime_provider,
    ):
        return None
    return (
        f"Resolved runtime provider '{runtime_provider}' differs from configured "
        f"ACTIVE_LLM_SERVER '{active_server}'."
    )
