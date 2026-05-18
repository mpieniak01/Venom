"""Tests for model introspection logit-lens shaping service."""

from __future__ import annotations

import pytest

from venom_core.services import model_introspection_logit_lens_service as service


def _checkpoint(token: str, confidence: float) -> dict[str, object]:
    return {
        "id": "cp",
        "percent": 25,
        "layer": 4,
        "top_k": [{"token": token, "token_index": 1, "score": 1.0}],
        "top_token": token,
        "confidence": confidence,
        "changed": False,
    }


def test_logit_lens_helpers_invalid_inputs() -> None:
    assert service._safe_float("x") is None  # noqa: SLF001
    assert service._normalize_top_k("bad") == []  # noqa: SLF001
    assert service._normalize_layers("bad") == []  # noqa: SLF001
    assert service._extract_token_preview({}) == []  # noqa: SLF001
    assert service._extract_raw_token_preview({}) == []  # noqa: SLF001


def test_select_layer_by_percent_empty_layers() -> None:
    selected = service._select_layer_by_percent([], 25)  # noqa: SLF001
    assert selected["layer"] == -1
    assert selected["top_k"] == []


@pytest.mark.asyncio
async def test_build_logit_lens_payload_maps_probe_logits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_probe(**_kwargs):
        return {
            "status": "ok",
            "runtime_label": "gemma · multi_runtime @ localhost:8014",
            "probe": {
                "mode": "logits",
                "tokenization": {
                    "tokens_preview": ["▁Co", "▁to", "▁jest", "▁słońce", "?"],
                },
                "layers": [
                    {
                        "layer": 4,
                        "logits_top": [
                            {"token": "▁planeta", "token_index": 101, "score": 1.1},
                            {"token": "▁gwiazda", "token_index": 202, "score": 1.0},
                        ],
                    },
                    {
                        "layer": 20,
                        "logits_top": [
                            {"token": "▁gwiazda", "token_index": 202, "score": 2.1},
                            {"token": "▁planeta", "token_index": 101, "score": 1.5},
                        ],
                    },
                ],
            },
            "diagnostics": {"elapsed_ms": 11.4},
        }

    monkeypatch.setattr(service, "run_model_introspection_probe", _fake_probe)

    payload = await service.build_logit_lens_payload(
        prompt="Co to jest słońce?",
        response_text="Słońce to gwiazda.",
    )

    assert payload["source"] == "probe_runtime"
    assert payload["status"] == "ok"
    assert payload["input_tokens"][:2] == ["Co", "to"]
    assert payload["raw_input_tokens"][:2] == ["▁Co", "▁to"]
    assert payload["output_tokens"][:2] == ["Słońce", "to"]
    assert payload["raw_output_tokens"] == []
    assert len(payload["checkpoints"]) == 4
    assert payload["checkpoints"][0]["top_token"] in {"planeta", "gwiazda"}
    assert payload["checkpoints"][0]["top_k"][0]["raw_token"] in {
        "▁planeta",
        "▁gwiazda",
    }
    assert payload["signals"]["late_stabilized"] is True
    assert "interpretability" in payload
    assert "token_noise_ratio" in payload["interpretability"]
    assert "elapsed_ms" in payload["diagnostics"]
    assert payload["diagnostics"]["heuristic_version"] == "v1.1"
    assert "heuristic_calibration" in payload["diagnostics"]


@pytest.mark.asyncio
async def test_build_logit_lens_payload_returns_unavailable_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_probe(**_kwargs):
        return {
            "status": "probe_unavailable",
            "code": "probe_disabled",
            "message": "Probe disabled",
            "runtime_label": "gemma · multi_runtime @ localhost:8014",
            "diagnostics": {"elapsed_ms": 2.2},
            "probe": None,
        }

    monkeypatch.setattr(service, "run_model_introspection_probe", _fake_probe)

    payload = await service.build_logit_lens_payload(
        prompt="Co to jest słońce?",
        response_text="Słońce to gwiazda.",
    )

    assert payload["source"] == "probe_unavailable"
    assert payload["status"] == "probe_unavailable"
    assert payload["checkpoints"] == []
    assert payload["raw_input_tokens"] == []
    assert payload["raw_output_tokens"] == []
    assert payload["signals"]["early_unstable"] is False
    assert payload["interpretability"]["interpretable"] is False
    assert payload["diagnostics"]["heuristic_version"] == "v1.1"


@pytest.mark.asyncio
async def test_build_logit_lens_payload_returns_invalid_probe_shape_when_probe_is_not_dict(
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
    payload = await service.build_logit_lens_payload(prompt="q", response_text="x")

    assert payload["status"] == "failed"
    assert payload["code"] == "invalid_probe_shape"


def test_build_logit_lens_signals_defaults_with_missing_confidence() -> None:
    signals = service._build_logit_lens_signals(  # noqa: SLF001
        [
            {"top_token": "A", "confidence": None},
            {"top_token": "B"},
        ]
    )
    assert signals["early_unstable"] is True
    assert signals["late_stabilized"] is False
    assert signals["low_confidence_path"] is True


@pytest.mark.parametrize(
    ("checkpoints", "expected_band", "expected_interpretable", "expected_noise"),
    [
        (
            [_checkpoint("gwiazda", 0.85), _checkpoint("słońce", 0.81)],
            "high",
            True,
            0.0,
        ),
        ([_checkpoint("gwiazda", 0.51), _checkpoint("?", 0.49)], "medium", True, 0.5),
        ([_checkpoint("###", 0.52), _checkpoint("؟؟", 0.48)], "medium", False, 1.0),
        (
            [_checkpoint("gwiazda", 0.25), _checkpoint("planeta", 0.22)],
            "low",
            False,
            0.0,
        ),
        (
            [_checkpoint("?", 0.2), _checkpoint("token", 0.2), _checkpoint("###", 0.2)],
            "low",
            False,
            0.6667,
        ),
    ],
)
def test_interpretability_calibration_matrix(
    checkpoints: list[dict[str, object]],
    expected_band: str,
    expected_interpretable: bool,
    expected_noise: float,
) -> None:
    interpretability = service._build_interpretability(checkpoints)
    assert interpretability["confidence_band"] == expected_band
    assert interpretability["interpretable"] is expected_interpretable
    assert interpretability["heuristic_version"] == "v1.1"
    assert (
        pytest.approx(interpretability["token_noise_ratio"], abs=0.0002)
        == expected_noise
    )
