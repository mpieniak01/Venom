"""Attention payload shaping for model introspection analysis."""

from __future__ import annotations

from typing import Any

from venom_core.services.model_introspection_probe_service import (
    run_model_introspection_probe,
)

_ATTENTION_LAYER_SELECTION = [0, 8, 16, 24, 31]
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
        if not isinstance(layer_id, int):
            continue
        heads: list[dict[str, Any]] = []
        raw_heads = raw_layer.get("heads")
        if isinstance(raw_heads, list):
            heads = _normalize_heads(raw_heads=raw_heads, tokens=tokens)
        if not heads:
            heads = _normalize_attention_top_fallback(
                attention_top=raw_layer.get("attention_top"),
                tokens=tokens,
            )
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


def _normalize_attention_top_fallback(
    *,
    attention_top: Any,
    tokens: list[str],
) -> list[dict[str, Any]]:
    if not isinstance(attention_top, list):
        return []
    if not tokens:
        return []
    query_index = len(tokens) - 1
    query_token = tokens[query_index]
    links: list[dict[str, Any]] = []
    for item in attention_top:
        if not isinstance(item, dict):
            continue
        to_index = item.get("token_index")
        weight = _safe_float(item.get("score"))
        if not isinstance(to_index, int) or weight is None:
            continue
        to_token = tokens[to_index] if 0 <= to_index < len(tokens) else "?"
        links.append(
            {
                "from_index": query_index,
                "to_index": to_index,
                "from_token": query_token,
                "to_token": to_token,
                "weight": round(weight, 6),
            }
        )
    links.sort(key=lambda entry: entry["weight"], reverse=True)
    if not links:
        return []
    return [{"head": 0, "top_links": links[:_ATTENTION_TOP_LINKS_PER_HEAD]}]


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


def _build_native_attention_payload(
    *,
    runtime_label: str | None,
    diagnostics: dict[str, Any],
    tokens: list[str],
    layers: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "source": "probe_runtime",
        "status": "ok",
        "code": None,
        "message": "Attention payload ready",
        "runtime_label": runtime_label,
        "tokens": tokens,
        "layers": layers,
        "diagnostics": diagnostics,
    }


def _build_proxy_links_from_logits(
    *,
    logits_top: list[Any],
    query_index: int,
    query_token: str,
) -> list[dict[str, Any]]:
    top_links: list[dict[str, Any]] = []
    for item in logits_top[:_ATTENTION_TOP_LINKS_PER_HEAD]:
        if not isinstance(item, dict):
            continue
        score = _safe_float(item.get("score"))
        if score is None:
            continue
        top_links.append(
            {
                "from_index": query_index,
                "to_index": -1,
                "from_token": query_token,
                "to_token": _normalize_token(item.get("token")),
                "weight": round(score, 6),
            }
        )
    return top_links


def _build_proxy_layers_from_logits(
    *,
    raw_layers: list[Any],
    query_index: int,
    query_token: str,
) -> list[dict[str, Any]]:
    layers: list[dict[str, Any]] = []
    for raw_layer in raw_layers:
        if not isinstance(raw_layer, dict):
            continue
        layer_id = raw_layer.get("layer")
        if not isinstance(layer_id, int):
            continue
        logits_top = raw_layer.get("logits_top")
        if not isinstance(logits_top, list):
            continue
        top_links = _build_proxy_links_from_logits(
            logits_top=logits_top,
            query_index=query_index,
            query_token=query_token,
        )
        if top_links:
            layers.append(
                {"layer": layer_id, "heads": [{"head": 0, "top_links": top_links}]}
            )
    return layers


async def _build_attention_proxy_from_logits(
    *,
    prompt: str,
    runtime_label: str | None,
    diagnostics: dict[str, Any],
) -> dict[str, Any] | None:
    probe_payload = await run_model_introspection_probe(
        prompt=prompt,
        mode="logits",
        layer_selection=_ATTENTION_LAYER_SELECTION,
        top_k=_ATTENTION_TOP_K,
    )
    if str(probe_payload.get("status") or "probe_unavailable") != "ok":
        return None
    probe = probe_payload.get("probe")
    if not isinstance(probe, dict):
        return None
    tokens = _extract_tokens(probe)
    if not tokens:
        return None
    query_index = len(tokens) - 1
    query_token = tokens[query_index]
    raw_layers = probe.get("layers")
    if not isinstance(raw_layers, list):
        return None
    layers = _build_proxy_layers_from_logits(
        raw_layers=raw_layers,
        query_index=query_index,
        query_token=query_token,
    )
    if not layers:
        return None
    proxy_diagnostics = dict(diagnostics)
    proxy_diagnostics["proxy_from_mode"] = "logits"
    return {
        "source": "probe_runtime",
        "status": "ok",
        "code": "attention_proxy_logits",
        "message": "Attention payload approximated from logits probe",
        "runtime_label": runtime_label,
        "tokens": tokens,
        "layers": layers,
        "diagnostics": proxy_diagnostics,
    }


async def _retry_native_attention_payload(
    *,
    prompt: str,
    runtime_label: str | None,
    diagnostics: dict[str, Any],
) -> dict[str, Any] | None:
    probe_payload = await run_model_introspection_probe(
        prompt=prompt,
        mode="attention",
        layer_selection=[],
        top_k=_ATTENTION_TOP_K,
    )
    if str(probe_payload.get("status") or "probe_unavailable") != "ok":
        return None
    probe = probe_payload.get("probe")
    if not isinstance(probe, dict):
        return None
    tokens = _extract_tokens(probe)
    layers = _normalize_layers(probe=probe, tokens=tokens)
    if not layers:
        return None
    retry_diagnostics = dict(diagnostics)
    retry_diagnostics["native_retry"] = True
    retry_diagnostics["native_retry_layer_selection"] = []
    return _build_native_attention_payload(
        runtime_label=runtime_label,
        diagnostics=retry_diagnostics,
        tokens=tokens,
        layers=layers,
    )


async def _recover_attention_payload(
    *,
    prompt: str,
    runtime_label: str | None,
    diagnostics: dict[str, Any],
) -> dict[str, Any] | None:
    native_retry_payload = await _retry_native_attention_payload(
        prompt=prompt,
        runtime_label=runtime_label,
        diagnostics=diagnostics,
    )
    if native_retry_payload is not None:
        return native_retry_payload
    return await _build_attention_proxy_from_logits(
        prompt=prompt,
        runtime_label=runtime_label,
        diagnostics=diagnostics,
    )


async def build_attention_payload(
    *,
    prompt: str,
) -> dict[str, Any]:
    probe_payload = await run_model_introspection_probe(
        prompt=prompt,
        mode="attention",
        layer_selection=_ATTENTION_LAYER_SELECTION,
        top_k=_ATTENTION_TOP_K,
    )
    status = str(probe_payload.get("status") or "probe_unavailable")
    diagnostics_raw = probe_payload.get("diagnostics")
    diagnostics = diagnostics_raw if isinstance(diagnostics_raw, dict) else {}
    runtime_label = probe_payload.get("runtime_label")
    runtime_label_str = str(runtime_label) if runtime_label else None

    if status != "ok":
        recovered_payload = await _recover_attention_payload(
            prompt=prompt,
            runtime_label=runtime_label_str,
            diagnostics=diagnostics,
        )
        if recovered_payload is not None:
            return recovered_payload
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
        recovered_payload = await _recover_attention_payload(
            prompt=prompt,
            runtime_label=runtime_label_str,
            diagnostics=diagnostics,
        )
        if recovered_payload is not None:
            return recovered_payload
        return _build_unavailable_attention_payload(
            status="probe_unavailable",
            code="attention_unavailable",
            message="Attention payload is unavailable for selected layers/heads",
            runtime_label=runtime_label_str,
            diagnostics=diagnostics,
        )

    return _build_native_attention_payload(
        runtime_label=runtime_label_str,
        diagnostics=diagnostics,
        tokens=tokens,
        layers=layers,
    )
