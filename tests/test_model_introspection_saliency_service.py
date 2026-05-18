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


@pytest.mark.asyncio
async def test_build_saliency_payload_falls_back_to_attention_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_probe(**kwargs):
        if kwargs.get("mode") == "saliency":
            return {
                "status": "probe_unavailable",
                "code": "saliency_unavailable",
                "message": "saliency unavailable",
                "runtime_label": "runtime",
                "diagnostics": {},
            }
        return {
            "status": "ok",
            "runtime_label": "runtime",
            "probe": {
                "layers": [
                    {
                        "layer": 31,
                        "attention_top": [
                            {"token": "▁Słońce", "token_index": 0, "score": 0.85},
                            {"token": "▁to", "token_index": 1, "score": 0.41},
                        ],
                    }
                ]
            },
            "diagnostics": {"elapsed_ms": 21.0},
        }

    monkeypatch.setattr(service, "run_model_introspection_probe", _fake_probe)
    payload = await service.build_saliency_payload(
        prompt="q", response_text="Słońce to gwiazda."
    )

    assert payload["status"] == "ok"
    assert payload["code"] == "saliency_proxy_attention"
    assert payload["method"] == "attention_proxy"
    assert payload["token_weights"][0]["token"] == "Słońce"


@pytest.mark.asyncio
async def test_build_saliency_payload_falls_back_to_logits_proxy_when_attention_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_probe(**kwargs):
        mode = kwargs.get("mode")
        if mode == "saliency":
            return {
                "status": "probe_unavailable",
                "code": "saliency_unavailable",
                "message": "saliency unavailable",
                "runtime_label": "runtime",
                "diagnostics": {},
            }
        if mode == "attention":
            return {
                "status": "probe_unavailable",
                "code": "attention_unavailable",
                "message": "attention unavailable",
                "runtime_label": "runtime",
                "diagnostics": {},
            }
        return {
            "status": "ok",
            "runtime_label": "runtime",
            "probe": {
                "layers": [
                    {
                        "layer": 31,
                        "logits_top": [
                            {"token": "▁Słońce", "token_index": 0, "score": 0.85},
                            {"token": "▁to", "token_index": 1, "score": 0.41},
                        ],
                    }
                ]
            },
            "diagnostics": {"elapsed_ms": 13.0},
        }

    monkeypatch.setattr(service, "run_model_introspection_probe", _fake_probe)
    payload = await service.build_saliency_payload(
        prompt="q", response_text="Słońce to gwiazda."
    )

    assert payload["status"] == "ok"
    assert payload["code"] == "saliency_proxy_logits"
    assert payload["method"] == "logits_proxy"
    assert payload["token_weights"][0]["token"] == "Słońce"


@pytest.mark.asyncio
async def test_build_saliency_payload_returns_invalid_probe_shape_when_probe_is_not_dict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_probe(**_kwargs):
        return {
            "status": "ok",
            "runtime_label": "runtime",
            "probe": ["invalid-shape"],
            "diagnostics": {"elapsed_ms": 5.0},
        }

    monkeypatch.setattr(service, "run_model_introspection_probe", _fake_probe)
    payload = await service.build_saliency_payload(prompt="q", response_text="Słońce")

    assert payload["status"] == "failed"
    assert payload["code"] == "invalid_probe_shape"


@pytest.mark.asyncio
async def test_build_saliency_payload_returns_unavailable_when_token_weights_and_proxies_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_probe(**kwargs):
        mode = kwargs.get("mode")
        if mode == "saliency":
            return {
                "status": "ok",
                "runtime_label": "runtime",
                "probe": {"token_weights": []},
                "diagnostics": {"elapsed_ms": 5.0},
            }
        if mode == "attention":
            return {
                "status": "probe_unavailable",
                "code": "attention_unavailable",
                "probe": None,
                "diagnostics": {},
            }
        return {
            "status": "probe_unavailable",
            "code": "probe_unavailable",
            "probe": None,
            "diagnostics": {},
        }

    monkeypatch.setattr(service, "run_model_introspection_probe", _fake_probe)
    payload = await service.build_saliency_payload(prompt="q", response_text="Słońce")

    assert payload["status"] == "probe_unavailable"
    assert payload["code"] == "saliency_unavailable"


@pytest.mark.asyncio
async def test_build_saliency_payload_uses_requested_target_token_when_probe_missing_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_probe(**_kwargs):
        return {
            "status": "ok",
            "runtime_label": "runtime",
            "probe": {
                "method": "integrated_gradients",
                "target_output_token_index": -4,
                "token_weights": [
                    {"token": "▁Słońce", "token_index": 0, "weight": 0.9}
                ],
            },
            "diagnostics": {},
        }

    monkeypatch.setattr(service, "run_model_introspection_probe", _fake_probe)
    payload = await service.build_saliency_payload(
        prompt="q",
        response_text="Słońce to gwiazda",
    )

    assert payload["target_output_token_index"] == 0
    assert payload["target_output_token"] == "Słońce"
