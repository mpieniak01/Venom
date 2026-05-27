"""Tests for activation-path shaping in model introspection analysis."""

from __future__ import annotations

import pytest

from venom_core.services import (
    model_introspection_activation_path_service as activation_service,
)


def _architecture_graph() -> dict[str, object]:
    return {
        "nodes": [
            {"id": "input", "label": "Prompt input", "role": "input", "layer_index": 0},
            {
                "id": "layer_4",
                "label": "Layer 4 (full_attention)",
                "role": "layer",
                "layer_index": 4,
            },
        ]
    }


def _mlp_architecture_graph() -> dict[str, object]:
    return {
        "nodes": [
            {
                "id": "mlp",
                "label": "Response synthesis",
                "role": "mlp",
                "layer_index": 3,
            },
            {
                "id": "residual",
                "label": "Reuse path",
                "role": "residual",
                "layer_index": 4,
            },
        ]
    }


@pytest.mark.asyncio
async def test_build_activation_path_payload_normalizes_hidden_slices(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_probe(**_kwargs):
        return {
            "status": "ok",
            "runtime_label": "gemma-4-E2B-it · multi_runtime @ localhost:8014",
            "probe": {
                "layers": [
                    {"layer": 0, "hidden_slice": [0.12, -0.24, 0.31, -0.18]},
                    {"layer": 4, "hidden_slice": [0.18, -0.11, 0.44, -0.07]},
                ]
            },
        }

    monkeypatch.setattr(
        activation_service, "run_model_introspection_probe", _fake_probe
    )

    payload = await activation_service.build_activation_path_payload(
        prompt="Co to jest słońce?",
        architecture_graph=_architecture_graph(),
    )

    assert payload["status"] == "ok"
    assert payload["selected_layers"] == [0, 4]
    assert payload["layers"][0]["label"] == "Prompt input"
    assert payload["layers"][1]["role_hint"] == "layer"
    assert payload["transitions"][0]["from_layer"] == 0
    assert payload["transitions"][0]["to_layer"] == 4
    assert payload["summary"]["selected_layer_count"] == 2
    assert payload["summary"]["transition_count"] == 1
    assert payload["summary"]["focus_layer"] == 4


@pytest.mark.asyncio
async def test_build_activation_path_payload_returns_unavailable_on_probe_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_probe(**_kwargs):
        return {
            "status": "probe_unavailable",
            "code": "runtime_not_supported",
            "message": "Probe is available only for multi_runtime",
            "runtime_label": "gemma-4-E2B-it · ollama @ localhost:11434",
        }

    monkeypatch.setattr(
        activation_service, "run_model_introspection_probe", _fake_probe
    )

    payload = await activation_service.build_activation_path_payload(
        prompt="Co to jest słońce?",
        architecture_graph=None,
    )

    assert payload["status"] == "probe_unavailable"
    assert payload["code"] == "runtime_not_supported"
    assert payload["layers"] == []
    assert payload["transitions"] == []


@pytest.mark.asyncio
async def test_build_mlp_activation_payload_returns_unavailable_on_probe_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_probe(**_kwargs):
        return {
            "status": "probe_unavailable",
            "code": "runtime_not_supported",
            "message": "Probe is available only for multi_runtime",
            "runtime_label": "gemma-4-E2B-it · ollama @ localhost:11434",
        }

    monkeypatch.setattr(
        activation_service, "run_model_introspection_probe", _fake_probe
    )

    payload = await activation_service.build_mlp_activation_payload(
        prompt="Co to jest słońce?",
        architecture_graph=_mlp_architecture_graph(),
    )

    assert payload["status"] == "probe_unavailable"
    assert payload["code"] == "runtime_not_supported"
    assert payload["mlp_layer"] is None
    assert payload["residual_layer"] is None
    assert payload["transition"] is None
    assert payload["tensor_activation"] is None


@pytest.mark.asyncio
async def test_build_mlp_activation_payload_uses_mlp_and_residual_layers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_probe(**_kwargs):
        return {
            "status": "ok",
            "runtime_label": "gemma-4-E2B-it · multi_runtime @ localhost:8014",
            "probe": {
                "layers": [
                    {"layer": 3, "hidden_slice": [0.09, -0.15, 0.38, -0.04]},
                    {"layer": 4, "hidden_slice": [0.18, -0.11, 0.44, -0.07]},
                ]
            },
        }

    monkeypatch.setattr(
        activation_service, "run_model_introspection_probe", _fake_probe
    )

    payload = await activation_service.build_mlp_activation_payload(
        prompt="Co to jest słońce?",
        architecture_graph=_mlp_architecture_graph(),
    )

    assert payload["status"] == "ok"
    assert payload["selected_layers"] == [3, 4]
    assert payload["mlp_layer"]["label"] == "Response synthesis"
    assert payload["residual_layer"]["label"] == "Reuse path"
    assert payload["transition"]["from_layer"] == 3
    assert payload["transition"]["to_layer"] == 4
    assert payload["summary"]["focus_layer"] == 3
    assert payload["summary"]["residual_layer"] == 4
    assert payload["summary"]["hidden_dimension_count"] == 4
    assert payload["tensor_activation"]["status"] == "ok"
    assert payload["tensor_activation"]["vector_length"] == 4
    assert payload["tensor_activation"]["focus_layer"] == 3
    assert payload["tensor_activation"]["residual_layer"] == 4
