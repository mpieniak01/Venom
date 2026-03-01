"""Domain helpers for remote model provider catalog and validation routing."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from threading import Lock
from typing import Any, Awaitable, Callable, Protocol

import httpx

from venom_core.infrastructure.traffic_control import TrafficControlledHttpClient

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


def is_api_key_configured(api_key: str | None) -> bool:
    return bool((api_key or "").strip())


def openai_static_catalog_payload() -> list[dict[str, Any]]:
    return [
        {
            "id": "gpt-4o",
            "name": "GPT-4o",
            "provider": "openai",
            "capabilities": ["chat", "text-generation", "function-calling", "vision"],
            "model_alias": "gpt-4o-2024-08-06",
        },
        {
            "id": "gpt-4o-mini",
            "name": "GPT-4o Mini",
            "provider": "openai",
            "capabilities": ["chat", "text-generation", "function-calling"],
            "model_alias": "gpt-4o-mini-2024-07-18",
        },
        {
            "id": "gpt-4-turbo",
            "name": "GPT-4 Turbo",
            "provider": "openai",
            "capabilities": ["chat", "text-generation", "function-calling", "vision"],
            "model_alias": "gpt-4-turbo-2024-04-09",
        },
        {
            "id": "gpt-3.5-turbo",
            "name": "GPT-3.5 Turbo",
            "provider": "openai",
            "capabilities": ["chat", "text-generation", "function-calling"],
            "model_alias": "gpt-3.5-turbo-0125",
        },
    ]


def google_static_catalog_payload() -> list[dict[str, Any]]:
    return [
        {
            "id": "gemini-1.5-pro",
            "name": "Gemini 1.5 Pro",
            "provider": "google",
            "capabilities": [
                "chat",
                "text-generation",
                "function-calling",
                "vision",
                "multimodal",
            ],
            "model_alias": "gemini-1.5-pro-latest",
        },
        {
            "id": "gemini-1.5-flash",
            "name": "Gemini 1.5 Flash",
            "provider": "google",
            "capabilities": ["chat", "text-generation", "function-calling"],
            "model_alias": "gemini-1.5-flash-latest",
        },
        {
            "id": "gemini-pro",
            "name": "Gemini Pro",
            "provider": "google",
            "capabilities": ["chat", "text-generation"],
            "model_alias": "gemini-pro",
        },
    ]


def service_model_bindings_payload(*, settings: Any) -> list[dict[str, Any]]:
    bindings: list[dict[str, Any]] = []

    llm_service_type = getattr(settings, "LLM_SERVICE_TYPE", "local")
    llm_model_name = getattr(settings, "LLM_MODEL_NAME", "phi3:latest")

    if llm_service_type in ("openai", "google"):
        bindings.append(
            {
                "service_id": "venom_llm_service",
                "endpoint": "/api/v1/llm/chat",
                "http_method": "POST",
                "provider": llm_service_type,
                "model": llm_model_name,
                "routing_mode": "direct",
                "fallback_order": None,
                "status": "active",
            }
        )

    ai_mode = getattr(settings, "AI_MODE", "LOCAL")
    if ai_mode in ("HYBRID", "CLOUD"):
        hybrid_provider = getattr(settings, "HYBRID_CLOUD_PROVIDER", "google")
        hybrid_model = getattr(settings, "HYBRID_CLOUD_MODEL", "gemini-1.5-pro")
        hybrid_local_model = getattr(settings, "HYBRID_LOCAL_MODEL", "llama3")
        bindings.append(
            {
                "service_id": "venom_hybrid_service",
                "endpoint": "/api/v1/llm/chat",
                "http_method": "POST",
                "provider": hybrid_provider,
                "model": hybrid_model,
                "routing_mode": "hybrid" if ai_mode == "HYBRID" else "direct",
                "fallback_order": (
                    [hybrid_local_model, hybrid_model] if ai_mode == "HYBRID" else None
                ),
                "status": "active",
            }
        )

    return bindings


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


class LoggerLike(Protocol):
    def warning(self, msg: str, *args: Any, **kwargs: Any) -> Any: ...


@dataclass(frozen=True)
class CatalogProviderDeps:
    cache_get_fn: Callable[
        [dict[str, dict[str, Any]], Lock, str, int], dict[str, Any] | None
    ]
    cache_put_fn: Callable[..., None]
    fetch_openai_models_catalog_live_fn: Callable[[], Awaitable[list[dict[str, Any]]]]
    fetch_google_models_catalog_live_fn: Callable[[], Awaitable[list[dict[str, Any]]]]
    openai_static_catalog_payload_fn: Callable[[], list[dict[str, Any]]]
    google_static_catalog_payload_fn: Callable[[], list[dict[str, Any]]]
    check_openai_configured_fn: Callable[[], bool]
    check_google_configured_fn: Callable[[], bool]
    now_iso_fn: Callable[[], str]
    logger: LoggerLike


class ResponseLike(Protocol):
    status_code: int

    def json(self) -> Any: ...


class HttpClientLike(Protocol):
    async def __aenter__(self) -> Any: ...

    async def __aexit__(
        self,
        exc_type: Any,
        exc: Any,
        tb: Any,
    ) -> Any: ...

    async def aget(self, url: str, **kwargs: Any) -> ResponseLike: ...


def traffic_controlled_http_client_cls() -> type[TrafficControlledHttpClient]:
    """Expose traffic client class for router compatibility wrappers."""
    return TrafficControlledHttpClient


def httpx_module() -> Any:
    """Expose httpx module for router compatibility wrappers/tests."""
    return httpx


async def probe_provider_cached(
    *,
    provider: str,
    cache: dict[str, dict[str, Any]],
    lock: Lock,
    provider_probe_ttl_seconds: int,
    cache_get_fn: Callable[
        [dict[str, dict[str, Any]], Lock, str, int], dict[str, Any] | None
    ],
    cache_put_fn: Callable[..., None],
    validate_openai_connection_fn: Callable[
        [], Awaitable[tuple[bool, str, float | None]]
    ],
    validate_google_connection_fn: Callable[
        [], Awaitable[tuple[bool, str, float | None]]
    ],
) -> tuple[str, str | None, float | None]:
    cached = cache_get_fn(cache, lock, provider, provider_probe_ttl_seconds)
    if cached:
        return (
            str(cached.get("status") or "degraded"),
            cached.get("error"),
            cached.get("latency_ms"),
        )

    if provider == "openai":
        valid, message, latency = await validate_openai_connection_fn()
    else:
        valid, message, latency = await validate_google_connection_fn()

    status = "reachable" if valid else "degraded"
    error = None if valid else message
    cache_put_fn(
        cache,
        lock,
        provider,
        payload={"status": status, "error": error, "latency_ms": latency},
    )
    return status, error, latency


async def fetch_openai_models_catalog_live(
    *,
    api_key: str,
    timeout_seconds: float,
    models_url: str,
    traffic_client_factory: Callable[..., HttpClientLike],
    map_openai_capabilities_fn: Callable[[str], list[str]],
) -> list[dict[str, Any]]:
    if not api_key:
        return []

    headers = {"Authorization": f"Bearer {api_key}"}
    async with traffic_client_factory(
        provider="openai", timeout=timeout_seconds
    ) as client:
        response = await client.aget(models_url, headers=headers)
        payload = response.json()

    raw_items = payload.get("data") if isinstance(payload, dict) else []
    items = raw_items if isinstance(raw_items, list) else []
    models: list[dict[str, Any]] = []
    for item in items:
        model_id = str(item.get("id") or "").strip()
        if not model_id:
            continue
        models.append(
            {
                "id": model_id,
                "name": model_id,
                "provider": "openai",
                "capabilities": map_openai_capabilities_fn(model_id),
                "model_alias": None,
            }
        )
    models.sort(key=lambda model: str(model.get("id", "")).lower())
    return models


async def fetch_google_models_catalog_live(
    *,
    api_key: str,
    timeout_seconds: float,
    models_url: str,
    traffic_client_factory: Callable[..., HttpClientLike],
    map_google_capabilities_fn: Callable[[dict[str, Any]], list[str]],
) -> list[dict[str, Any]]:
    if not api_key:
        return []

    async with traffic_client_factory(
        provider="google", timeout=timeout_seconds
    ) as client:
        response = await client.aget(models_url, params={"key": api_key})
        payload = response.json()

    raw_items = payload.get("models") if isinstance(payload, dict) else []
    items = raw_items if isinstance(raw_items, list) else []
    models: list[dict[str, Any]] = []
    for item in items:
        raw_name = str(item.get("name") or "").strip()
        model_id = raw_name.removeprefix("models/")
        if not model_id:
            continue
        models.append(
            {
                "id": model_id,
                "name": model_id,
                "provider": "google",
                "capabilities": map_google_capabilities_fn(item),
                "model_alias": raw_name if raw_name != model_id else None,
            }
        )
    models.sort(key=lambda model: str(model.get("id", "")).lower())
    return models


async def validate_openai_connection(
    *,
    api_key: str,
    model: str | None,
    timeout_seconds: float,
    openai_models_url: str,
    openai_model_url_fn: Callable[[str], str],
    traffic_client_factory: Callable[..., HttpClientLike],
    http_error_type: type[Exception],
) -> tuple[bool, str, float | None]:
    if not api_key:
        return False, "OPENAI_API_KEY not configured", None

    url = openai_model_url_fn(model) if model else openai_models_url
    headers = {"Authorization": f"Bearer {api_key}"}
    start = time.perf_counter()
    try:
        async with traffic_client_factory(
            provider="openai", timeout=timeout_seconds
        ) as client:
            response = await client.aget(url, headers=headers, raise_for_status=False)
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
    except http_error_type as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return False, f"OpenAI validation error: {exc}", elapsed_ms
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return False, f"OpenAI validation error: {exc}", elapsed_ms


async def validate_google_connection(
    *,
    api_key: str,
    model: str | None,
    timeout_seconds: float,
    google_models_url: str,
    google_model_url_fn: Callable[[str], str],
    traffic_client_factory: Callable[..., HttpClientLike],
    http_error_type: type[Exception],
) -> tuple[bool, str, float | None]:
    if not api_key:
        return False, "GOOGLE_API_KEY not configured", None

    url = google_model_url_fn(model) if model else google_models_url
    start = time.perf_counter()
    try:
        async with traffic_client_factory(
            provider="google", timeout=timeout_seconds
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
    except http_error_type as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return False, f"Google validation error: {exc}", elapsed_ms
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return False, f"Google validation error: {exc}", elapsed_ms


async def catalog_for_provider(
    *,
    provider: str,
    cache: dict[str, dict[str, Any]],
    lock: Lock,
    catalog_ttl_seconds: int,
    deps: CatalogProviderDeps,
) -> tuple[list[dict[str, Any]], str, str | None]:
    cached = deps.cache_get_fn(cache, lock, provider, catalog_ttl_seconds)
    if cached:
        models = cached.get("models", [])
        return (
            models if isinstance(models, list) else [],
            str(cached.get("source") or "cache"),
            cached.get("error"),
        )

    if provider == "openai":
        fetch_live = deps.fetch_openai_models_catalog_live_fn
        static_models = deps.openai_static_catalog_payload_fn()
        configured = deps.check_openai_configured_fn()
    else:
        fetch_live = deps.fetch_google_models_catalog_live_fn
        static_models = deps.google_static_catalog_payload_fn()
        configured = deps.check_google_configured_fn()

    live_error: str | None = None
    if configured:
        try:
            models = await fetch_live()
            source = f"{provider}_api"
            if not models:
                models = static_models
                source = "static_fallback_empty_live"
                live_error = "live catalog empty"
        except Exception as exc:
            deps.logger.warning(
                "Remote catalog live fetch failed for %s: %s", provider, exc
            )
            models = static_models
            source = "static_fallback_error"
            live_error = str(exc)
    else:
        models = static_models
        source = "static_fallback_unconfigured"
        live_error = f"{provider.upper()}_API_KEY not configured"

    deps.cache_put_fn(
        cache,
        lock,
        provider,
        payload={
            "models": models,
            "source": source,
            "error": live_error,
            "refreshed_at": deps.now_iso_fn(),
        },
    )
    return models, source, live_error
