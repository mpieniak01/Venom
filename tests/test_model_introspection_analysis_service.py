"""Tests for optional model introspection analysis service."""

from __future__ import annotations

import json
import types

import pytest

from venom_core.api.schemas.llm_simple import SimpleChatRequest
from venom_core.services import llm_simple_service
from venom_core.services import model_introspection_analysis_service as analysis_service


class _FakeStreamingResponse:
    def __init__(
        self, chunks: list[str], headers: dict[str, str] | None = None
    ) -> None:
        self.body_iterator = self._iter(chunks)
        self.headers = headers or {}

    async def _iter(self, chunks: list[str]):
        for chunk in chunks:
            yield chunk


async def _async_return(value):
    return value


def _build_snapshot() -> dict[str, object]:
    return {
        "runtime": {
            "provider": "multi_runtime",
            "model": "google/gemma-4-E2B-it",
            "endpoint": "http://localhost:8014/v1",
            "service_type": "local",
            "mode": "LOCAL",
            "label": "gemma-4-E2B-it · multi_runtime @ localhost:8014",
            "config_hash": "abc123",
            "runtime_id": "multi_runtime@http://localhost:8014/v1",
        },
        "runtime_drift": {"issues": []},
        "packages": {},
        "available_packages": [],
        "missing_packages": [],
        "model_manager": {"available": False, "usage_metrics": None, "error": None},
        "probe": {
            "enabled": True,
            "status": "ready",
            "healthy": True,
            "runtime_supported": True,
            "endpoint_configured": True,
            "profile": "dev",
            "limits": {
                "timeout_seconds": 20.0,
                "max_attempts": 2,
                "max_top_k": 32,
                "max_layer_count": 8,
                "max_head_count": 32,
                "max_prompt_tokens": 1024,
            },
        },
        "reuse": {
            "brain": {"path": "/brain", "available": True, "purpose": "rag"},
            "diagnostics": [],
        },
        "summary": {
            "active_model": "google/gemma-4-E2B-it",
            "provider": "multi_runtime",
            "runtime_label": "gemma-4-E2B-it · multi_runtime @ localhost:8014",
            "introspection_ready": True,
        },
        "architecture_graph": {
            "nodes": [
                {
                    "id": "input",
                    "label": "Prompt input",
                    "kind": "input",
                    "status": "ready",
                    "layer_index": 0,
                    "role": "input",
                },
                {
                    "id": "layer",
                    "label": "Layer 1",
                    "kind": "layer",
                    "status": "ready",
                    "layer_index": 1,
                    "role": "layer",
                },
                {
                    "id": "attention",
                    "label": "Attention probe",
                    "kind": "attention",
                    "status": "ready",
                    "layer_index": 2,
                    "role": "attention",
                },
                {
                    "id": "mlp",
                    "label": "Response synthesis",
                    "kind": "mlp",
                    "status": "ready",
                    "layer_index": 3,
                    "role": "mlp",
                },
                {
                    "id": "residual",
                    "label": "Reuse path",
                    "kind": "residual",
                    "status": "ready",
                    "layer_index": 3,
                    "role": "residual",
                },
                {
                    "id": "output",
                    "label": "Answer output",
                    "kind": "output",
                    "status": "ready",
                    "layer_index": 4,
                    "role": "output",
                },
            ],
            "edges": [
                {
                    "from": "input",
                    "to": "layer",
                    "label": "enter model",
                    "direction": "forward",
                },
                {
                    "from": "layer",
                    "to": "attention",
                    "label": "probe path",
                    "direction": "forward",
                },
                {
                    "from": "layer",
                    "to": "mlp",
                    "label": "synthesis path",
                    "direction": "forward",
                },
                {
                    "from": "attention",
                    "to": "residual",
                    "label": "merge",
                    "direction": "forward",
                },
                {
                    "from": "mlp",
                    "to": "residual",
                    "label": "merge",
                    "direction": "forward",
                },
                {
                    "from": "residual",
                    "to": "output",
                    "label": "decode",
                    "direction": "forward",
                },
            ],
            "summary": {
                "nodes": 6,
                "edges": 6,
                "layer_count": 4,
                "block_count": 2,
            },
            "meta": {
                "runtime": "gemma-4-E2B-it · multi_runtime @ localhost:8014",
                "model": "google/gemma-4-E2B-it",
                "provider": "multi_runtime",
                "generated_at": "2026-05-27T10:00:00Z",
                "fidelity": "native",
                "source": "native hf cache config",
            },
        },
    }


def _build_logit_lens_stub() -> dict[str, object]:
    return {
        "status": "ok",
        "code": None,
        "message": "Logit lens ready",
        "runtime_label": "gemma-4-E2B-it · multi_runtime @ localhost:8014",
        "input_tokens": ["Co", "to", "jest", "słońce", "?"],
        "output_tokens": ["Słońce", "to", "gwiazda"],
        "checkpoints": [
            {
                "id": "cp_25",
                "percent": 25,
                "layer": 8,
                "top_k": [{"token": "planeta", "token_index": 1, "score": 1.0}],
                "top_token": "planeta",
                "confidence": 0.31,
                "changed": False,
            },
            {
                "id": "cp_100",
                "percent": 100,
                "layer": 31,
                "top_k": [{"token": "gwiazda", "token_index": 2, "score": 2.2}],
                "top_token": "gwiazda",
                "confidence": 0.71,
                "changed": True,
            },
        ],
        "signals": {
            "early_unstable": True,
            "late_stabilized": True,
            "low_confidence_path": False,
        },
        "interpretability": {
            "interpretable": True,
            "confidence_band": "medium",
            "token_noise_ratio": 0.2,
            "readable_top_tokens": 4,
            "total_top_tokens": 5,
        },
        "diagnostics": {"elapsed_ms": 17.4},
    }


def _build_attention_stub() -> dict[str, object]:
    return {
        "source": "probe_runtime",
        "status": "ok",
        "code": None,
        "message": "Attention payload ready",
        "runtime_label": "gemma-4-E2B-it · multi_runtime @ localhost:8014",
        "tokens": ["Co", "to", "jest", "słońce", "?"],
        "layers": [
            {
                "layer": 4,
                "heads": [
                    {
                        "head": 0,
                        "top_links": [
                            {
                                "from_index": 0,
                                "to_index": 3,
                                "from_token": "Co",
                                "to_token": "Słońce",
                                "weight": 0.812,
                            }
                        ],
                    }
                ],
            }
        ],
        "diagnostics": {"elapsed_ms": 8.1},
    }


def _build_hidden_state_stub() -> dict[str, object]:
    return {
        "source": "probe_runtime",
        "status": "ok",
        "code": None,
        "message": "Activation path ready",
        "runtime_label": "gemma-4-E2B-it · multi_runtime @ localhost:8014",
        "selected_layers": [0, 4],
        "layers": [
            {
                "layer": 0,
                "label": "Prompt input",
                "role_hint": "input",
                "hidden_slice": [0.12, -0.24, 0.31, -0.18],
                "metrics": {
                    "mean": 0.0025,
                    "norm": 0.4235,
                    "max_abs": 0.31,
                    "top_dimensions": [
                        {"index": 2, "value": 0.31, "abs_value": 0.31},
                        {"index": 1, "value": -0.24, "abs_value": 0.24},
                    ],
                },
                "summary": "norm 0.424; mean 0.003; top dims 2, 1",
                "evidence": ["slice[0]=0.120", "slice len=4"],
            },
            {
                "layer": 4,
                "label": "Layer 4",
                "role_hint": "layer",
                "hidden_slice": [0.18, -0.11, 0.44, -0.07],
                "metrics": {
                    "mean": 0.11,
                    "norm": 0.495923,
                    "max_abs": 0.44,
                    "top_dimensions": [
                        {"index": 2, "value": 0.44, "abs_value": 0.44},
                        {"index": 0, "value": 0.18, "abs_value": 0.18},
                    ],
                },
                "summary": "norm 0.496; mean 0.110; top dims 2, 0",
                "evidence": ["slice[0]=0.180", "slice len=4"],
            },
        ],
        "transitions": [
            {
                "from_layer": 0,
                "to_layer": 4,
                "before": "Prompt input",
                "after": "Layer 4",
                "delta_norm": 0.271664,
                "mean_shift": 0.1075,
                "max_abs_shift": 0.13,
                "summary": "Hidden-state delta norm 0.272; mean shift 0.108; peak shift 0.130.",
                "impact": "The activation path changes most strongly across this transition.",
                "evidence": ["ΔL2 0.272", "Δmean 0.108", "peak |Δ| 0.130"],
            }
        ],
        "summary": {
            "selected_layer_count": 2,
            "transition_count": 1,
            "focus_layer": 4,
            "max_delta_norm": 0.271664,
            "average_norm": 0.459712,
        },
        "notes": [
            "Source data comes from hidden.hidden_slice for selected layers.",
            "This is a probe slice, not a full tensor dump.",
        ],
    }


def _build_mlp_activation_stub() -> dict[str, object]:
    return {
        "source": "probe_runtime",
        "status": "ok",
        "code": None,
        "message": "MLP activation ready",
        "runtime_label": "gemma-4-E2B-it · multi_runtime @ localhost:8014",
        "selected_layers": [3],
        "mlp_layer": {
            "layer": 3,
            "label": "Response synthesis",
            "role_hint": "mlp",
            "hidden_slice": [0.09, -0.15, 0.38, -0.04],
            "metrics": {
                "mean": 0.07,
                "norm": 0.416533,
                "max_abs": 0.38,
                "top_dimensions": [
                    {"index": 2, "value": 0.38, "abs_value": 0.38},
                    {"index": 1, "value": -0.15, "abs_value": 0.15},
                ],
            },
            "summary": "norm 0.417; mean 0.070; top dims 2, 1",
            "evidence": ["slice[0]=0.090", "slice len=4"],
        },
        "residual_layer": None,
        "transition": None,
        "tensor_activation": {
            "source": "probe_runtime.hidden.hidden_slice",
            "status": "ok",
            "slice_kind": "hidden_state_slice",
            "focus_layer": 3,
            "residual_layer": None,
            "vector_length": 4,
            "mlp_vector": [0.09, -0.15, 0.38, -0.04],
            "residual_vector": None,
            "delta_vector": None,
            "norms": {
                "mlp_l2": 0.416533,
                "residual_l2": None,
                "delta_l2": None,
                "cosine_similarity": None,
            },
            "top_delta_dimensions": [],
            "notes": [
                "Contract exposes hidden-state slice vectors for activation analysis.",
                "This payload is not a full tensor dump of the MLP block.",
            ],
        },
        "summary": {
            "selected_layer_count": 1,
            "focus_layer": 3,
            "residual_layer": None,
            "hidden_dimension_count": 4,
            "max_delta_norm": 0.0,
            "average_norm": 0.416533,
            "transition_summary": None,
            "transition_impact": None,
        },
        "notes": [
            "Source data comes from hidden.hidden_slice for the selected MLP layer.",
            "This is a probe slice, not a full tensor dump.",
        ],
    }


def _build_saliency_stub() -> dict[str, object]:
    return {
        "source": "probe_runtime",
        "status": "ok",
        "code": None,
        "message": "Saliency payload ready",
        "runtime_label": "gemma-4-E2B-it · multi_runtime @ localhost:8014",
        "method": "logits_proxy",
        "target_output_token_index": 0,
        "target_output_token": "Słońce",
        "token_weights": [
            {"token": "Słońce", "token_index": 0, "weight": 0.91},
            {"token": "gwiazda", "token_index": 1, "weight": 0.42},
            {"token": "to", "token_index": 2, "weight": 0.21},
        ],
        "diagnostics": {"elapsed_ms": 6.7},
    }


@pytest.mark.asyncio
async def test_analysis_skipped_when_live_mode_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_snapshot(**kwargs):
        return _build_snapshot()

    monkeypatch.setattr(
        analysis_service,
        "build_model_introspection_snapshot",
        fake_snapshot,
    )

    result = await analysis_service.analyze_model_with_optional_live_run(
        prompt="Co to jest slonce?",
        live_analysis_enabled=False,
    )

    assert result["status"] == "skipped"
    assert result["skipped_reason"] == "live_analysis_disabled"
    timeline = result["analysis"]["timeline"]
    assert timeline[0]["id"] == "snapshot_before"
    assert timeline[0]["status"] == "done"
    assert timeline[2]["id"] == "stream_opened"
    assert timeline[2]["label"] == "Stream opened"
    assert timeline[2]["status"] == "skipped"
    assert timeline[2]["reason_code"] == "live_analysis_disabled"


@pytest.mark.asyncio
async def test_analysis_collects_streamed_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = _build_snapshot()

    async def fake_snapshot(**kwargs):
        return snapshot

    async def fake_stream_simple_chat(request):
        assert request.content == "Co to jest slonce?"
        return _FakeStreamingResponse(
            [
                "event: start\ndata: {}\n\n",
                'event: content\ndata: {"text":"Slonce to gwiazda."}\n\n',
                "event: done\ndata: {}\n\n",
            ]
        )

    monkeypatch.setattr(
        analysis_service,
        "build_model_introspection_snapshot",
        fake_snapshot,
    )
    monkeypatch.setattr(analysis_service, "stream_simple_chat", fake_stream_simple_chat)
    monkeypatch.setattr(
        analysis_service,
        "_collect_logit_lens_payload_safe",
        lambda **_kwargs: _async_return(_build_logit_lens_stub()),
    )
    monkeypatch.setattr(
        analysis_service,
        "_collect_attention_payload_safe",
        lambda **_kwargs: _async_return(_build_attention_stub()),
    )
    monkeypatch.setattr(
        analysis_service,
        "_collect_activation_path_payload_safe",
        lambda **_kwargs: _async_return(_build_hidden_state_stub()),
    )
    monkeypatch.setattr(
        analysis_service,
        "_collect_mlp_activation_payload_safe",
        lambda **_kwargs: _async_return(_build_mlp_activation_stub()),
    )
    monkeypatch.setattr(
        analysis_service,
        "_collect_saliency_payload_safe",
        lambda **_kwargs: _async_return(_build_saliency_stub()),
    )

    result = await analysis_service.analyze_model_with_optional_live_run(
        prompt="Co to jest slonce?",
        live_analysis_enabled=True,
    )

    assert result["status"] == "completed"
    assert result["analysis"]["response"] == "Slonce to gwiazda."
    assert result["analysis"]["chunk_count"] == 1
    assert result["analysis"]["provider"] == "multi_runtime"
    assert result["analysis"]["events"] == ["start", "content", "done"]
    assert result["analysis"]["timeline_step_count"] == 9
    assert result["analysis"]["timeline"][0]["label"] == "Snapshot captured"
    timeline_labels = [step["label"] for step in result["analysis"]["timeline"]]
    assert "Logit lens probe" in timeline_labels
    assert "Attention probe" in timeline_labels
    assert "Saliency probe" in timeline_labels
    assert timeline_labels[-1] == "Snapshot refreshed"
    assert result["analysis"]["logit_lens"]["status"] == "ok"
    assert result["analysis"]["rag_focus"]["source"] == "graph_fallback"
    assert "answer_evidence_links" in result["analysis"]["rag_focus"]
    assert result["analysis"]["input_profile"]["prompt_tokens_est"] >= 1
    assert "system_tokens_est" in result["analysis"]["input_profile"]
    assert result["analysis"]["generation_profile"]["max_tokens"] == 128
    assert result["analysis"]["generation_profile"]["top_p"] is None
    assert result["analysis"]["generation_profile"]["top_p_status"] == "unavailable"
    assert result["analysis"]["stream_profile"]["chunk_count"] == 1
    assert "time_to_first_byte_ms" in result["analysis"]["stream_profile"]
    assert (
        result["analysis"]["stream_profile"]["time_to_first_byte_source"]
        == "estimated_stream_open"
    )
    assert "chunk_interval_p50_ms" in result["analysis"]["stream_profile"]
    assert "chunk_interval_p95_ms" in result["analysis"]["stream_profile"]
    assert result["analysis"]["evidence_coverage"]["fragments_total"] >= 1
    assert result["analysis"]["operator_conclusion"]["verdict"] in {
        "grounded",
        "weakly_grounded",
        "ungrounded",
    }
    assert result["analysis"]["operator_conclusion"]["reason_codes"]
    assert "rag_profile" in result["analysis"]
    assert "logit_profile" in result["analysis"]
    assert "analysis_capabilities" in result["analysis"]
    assert result["analysis"]["analysis_capabilities"]["total_count"] == 4
    assert result["analysis"]["analysis_capabilities"]["probe_profile"] == "dev"
    assert result["analysis"]["analysis_capabilities"]["limits"]["max_head_count"] == 32
    assert (
        result["analysis"]["analysis_capabilities"]["hidden_state"]["available"] is True
    )
    assert result["analysis"]["introspection_level"] in {"full", "lite", "none"}
    assert "run_trends" in result["analysis"]


@pytest.mark.asyncio
async def test_analysis_includes_request_trace_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = _build_snapshot()
    trace_id = "8fd5af48-7d34-4f69-90e2-3e6b2c2a1c11"

    class _FakeTrace:
        def __init__(self) -> None:
            self.request_id = trace_id
            self.status = types.SimpleNamespace(value="COMPLETED")
            self.adapter_applied = False
            self.adapter_id = None
            self.steps = [
                types.SimpleNamespace(
                    component="SimpleMode",
                    action="request",
                    status="ok",
                    details="session_id=- prompt=Co to jest slonce?",
                ),
                types.SimpleNamespace(
                    component="SimpleMode",
                    action="first_chunk",
                    status="ok",
                    details="elapsed_ms=18 preview=Slonce to gwiazda.",
                ),
                types.SimpleNamespace(
                    component="SimpleMode",
                    action="response",
                    status="ok",
                    details=json.dumps(
                        {
                            "chunks": 2,
                            "total_ms": 61.7,
                            "chars": 18,
                            "response": "Slonce to gwiazda.",
                            "truncated": False,
                        }
                    ),
                ),
                types.SimpleNamespace(
                    component="Retriever",
                    action="rag_focus",
                    status="ok",
                    details=json.dumps(
                        {
                            "entities": [
                                {
                                    "id": "entity:sun",
                                    "label": "Słońce",
                                    "kind": "entity",
                                    "active": True,
                                }
                            ],
                            "evidence_edges": [
                                {
                                    "from": "query",
                                    "to": "entity:sun",
                                    "label": "retrieval",
                                    "active": True,
                                }
                            ],
                            "active_entity_ids": ["entity:sun"],
                            "grounding_score": 0.88,
                        }
                    ),
                ),
            ]

    class _FakeTracer:
        def get_trace(self, request_id):
            if str(request_id) == trace_id:
                return _FakeTrace()
            return None

    async def fake_snapshot(**kwargs):
        return snapshot

    async def fake_stream_simple_chat(request):
        assert request.content == "Co to jest slonce?"
        return _FakeStreamingResponse(
            [
                "event: start\ndata: {}\n\n",
                'event: content\ndata: {"text":"Slonce to gwiazda."}\n\n',
                "event: done\ndata: {}\n\n",
            ],
            headers={"X-Request-Id": trace_id},
        )

    monkeypatch.setattr(
        analysis_service,
        "build_model_introspection_snapshot",
        fake_snapshot,
    )
    monkeypatch.setattr(analysis_service, "get_request_tracer", lambda: _FakeTracer())
    monkeypatch.setattr(analysis_service, "stream_simple_chat", fake_stream_simple_chat)
    monkeypatch.setattr(
        analysis_service,
        "_collect_logit_lens_payload_safe",
        lambda **_kwargs: _async_return(_build_logit_lens_stub()),
    )
    monkeypatch.setattr(
        analysis_service,
        "_collect_attention_payload_safe",
        lambda **_kwargs: _async_return(_build_attention_stub()),
    )
    monkeypatch.setattr(
        analysis_service,
        "_collect_activation_path_payload_safe",
        lambda **_kwargs: _async_return(_build_hidden_state_stub()),
    )
    monkeypatch.setattr(
        analysis_service,
        "_collect_mlp_activation_payload_safe",
        lambda **_kwargs: _async_return(_build_mlp_activation_stub()),
    )
    monkeypatch.setattr(
        analysis_service,
        "_collect_saliency_payload_safe",
        lambda **_kwargs: _async_return(_build_saliency_stub()),
    )

    result = await analysis_service.analyze_model_with_optional_live_run(
        prompt="Co to jest slonce?",
        live_analysis_enabled=True,
    )

    process = result["analysis"]["process"]
    assert process["request_id"] == trace_id
    assert process["status"] == "COMPLETED"
    assert process["trace_step_count"] == 4
    assert process["first_chunk_ms"] == 18
    assert process["response_chars"] == 18
    assert process["response_chunks"] == 2
    assert process["response_truncated"] is False
    assert result["analysis"]["rag_focus"]["source"] == "runtime_trace"
    assert "answer_evidence_links" in result["analysis"]["rag_focus"]


@pytest.mark.asyncio
async def test_analysis_stream_emits_progressive_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_snapshot(**kwargs):
        return _build_snapshot()

    async def fake_stream_simple_chat(request):
        assert request.content == "Co to jest slonce?"
        return _FakeStreamingResponse(
            [
                "event: start\ndata: {}\n\n",
                'event: content\ndata: {"text":"Slonce to "}\n\n',
                'event: content\ndata: {"text":"gwiazda."}\n\n',
                "event: done\ndata: {}\n\n",
            ]
        )

    monkeypatch.setattr(
        analysis_service,
        "build_model_introspection_snapshot",
        fake_snapshot,
    )
    monkeypatch.setattr(analysis_service, "stream_simple_chat", fake_stream_simple_chat)
    monkeypatch.setattr(
        analysis_service,
        "_collect_logit_lens_payload_safe",
        lambda **_kwargs: _async_return(_build_logit_lens_stub()),
    )
    monkeypatch.setattr(
        analysis_service,
        "_collect_attention_payload_safe",
        lambda **_kwargs: _async_return(_build_attention_stub()),
    )
    monkeypatch.setattr(
        analysis_service,
        "_collect_activation_path_payload_safe",
        lambda **_kwargs: _async_return(_build_hidden_state_stub()),
    )
    monkeypatch.setattr(
        analysis_service,
        "_collect_mlp_activation_payload_safe",
        lambda **_kwargs: _async_return(_build_mlp_activation_stub()),
    )
    monkeypatch.setattr(
        analysis_service,
        "_collect_saliency_payload_safe",
        lambda **_kwargs: _async_return(_build_saliency_stub()),
    )

    chunks: list[str] = []
    async for chunk in analysis_service.stream_model_introspection_analysis(
        prompt="Co to jest slonce?",
        live_analysis_enabled=True,
    ):
        chunks.append(chunk)

    events = []
    for chunk in chunks:
        events.extend(analysis_service.parse_sse_events(chunk))

    event_names = [event_name for event_name, _ in events]
    assert event_names[0] == "analysis_start"
    assert "start" in event_names
    assert "content" in event_names
    assert event_names[-1] == "analysis_done"

    analysis_start = json.loads(events[0][1])
    analysis_done = json.loads(events[-1][1])
    assert analysis_start["status"] == "running"
    assert analysis_start["analysis"]["timeline"][0]["label"] == "Snapshot captured"
    assert analysis_done["status"] == "completed"
    assert analysis_done["analysis"]["response"] == "Slonce to gwiazda."
    assert analysis_done["analysis"]["timeline_step_count"] == 9
    timeline_labels = [step["label"] for step in analysis_done["analysis"]["timeline"]]
    assert "Logit lens probe" in timeline_labels
    assert "Attention probe" in timeline_labels
    assert "Saliency probe" in timeline_labels
    assert analysis_done["analysis"]["logit_lens"]["status"] == "ok"
    assert "interpretability" in analysis_done["analysis"]["logit_lens"]
    assert analysis_done["analysis"]["layer_internals"]["status"] == "ok"
    assert analysis_done["analysis"]["layer_internals"]["summary"]["block_count"] == 4
    assert (
        analysis_done["analysis"]["layer_internals"]["summary"][
            "architecture_block_count"
        ]
        >= 1
    )
    assert (
        analysis_done["analysis"]["layer_internals"]["summary"][
            "activation_layer_count"
        ]
        == 2
    )
    assert (
        analysis_done["analysis"]["layer_internals"]["summary"][
            "activation_transition_count"
        ]
        == 1
    )
    assert (
        analysis_done["analysis"]["layer_internals"]["summary"]["checkpoint_count"] == 2
    )
    assert (
        analysis_done["analysis"]["layer_internals"]["summary"]["attention_layer_count"]
        == 1
    )
    assert (
        analysis_done["analysis"]["layer_internals"]["summary"]["saliency_token_count"]
        == 3
    )
    assert len(analysis_done["analysis"]["layer_internals"]["layers"]) == 3
    assert analysis_done["analysis"]["layer_internals"]["layers"][0]["blocks"]
    assert analysis_done["analysis"]["layer_internals"]["layers"][0]["response_linkage"]
    assert (
        analysis_done["analysis"]["layer_internals"]["layers"][0]["response_linkage"][
            "linked_fragment_count"
        ]
        >= 0
    )
    assert analysis_done["analysis"]["layer_internals"]["layers"][0][
        "response_linkage"
    ]["impact"]
    assert analysis_done["analysis"]["layer_internals"]["architecture_blocks"]
    assert (
        analysis_done["analysis"]["layer_internals"]["activation_path"]["status"]
        == "ok"
    )
    assert (
        analysis_done["analysis"]["layer_internals"]["mlp_activation"]["status"] == "ok"
    )
    assert (
        analysis_done["analysis"]["layer_internals"]["mlp_activation"][
            "tensor_activation"
        ]["status"]
        == "ok"
    )
    assert (
        analysis_done["analysis"]["layer_internals"]["mlp_activation"]["summary"][
            "focus_layer"
        ]
        == 3
    )
    assert analysis_done["analysis"]["rag_focus"]["source"] == "graph_fallback"
    assert "answer_evidence_links" in analysis_done["analysis"]["rag_focus"]
    assert analysis_done["analysis"]["stream_profile"]["chunk_count"] == 2
    assert "run_trends" in analysis_done["analysis"]


@pytest.mark.asyncio
async def test_analysis_stream_flushes_sse_tail_and_emits_done(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_snapshot(**kwargs):
        return _build_snapshot()

    async def fake_stream_simple_chat(_request):
        # Tail flush path: final event has no trailing \n\n in chunk body
        return _FakeStreamingResponse(
            [
                "event: start\ndata: {}\n\n",
                'event: content\ndata: {"text":"A"}',
            ]
        )

    monkeypatch.setattr(
        analysis_service,
        "build_model_introspection_snapshot",
        fake_snapshot,
    )
    monkeypatch.setattr(analysis_service, "stream_simple_chat", fake_stream_simple_chat)
    monkeypatch.setattr(
        analysis_service,
        "_collect_logit_lens_payload_safe",
        lambda **_kwargs: _async_return(_build_logit_lens_stub()),
    )
    monkeypatch.setattr(
        analysis_service,
        "_collect_activation_path_payload_safe",
        lambda **_kwargs: _async_return(_build_hidden_state_stub()),
    )

    chunks: list[str] = []
    async for chunk in analysis_service.stream_model_introspection_analysis(
        prompt="Co to jest slonce?",
        live_analysis_enabled=True,
    ):
        chunks.append(chunk)

    events = []
    for chunk in chunks:
        events.extend(analysis_service.parse_sse_events(chunk))
    event_names = [name for name, _ in events]
    assert event_names[-1] == "analysis_done"
    done_payload = json.loads(events[-1][1])
    assert done_payload["analysis"]["response"] == "A"
    assert done_payload["analysis"]["logit_lens"]["status"] == "ok"
    assert done_payload["analysis"]["layer_internals"]["status"] == "ok"
    assert done_payload["analysis"]["layer_internals"]["summary"]["block_count"] >= 1
    assert done_payload["analysis"]["layer_internals"]["architecture_blocks"]


@pytest.mark.asyncio
async def test_analysis_stream_emits_failed_result_when_response_has_no_body_iterator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_snapshot(**kwargs):
        return _build_snapshot()

    async def fake_stream_simple_chat(_request):
        return object()

    monkeypatch.setattr(
        analysis_service,
        "build_model_introspection_snapshot",
        fake_snapshot,
    )
    monkeypatch.setattr(analysis_service, "stream_simple_chat", fake_stream_simple_chat)

    chunks: list[str] = []
    async for chunk in analysis_service.stream_model_introspection_analysis(
        prompt="Co to jest slonce?",
        live_analysis_enabled=True,
    ):
        chunks.append(chunk)

    events: list[tuple[str, str]] = []
    for chunk in chunks:
        events.extend(analysis_service.parse_sse_events(chunk))

    event_names = [name for name, _ in events]
    assert "error" in event_names
    assert event_names[-1] == "analysis_done"
    done_payload = json.loads(events[-1][1])
    assert done_payload["status"] == "failed"
    assert "body iterator" in done_payload["analysis"]["error"]


@pytest.mark.asyncio
async def test_analysis_stream_emits_error_on_stream_consumption_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_snapshot(**kwargs):
        return _build_snapshot()

    async def fake_stream_simple_chat(_request):
        return _FakeStreamingResponse(
            [
                "event: start\ndata: {}\n\n",
                'event: content\ndata: {"text":"Slonce to "}\n\n',
            ]
        )

    def _boom(**_kwargs):
        raise RuntimeError("stream consumption exploded")

    monkeypatch.setattr(
        analysis_service,
        "build_model_introspection_snapshot",
        fake_snapshot,
    )
    monkeypatch.setattr(analysis_service, "stream_simple_chat", fake_stream_simple_chat)
    monkeypatch.setattr(analysis_service, "_consume_sse_events", _boom)

    chunks: list[str] = []
    async for chunk in analysis_service.stream_model_introspection_analysis(
        prompt="Co to jest slonce?",
        live_analysis_enabled=True,
    ):
        chunks.append(chunk)

    events: list[tuple[str, str]] = []
    for chunk in chunks:
        events.extend(analysis_service.parse_sse_events(chunk))

    event_names = [name for name, _ in events]
    assert event_names[-2:] == ["error", "analysis_done"]
    done_payload = json.loads(events[-1][1])
    assert done_payload["status"] == "failed"
    assert "stream consumption exploded" in done_payload["analysis"]["error"]


@pytest.mark.asyncio
async def test_analysis_raises_when_stream_open_fails_with_non_degraded_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_snapshot(**kwargs):
        return _build_snapshot()

    async def fake_stream_simple_chat(_request):
        raise RuntimeError("unexpected bootstrap failure")

    monkeypatch.setattr(
        analysis_service,
        "build_model_introspection_snapshot",
        fake_snapshot,
    )
    monkeypatch.setattr(analysis_service, "stream_simple_chat", fake_stream_simple_chat)

    with pytest.raises(RuntimeError, match="unexpected bootstrap failure"):
        await analysis_service.analyze_model_with_optional_live_run(
            prompt="Co to jest slonce?",
            live_analysis_enabled=True,
        )


@pytest.mark.asyncio
async def test_analysis_raises_when_stream_collection_fails_with_non_degraded_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_snapshot(**kwargs):
        return _build_snapshot()

    async def fake_stream_simple_chat(_request):
        return _FakeStreamingResponse(
            [
                "event: start\ndata: {}\n\n",
                'event: content\ndata: {"text":"Slonce to "}\n\n',
            ]
        )

    async def fake_collect_streaming_response(_response):
        raise RuntimeError("unexpected collection failure")

    monkeypatch.setattr(
        analysis_service,
        "build_model_introspection_snapshot",
        fake_snapshot,
    )
    monkeypatch.setattr(analysis_service, "stream_simple_chat", fake_stream_simple_chat)
    monkeypatch.setattr(
        analysis_service,
        "_collect_streaming_response",
        fake_collect_streaming_response,
    )

    with pytest.raises(RuntimeError, match="unexpected collection failure"):
        await analysis_service.analyze_model_with_optional_live_run(
            prompt="Co to jest slonce?",
            live_analysis_enabled=True,
        )


@pytest.mark.asyncio
async def test_analysis_stream_maps_traffic_control_degraded_to_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_snapshot(**kwargs):
        return _build_snapshot()

    async def fake_stream_simple_chat(_request):
        raise RuntimeError("Traffic control is in degraded mode")

    monkeypatch.setattr(
        analysis_service,
        "build_model_introspection_snapshot",
        fake_snapshot,
    )
    monkeypatch.setattr(analysis_service, "stream_simple_chat", fake_stream_simple_chat)

    chunks: list[str] = []
    async for chunk in analysis_service.stream_model_introspection_analysis(
        prompt="Co to jest slonce?",
        live_analysis_enabled=True,
    ):
        chunks.append(chunk)

    events: list[tuple[str, str]] = []
    for chunk in chunks:
        events.extend(analysis_service.parse_sse_events(chunk))

    event_names = [name for name, _ in events]
    assert event_names[0] == "analysis_start"
    assert event_names[-1] == "analysis_done"
    done_payload = json.loads(events[-1][1])
    assert done_payload["status"] == "skipped"
    assert done_payload["skipped_reason"] == "traffic_control_degraded_mode"
    assert done_payload["analysis"]["error_code"] == "DEGRADED_POLICY_BLOCK"
    assert done_payload["analysis"]["timeline"][-1]["status"] == "skipped"


@pytest.mark.asyncio
async def test_analysis_maps_traffic_control_degraded_to_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_snapshot(**kwargs):
        return _build_snapshot()

    async def fake_stream_simple_chat(_request):
        raise RuntimeError("Traffic control is in degraded mode")

    monkeypatch.setattr(
        analysis_service,
        "build_model_introspection_snapshot",
        fake_snapshot,
    )
    monkeypatch.setattr(analysis_service, "stream_simple_chat", fake_stream_simple_chat)

    result = await analysis_service.analyze_model_with_optional_live_run(
        prompt="Co to jest slonce?",
        live_analysis_enabled=True,
    )

    assert result["status"] == "skipped"
    assert result["skipped_reason"] == "traffic_control_degraded_mode"
    assert result["analysis"]["error_code"] == "DEGRADED_POLICY_BLOCK"
    assert result["analysis"]["timeline"][-1]["status"] == "skipped"


@pytest.mark.asyncio
async def test_analysis_stream_maps_circuit_breaker_open_to_degraded_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_snapshot(**kwargs):
        return _build_snapshot()

    async def fake_stream_simple_chat(_request):
        raise RuntimeError("Circuit breaker open for provider 'multi_runtime'")

    monkeypatch.setattr(
        analysis_service,
        "build_model_introspection_snapshot",
        fake_snapshot,
    )
    monkeypatch.setattr(analysis_service, "stream_simple_chat", fake_stream_simple_chat)

    chunks: list[str] = []
    async for chunk in analysis_service.stream_model_introspection_analysis(
        prompt="Co to jest slonce?",
        live_analysis_enabled=True,
    ):
        chunks.append(chunk)

    events: list[tuple[str, str]] = []
    for chunk in chunks:
        events.extend(analysis_service.parse_sse_events(chunk))
    done_payload = json.loads(events[-1][1])
    assert done_payload["status"] == "skipped"
    assert done_payload["analysis"]["error_code"] == "DEGRADED_CIRCUIT_OPEN"


@pytest.mark.asyncio
async def test_analysis_maps_endpoint_unreachable_to_degraded_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_snapshot(**kwargs):
        return _build_snapshot()

    async def fake_stream_simple_chat(_request):
        raise RuntimeError("Connect error while contacting runtime endpoint")

    monkeypatch.setattr(
        analysis_service,
        "build_model_introspection_snapshot",
        fake_snapshot,
    )
    monkeypatch.setattr(analysis_service, "stream_simple_chat", fake_stream_simple_chat)

    result = await analysis_service.analyze_model_with_optional_live_run(
        prompt="Co to jest slonce?",
        live_analysis_enabled=True,
    )

    assert result["status"] == "skipped"
    assert result["analysis"]["error_code"] == "DEGRADED_ENDPOINT_UNREACHABLE"


@pytest.mark.asyncio
async def test_analysis_stream_maps_degraded_error_event_to_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_snapshot(**kwargs):
        return _build_snapshot()

    async def fake_stream_simple_chat(_request):
        return _FakeStreamingResponse(
            [
                "event: start\ndata: {}\n\n",
                'event: error\ndata: {"message":"Traffic control is in degraded mode"}\n\n',
            ]
        )

    monkeypatch.setattr(
        analysis_service,
        "build_model_introspection_snapshot",
        fake_snapshot,
    )
    monkeypatch.setattr(analysis_service, "stream_simple_chat", fake_stream_simple_chat)

    chunks: list[str] = []
    async for chunk in analysis_service.stream_model_introspection_analysis(
        prompt="Co to jest slonce?",
        live_analysis_enabled=True,
    ):
        chunks.append(chunk)

    events: list[tuple[str, str]] = []
    for chunk in chunks:
        events.extend(analysis_service.parse_sse_events(chunk))

    done_payload = json.loads(events[-1][1])
    assert done_payload["status"] == "skipped"
    assert done_payload["skipped_reason"] == "traffic_control_degraded_mode"


@pytest.mark.asyncio
async def test_analysis_maps_degraded_error_event_to_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_snapshot(**kwargs):
        return _build_snapshot()

    async def fake_stream_simple_chat(_request):
        return _FakeStreamingResponse(
            [
                "event: start\ndata: {}\n\n",
                'event: error\ndata: {"message":"Traffic control is in degraded mode"}\n\n',
            ]
        )

    monkeypatch.setattr(
        analysis_service,
        "build_model_introspection_snapshot",
        fake_snapshot,
    )
    monkeypatch.setattr(analysis_service, "stream_simple_chat", fake_stream_simple_chat)

    result = await analysis_service.analyze_model_with_optional_live_run(
        prompt="Co to jest slonce?",
        live_analysis_enabled=True,
    )

    assert result["status"] == "skipped"


@pytest.mark.asyncio
async def test_analysis_stream_skips_when_model_drift_detected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = _build_snapshot()
    snapshot["runtime_drift"] = {
        "issues": [
            "Runtime provider 'multi_runtime' does not match daemon target model ('model-a' vs 'model-b')."
        ],
        "runtime_active_model_id": "model-a",
        "daemon_target_model": "model-b",
    }

    async def fake_snapshot(**kwargs):
        return snapshot

    monkeypatch.setattr(
        analysis_service,
        "build_model_introspection_snapshot",
        fake_snapshot,
    )

    chunks: list[str] = []
    async for chunk in analysis_service.stream_model_introspection_analysis(
        prompt="Co to jest slonce?",
        live_analysis_enabled=True,
    ):
        chunks.append(chunk)

    events: list[tuple[str, str]] = []
    for chunk in chunks:
        events.extend(analysis_service.parse_sse_events(chunk))

    assert [name for name, _ in events] == ["analysis_start", "analysis_done"]
    done_payload = json.loads(events[-1][1])
    assert done_payload["status"] == "skipped"
    assert done_payload["skipped_reason"] == "model_drift_detected"
    assert done_payload["analysis"]["error"] == "MODEL_DRIFT_DETECTED"
    assert done_payload["analysis"]["runtime_active_model_id"] == "model-a"
    assert done_payload["analysis"]["daemon_target_model"] == "model-b"


@pytest.mark.asyncio
async def test_analysis_skips_when_model_drift_detected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = _build_snapshot()
    snapshot["runtime_drift"] = {
        "issues": [
            "Runtime provider 'multi_runtime' does not match daemon target model ('model-a' vs 'model-b')."
        ],
        "runtime_active_model_id": "model-a",
        "daemon_target_model": "model-b",
    }

    async def fake_snapshot(**kwargs):
        return snapshot

    monkeypatch.setattr(
        analysis_service,
        "build_model_introspection_snapshot",
        fake_snapshot,
    )

    result = await analysis_service.analyze_model_with_optional_live_run(
        prompt="Co to jest slonce?",
        live_analysis_enabled=True,
    )

    assert result["status"] == "skipped"
    assert result["skipped_reason"] == "model_drift_detected"
    assert result["analysis"]["error_code"] == "MODEL_DRIFT_DETECTED"
    assert result["analysis"]["runtime_active_model_id"] == "model-a"
    assert result["analysis"]["daemon_target_model"] == "model-b"


def test_classify_stream_quality_variants() -> None:
    assert (
        analysis_service._classify_stream_quality(
            chunk_count=0,
            first_content_at_ms=None,
            elapsed_ms=10.0,
        )
        == "no_content"
    )
    assert (
        analysis_service._classify_stream_quality(
            chunk_count=2,
            first_content_at_ms=5.0,
            elapsed_ms=12.0,
        )
        == "live_streaming"
    )
    assert (
        analysis_service._classify_stream_quality(
            chunk_count=1,
            first_content_at_ms=1500.0,
            elapsed_ms=1600.0,
        )
        == "single_chunk_delayed"
    )


def test_build_logit_lens_timeline_step_for_failed_probe() -> None:
    step = analysis_service._build_logit_lens_timeline_step(
        logit_lens={
            "status": "failed",
            "code": "probe_timeout",
            "message": "Probe request timed out on active runtime",
        },
        at_ms=100.0,
    )
    assert step["status"] == "failed"
    assert step["detail"] == "Probe request timed out on active runtime (probe_timeout)"
    assert step["reason_code"] == "probe_timeout"


def test_build_logit_lens_timeline_step_for_unavailable_probe() -> None:
    step = analysis_service._build_logit_lens_timeline_step(
        logit_lens={
            "status": "probe_unavailable",
            "code": "probe_disabled",
            "message": "Probe is disabled by runtime configuration",
        },
        at_ms=100.0,
    )
    assert step["status"] == "skipped"
    assert (
        step["detail"] == "Probe is disabled by runtime configuration (probe_disabled)"
    )
    assert step["reason_code"] == "probe_disabled"


def test_build_probe_timeline_step_for_failed_probe() -> None:
    step = analysis_service._build_probe_timeline_step(
        step_id="attention_probe",
        step_label="Attention probe",
        payload={
            "status": "failed",
            "code": "probe_transport_error",
            "message": "Probe transport error on active runtime",
        },
        at_ms=42.0,
    )
    assert step["status"] == "failed"
    assert (
        step["detail"]
        == "Probe transport error on active runtime (probe_transport_error)"
    )
    assert step["reason_code"] == "probe_transport_error"


@pytest.mark.asyncio
async def test_collect_logit_lens_payload_safe_returns_fallback_on_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _raise(*_args, **_kwargs):
        raise RuntimeError("probe failed")

    monkeypatch.setattr(analysis_service, "build_logit_lens_payload", _raise)
    payload = await analysis_service._collect_logit_lens_payload_safe(
        prompt="q",
        response_text="a",
    )
    assert payload["status"] == "probe_unavailable"
    assert payload["source"] == "probe_unavailable"


def test_collect_rag_focus_payload_safe_returns_fallback_on_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise(*_args, **_kwargs):
        raise ValueError("bad trace")

    monkeypatch.setattr(analysis_service, "build_rag_focus_payload", _raise)
    payload = analysis_service._collect_rag_focus_payload_safe(
        prompt="q",
        snapshot={},
        process_trace=None,
        response_text="a",
    )
    assert payload["source"] == "graph_fallback"


def test_build_payload_sets_top_p_for_simple_chat_request() -> None:
    class _Runtime:
        provider = "openai"

    payload = llm_simple_service._build_payload(
        request=SimpleChatRequest(content="hello", top_p=0.85),
        runtime=_Runtime(),
        model_name="m",
        messages=[{"role": "user", "content": "hello"}],
    )
    assert payload["top_p"] == 0.85


def test_extract_system_prompt_text_handles_multiline_markers() -> None:
    context_preview = "SYSTEM:\nRules line 1\nRules line 2\n\nUSER: Co to jest slonce?"
    extracted = analysis_service._extract_system_prompt_text(context_preview)
    assert extracted == "Rules line 1\nRules line 2"


def test_extract_system_prompt_text_handles_missing_user_marker() -> None:
    context_preview = "SYSTEM: Rules only"
    extracted = analysis_service._extract_system_prompt_text(context_preview)
    assert extracted == "Rules only"


def test_analysis_capabilities_marks_proxy_as_partial_not_full() -> None:
    payload = analysis_service._build_analysis_capabilities_payload(
        hidden_state={"source": "probe_runtime", "status": "ok"},
        attention={
            "source": "probe_runtime",
            "status": "ok",
            "code": "attention_proxy_logits",
        },
        saliency={"source": "probe_runtime", "status": "ok"},
        logit_lens={"source": "probe_runtime", "status": "ok"},
        probe_health={"enabled": True, "healthy": True, "runtime_supported": True},
    )
    assert payload["available_count"] == 4
    assert payload["native_available_count"] == 3
    assert payload["proxy_active"] is True
    assert payload["internals_verdict"] == "partial"
    assert payload["hidden_state"]["availability_class"] == "native_ok"
    assert payload["attention"]["availability_class"] == "proxy_ok"
    assert payload["saliency"]["availability_class"] == "native_ok"
    assert payload["logit_lens"]["availability_class"] == "native_ok"


def test_analysis_capabilities_marks_native_runtime_as_full() -> None:
    payload = analysis_service._build_analysis_capabilities_payload(
        hidden_state={"source": "probe_runtime", "status": "ok"},
        attention={"source": "probe_runtime", "status": "ok"},
        saliency={"source": "probe_runtime", "status": "ok"},
        logit_lens={"source": "probe_runtime", "status": "ok"},
        probe_health={"enabled": True, "healthy": True, "runtime_supported": True},
    )
    assert payload["available_count"] == 4
    assert payload["native_available_count"] == 4
    assert payload["proxy_active"] is False
    assert payload["internals_verdict"] == "full"
    assert payload["hidden_state"]["availability_class"] == "native_ok"
    assert payload["attention"]["availability_class"] == "native_ok"
    assert payload["saliency"]["availability_class"] == "native_ok"
    assert payload["logit_lens"]["availability_class"] == "native_ok"


def test_analysis_capabilities_marks_failed_and_unavailable_classes() -> None:
    payload = analysis_service._build_analysis_capabilities_payload(
        hidden_state={"source": "probe_unavailable", "status": "probe_unavailable"},
        attention={
            "source": "probe_runtime",
            "status": "failed",
            "code": "probe_failed",
        },
        saliency={"source": "probe_unavailable", "status": "probe_unavailable"},
        logit_lens={"source": "probe_runtime", "status": "ok"},
        probe_health={"enabled": True, "healthy": True, "runtime_supported": True},
    )
    assert payload["hidden_state"]["availability_class"] == "unavailable"
    assert payload["attention"]["availability_class"] == "failed"
    assert payload["saliency"]["availability_class"] == "unavailable"
    assert payload["logit_lens"]["availability_class"] == "native_ok"


def test_analysis_capabilities_marks_probe_lite_as_available_proxy() -> None:
    payload = analysis_service._build_analysis_capabilities_payload(
        hidden_state={"source": "probe_unavailable", "status": "probe_unavailable"},
        attention={"source": "probe_unavailable", "status": "probe_unavailable"},
        saliency={"source": "probe_unavailable", "status": "probe_unavailable"},
        logit_lens={
            "source": "probe_lite",
            "status": "ok",
            "code": "ollama_logprobs_lite",
        },
        probe_health={"enabled": False, "healthy": False, "runtime_supported": False},
    )
    assert payload["available_count"] == 1
    assert payload["native_available_count"] == 0
    assert payload["proxy_active"] is True
    assert payload["internals_verdict"] == "partial"
    assert payload["logit_lens"]["availability_class"] == "proxy_ok"


@pytest.mark.asyncio
async def test_analysis_ollama_requests_non_stream_logprobs_and_uses_lite_logit_lens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = _build_snapshot()
    snapshot["runtime"]["provider"] = "ollama"
    snapshot["runtime"]["model"] = "gemma3:latest"
    snapshot["runtime"]["endpoint"] = "http://localhost:11434/v1"
    snapshot["runtime"]["label"] = "gemma3:latest · ollama @ localhost:11434"

    async def fake_snapshot(**kwargs):
        return snapshot

    async def fake_stream_simple_chat(request):
        assert request.stream is False
        assert request.logprobs is True
        assert request.top_logprobs == 3
        return _FakeStreamingResponse(
            [
                "event: start\ndata: {}\n\n",
                'event: telemetry\ndata: {"kind":"logprobs","content":[{"token":"Słońce","logprob":-0.1,"top_logprobs":[{"token":"Słońce","logprob":-0.1},{"token":"Planeta","logprob":-2.0}]}]}\n\n',
                'event: content\ndata: {"text":"Słońce to gwiazda."}\n\n',
                "event: done\ndata: {}\n\n",
            ]
        )

    async def _unexpected_probe_call(**_kwargs):
        raise AssertionError("probe path should not be used for ollama lite mode")

    monkeypatch.setattr(
        analysis_service,
        "build_model_introspection_snapshot",
        fake_snapshot,
    )
    monkeypatch.setattr(analysis_service, "stream_simple_chat", fake_stream_simple_chat)
    monkeypatch.setattr(
        analysis_service,
        "_collect_logit_lens_payload_safe",
        _unexpected_probe_call,
    )

    result = await analysis_service.analyze_model_with_optional_live_run(
        prompt="Co to jest slonce?",
        live_analysis_enabled=True,
    )

    assert result["status"] == "completed"
    assert result["analysis"]["logit_lens"]["source"] == "probe_lite"
    assert result["analysis"]["logit_lens"]["status"] == "ok"
    assert (
        result["analysis"]["analysis_capabilities"]["logit_lens"]["available"] is True
    )
    assert result["analysis"]["analysis_capabilities"]["logit_lens"]["proxy"] is True
    assert result["analysis"]["analysis_capabilities"]["introspection_level"] == "lite"
    assert result["analysis"]["introspection_level"] == "lite"


def test_operator_conclusion_uses_proxy_reason_code() -> None:
    payload = analysis_service._build_operator_conclusion_payload(
        rag_focus={"source": "runtime_trace", "grounding_score": 0.9},
        logit_lens={
            "source": "probe_runtime",
            "interpretability": {"token_noise_ratio": 0.1},
        },
        evidence_coverage={"coverage_percent": 100.0},
        stream_profile={"stream_quality": "single_chunk"},
        analysis_capabilities={"proxy_active": True},
    )
    assert "R3_PROBE_PROXY" in payload["reason_codes"]
    assert payload["partial"] is True
    assert payload["internals_quality"] == "proxy_probe"
