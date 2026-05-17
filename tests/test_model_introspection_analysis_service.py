"""Tests for optional model introspection analysis service."""

from __future__ import annotations

import json
import types

import pytest

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
    assert result["analysis"]["timeline"][0]["label"] == "Live analysis disabled"
    assert result["analysis"]["timeline"][0]["status"] == "skipped"


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

    result = await analysis_service.analyze_model_with_optional_live_run(
        prompt="Co to jest slonce?",
        live_analysis_enabled=True,
    )

    assert result["status"] == "completed"
    assert result["analysis"]["response"] == "Slonce to gwiazda."
    assert result["analysis"]["chunk_count"] == 1
    assert result["analysis"]["provider"] == "multi_runtime"
    assert result["analysis"]["events"] == ["start", "content", "done"]
    assert result["analysis"]["timeline_step_count"] == 7
    assert result["analysis"]["timeline"][0]["label"] == "Snapshot captured"
    assert result["analysis"]["timeline"][-2]["label"] == "Logit lens probe"
    assert result["analysis"]["timeline"][-1]["label"] == "Snapshot refreshed"
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
    assert analysis_done["analysis"]["timeline_step_count"] == 7
    assert analysis_done["analysis"]["logit_lens"]["status"] == "ok"
    assert "interpretability" in analysis_done["analysis"]["logit_lens"]
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
