"""Domain helpers for remote model provider catalog and validation routing."""

from __future__ import annotations

import os
import time
from threading import Lock
from typing import Any

_DEFAULT_CATALOG_TTL_SECONDS = 300
_DEFAULT_PROVIDER_PROBE_TTL_SECONDS = 60
_DEFAULT_REMOTE_TIMEOUT_SECONDS = 6.0


def env_int(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def catalog_ttl_seconds() -> int:
    return max(
        30,
        env_int(
            "VENOM_REMOTE_MODELS_CATALOG_TTL_SECONDS", _DEFAULT_CATALOG_TTL_SECONDS
        ),
    )


def provider_probe_ttl_seconds() -> int:
    return max(
        10,
        env_int(
            "VENOM_REMOTE_MODELS_PROVIDER_PROBE_TTL_SECONDS",
            _DEFAULT_PROVIDER_PROBE_TTL_SECONDS,
        ),
    )


def remote_timeout_seconds(*, openai_api_timeout: float | int | None) -> float:
    return max(
        1.0,
        min(float(openai_api_timeout or _DEFAULT_REMOTE_TIMEOUT_SECONDS), 20.0),
    )


def openai_models_url(*, chat_completions_endpoint: str) -> str:
    endpoint = (chat_completions_endpoint or "").strip()
    if endpoint.endswith("/chat/completions"):
        return f"{endpoint[: -len('/chat/completions')]}/models"
    if endpoint.endswith("/v1"):
        return f"{endpoint}/models"
    if "/v1/" in endpoint:
        root, _, _ = endpoint.partition("/v1/")
        return f"{root}/v1/models"
    return "https://api.openai.com/v1/models"


def openai_model_url(*, models_url: str, model_id: str) -> str:
    return f"{models_url.rstrip('/')}/{model_id}"


def google_models_url() -> str:
    return "https://generativelanguage.googleapis.com/v1beta/models"


def google_model_url(model_id: str) -> str:
    normalized = model_id if model_id.startswith("models/") else f"models/{model_id}"
    return f"https://generativelanguage.googleapis.com/v1beta/{normalized}"


def map_openai_capabilities(model_id: str) -> list[str]:
    model = model_id.lower()
    capabilities = ["chat", "text-generation"]
    if "gpt-4" in model or "gpt-5" in model or "o1" in model or "o3" in model:
        capabilities.append("function-calling")
    if "gpt-4o" in model or "vision" in model:
        capabilities.append("vision")
    return capabilities


def map_google_capabilities(item: dict[str, Any]) -> list[str]:
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


def cache_get(
    cache: dict[str, dict[str, Any]],
    lock: Lock,
    key: str,
    ttl_seconds: int,
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


def cache_put(
    cache: dict[str, dict[str, Any]],
    lock: Lock,
    key: str,
    *,
    payload: dict[str, Any],
) -> None:
    with lock:
        cache[key] = {**payload, "ts_monotonic": time.monotonic()}
