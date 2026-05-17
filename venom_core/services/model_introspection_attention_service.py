"""Attention payload shaping for model introspection analysis."""

from __future__ import annotations

from typing import Any

from venom_core.services.model_introspection_probe_service import (
    run_model_introspection_probe,
)

_ATTENTION_LAYER_SELECTION = [0, 8, 16, 24, 31]
_ATTENTION_HEAD_SELECTION = [0, 3, 7]
_ATTENTION_TOP_K = 6
_ATTENTION_TOP_LINKS_PER_HEAD = 6


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


def _extract_tokens(probe: dict[str, Any]) -> list[str]:
    tokenization = probe.get("tokenization")
    if not isinstance(tokenization, dict):
        return []
    preview = tokenization.get("tokens_preview")
    if not isinstance(preview, list):
        return []
    return [_normalize_token(token) for token in preview][:64]


def _normalize_head_links(
    *,
    links: Any,
    tokens: list[str],
) -> list[dict[str, Any]]:
    if not isinstance(links, list):
        return []
    normalized: list[dict[str, Any]] = []
    for link in links:
        if not isinstance(link, dict):
            continue
        from_index = link.get("from_index")
        to_index = link.get("to_index")
        weight = _safe_float(link.get("weight"))
        if not isinstance(from_index, int) or not isinstance(to_index, int):
            continue
        if weight is None:
            continue
        from_token = tokens[from_index] if 0 <= from_index < len(tokens) else "?"
        to_token = tokens[to_index] if 0 <= to_index < len(tokens) else "?"
        normalized.append(
            {
                "from_index": from_index,
                "to_index": to_index,
                "from_token": from_token,
                "to_token": to_token,
                "weight": round(weight, 6),
            }
        )
    normalized.sort(key=lambda item: item["weight"], reverse=True)
    return normalized[:_ATTENTION_TOP_LINKS_PER_HEAD]


def _normalize_layers(
    *,
    probe: dict[str, Any],
    tokens: list[str],
) -> list[dict[str, Any]]:
    raw_layers = probe.get("layers")
    if not isinstance(raw_layers, list):
        return []
    normalized_layers: list[dict[str, Any]] = []
    for raw_layer in raw_layers:
        if not isinstance(raw_layer, dict):
            continue
        layer_id = raw_layer.get("layer")
        raw_heads = raw_layer.get("heads")
        if not isinstance(layer_id, int) or not isinstance(raw_heads, list):
            continue
        heads = _normalize_heads(raw_heads=raw_heads, tokens=tokens)
        if heads:
            heads.sort(key=lambda item: item["head"])
            normalized_layers.append({"layer": layer_id, "heads": heads})
    normalized_layers.sort(key=lambda item: item["layer"])
    return normalized_layers


def _normalize_heads(
    *, raw_heads: list[Any], tokens: list[str]
) -> list[dict[str, Any]]:
    heads: list[dict[str, Any]] = []
    for raw_head in raw_heads:
        if not isinstance(raw_head, dict):
            continue
        head_id = raw_head.get("head")
        if not isinstance(head_id, int):
            continue
        links = _normalize_head_links(links=raw_head.get("links"), tokens=tokens)
        if not links:
            continue
        heads.append({"head": head_id, "top_links": links})
    return heads


def _build_unavailable_attention_payload(
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
        "tokens": [],
        "layers": [],
        "diagnostics": diagnostics,
    }


async def build_attention_payload(
    *,
    prompt: str,
) -> dict[str, Any]:
    probe_payload = await run_model_introspection_probe(
        prompt=prompt,
        mode="attention",
        layer_selection=_ATTENTION_LAYER_SELECTION,
        head_selection=_ATTENTION_HEAD_SELECTION,
        top_k=_ATTENTION_TOP_K,
    )
    status = str(probe_payload.get("status") or "probe_unavailable")
    diagnostics_raw = probe_payload.get("diagnostics")
    diagnostics = diagnostics_raw if isinstance(diagnostics_raw, dict) else {}
    runtime_label = probe_payload.get("runtime_label")
    runtime_label_str = str(runtime_label) if runtime_label else None

    if status != "ok":
        return _build_unavailable_attention_payload(
            status=status,
            code=str(probe_payload.get("code") or "attention_unavailable"),
            message=str(probe_payload.get("message") or "Attention probe unavailable"),
            runtime_label=runtime_label_str,
            diagnostics=diagnostics,
        )

    probe = probe_payload.get("probe")
    if not isinstance(probe, dict):
        return _build_unavailable_attention_payload(
            status="failed",
            code="invalid_probe_shape",
            message="Probe payload has invalid shape",
            runtime_label=runtime_label_str,
            diagnostics=diagnostics,
        )

    tokens = _extract_tokens(probe)
    layers = _normalize_layers(probe=probe, tokens=tokens)
    if not layers:
        return _build_unavailable_attention_payload(
            status="probe_unavailable",
            code="attention_unavailable",
            message="Attention payload is unavailable for selected layers/heads",
            runtime_label=runtime_label_str,
            diagnostics=diagnostics,
        )

    return {
        "source": "probe_runtime",
        "status": "ok",
        "code": None,
        "message": "Attention payload ready",
        "runtime_label": runtime_label_str,
        "tokens": tokens,
        "layers": layers,
        "diagnostics": diagnostics,
    }
