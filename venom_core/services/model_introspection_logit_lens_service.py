"""Logit-lens shaping for model introspection analysis payloads."""

from __future__ import annotations

import math
from typing import Any

from venom_core.services.model_introspection_probe_service import (
    run_model_introspection_probe,
)

_LOGIT_LENS_LAYER_SELECTION = [0, 4, 8, 12, 16, 20, 24, 31]
_LOGIT_LENS_TOP_K = 5
_CHECKPOINT_PERCENTS = (25, 50, 75, 100)
_INTERPRETABILITY_HEURISTIC_VERSION = "v1.1"
_CONFIDENCE_HIGH_THRESHOLD = 0.65
_CONFIDENCE_MEDIUM_THRESHOLD = 0.4
_NOISE_HIGH_THRESHOLD = 0.7
_NOISE_MEDIUM_THRESHOLD = 0.35
_INTERPRETABLE_MAX_NOISE_RATIO = 0.5


def _normalize_token(token: Any) -> str:
    value = str(token or "")
    if value.startswith("▁"):
        value = value[1:]
    return value.strip() or "?"


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _tokenize_output_preview(response_text: str) -> list[str]:
    return [token for token in response_text.split() if token][:16]


def _normalize_top_k(entries: Any) -> list[dict[str, Any]]:
    if not isinstance(entries, list):
        return []
    normalized: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        score = _safe_float(entry.get("score"))
        if score is None:
            continue
        normalized.append(
            {
                "token": _normalize_token(entry.get("token")),
                "raw_token": str(entry.get("token") or ""),
                "token_index": int(entry.get("token_index", -1)),
                "score": round(score, 6),
            }
        )
    normalized.sort(key=lambda item: item["score"], reverse=True)
    return normalized


def _compute_top_confidence(top_k: list[dict[str, Any]]) -> float | None:
    if not top_k:
        return None
    scores = [float(item["score"]) for item in top_k]
    max_score = max(scores)
    exp_values = [math.exp(score - max_score) for score in scores]
    denominator = sum(exp_values)
    if denominator <= 0:
        return None
    return round(exp_values[0] / denominator, 4)


def _normalize_layers(payload_layers: Any) -> list[dict[str, Any]]:
    if not isinstance(payload_layers, list):
        return []
    layers: list[dict[str, Any]] = []
    for item in payload_layers:
        if not isinstance(item, dict):
            continue
        layer_value = item.get("layer")
        if not isinstance(layer_value, int):
            continue
        top_k = _normalize_top_k(item.get("logits_top"))
        if not top_k:
            continue
        layers.append(
            {
                "layer": layer_value,
                "top_k": top_k,
            }
        )
    layers.sort(key=lambda item: item["layer"])
    return layers


def _select_layer_by_percent(
    layers: list[dict[str, Any]],
    percent: int,
) -> dict[str, Any]:
    if not layers:
        return {"layer": -1, "top_k": []}
    raw_index = math.ceil((percent / 100.0) * len(layers)) - 1
    bounded_index = max(0, min(len(layers) - 1, raw_index))
    return layers[bounded_index]


def _build_logit_lens_signals(
    checkpoints: list[dict[str, Any]],
) -> dict[str, bool]:
    top_tokens = [checkpoint.get("top_token") for checkpoint in checkpoints]
    confidences = [
        float(checkpoint["confidence"])
        for checkpoint in checkpoints
        if isinstance(checkpoint.get("confidence"), (int, float))
    ]
    early_unstable = False
    if len(top_tokens) >= 2:
        early_unstable = bool(top_tokens[0]) and top_tokens[0] != top_tokens[1]
    late_stabilized = False
    if len(top_tokens) >= 2:
        late_stabilized = bool(top_tokens[-1]) and top_tokens[-1] == top_tokens[-2]
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    low_confidence_path = avg_confidence < 0.45
    return {
        "early_unstable": early_unstable,
        "late_stabilized": late_stabilized,
        "low_confidence_path": low_confidence_path,
    }


def _is_noisy_token(token: str) -> bool:
    stripped = token.strip()
    if not stripped or stripped == "?":
        return True
    alnum_chars = sum(1 for char in stripped if char.isalnum())
    punctuation_chars = sum(
        1 for char in stripped if not char.isalnum() and not char.isspace()
    )
    if alnum_chars == 0 and punctuation_chars > 0:
        return True
    total_chars = max(1, len(stripped))
    punctuation_ratio = punctuation_chars / total_chars
    return punctuation_ratio >= 0.65


def _resolve_confidence_band(avg_confidence: float) -> str:
    if avg_confidence >= _CONFIDENCE_HIGH_THRESHOLD:
        return "high"
    if avg_confidence >= _CONFIDENCE_MEDIUM_THRESHOLD:
        return "medium"
    return "low"


def _build_interpretability(checkpoints: list[dict[str, Any]]) -> dict[str, Any]:
    top_tokens: list[str] = []
    confidence_values: list[float] = []
    for checkpoint in checkpoints:
        token = checkpoint.get("top_token")
        if isinstance(token, str) and token:
            top_tokens.append(token)
        confidence = checkpoint.get("confidence")
        if isinstance(confidence, (int, float)):
            confidence_values.append(float(confidence))

    if not top_tokens:
        return {
            "interpretable": False,
            "confidence_band": "unknown",
            "token_noise_ratio": 1.0,
            "readable_top_tokens": 0,
            "total_top_tokens": 0,
        }

    noisy_tokens = sum(1 for token in top_tokens if _is_noisy_token(token))
    token_noise_ratio = noisy_tokens / len(top_tokens)
    avg_confidence = (
        sum(confidence_values) / len(confidence_values) if confidence_values else 0.0
    )
    confidence_band = _resolve_confidence_band(avg_confidence)
    interpretable = (
        token_noise_ratio <= _INTERPRETABLE_MAX_NOISE_RATIO and confidence_band != "low"
    )
    return {
        "interpretable": interpretable,
        "confidence_band": confidence_band,
        "token_noise_ratio": round(token_noise_ratio, 4),
        "readable_top_tokens": len(top_tokens) - noisy_tokens,
        "total_top_tokens": len(top_tokens),
        "heuristic_version": _INTERPRETABILITY_HEURISTIC_VERSION,
        "confidence_thresholds": {
            "medium": _CONFIDENCE_MEDIUM_THRESHOLD,
            "high": _CONFIDENCE_HIGH_THRESHOLD,
        },
        "noise_thresholds": {
            "medium": _NOISE_MEDIUM_THRESHOLD,
            "high": _NOISE_HIGH_THRESHOLD,
        },
    }


def _with_calibration_diagnostics(diagnostics: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(diagnostics)
    enriched["heuristic_version"] = _INTERPRETABILITY_HEURISTIC_VERSION
    enriched["heuristic_calibration"] = {
        "confidence": {
            "medium": _CONFIDENCE_MEDIUM_THRESHOLD,
            "high": _CONFIDENCE_HIGH_THRESHOLD,
        },
        "noise": {
            "medium": _NOISE_MEDIUM_THRESHOLD,
            "high": _NOISE_HIGH_THRESHOLD,
        },
        "interpretable_max_noise_ratio": _INTERPRETABLE_MAX_NOISE_RATIO,
    }
    return enriched


def _build_unavailable_logit_lens(
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
        "input_tokens": [],
        "output_tokens": [],
        "raw_input_tokens": [],
        "raw_output_tokens": [],
        "checkpoints": [],
        "signals": {
            "early_unstable": False,
            "late_stabilized": False,
            "low_confidence_path": False,
        },
        "interpretability": {
            "interpretable": False,
            "confidence_band": "unknown",
            "token_noise_ratio": 1.0,
            "readable_top_tokens": 0,
            "total_top_tokens": 0,
        },
        "diagnostics": _with_calibration_diagnostics(diagnostics),
    }


def _runtime_label_from_probe_payload(probe_payload: dict[str, Any]) -> str | None:
    raw_runtime_label = probe_payload.get("runtime_label")
    if raw_runtime_label:
        return str(raw_runtime_label)
    return None


def _extract_token_preview(probe: dict[str, Any]) -> list[str]:
    tokenization = probe.get("tokenization")
    if not isinstance(tokenization, dict):
        return []
    raw_tokens = tokenization.get("tokens_preview")
    if not isinstance(raw_tokens, list):
        return []
    return [_normalize_token(token) for token in raw_tokens][:32]


def _extract_raw_token_preview(probe: dict[str, Any]) -> list[str]:
    tokenization = probe.get("tokenization")
    if not isinstance(tokenization, dict):
        return []
    raw_tokens = tokenization.get("tokens_preview")
    if not isinstance(raw_tokens, list):
        return []
    return [str(token or "") for token in raw_tokens][:32]


def _build_checkpoints(layers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    checkpoints: list[dict[str, Any]] = []
    previous_token: str | None = None
    for percent in _CHECKPOINT_PERCENTS:
        layer = _select_layer_by_percent(layers, percent)
        top_k = layer.get("top_k", [])
        top_token = top_k[0]["token"] if top_k else None
        confidence = _compute_top_confidence(top_k)
        changed = previous_token is not None and top_token != previous_token
        checkpoints.append(
            {
                "id": f"cp_{percent}",
                "percent": percent,
                "layer": int(layer.get("layer", -1)),
                "top_k": top_k,
                "top_token": top_token,
                "confidence": confidence,
                "changed": changed,
            }
        )
        previous_token = top_token
    return checkpoints


async def build_logit_lens_payload(
    *,
    prompt: str,
    response_text: str,
) -> dict[str, Any]:
    probe_payload = await run_model_introspection_probe(
        prompt=prompt,
        mode="logits",
        layer_selection=_LOGIT_LENS_LAYER_SELECTION,
        top_k=_LOGIT_LENS_TOP_K,
    )
    status = str(probe_payload.get("status") or "probe_unavailable")
    diagnostics_raw = probe_payload.get("diagnostics")
    diagnostics = diagnostics_raw if isinstance(diagnostics_raw, dict) else {}
    runtime_label = _runtime_label_from_probe_payload(probe_payload)

    if status != "ok":
        return _build_unavailable_logit_lens(
            status=status,
            code=str(probe_payload.get("code") or "probe_unavailable"),
            message=str(probe_payload.get("message") or "Probe unavailable"),
            runtime_label=runtime_label,
            diagnostics=diagnostics,
        )

    probe = probe_payload.get("probe")
    if not isinstance(probe, dict):
        return _build_unavailable_logit_lens(
            status="failed",
            code="invalid_probe_shape",
            message="Probe payload has invalid shape",
            runtime_label=runtime_label,
            diagnostics=diagnostics,
        )

    raw_token_preview = _extract_raw_token_preview(probe)
    layers = _normalize_layers(probe.get("layers"))
    checkpoints = _build_checkpoints(layers)

    return {
        "source": "probe_runtime",
        "status": "ok",
        "code": None,
        "message": "Logit lens ready",
        "runtime_label": runtime_label,
        "input_tokens": _tokenize_output_preview(prompt),
        "output_tokens": _tokenize_output_preview(response_text),
        "raw_input_tokens": raw_token_preview,
        "raw_output_tokens": [],
        "checkpoints": checkpoints,
        "signals": _build_logit_lens_signals(checkpoints),
        "interpretability": _build_interpretability(checkpoints),
        "diagnostics": _with_calibration_diagnostics(diagnostics),
    }
