"""Saliency payload shaping for model introspection analysis."""

from __future__ import annotations

from typing import Any

from venom_core.services.model_introspection_probe_service import (
    run_model_introspection_probe,
)

_SALIENCY_LAYER_SELECTION = [31]
_SALIENCY_TOP_K = 16
_SALIENCY_TARGET_OUTPUT_TOKEN_INDEX = 0


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_token(token: Any) -> str:
    value = str(token or "")
    if value.startswith("▁"):
        value = value[1:]
    value = value.strip()
    return value or "?"


def _resolve_target_token(
    *,
    probe_target_token: Any,
    requested_target_token: str | None,
) -> str | None:
    if probe_target_token is not None:
        return _normalize_token(probe_target_token)
    if requested_target_token:
        return _normalize_token(requested_target_token)
    return None


def _normalize_token_weights(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        token_index = item.get("token_index")
        weight = _safe_float(item.get("weight"))
        if not isinstance(token_index, int) or weight is None:
            continue
        normalized.append(
            {
                "token": _normalize_token(item.get("token")),
                "token_index": token_index,
                "weight": round(weight, 6),
            }
        )
    normalized.sort(key=lambda entry: abs(entry["weight"]), reverse=True)
    return normalized


def _build_unavailable_saliency_payload(
    *,
    status: str,
    code: str | None,
    message: str | None,
    runtime_label: str | None,
    diagnostics: dict[str, Any],
) -> dict[str, Any]:
    return {
        "source": "probe_unavailable",
        "status": status,
        "code": code,
        "message": message,
        "runtime_label": runtime_label,
        "method": None,
        "target_output_token_index": None,
        "target_output_token": None,
        "token_weights": [],
        "diagnostics": diagnostics,
    }


async def _build_saliency_proxy_from_attention(
    *,
    prompt: str,
    runtime_label: str | None,
    diagnostics: dict[str, Any],
) -> dict[str, Any] | None:
    probe_payload = await run_model_introspection_probe(
        prompt=prompt,
        mode="attention",
        layer_selection=_SALIENCY_LAYER_SELECTION,
        top_k=_SALIENCY_TOP_K,
    )
    if str(probe_payload.get("status") or "probe_unavailable") != "ok":
        return None
    probe = probe_payload.get("probe")
    if not isinstance(probe, dict):
        return None
    raw_layers = probe.get("layers")
    if not isinstance(raw_layers, list) or not raw_layers:
        return None
    last_layer = raw_layers[-1]
    if not isinstance(last_layer, dict):
        return None
    attention_top = last_layer.get("attention_top")
    token_weights = _normalize_token_weights(
        [
            {
                "token": item.get("token"),
                "token_index": item.get("token_index"),
                "weight": item.get("score"),
            }
            for item in attention_top
        ]
        if isinstance(attention_top, list)
        else []
    )
    if not token_weights:
        return None
    proxy_diagnostics = dict(diagnostics)
    proxy_diagnostics["proxy_from_mode"] = "attention"
    return {
        "source": "probe_runtime",
        "status": "ok",
        "code": "saliency_proxy_attention",
        "message": "Saliency payload approximated from attention probe",
        "runtime_label": runtime_label,
        "method": "attention_proxy",
        "target_output_token_index": _SALIENCY_TARGET_OUTPUT_TOKEN_INDEX,
        "target_output_token": None,
        "token_weights": token_weights,
        "diagnostics": proxy_diagnostics,
    }


async def _build_saliency_proxy_from_logits(
    *,
    prompt: str,
    runtime_label: str | None,
    diagnostics: dict[str, Any],
) -> dict[str, Any] | None:
    probe_payload = await run_model_introspection_probe(
        prompt=prompt,
        mode="logits",
        layer_selection=_SALIENCY_LAYER_SELECTION,
        top_k=_SALIENCY_TOP_K,
    )
    if str(probe_payload.get("status") or "probe_unavailable") != "ok":
        return None
    probe = probe_payload.get("probe")
    if not isinstance(probe, dict):
        return None
    raw_layers = probe.get("layers")
    if not isinstance(raw_layers, list) or not raw_layers:
        return None
    last_layer = raw_layers[-1]
    if not isinstance(last_layer, dict):
        return None
    logits_top = last_layer.get("logits_top")
    token_weights = _normalize_token_weights(
        [
            {
                "token": item.get("token"),
                "token_index": item.get("token_index"),
                "weight": item.get("score"),
            }
            for item in logits_top
        ]
        if isinstance(logits_top, list)
        else []
    )
    if not token_weights:
        return None
    proxy_diagnostics = dict(diagnostics)
    proxy_diagnostics["proxy_from_mode"] = "logits"
    return {
        "source": "probe_runtime",
        "status": "ok",
        "code": "saliency_proxy_logits",
        "message": "Saliency payload approximated from logits probe",
        "runtime_label": runtime_label,
        "method": "logits_proxy",
        "target_output_token_index": _SALIENCY_TARGET_OUTPUT_TOKEN_INDEX,
        "target_output_token": None,
        "token_weights": token_weights,
        "diagnostics": proxy_diagnostics,
    }


async def _resolve_saliency_proxy_payload(
    *,
    prompt: str,
    runtime_label: str | None,
    diagnostics: dict[str, Any],
) -> dict[str, Any] | None:
    proxy_payload = await _build_saliency_proxy_from_attention(
        prompt=prompt,
        runtime_label=runtime_label,
        diagnostics=diagnostics,
    )
    if proxy_payload is not None:
        return proxy_payload
    return await _build_saliency_proxy_from_logits(
        prompt=prompt,
        runtime_label=runtime_label,
        diagnostics=diagnostics,
    )


async def _resolve_saliency_proxy_or_unavailable(
    *,
    prompt: str,
    runtime_label: str | None,
    diagnostics: dict[str, Any],
    status: str,
    code: str,
    message: str,
) -> dict[str, Any]:
    proxy_payload = await _resolve_saliency_proxy_payload(
        prompt=prompt,
        runtime_label=runtime_label,
        diagnostics=diagnostics,
    )
    if proxy_payload is not None:
        return proxy_payload
    return _build_unavailable_saliency_payload(
        status=status,
        code=code,
        message=message,
        runtime_label=runtime_label,
        diagnostics=diagnostics,
    )


async def build_saliency_payload(
    *,
    prompt: str,
    response_text: str,
) -> dict[str, Any]:
    target_output_token = response_text.split()[0] if response_text.strip() else None
    probe_payload = await run_model_introspection_probe(
        prompt=prompt,
        mode="saliency",
        layer_selection=_SALIENCY_LAYER_SELECTION,
        top_k=_SALIENCY_TOP_K,
    )
    status = str(probe_payload.get("status") or "probe_unavailable")
    diagnostics_raw = probe_payload.get("diagnostics")
    diagnostics = diagnostics_raw if isinstance(diagnostics_raw, dict) else {}
    runtime_label = probe_payload.get("runtime_label")
    runtime_label_str = str(runtime_label) if runtime_label else None

    if status != "ok":
        return await _resolve_saliency_proxy_or_unavailable(
            prompt=prompt,
            runtime_label=runtime_label_str,
            diagnostics=diagnostics,
            status=status,
            code=str(probe_payload.get("code") or "saliency_unavailable"),
            message=str(probe_payload.get("message") or "Saliency probe unavailable"),
        )

    probe = probe_payload.get("probe")
    if not isinstance(probe, dict):
        return _build_unavailable_saliency_payload(
            status="failed",
            code="invalid_probe_shape",
            message="Probe payload has invalid shape",
            runtime_label=runtime_label_str,
            diagnostics=diagnostics,
        )

    token_weights = _normalize_token_weights(probe.get("token_weights"))
    if not token_weights:
        return await _resolve_saliency_proxy_or_unavailable(
            prompt=prompt,
            runtime_label=runtime_label_str,
            diagnostics=diagnostics,
            status="probe_unavailable",
            code="saliency_unavailable",
            message="Saliency payload is unavailable for selected output token",
        )

    target_index_raw = probe.get("target_output_token_index")
    target_index = (
        int(target_index_raw)
        if isinstance(target_index_raw, int) and target_index_raw >= 0
        else _SALIENCY_TARGET_OUTPUT_TOKEN_INDEX
    )
    target_token = probe.get("target_output_token")
    target_token_str = _resolve_target_token(
        probe_target_token=target_token,
        requested_target_token=target_output_token,
    )

    return {
        "source": "probe_runtime",
        "status": "ok",
        "code": None,
        "message": "Saliency payload ready",
        "runtime_label": runtime_label_str,
        "method": str(probe.get("method") or "integrated_gradients"),
        "target_output_token_index": target_index,
        "target_output_token": target_token_str,
        "token_weights": token_weights,
        "diagnostics": diagnostics,
    }
