"""Activation-path shaping for model introspection analysis payloads."""

from __future__ import annotations

import math
from typing import Any

from venom_core.services.model_introspection_probe_service import (
    run_model_introspection_probe,
)

_ACTIVATION_PATH_LAYER_SELECTION = [0, 4, 8, 12, 16, 20, 24, 31]
_ACTIVATION_PATH_TOP_DIMENSIONS = 4
_INVALID_PROBE_SHAPE_MESSAGE = "Probe payload has invalid shape"
_SLICE_EMPTY_LABEL = "slice empty"


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_slice(raw_slice: Any) -> list[float]:
    if not isinstance(raw_slice, list):
        return []
    values: list[float] = []
    for item in raw_slice:
        value = _safe_float(item)
        if value is None:
            continue
        values.append(round(value, 6))
    return values


def _coerce_layer_index(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _slice_mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 6)


def _slice_norm(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(math.sqrt(sum(value * value for value in values)), 6)


def _slice_max_abs(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(max(abs(value) for value in values), 6)


def _slice_top_dimensions(values: list[float]) -> list[dict[str, Any]]:
    indexed = [
        {
            "index": index,
            "value": round(value, 6),
            "abs_value": round(abs(value), 6),
        }
        for index, value in enumerate(values)
    ]
    indexed.sort(key=lambda item: item["abs_value"], reverse=True)
    return indexed[:_ACTIVATION_PATH_TOP_DIMENSIONS]


def _resolve_layer_label(
    layer_index: int, architecture_graph: dict[str, Any] | None
) -> str:
    if not isinstance(architecture_graph, dict):
        return f"Layer {layer_index}"
    nodes = architecture_graph.get("nodes")
    if not isinstance(nodes, list):
        return f"Layer {layer_index}"
    for node in nodes:
        if not isinstance(node, dict):
            continue
        if node.get("layer_index") == layer_index:
            label = str(node.get("label") or "").strip()
            if label:
                return label
    return f"Layer {layer_index}"


def _resolve_layer_role(
    layer_index: int, architecture_graph: dict[str, Any] | None
) -> str | None:
    if not isinstance(architecture_graph, dict):
        return None
    nodes = architecture_graph.get("nodes")
    if not isinstance(nodes, list):
        return None
    for node in nodes:
        if not isinstance(node, dict):
            continue
        if node.get("layer_index") == layer_index:
            role = str(node.get("role") or "").strip()
            return role or None
    return None


def _find_graph_node_by_role(
    architecture_graph: dict[str, Any] | None,
    role: str,
) -> dict[str, Any] | None:
    if not isinstance(architecture_graph, dict):
        return None
    nodes = architecture_graph.get("nodes")
    if not isinstance(nodes, list):
        return None
    for node in nodes:
        if not isinstance(node, dict):
            continue
        if str(node.get("role") or "").strip() == role:
            return node
    return None


def _build_unavailable_payload(
    *,
    status: str,
    code: str | None,
    message: str | None,
    runtime_label: str | None,
) -> dict[str, Any]:
    return {
        "source": "probe_unavailable",
        "status": status,
        "code": code,
        "message": message,
        "runtime_label": runtime_label,
        "selected_layers": [],
        "layers": [],
        "transitions": [],
        "summary": {
            "selected_layer_count": 0,
            "transition_count": 0,
            "focus_layer": None,
            "max_delta_norm": 0.0,
            "average_norm": 0.0,
        },
        "notes": [],
    }


def _build_mlp_unavailable_payload(
    *,
    status: str,
    code: str | None,
    message: str | None,
    runtime_label: str | None,
) -> dict[str, Any]:
    return {
        "source": "probe_unavailable",
        "status": status,
        "code": code,
        "message": message,
        "runtime_label": runtime_label,
        "selected_layers": [],
        "mlp_layer": None,
        "residual_layer": None,
        "transition": None,
        "tensor_activation": None,
        "summary": {
            "selected_layer_count": 0,
            "focus_layer": None,
            "residual_layer": None,
            "hidden_dimension_count": 0,
            "max_delta_norm": 0.0,
            "average_norm": 0.0,
            "transition_summary": None,
            "transition_impact": None,
        },
        "notes": [],
    }


def _build_tensor_activation_contract(
    *,
    mlp_layer: dict[str, Any],
    residual_layer: dict[str, Any] | None,
    transition: dict[str, Any] | None,
) -> dict[str, Any]:
    mlp_hidden_slice = _safe_slice(mlp_layer.get("hidden_slice"))
    residual_hidden_slice = (
        _safe_slice(residual_layer.get("hidden_slice"))
        if isinstance(residual_layer, dict)
        else []
    )
    delta_vector = (
        [
            round(current - previous, 6)
            for previous, current in zip(mlp_hidden_slice, residual_hidden_slice)
        ]
        if residual_hidden_slice
        else []
    )
    top_delta_dimensions = _slice_top_dimensions(delta_vector)
    mlp_norm = _slice_norm(mlp_hidden_slice)
    residual_norm = _slice_norm(residual_hidden_slice) if residual_hidden_slice else 0.0
    cosine_similarity = None
    if (
        mlp_hidden_slice
        and residual_hidden_slice
        and mlp_norm > 0.0
        and residual_norm > 0.0
    ):
        dot_product = sum(
            left * right for left, right in zip(mlp_hidden_slice, residual_hidden_slice)
        )
        cosine_similarity = round(dot_product / (mlp_norm * residual_norm), 6)

    return {
        "source": "probe_runtime.hidden.hidden_slice",
        "status": "ok",
        "slice_kind": "hidden_state_slice",
        "focus_layer": mlp_layer.get("layer"),
        "residual_layer": residual_layer.get("layer")
        if isinstance(residual_layer, dict)
        else None,
        "vector_length": len(mlp_hidden_slice),
        "mlp_vector": mlp_hidden_slice,
        "residual_vector": residual_hidden_slice if residual_hidden_slice else None,
        "delta_vector": delta_vector if delta_vector else None,
        "norms": {
            "mlp_l2": round(mlp_norm, 6),
            "residual_l2": round(residual_norm, 6) if residual_hidden_slice else None,
            "delta_l2": transition.get("delta_norm")
            if isinstance(transition, dict)
            else None,
            "cosine_similarity": cosine_similarity,
        },
        "top_delta_dimensions": top_delta_dimensions,
        "notes": [
            "Contract exposes hidden-state slice vectors for activation analysis.",
            "This payload is not a full tensor dump of the MLP block.",
        ],
    }


def _build_transition(
    *,
    previous_layer: dict[str, Any],
    current_layer: dict[str, Any],
) -> dict[str, Any]:
    previous_slice = list(previous_layer.get("hidden_slice") or [])
    current_slice = list(current_layer.get("hidden_slice") or [])
    max_length = min(len(previous_slice), len(current_slice))
    deltas = [
        round(current_slice[index] - previous_slice[index], 6)
        for index in range(max_length)
    ]
    delta_norm = _slice_norm(deltas)
    mean_shift = round(_slice_mean(current_slice) - _slice_mean(previous_slice), 6)
    max_abs_shift = _slice_max_abs(deltas)
    from_layer = int(previous_layer.get("layer") or 0)
    to_layer = int(current_layer.get("layer") or 0)
    summary = (
        f"Hidden-state delta norm {delta_norm:.3f}; mean shift {mean_shift:.3f}; "
        f"peak shift {max_abs_shift:.3f}."
    )
    impact = (
        "The activation path changes most strongly across this transition."
        if delta_norm >= 1.0
        else "The activation path remains relatively stable across this transition."
    )
    return {
        "from_layer": from_layer,
        "to_layer": to_layer,
        "before": str(previous_layer.get("label") or f"Layer {from_layer}"),
        "after": str(current_layer.get("label") or f"Layer {to_layer}"),
        "delta_norm": delta_norm,
        "mean_shift": mean_shift,
        "max_abs_shift": max_abs_shift,
        "summary": summary,
        "impact": impact,
        "evidence": [
            f"ΔL2 {delta_norm:.3f}",
            f"Δmean {mean_shift:.3f}",
            f"peak |Δ| {max_abs_shift:.3f}",
        ],
    }


def _build_probe_shape_error_payload(
    *,
    runtime_label: str | None,
) -> dict[str, Any]:
    return _build_unavailable_payload(
        status="failed",
        code="invalid_probe_shape",
        message=_INVALID_PROBE_SHAPE_MESSAGE,
        runtime_label=runtime_label,
    )


def _build_mlp_probe_shape_error_payload(
    *,
    runtime_label: str | None,
) -> dict[str, Any]:
    return _build_mlp_unavailable_payload(
        status="failed",
        code="invalid_probe_shape",
        message=_INVALID_PROBE_SHAPE_MESSAGE,
        runtime_label=runtime_label,
    )


def _build_hidden_slice_evidence(hidden_slice: list[float]) -> list[str]:
    return [
        f"slice[0]={hidden_slice[0]:.3f}" if hidden_slice else _SLICE_EMPTY_LABEL,
        f"slice len={len(hidden_slice)}",
    ]


def _build_layer_payload(
    *,
    layer_index: int,
    hidden_slice: list[float],
    architecture_graph: dict[str, Any] | None,
) -> dict[str, Any]:
    layer_label = _resolve_layer_label(layer_index, architecture_graph)
    layer_role = _resolve_layer_role(layer_index, architecture_graph)
    top_dimensions = _slice_top_dimensions(hidden_slice)
    mean_value = _slice_mean(hidden_slice)
    norm_value = _slice_norm(hidden_slice)
    max_abs_value = _slice_max_abs(hidden_slice)
    return {
        "layer": layer_index,
        "label": layer_label,
        "role_hint": layer_role,
        "hidden_slice": hidden_slice,
        "metrics": {
            "mean": mean_value,
            "norm": norm_value,
            "max_abs": max_abs_value,
            "top_dimensions": top_dimensions,
        },
        "summary": (
            f"norm {norm_value:.3f}; "
            f"mean {mean_value:.3f}; "
            f"top dims {', '.join(str(dim['index']) for dim in top_dimensions[:3]) or 'n/a'}"
        ),
        "evidence": _build_hidden_slice_evidence(hidden_slice),
    }


def _extract_hidden_layers(raw_layers: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_layers, list):
        return []
    layers: list[dict[str, Any]] = []
    for raw_layer in raw_layers:
        if not isinstance(raw_layer, dict):
            continue
        layer_index = raw_layer.get("layer")
        if not isinstance(layer_index, int):
            continue
        hidden_slice = _safe_slice(raw_layer.get("hidden_slice"))
        if not hidden_slice:
            continue
        layers.append({"layer": layer_index, "hidden_slice": hidden_slice})
    return layers


def _index_hidden_probe_layers(raw_layers: Any) -> dict[int, dict[str, Any]]:
    if not isinstance(raw_layers, list):
        return {}
    indexed: dict[int, dict[str, Any]] = {}
    for raw_layer in raw_layers:
        if not isinstance(raw_layer, dict):
            continue
        layer_index = raw_layer.get("layer")
        if not isinstance(layer_index, int):
            continue
        indexed[layer_index] = raw_layer
    return indexed


def _resolve_residual_layer_selection(
    *,
    architecture_graph: dict[str, Any] | None,
    mlp_layer_index: int,
) -> tuple[int | None, list[int]]:
    residual_node = _find_graph_node_by_role(architecture_graph, "residual")
    residual_layer_index = (
        _coerce_layer_index(residual_node.get("layer_index"))
        if residual_node is not None
        else None
    )
    selected_layers = [mlp_layer_index]
    if residual_layer_index is not None and residual_layer_index not in selected_layers:
        selected_layers.append(residual_layer_index)
    return residual_layer_index, selected_layers


def _build_mlp_layer_entry(
    *,
    layer_index: int,
    hidden_slice: list[float],
    architecture_graph: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    top_dimensions = _slice_top_dimensions(hidden_slice)
    metrics = {
        "mean": _slice_mean(hidden_slice),
        "norm": _slice_norm(hidden_slice),
        "max_abs": _slice_max_abs(hidden_slice),
        "top_dimensions": top_dimensions,
    }
    return (
        {
            "layer": layer_index,
            "label": _resolve_layer_label(layer_index, architecture_graph),
            "role_hint": _resolve_layer_role(layer_index, architecture_graph),
            "hidden_slice": hidden_slice,
            "metrics": metrics,
            "summary": (
                f"norm {metrics['norm']:.3f}; "
                f"mean {metrics['mean']:.3f}; "
                f"top dims {', '.join(str(dim['index']) for dim in top_dimensions[:3]) or 'n/a'}"
            ),
            "evidence": _build_hidden_slice_evidence(hidden_slice),
        },
        metrics,
    )


def _build_residual_layer_entry(
    *,
    layer_index: int | None,
    raw_layer: dict[str, Any] | None,
    architecture_graph: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if layer_index is None or not isinstance(raw_layer, dict):
        return None
    hidden_slice = _safe_slice(raw_layer.get("hidden_slice"))
    if not hidden_slice:
        return None
    top_dimensions = _slice_top_dimensions(hidden_slice)
    mean_value = _slice_mean(hidden_slice)
    norm_value = _slice_norm(hidden_slice)
    return {
        "layer": layer_index,
        "label": _resolve_layer_label(layer_index, architecture_graph),
        "role_hint": _resolve_layer_role(layer_index, architecture_graph),
        "hidden_slice": hidden_slice,
        "metrics": {
            "mean": mean_value,
            "norm": norm_value,
            "max_abs": _slice_max_abs(hidden_slice),
            "top_dimensions": top_dimensions,
        },
        "summary": (
            f"norm {norm_value:.3f}; "
            f"mean {mean_value:.3f}; "
            f"top dims {', '.join(str(dim['index']) for dim in top_dimensions[:3]) or 'n/a'}"
        ),
        "evidence": _build_hidden_slice_evidence(hidden_slice),
    }


def _build_mlp_notes(architecture_graph: dict[str, Any] | None) -> list[str]:
    notes = [
        "Source data comes from hidden.hidden_slice for the selected MLP layer.",
        "The residual bridge is sourced from the paired residual layer hidden slice.",
        "This is a probe slice, not a full tensor dump.",
    ]
    if architecture_graph is not None:
        notes.append(
            "Architecture labels are used as hints for the MLP and residual nodes."
        )
    return notes


async def build_activation_path_payload(
    *,
    prompt: str,
    architecture_graph: dict[str, Any] | None = None,
) -> dict[str, Any]:
    probe_payload = await run_model_introspection_probe(
        prompt=prompt,
        mode="hidden",
        layer_selection=_ACTIVATION_PATH_LAYER_SELECTION,
        top_k=8,
    )
    status = str(probe_payload.get("status") or "probe_unavailable")
    runtime_label = probe_payload.get("runtime_label")
    runtime_label_str = str(runtime_label) if runtime_label else None
    if status != "ok":
        return _build_unavailable_payload(
            status=status,
            code=str(probe_payload.get("code") or "probe_unavailable"),
            message=str(probe_payload.get("message") or "Probe unavailable"),
            runtime_label=runtime_label_str,
        )

    probe = probe_payload.get("probe")
    if not isinstance(probe, dict):
        return _build_probe_shape_error_payload(runtime_label=runtime_label_str)

    raw_layers = probe.get("layers")
    if not isinstance(raw_layers, list):
        return _build_probe_shape_error_payload(runtime_label=runtime_label_str)

    layers = [
        _build_layer_payload(
            layer_index=int(layer_data["layer"]),
            hidden_slice=list(layer_data["hidden_slice"]),
            architecture_graph=architecture_graph,
        )
        for layer_data in _extract_hidden_layers(raw_layers)
    ]

    transitions: list[dict[str, Any]] = []
    for previous_layer, current_layer in zip(layers, layers[1:]):
        transitions.append(
            _build_transition(
                previous_layer=previous_layer,
                current_layer=current_layer,
            )
        )

    max_delta_norm = max(
        (transition["delta_norm"] for transition in transitions),
        default=0.0,
    )
    average_norm = (
        round(sum(layer["metrics"]["norm"] for layer in layers) / len(layers), 6)
        if layers
        else 0.0
    )
    focus_layer = None
    if transitions:
        focus_transition = max(transitions, key=lambda item: item["delta_norm"])
        focus_layer = int(focus_transition["to_layer"])

    notes = [
        "Source data comes from hidden.hidden_slice for selected layers.",
        "This is a probe slice, not a full tensor dump.",
    ]
    if architecture_graph is not None:
        notes.append(
            "Architecture labels are used only as hints; hidden slices remain the source of truth."
        )

    return {
        "source": "probe_runtime",
        "status": "ok",
        "code": None,
        "message": "Activation path ready",
        "runtime_label": runtime_label_str,
        "selected_layers": [layer["layer"] for layer in layers],
        "layers": layers,
        "transitions": transitions,
        "summary": {
            "selected_layer_count": len(layers),
            "transition_count": len(transitions),
            "focus_layer": focus_layer,
            "max_delta_norm": round(max_delta_norm, 6),
            "average_norm": average_norm,
        },
        "notes": notes,
    }


async def build_mlp_activation_payload(
    *,
    prompt: str,
    architecture_graph: dict[str, Any] | None = None,
) -> dict[str, Any]:
    mlp_node = _find_graph_node_by_role(architecture_graph, "mlp")
    if mlp_node is None:
        return _build_mlp_unavailable_payload(
            status="probe_unavailable",
            code="mlp_activation_unavailable",
            message="MLP activation probe unavailable",
            runtime_label=None,
        )

    mlp_layer_index = _coerce_layer_index(mlp_node.get("layer_index"))
    if mlp_layer_index is None:
        return _build_mlp_unavailable_payload(
            status="failed",
            code="invalid_graph_shape",
            message="MLP graph node is missing a valid layer index",
            runtime_label=None,
        )

    residual_layer_index, selected_layers = _resolve_residual_layer_selection(
        architecture_graph=architecture_graph,
        mlp_layer_index=mlp_layer_index,
    )

    probe_payload = await run_model_introspection_probe(
        prompt=prompt,
        mode="hidden",
        layer_selection=selected_layers,
        top_k=8,
    )
    status = str(probe_payload.get("status") or "probe_unavailable")
    runtime_label = probe_payload.get("runtime_label")
    runtime_label_str = str(runtime_label) if runtime_label else None
    if status != "ok":
        return _build_mlp_unavailable_payload(
            status=status,
            code=str(probe_payload.get("code") or "probe_unavailable"),
            message=str(probe_payload.get("message") or "Probe unavailable"),
            runtime_label=runtime_label_str,
        )

    probe = probe_payload.get("probe")
    if not isinstance(probe, dict):
        return _build_mlp_probe_shape_error_payload(runtime_label=runtime_label_str)

    raw_layers = probe.get("layers")
    if not isinstance(raw_layers, list):
        return _build_mlp_probe_shape_error_payload(runtime_label=runtime_label_str)

    raw_layers_by_index = _index_hidden_probe_layers(raw_layers)

    mlp_layer_raw = raw_layers_by_index.get(mlp_layer_index)
    if not isinstance(mlp_layer_raw, dict):
        return _build_mlp_unavailable_payload(
            status="failed",
            code="mlp_layer_missing",
            message="MLP probe layer is missing from payload",
            runtime_label=runtime_label_str,
        )

    mlp_hidden_slice = _safe_slice(mlp_layer_raw.get("hidden_slice"))
    if not mlp_hidden_slice:
        return _build_mlp_unavailable_payload(
            status="failed",
            code="empty_hidden_slice",
            message="MLP probe layer returned an empty hidden slice",
            runtime_label=runtime_label_str,
        )

    mlp_entry, mlp_metrics = _build_mlp_layer_entry(
        layer_index=mlp_layer_index,
        hidden_slice=mlp_hidden_slice,
        architecture_graph=architecture_graph,
    )
    residual_entry = _build_residual_layer_entry(
        layer_index=residual_layer_index,
        raw_layer=(
            raw_layers_by_index.get(residual_layer_index)
            if residual_layer_index is not None
            else None
        ),
        architecture_graph=architecture_graph,
    )

    transition: dict[str, Any] | None = None
    if residual_entry is not None:
        transition = _build_transition(
            previous_layer=mlp_entry,
            current_layer=residual_entry,
        )

    notes = _build_mlp_notes(architecture_graph)

    max_delta_norm = transition["delta_norm"] if isinstance(transition, dict) else 0.0
    average_norm_inputs = [mlp_metrics["norm"]]
    if residual_entry is not None:
        average_norm_inputs.append(float(residual_entry["metrics"]["norm"]))
    average_norm = (
        round(sum(average_norm_inputs) / len(average_norm_inputs), 6)
        if average_norm_inputs
        else 0.0
    )
    transition_summary = (
        transition["summary"]
        if isinstance(transition, dict)
        else "No residual comparison captured for this MLP activation."
    )
    transition_impact = (
        transition["impact"]
        if isinstance(transition, dict)
        else "Residual comparison unavailable for this activation slice."
    )
    tensor_activation = _build_tensor_activation_contract(
        mlp_layer=mlp_entry,
        residual_layer=residual_entry,
        transition=transition,
    )
    return {
        "source": "probe_runtime",
        "status": "ok",
        "code": None,
        "message": "MLP activation ready",
        "runtime_label": runtime_label_str,
        "selected_layers": selected_layers,
        "mlp_layer": mlp_entry,
        "residual_layer": residual_entry,
        "transition": transition,
        "tensor_activation": tensor_activation,
        "summary": {
            "selected_layer_count": len(selected_layers),
            "focus_layer": mlp_layer_index,
            "residual_layer": residual_layer_index,
            "hidden_dimension_count": len(mlp_hidden_slice),
            "max_delta_norm": round(max_delta_norm, 6),
            "average_norm": average_norm,
            "transition_summary": transition_summary,
            "transition_impact": transition_impact,
        },
        "notes": notes,
    }
