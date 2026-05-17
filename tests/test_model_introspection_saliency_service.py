"""Tests for model introspection saliency payload shaping service."""

from __future__ import annotations

import pytest

from venom_core.services import model_introspection_saliency_service as service


@pytest.mark.asyncio
async def test_build_saliency_payload_returns_runtime_probe_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_probe(**_kwargs):
        return {
            "status": "ok",
            "runtime_label": "gemma · multi_runtime @ localhost:8014",
            "probe": {
                "method": "integrated_gradients",
                "target_output_token_index": 0,
                "target_output_token": "Słońce",
                "token_weights": [
                    {"token": "Słońce", "token_index": 2, "weight": 0.85},
                    {"token": "to", "token_index": 3, "weight": 0.41},
                ],
            },
            "diagnostics": {"elapsed_ms": 21.0},
        }

    monkeypatch.setattr(service, "run_model_introspection_probe", _fake_probe)
    payload = await service.build_saliency_payload(
        prompt="Co to jest slonce?",
        response_text="Slonce to gwiazda.",
    )

    assert payload["status"] == "ok"
    assert payload["source"] == "probe_runtime"
    assert payload["method"] == "integrated_gradients"
    assert payload["target_output_token"] == "Słońce"
    assert payload["token_weights"][0]["weight"] == 0.85


@pytest.mark.asyncio
async def test_build_saliency_payload_maps_unavailable_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_probe(**_kwargs):
        return {
            "status": "probe_unavailable",
            "code": "saliency_unavailable",
            "message": "probe unavailable",
            "runtime_label": "runtime",
            "diagnostics": {},
        }

    monkeypatch.setattr(service, "run_model_introspection_probe", _fake_probe)
    payload = await service.build_saliency_payload(prompt="q", response_text="")

    assert payload["source"] == "probe_unavailable"
    assert payload["status"] == "probe_unavailable"
    assert payload["code"] == "saliency_unavailable"
    assert payload["token_weights"] == []
