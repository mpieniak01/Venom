"""Tests for model introspection attention payload shaping service."""

from __future__ import annotations

import pytest

from venom_core.services import model_introspection_attention_service as service


@pytest.mark.asyncio
async def test_build_attention_payload_returns_runtime_probe_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_probe(**_kwargs):
        return {
            "status": "ok",
            "runtime_label": "gemma · multi_runtime @ localhost:8014",
            "probe": {
                "tokenization": {"tokens_preview": ["▁Co", "to", "jest"]},
                "layers": [
                    {
                        "layer": 8,
                        "heads": [
                            {
                                "head": 3,
                                "links": [
                                    {"from_index": 0, "to_index": 2, "weight": 0.88},
                                    {"from_index": 1, "to_index": 2, "weight": 0.51},
                                ],
                            }
                        ],
                    }
                ],
            },
            "diagnostics": {"elapsed_ms": 12.4},
        }

    monkeypatch.setattr(service, "run_model_introspection_probe", _fake_probe)
    payload = await service.build_attention_payload(prompt="Co to jest slonce?")

    assert payload["status"] == "ok"
    assert payload["source"] == "probe_runtime"
    assert payload["tokens"] == ["Co", "to", "jest"]
    assert payload["layers"][0]["layer"] == 8
    assert payload["layers"][0]["heads"][0]["head"] == 3
    assert payload["layers"][0]["heads"][0]["top_links"][0]["weight"] == 0.88


@pytest.mark.asyncio
async def test_build_attention_payload_maps_unavailable_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_probe(**_kwargs):
        return {
            "status": "probe_unavailable",
            "code": "attention_unavailable",
            "message": "probe unavailable",
            "runtime_label": "runtime",
            "diagnostics": {},
        }

    monkeypatch.setattr(service, "run_model_introspection_probe", _fake_probe)
    payload = await service.build_attention_payload(prompt="q")

    assert payload["source"] == "probe_unavailable"
    assert payload["status"] == "probe_unavailable"
    assert payload["code"] == "attention_unavailable"
    assert payload["layers"] == []


@pytest.mark.asyncio
async def test_build_attention_payload_falls_back_to_logits_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_probe(**kwargs):
        if kwargs.get("mode") == "attention":
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
                "tokenization": {"tokens_preview": ["▁Co", "▁to", "▁jest"]},
                "layers": [
                    {
                        "layer": 8,
                        "logits_top": [
                            {"token": "▁gwiazda", "token_index": 1, "score": 2.1},
                            {"token": "▁planeta", "token_index": 2, "score": 1.9},
                        ],
                    }
                ],
            },
            "diagnostics": {"elapsed_ms": 12.0},
        }

    monkeypatch.setattr(service, "run_model_introspection_probe", _fake_probe)
    payload = await service.build_attention_payload(prompt="Co to jest slonce?")

    assert payload["status"] == "ok"
    assert payload["code"] == "attention_proxy_logits"
    assert payload["layers"][0]["heads"][0]["top_links"][0]["to_token"] == "gwiazda"


@pytest.mark.asyncio
async def test_build_attention_payload_supports_attention_top_runtime_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_probe(**_kwargs):
        return {
            "status": "ok",
            "runtime_label": "gemma · multi_runtime @ localhost:8014",
            "probe": {
                "tokenization": {"tokens_preview": ["▁Co", "to", "jest"]},
                "layers": [
                    {
                        "layer": 8,
                        "attention_top": [
                            {"token_index": 0, "token": "▁Co", "score": 0.7},
                            {"token_index": 1, "token": "to", "score": 0.5},
                        ],
                    }
                ],
            },
            "diagnostics": {"elapsed_ms": 9.4},
        }

    monkeypatch.setattr(service, "run_model_introspection_probe", _fake_probe)
    payload = await service.build_attention_payload(prompt="Co to jest slonce?")

    assert payload["status"] == "ok"
    assert payload["layers"][0]["heads"][0]["head"] == 0
    assert payload["layers"][0]["heads"][0]["top_links"][0]["from_token"] == "jest"
