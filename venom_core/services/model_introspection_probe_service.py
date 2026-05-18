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
_PROBE_MAX_HEAD_COUNT = 32
_PROBE_MAX_PROMPT_TOKENS = 1024
_PROBE_UNAVAILABLE = "probe_unavailable"
_PROBE_OK = "ok"
_PROBE_FAILED = "failed"
_PROBE_TRANSIENT_STATUS_CODES = {502, 503, 504}
_PROBE_DEFAULT_PROFILE = "dev"
_PROBE_TRANSPORT_ERROR_MESSAGE = "Probe transport error on active runtime"
_PROBE_RUNTIME_SUPPORTED_MODES = {"hidden", "attention", "logits", "saliency"}
_PROBE_HTTP_CLIENT: httpx.AsyncClient | None = None
_PROBE_PROFILE_LIMITS: dict[str, dict[str, float | int]] = {
    "dev": {
        "timeout_seconds": _PROBE_TIMEOUT_SECONDS,
        "max_attempts": _PROBE_MAX_ATTEMPTS,
        "max_top_k": _PROBE_MAX_TOP_K,
        "max_layer_count": _PROBE_MAX_LAYER_COUNT,
        "max_head_count": _PROBE_MAX_HEAD_COUNT,
        "max_prompt_tokens": _PROBE_MAX_PROMPT_TOKENS,
    },
    "stage": {
        "timeout_seconds": 14.0,
        "max_attempts": 2,
        "max_top_k": 24,
        "max_layer_count": 6,
        "max_head_count": 24,
        "max_prompt_tokens": 768,
    },
    "prod": {
        "timeout_seconds": 10.0,
        "max_attempts": 1,
        "max_top_k": 16,
        "max_layer_count": 4,
        "max_head_count": 16,
        "max_prompt_tokens": 512,
    },
}
_PROBE_MODEL_WHITELIST_DEFAULT = "google/gemma-4-e2b-it,google/gemma-4-e2b-it:latest,openclaw-qwen3vl-8b-opt:latest,qwen3.5:latest,qwen3.5"


def _parse_csv_env(raw_value: str | None) -> list[str]:
    if raw_value is None:
        return []
    values: list[str] = []
    for part in raw_value.split(","):
        normalized = part.strip().lower()
        if normalized:
            values.append(normalized)
    return values


def get_probe_model_whitelist() -> list[str]:
    configured = os.getenv(
        "VENOM_INTROSPECTION_PROBE_MODEL_WHITELIST",
        _PROBE_MODEL_WHITELIST_DEFAULT,
    )
    return _parse_csv_env(configured)


def _is_probe_model_whitelisted(model_name: str) -> bool:
    model = str(model_name or "").strip().lower()
    whitelist = get_probe_model_whitelist()
    return bool(model and whitelist and model in whitelist)


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
    max_head_count = _read_int_env(
        "VENOM_INTROSPECTION_PROBE_MAX_HEAD_COUNT",
        int(profile_limits["max_head_count"]),
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
        "max_head_count": max(1, int(max_head_count)),
        "max_prompt_tokens": max(1, int(max_prompt_tokens)),
    }


def build_probe_health_payload(runtime: Any) -> dict[str, Any]:
    config = get_probe_runtime_config()
    provider = str(getattr(runtime, "provider", "") or "")
    endpoint = str(getattr(runtime, "endpoint", "") or "")
    runtime_supported = is_multi_runtime(provider)
    endpoint_configured = bool(endpoint)
    model_name = str(getattr(runtime, "model_name", "") or "")
    model_whitelisted = _is_probe_model_whitelisted(model_name)
    enabled = bool(config["enabled"])
    if not enabled:
        status = "disabled"
    elif not runtime_supported:
        status = "unsupported_runtime"
    elif not model_whitelisted:
        status = "model_not_whitelisted"
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
        "model_whitelisted": model_whitelisted,
        "model_name": model_name,
        "profile": str(config["profile"]),
        "limits": {
            "timeout_seconds": float(config["timeout_seconds"]),
            "max_attempts": int(config["max_attempts"]),
            "max_top_k": int(config["max_top_k"]),
            "max_layer_count": int(config["max_layer_count"]),
            "max_head_count": int(config["max_head_count"]),
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


def _sanitize_head_selection(heads: list[int]) -> list[int]:
    deduplicated: list[int] = []
    for head in heads:
        if head < 0:
            raise ValueError("head_selection must contain non-negative integers")
        if head not in deduplicated:
            deduplicated.append(head)
    if len(deduplicated) > _PROBE_MAX_HEAD_COUNT:
        raise ValueError(f"head_selection exceeds limit ({_PROBE_MAX_HEAD_COUNT})")
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
    if not _is_probe_model_whitelisted(getattr(runtime, "model_name", "")):
        return _probe_unavailable(
            code="model_not_whitelisted",
            message="Probe is disabled for active model (not in whitelist)",
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
    head_selection: list[int],
    config: dict[str, Any],
) -> tuple[list[int], list[int]]:
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
    sanitized_heads = _sanitize_head_selection(head_selection)
    max_head_count = int(config["max_head_count"])
    if len(sanitized_heads) > max_head_count:
        raise ValueError(f"head_selection exceeds limit ({max_head_count})")
    return sanitized_layers, sanitized_heads


def _build_unavailable_code_for_mode(mode: str) -> str:
    normalized_mode = str(mode or "").strip().lower()
    if normalized_mode == "attention":
        return "attention_unavailable"
    if normalized_mode == "saliency":
        return "saliency_unavailable"
    return "probe_unavailable"


def _handle_probe_http_response(
    *,
    response: httpx.Response,
    mode: str,
    runtime_label: str,
    flow_started_at: float,
) -> dict[str, Any] | None:
    elapsed_ms = _elapsed_ms(flow_started_at)
    if response.status_code in {404, 501, 503}:
        return _build_unavailable_response(
            code=_build_unavailable_code_for_mode(mode),
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


def _is_last_probe_attempt(attempt: int, max_attempts: int) -> bool:
    return attempt >= max_attempts


def _build_retry_exhausted_response(
    *,
    code: str,
    message: str,
    runtime_label: str,
    flow_started_at: float,
) -> dict[str, Any]:
    return _probe_unavailable(
        code=code,
        message=message,
        runtime_label=runtime_label,
        flow_started_at=flow_started_at,
    )


def _handle_probe_response_attempt(
    *,
    response: httpx.Response,
    mode: str,
    attempt: int,
    max_attempts: int,
    runtime_label: str,
    flow_started_at: float,
) -> tuple[dict[str, Any] | None, bool]:
    if response.status_code in _PROBE_TRANSIENT_STATUS_CODES:
        if _is_last_probe_attempt(attempt, max_attempts):
            return (
                _build_retry_exhausted_response(
                    code="runtime_error",
                    message="Runtime probe is temporarily unavailable",
                    runtime_label=runtime_label,
                    flow_started_at=flow_started_at,
                ),
                False,
            )
        return None, True

    handled = _handle_probe_http_response(
        response=response,
        mode=mode,
        runtime_label=runtime_label,
        flow_started_at=flow_started_at,
    )
    if handled is not None:
        return handled, False

    return (
        _normalize_success_probe_response(
            response=response,
            runtime_label=runtime_label,
            flow_started_at=flow_started_at,
        ),
        False,
    )


def _handle_probe_retry_exception(
    *,
    attempt: int,
    max_attempts: int,
    runtime_label: str,
    flow_started_at: float,
    timeout: bool,
) -> dict[str, Any] | None:
    if not _is_last_probe_attempt(attempt, max_attempts):
        return None
    if timeout:
        return _build_retry_exhausted_response(
            code="probe_timeout",
            message="Probe request timed out on active runtime",
            runtime_label=runtime_label,
            flow_started_at=flow_started_at,
        )
    return _build_retry_exhausted_response(
        code="probe_transport_error",
        message=_PROBE_TRANSPORT_ERROR_MESSAGE,
        runtime_label=runtime_label,
        flow_started_at=flow_started_at,
    )


async def _run_single_probe_attempt(
    *,
    probe_url: str,
    probe_payload: dict[str, Any],
    mode: str,
    timeout_seconds: float,
    attempt: int,
    max_attempts: int,
    runtime_label: str,
    flow_started_at: float,
) -> tuple[dict[str, Any] | None, bool, str | None]:
    try:
        response = await _post_probe_request(
            url=probe_url,
            payload=probe_payload,
            timeout_seconds=timeout_seconds,
        )
        result, should_retry = _handle_probe_response_attempt(
            response=response,
            mode=mode,
            attempt=attempt,
            max_attempts=max_attempts,
            runtime_label=runtime_label,
            flow_started_at=flow_started_at,
        )
        retry_reason = (
            "transient_http"
            if should_retry and response.status_code in _PROBE_TRANSIENT_STATUS_CODES
            else None
        )
        return result, should_retry, retry_reason
    except ValueError:
        raise
    except httpx.TimeoutException:
        failure = _handle_probe_retry_exception(
            attempt=attempt,
            max_attempts=max_attempts,
            runtime_label=runtime_label,
            flow_started_at=flow_started_at,
            timeout=True,
        )
        if failure is not None:
            return failure, False, None
        return None, True, "timeout"
    except httpx.ConnectError:
        failure = _handle_probe_retry_exception(
            attempt=attempt,
            max_attempts=max_attempts,
            runtime_label=runtime_label,
            flow_started_at=flow_started_at,
            timeout=False,
        )
        if failure is not None:
            return failure, False, None
        return None, True, "transport"
    except httpx.HTTPError:
        failure = _handle_probe_retry_exception(
            attempt=attempt,
            max_attempts=max_attempts,
            runtime_label=runtime_label,
            flow_started_at=flow_started_at,
            timeout=False,
        )
        if failure is not None:
            return failure, False, None
        return None, True, "transport"


async def _execute_probe_with_retry(
    *,
    probe_url: str,
    probe_payload: dict[str, Any],
    mode: str,
    timeout_seconds: float,
    max_attempts: int,
    runtime_label: str,
    flow_started_at: float,
) -> dict[str, Any]:
    attempt = 0
    timeout_attempts = 0
    transient_http_attempts = 0
    transport_attempts = 0
    while attempt < max_attempts:
        attempt += 1
        result, should_retry, retry_reason = await _run_single_probe_attempt(
            probe_url=probe_url,
            probe_payload=probe_payload,
            mode=mode,
            timeout_seconds=timeout_seconds,
            attempt=attempt,
            max_attempts=max_attempts,
            runtime_label=runtime_label,
            flow_started_at=flow_started_at,
        )
        if result is None and should_retry:
            timeout_attempts, transient_http_attempts, transport_attempts = (
                _increment_retry_counters(
                    retry_reason=retry_reason,
                    timeout_attempts=timeout_attempts,
                    transient_http_attempts=transient_http_attempts,
                    transport_attempts=transport_attempts,
                )
            )
        if should_retry:
            continue
        if result is None:
            return _build_retry_exhausted_response(
                code="probe_transport_error",
                message=_PROBE_TRANSPORT_ERROR_MESSAGE,
                runtime_label=runtime_label,
                flow_started_at=flow_started_at,
            )
        _enrich_retry_diagnostics(
            result=result,
            attempt=attempt,
            max_attempts=max_attempts,
            timeout_attempts=timeout_attempts,
            transient_http_attempts=transient_http_attempts,
            transport_attempts=transport_attempts,
        )
        return result
    return _build_retry_exhausted_response(
        code="probe_transport_error",
        message=_PROBE_TRANSPORT_ERROR_MESSAGE,
        runtime_label=runtime_label,
        flow_started_at=flow_started_at,
    )


def _increment_retry_counters(
    *,
    retry_reason: str | None,
    timeout_attempts: int,
    transient_http_attempts: int,
    transport_attempts: int,
) -> tuple[int, int, int]:
    if retry_reason == "timeout":
        return timeout_attempts + 1, transient_http_attempts, transport_attempts
    if retry_reason == "transient_http":
        return timeout_attempts, transient_http_attempts + 1, transport_attempts
    return timeout_attempts, transient_http_attempts, transport_attempts + 1


def _enrich_retry_diagnostics(
    *,
    result: dict[str, Any],
    attempt: int,
    max_attempts: int,
    timeout_attempts: int,
    transient_http_attempts: int,
    transport_attempts: int,
) -> None:
    diagnostics = result.get("diagnostics")
    if not isinstance(diagnostics, dict):
        return
    diagnostics["attempts_used"] = attempt
    diagnostics["attempts_max"] = max_attempts
    diagnostics["retry_count"] = max(0, attempt - 1)
    diagnostics["timeout_attempts"] = timeout_attempts
    diagnostics["transient_http_attempts"] = transient_http_attempts
    diagnostics["transport_attempts"] = transport_attempts

    status = result.get("status")
    if status == _PROBE_OK and attempt > 1:
        diagnostics["retry_class"] = (
            "soft_timeout_recovered" if timeout_attempts > 0 else "soft_retry_recovered"
        )
        return
    if status != _PROBE_UNAVAILABLE:
        return
    code = str(result.get("code") or "")
    if code == "probe_timeout":
        result["code"] = (
            "probe_timeout_hard" if max_attempts > 1 else "probe_timeout_soft"
        )
        return
    if code in {"runtime_error", "probe_transport_error"} and attempt > 1:
        diagnostics["retry_class"] = "hard_retry_exhausted"


async def run_model_introspection_probe(
    *,
    prompt: str,
    mode: str,
    layer_selection: list[int],
    head_selection: list[int] | None = None,
    target_output_token_index: int | None = None,
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

    normalized_mode = str(mode or "").strip().lower()
    if normalized_mode not in _PROBE_RUNTIME_SUPPORTED_MODES:
        raise ValueError(
            f"mode must be one of: {', '.join(sorted(_PROBE_RUNTIME_SUPPORTED_MODES))}"
        )

    sanitized_layers, sanitized_heads = _validate_probe_request_limits(
        prompt=prompt,
        top_k=top_k,
        layer_selection=layer_selection,
        head_selection=head_selection or [],
        config=config,
    )
    endpoint = str(runtime.endpoint)
    probe_url = _build_probe_url(endpoint)
    probe_payload = {
        "prompt": prompt,
        "mode": normalized_mode,
        "layer_selection": sanitized_layers,
        "top_k": top_k,
    }
    if normalized_mode == "saliency" and isinstance(target_output_token_index, int):
        probe_payload["target_output_token_index"] = max(0, target_output_token_index)
    # Keep request-level validation for compatibility with callers that still pass
    # legacy fields, but do not forward unsupported keys to multi_runtime.
    _ = sanitized_heads
    if normalized_mode != "saliency":
        _ = target_output_token_index
    return await _execute_probe_with_retry(
        probe_url=probe_url,
        probe_payload=probe_payload,
        mode=normalized_mode,
        timeout_seconds=float(config["timeout_seconds"]),
        max_attempts=int(config["max_attempts"]),
        runtime_label=runtime_label,
        flow_started_at=flow_started_at,
    )
