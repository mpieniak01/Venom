"""Tests for model introspection attention payload shaping service."""

from __future__ import annotations

import pytest

from venom_core.services import model_introspection_attention_service as service


def test_attention_helpers_handle_invalid_shapes() -> None:
    assert service._safe_float("x") is None  # noqa: SLF001
    assert service._extract_tokens({}) == []  # noqa: SLF001
    assert service._extract_tokens({"tokenization": {"tokens_preview": "bad"}}) == []  # noqa: SLF001


def test_normalize_head_links_maps_unknown_indexes_to_question_mark() -> None:
    links = service._normalize_head_links(  # noqa: SLF001
        links=[
            {"from_index": 99, "to_index": 1, "weight": "0.4"},
            {"from_index": 0, "to_index": 88, "weight": 0.5},
            {"from_index": "bad", "to_index": 1, "weight": 0.9},
        ],
        tokens=["A", "B"],
    )
    assert len(links) == 2
    assert links[0]["to_token"] == "?"
    assert links[1]["from_token"] == "?"


def test_normalize_layers_returns_empty_for_invalid_layers() -> None:
    assert service._normalize_layers(probe={"layers": "bad"}, tokens=["A"]) == []  # noqa: SLF001
    assert (
        service._normalize_layers(  # noqa: SLF001
            probe={"layers": [{"layer": "x"}, {"layer": 1, "heads": []}]},
            tokens=[],
        )
        == []
    )


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


@pytest.mark.asyncio
async def test_build_attention_payload_returns_invalid_probe_shape_when_probe_is_not_dict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_probe(**_kwargs):
        return {
            "status": "ok",
            "runtime_label": "runtime",
            "probe": "invalid",
            "diagnostics": {},
        }

    monkeypatch.setattr(service, "run_model_introspection_probe", _fake_probe)
    payload = await service.build_attention_payload(prompt="q")

    assert payload["status"] == "failed"
    assert payload["code"] == "invalid_probe_shape"


@pytest.mark.asyncio
async def test_build_attention_payload_returns_unavailable_when_layers_and_proxy_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_probe(**kwargs):
        mode = kwargs.get("mode")
        if mode == "attention":
            return {
                "status": "ok",
                "runtime_label": "runtime",
                "probe": {"tokenization": {"tokens_preview": ["▁Co"]}, "layers": []},
                "diagnostics": {},
            }
        return {
            "status": "probe_unavailable",
            "code": "probe_unavailable",
            "probe": None,
            "diagnostics": {},
        }

    monkeypatch.setattr(service, "run_model_introspection_probe", _fake_probe)
    payload = await service.build_attention_payload(prompt="q")

    assert payload["status"] == "probe_unavailable"
    assert payload["code"] == "attention_unavailable"


@pytest.mark.asyncio
async def test_build_attention_payload_recovers_native_with_relaxed_layers_before_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, list[int]]] = []

    async def _fake_probe(**kwargs):
        mode = kwargs.get("mode")
        layers = kwargs.get("layer_selection")
        calls.append((str(mode), list(layers or [])))
        if mode == "attention" and layers:
            return {
                "status": "probe_unavailable",
                "code": "attention_unavailable",
                "message": "strict layers unavailable",
                "runtime_label": "runtime",
                "diagnostics": {},
            }
        if mode == "attention" and not layers:
            return {
                "status": "ok",
                "runtime_label": "runtime",
                "probe": {
                    "tokenization": {"tokens_preview": ["▁Co", "▁to", "▁jest"]},
                    "layers": [
                        {
                            "layer": 1,
                            "heads": [
                                {
                                    "head": 0,
                                    "links": [
                                        {"from_index": 2, "to_index": 0, "weight": 0.7}
                                    ],
                                }
                            ],
                        }
                    ],
                },
                "diagnostics": {"elapsed_ms": 9.0},
            }
        raise AssertionError(f"unexpected probe call: {kwargs}")

    monkeypatch.setattr(service, "run_model_introspection_probe", _fake_probe)
    payload = await service.build_attention_payload(prompt="Co to jest slonce?")

    assert payload["status"] == "ok"
    assert payload["code"] is None
    assert payload["layers"]
    assert payload["diagnostics"]["native_retry"] is True
    assert ("attention", []) in calls


@pytest.mark.asyncio
async def test_attention_proxy_from_logits_returns_none_for_invalid_shapes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_probe(**_kwargs):
        return {
            "status": "ok",
            "runtime_label": "runtime",
            "probe": {"tokenization": {"tokens_preview": []}, "layers": "bad"},
            "diagnostics": {},
        }

    monkeypatch.setattr(service, "run_model_introspection_probe", _fake_probe)
    payload = await service._build_attention_proxy_from_logits(  # noqa: SLF001
        prompt="q",
        runtime_label="runtime",
        diagnostics={},
    )
    assert payload is None
