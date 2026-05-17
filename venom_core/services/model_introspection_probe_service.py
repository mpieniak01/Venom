"""Probe proxy service for model introspection internals (multi_runtime)."""

from __future__ import annotations

import os
import time
from typing import Any
from uuid import uuid4

import httpx

from venom_core.utils.llm_runtime import format_runtime_label, get_active_llm_runtime
from venom_core.utils.runtime_names import is_multi_runtime

_PROBE_TIMEOUT_SECONDS = 20.0
_PROBE_MAX_ATTEMPTS = 2
_PROBE_MAX_TOP_K = 32
_PROBE_MAX_LAYER_COUNT = 8
_PROBE_MAX_PROMPT_TOKENS = 1024
_PROBE_UNAVAILABLE = "probe_unavailable"
_PROBE_OK = "ok"
_PROBE_FAILED = "failed"
_PROBE_TRANSIENT_STATUS_CODES = {502, 503, 504}
_PROBE_DEFAULT_PROFILE = "dev"
_PROBE_HTTP_CLIENT: httpx.AsyncClient | None = None
_PROBE_PROFILE_LIMITS: dict[str, dict[str, float | int]] = {
    "dev": {
        "timeout_seconds": _PROBE_TIMEOUT_SECONDS,
        "max_attempts": _PROBE_MAX_ATTEMPTS,
        "max_top_k": _PROBE_MAX_TOP_K,
        "max_layer_count": _PROBE_MAX_LAYER_COUNT,
        "max_prompt_tokens": _PROBE_MAX_PROMPT_TOKENS,
    },
    "stage": {
        "timeout_seconds": 14.0,
        "max_attempts": 2,
        "max_top_k": 24,
        "max_layer_count": 6,
        "max_prompt_tokens": 768,
    },
    "prod": {
        "timeout_seconds": 10.0,
        "max_attempts": 1,
        "max_top_k": 16,
        "max_layer_count": 4,
        "max_prompt_tokens": 512,
    },
}


def _parse_bool_env(raw_value: str | None, *, default: bool) -> bool:
    if raw_value is None:
        return default
    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _read_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _read_float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _resolve_probe_profile_name() -> str:
    configured = os.getenv(
        "VENOM_INTROSPECTION_PROBE_PROFILE",
        os.getenv("GEMMA4_AUDIO_PROBE_PROFILE", _PROBE_DEFAULT_PROFILE),
    )
    profile = str(configured or _PROBE_DEFAULT_PROFILE).strip().lower()
    if profile not in _PROBE_PROFILE_LIMITS:
        return _PROBE_DEFAULT_PROFILE
    return profile


def get_probe_runtime_config() -> dict[str, Any]:
    profile = _resolve_probe_profile_name()
    profile_limits = _PROBE_PROFILE_LIMITS.get(
        profile,
        _PROBE_PROFILE_LIMITS[_PROBE_DEFAULT_PROFILE],
    )
    timeout_seconds = _read_float_env(
        "VENOM_INTROSPECTION_PROBE_TIMEOUT_SECONDS",
        _read_float_env(
            "GEMMA4_AUDIO_PROBE_TIMEOUT_SECONDS",
            float(profile_limits["timeout_seconds"]),
        ),
    )
    max_attempts = _read_int_env(
        "VENOM_INTROSPECTION_PROBE_MAX_ATTEMPTS",
        int(profile_limits["max_attempts"]),
    )
    max_top_k = _read_int_env(
        "VENOM_INTROSPECTION_PROBE_MAX_TOP_K",
        int(profile_limits["max_top_k"]),
    )
    max_layer_count = _read_int_env(
        "VENOM_INTROSPECTION_PROBE_MAX_LAYER_COUNT",
        int(profile_limits["max_layer_count"]),
    )
    max_prompt_tokens = _read_int_env(
        "VENOM_INTROSPECTION_PROBE_MAX_PROMPT_TOKENS",
        int(profile_limits["max_prompt_tokens"]),
    )
    enabled = _parse_bool_env(
        os.getenv("GEMMA4_AUDIO_PROBE_ENABLED"),
        default=False,
    )
    return {
        "profile": profile,
        "enabled": enabled,
        "timeout_seconds": max(1.0, float(timeout_seconds)),
        "max_attempts": max(1, int(max_attempts)),
        "max_top_k": max(1, int(max_top_k)),
        "max_layer_count": max(1, int(max_layer_count)),
        "max_prompt_tokens": max(1, int(max_prompt_tokens)),
    }


def build_probe_health_payload(runtime: Any) -> dict[str, Any]:
    config = get_probe_runtime_config()
    provider = str(getattr(runtime, "provider", "") or "")
    endpoint = str(getattr(runtime, "endpoint", "") or "")
    runtime_supported = is_multi_runtime(provider)
    endpoint_configured = bool(endpoint)
    enabled = bool(config["enabled"])
    if not enabled:
        status = "disabled"
    elif not runtime_supported:
        status = "unsupported_runtime"
    elif not endpoint_configured:
        status = "endpoint_missing"
    else:
        status = "ready"
    return {
        "enabled": enabled,
        "status": status,
        "healthy": status == "ready",
        "runtime_supported": runtime_supported,
        "endpoint_configured": endpoint_configured,
        "profile": str(config["profile"]),
        "limits": {
            "timeout_seconds": float(config["timeout_seconds"]),
            "max_attempts": int(config["max_attempts"]),
            "max_top_k": int(config["max_top_k"]),
            "max_layer_count": int(config["max_layer_count"]),
            "max_prompt_tokens": int(config["max_prompt_tokens"]),
        },
    }


def _estimate_prompt_tokens(prompt: str) -> int:
    stripped = prompt.strip()
    if not stripped:
        return 0
    return max(len(stripped.split()), len(stripped) // 4)


def _build_probe_url(runtime_endpoint: str) -> str:
    base = runtime_endpoint.rstrip("/")
    if base.endswith("/v1"):
        return f"{base}/introspection/probe"
    return f"{base}/v1/introspection/probe"


def _sanitize_layer_selection(layers: list[int]) -> list[int]:
    deduplicated: list[int] = []
    for layer in layers:
        if layer < 0:
            raise ValueError("layer_selection must contain non-negative integers")
        if layer not in deduplicated:
            deduplicated.append(layer)
    if len(deduplicated) > _PROBE_MAX_LAYER_COUNT:
        raise ValueError(f"layer_selection exceeds limit ({_PROBE_MAX_LAYER_COUNT})")
    return sorted(deduplicated)


def _get_probe_http_client() -> httpx.AsyncClient:
    global _PROBE_HTTP_CLIENT
    if _PROBE_HTTP_CLIENT is None:
        _PROBE_HTTP_CLIENT = httpx.AsyncClient()
    return _PROBE_HTTP_CLIENT


async def _post_probe_request(
    *,
    url: str,
    payload: dict[str, Any],
    timeout_seconds: float,
) -> httpx.Response:
    headers = {
        "Content-Type": "application/json",
        "X-Request-Id": str(uuid4()),
    }
    timeout = httpx.Timeout(timeout_seconds, connect=5.0)
    client = _get_probe_http_client()
    return await client.post(url, json=payload, headers=headers, timeout=timeout)


def _build_unavailable_response(
    *,
    code: str,
    message: str,
    runtime_label: str,
    elapsed_ms: float,
) -> dict[str, Any]:
    return {
        "status": _PROBE_UNAVAILABLE,
        "code": code,
        "message": message,
        "runtime_label": runtime_label,
        "probe": None,
        "diagnostics": {
            "elapsed_ms": round(elapsed_ms, 2),
        },
    }


def _parse_probe_response_json(response: httpx.Response) -> dict[str, Any]:
    try:
        parsed = response.json()
    except ValueError as exc:
        raise RuntimeError("Probe response is not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("Probe response has invalid shape")
    return parsed


def _normalize_probe_payload(
    *,
    parsed: dict[str, Any],
    elapsed_ms: float,
) -> dict[str, Any]:
    status = str(parsed.get("status") or _PROBE_OK)
    probe_payload = parsed.get("probe")
    diagnostics = parsed.get("diagnostics")
    if not isinstance(diagnostics, dict):
        diagnostics = {}
    diagnostics["elapsed_ms"] = round(elapsed_ms, 2)
    diagnostics["payload_bytes"] = len(str(parsed))
    return {
        "status": status,
        "code": parsed.get("code"),
        "message": parsed.get("message"),
        "runtime_label": parsed.get("runtime_label"),
        "probe": probe_payload,
        "diagnostics": diagnostics,
    }


def _elapsed_ms(flow_started_at: float) -> float:
    return (time.perf_counter() - flow_started_at) * 1000.0


def _probe_unavailable(
    *,
    code: str,
    message: str,
    runtime_label: str,
    flow_started_at: float,
) -> dict[str, Any]:
    return _build_unavailable_response(
        code=code,
        message=message,
        runtime_label=runtime_label,
        elapsed_ms=_elapsed_ms(flow_started_at),
    )


def _validate_probe_runtime_preconditions(
    *,
    runtime: Any,
    config: dict[str, Any],
    runtime_label: str,
    flow_started_at: float,
) -> dict[str, Any] | None:
    if not bool(config["enabled"]):
        return _probe_unavailable(
            code="probe_disabled",
            message="Probe is disabled by runtime configuration",
            runtime_label=runtime_label,
            flow_started_at=flow_started_at,
        )
    if not is_multi_runtime(runtime.provider):
        return _probe_unavailable(
            code="runtime_not_supported",
            message="Probe is available only for multi_runtime",
            runtime_label=runtime_label,
            flow_started_at=flow_started_at,
        )
    if not runtime.endpoint:
        return _probe_unavailable(
            code="endpoint_missing",
            message="Active multi_runtime endpoint is not configured",
            runtime_label=runtime_label,
            flow_started_at=flow_started_at,
        )
    return None


def _validate_probe_request_limits(
    *,
    prompt: str,
    top_k: int,
    layer_selection: list[int],
    config: dict[str, Any],
) -> list[int]:
    estimated_tokens = _estimate_prompt_tokens(prompt)
    max_prompt_tokens = int(config["max_prompt_tokens"])
    if estimated_tokens > max_prompt_tokens:
        raise ValueError(f"prompt exceeds probe token limit ({max_prompt_tokens})")

    max_top_k = int(config["max_top_k"])
    if top_k < 1 or top_k > max_top_k:
        raise ValueError(f"top_k must be between 1 and {max_top_k}")

    sanitized_layers = _sanitize_layer_selection(layer_selection)
    max_layer_count = int(config["max_layer_count"])
    if len(sanitized_layers) > max_layer_count:
        raise ValueError(f"layer_selection exceeds limit ({max_layer_count})")
    return sanitized_layers


def _handle_probe_http_response(
    *,
    response: httpx.Response,
    runtime_label: str,
    flow_started_at: float,
) -> dict[str, Any] | None:
    elapsed_ms = _elapsed_ms(flow_started_at)
    if response.status_code in {404, 501, 503}:
        return _build_unavailable_response(
            code="probe_unavailable",
            message="Probe endpoint is unavailable on active runtime",
            runtime_label=runtime_label,
            elapsed_ms=elapsed_ms,
        )
    if response.status_code in {400, 422}:
        raise ValueError("Invalid probe request parameters")
    if response.status_code >= 500:
        return _build_unavailable_response(
            code="runtime_error",
            message="Runtime probe is temporarily unavailable",
            runtime_label=runtime_label,
            elapsed_ms=elapsed_ms,
        )
    return None


def _normalize_success_probe_response(
    *,
    response: httpx.Response,
    runtime_label: str,
    flow_started_at: float,
) -> dict[str, Any]:
    parsed = _parse_probe_response_json(response)
    normalized = _normalize_probe_payload(
        parsed=parsed,
        elapsed_ms=_elapsed_ms(flow_started_at),
    )
    if normalized.get("runtime_label") in (None, ""):
        normalized["runtime_label"] = runtime_label
    if normalized.get("status") not in {_PROBE_OK, _PROBE_UNAVAILABLE, _PROBE_FAILED}:
        normalized["status"] = _PROBE_FAILED
    return normalized


async def _execute_probe_with_retry(
    *,
    probe_url: str,
    probe_payload: dict[str, Any],
    timeout_seconds: float,
    max_attempts: int,
    runtime_label: str,
    flow_started_at: float,
) -> dict[str, Any]:
    attempt = 0
    while attempt < max_attempts:
        attempt += 1
        try:
            response = await _post_probe_request(
                url=probe_url,
                payload=probe_payload,
                timeout_seconds=timeout_seconds,
            )
            if response.status_code in _PROBE_TRANSIENT_STATUS_CODES:
                if attempt >= max_attempts:
                    return _probe_unavailable(
                        code="runtime_error",
                        message="Runtime probe is temporarily unavailable",
                        runtime_label=runtime_label,
                        flow_started_at=flow_started_at,
                    )
                continue
            handled = _handle_probe_http_response(
                response=response,
                runtime_label=runtime_label,
                flow_started_at=flow_started_at,
            )
            if handled is not None:
                return handled
            return _normalize_success_probe_response(
                response=response,
                runtime_label=runtime_label,
                flow_started_at=flow_started_at,
            )
        except ValueError:
            raise
        except (httpx.TimeoutException, httpx.ConnectError):
            if attempt >= max_attempts:
                return _probe_unavailable(
                    code="probe_timeout",
                    message="Probe request timed out on active runtime",
                    runtime_label=runtime_label,
                    flow_started_at=flow_started_at,
                )
        except httpx.HTTPError:
            if attempt >= max_attempts:
                return _probe_unavailable(
                    code="probe_transport_error",
                    message="Probe transport error on active runtime",
                    runtime_label=runtime_label,
                    flow_started_at=flow_started_at,
                )
    return _probe_unavailable(
        code="probe_transport_error",
        message="Probe transport error on active runtime",
        runtime_label=runtime_label,
        flow_started_at=flow_started_at,
    )


async def run_model_introspection_probe(
    *,
    prompt: str,
    mode: str,
    layer_selection: list[int],
    top_k: int,
) -> dict[str, Any]:
    runtime = get_active_llm_runtime()
    config = get_probe_runtime_config()
    runtime_label = format_runtime_label(runtime)
    flow_started_at = time.perf_counter()
    precondition_error = _validate_probe_runtime_preconditions(
        runtime=runtime,
        config=config,
        runtime_label=runtime_label,
        flow_started_at=flow_started_at,
    )
    if precondition_error is not None:
        return precondition_error

    sanitized_layers = _validate_probe_request_limits(
        prompt=prompt,
        top_k=top_k,
        layer_selection=layer_selection,
        config=config,
    )
    endpoint = str(runtime.endpoint)
    probe_url = _build_probe_url(endpoint)
    probe_payload = {
        "prompt": prompt,
        "mode": mode,
        "layer_selection": sanitized_layers,
        "top_k": top_k,
    }
    return await _execute_probe_with_retry(
        probe_url=probe_url,
        probe_payload=probe_payload,
        timeout_seconds=float(config["timeout_seconds"]),
        max_attempts=int(config["max_attempts"]),
        runtime_label=runtime_label,
        flow_started_at=flow_started_at,
    )
