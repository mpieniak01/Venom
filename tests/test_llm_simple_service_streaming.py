from __future__ import annotations

import json
from contextlib import asynccontextmanager
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException
from starlette.responses import StreamingResponse

from venom_core.api.schemas.llm_simple import SimpleChatRequest
from venom_core.services import llm_simple_service


class _Runtime:
    def __init__(self, provider: str = "ollama", model_name: str | None = "model-x"):
        self.provider = provider
        self.model_name = model_name
        self.endpoint = "http://localhost:1234/v1"
        self.service_type = "local"
        self.config_hash = "cfg"
        self.runtime_id = "rid"


class _LinesResponse:
    def __init__(self, lines: list[str]):
        self._lines = lines

    def raise_for_status(self) -> None:
        return None

    async def aiter_lines(self):
        for line in self._lines:
            yield line


async def _collect_events(stream):
    out: list[tuple[str, dict[str, object] | None]] = []
    async for chunk in stream:
        parts = [p for p in chunk.split("\n") if p]
        if len(parts) < 2:
            continue
        event = parts[0].replace("event: ", "")
        data_raw = parts[1].replace("data: ", "")
        payload = json.loads(data_raw) if data_raw and data_raw != "{}" else {}
        out.append((event, payload))
    return out


async def _collect_response_events(response: StreamingResponse):
    return await _collect_events(response.body_iterator)


class _Tracer:
    def __init__(self):
        self.steps: list[tuple[tuple, dict]] = []
        self.calls: list[tuple[str, tuple, dict]] = []

    def add_step(self, *args, **kwargs):
        self.steps.append((args, kwargs))

    def create_trace(self, *args, **kwargs):
        self.calls.append(("create_trace", args, kwargs))

    def set_llm_metadata(self, *args, **kwargs):
        self.calls.append(("set_llm_metadata", args, kwargs))

    def update_status(self, *args, **kwargs):
        self.calls.append(("update_status", args, kwargs))

    def set_error_metadata(self, *args, **kwargs):
        self.calls.append(("set_error_metadata", args, kwargs))


def test_helper_model_resolution_and_content_extractors():
    assert (
        llm_simple_service._resolve_model_name_for_simple_request(
            request_model=None,
            runtime_model="base-model",
            active_adapter_id=None,
        )
        == "base-model"
    )
    assert (
        llm_simple_service._resolve_model_name_for_simple_request(
            request_model=None,
            runtime_model="base-model",
            active_adapter_id="abc",
        )
        == "venom-adapter-abc"
    )
    assert (
        llm_simple_service._extract_message_content(
            {"choices": [{"message": {"content": " hello "}}]},
            fallback_text="x",
        )
        == "hello"
    )
    assert (
        llm_simple_service._extract_message_content(
            {"choices": [{"text": " world "}]},
            fallback_text="x",
        )
        == "world"
    )
    assert (
        llm_simple_service._extract_message_content({}, fallback_text="fallback")
        == "fallback"
    )


def test_build_payload_includes_top_p_when_provided():
    request = SimpleChatRequest(
        content="hello",
        max_tokens=64,
        temperature=0.2,
        top_p=0.9,
    )
    runtime = _Runtime("openai")
    payload = llm_simple_service._build_payload(
        request=request,
        runtime=runtime,
        model_name="model-x",
        messages=[{"role": "user", "content": "hello"}],
        stream=True,
    )
    assert payload["top_p"] == 0.9


def test_build_payload_includes_logprobs_and_top_logprobs():
    request = SimpleChatRequest(
        content="hello",
        logprobs=True,
        top_logprobs=3,
    )
    runtime = _Runtime("openai")
    payload = llm_simple_service._build_payload(
        request=request,
        runtime=runtime,
        model_name="model-x",
        messages=[{"role": "user", "content": "hello"}],
        stream=False,
    )
    assert payload["logprobs"] is True
    assert payload["top_logprobs"] == 3


def test_extract_logprobs_telemetry_guard_branches():
    assert llm_simple_service._extract_logprobs_telemetry({}) is None
    assert llm_simple_service._extract_logprobs_telemetry({"choices": [{}]}) is None
    assert (
        llm_simple_service._extract_logprobs_telemetry(
            {"choices": [{"logprobs": {"content": "bad"}}]}
        )
        is None
    )


def test_extract_logprobs_telemetry_normalizes_valid_items():
    payload = {
        "choices": [
            {
                "logprobs": {
                    "content": [
                        {
                            "token": "A",
                            "logprob": -0.1,
                            "top_logprobs": [
                                None,
                                {"token": "B", "logprob": -0.2},
                            ],
                        },
                        {"token": "skip", "logprob": "bad"},
                    ]
                }
            }
        ]
    }
    telemetry = llm_simple_service._extract_logprobs_telemetry(payload)
    assert telemetry is not None
    assert telemetry["kind"] == "logprobs"
    assert len(telemetry["content"]) == 1
    assert telemetry["content"][0]["token"] == "A"
    assert telemetry["content"][0]["top_logprobs"][0]["token"] == "B"


@pytest.mark.asyncio
async def test_get_active_adapter_id_variants(monkeypatch):
    monkeypatch.setattr(llm_simple_service, "get_model_manager", lambda: None)
    assert await llm_simple_service._get_active_adapter_id() is None

    class _MgrSync:
        def get_active_adapter_info(self):
            return {"adapter_id": "sync-adapter"}

    monkeypatch.setattr(llm_simple_service, "get_model_manager", lambda: _MgrSync())
    assert await llm_simple_service._get_active_adapter_id() == "sync-adapter"

    class _MgrAsync:
        async def get_active_adapter_info(self):
            return {"adapter_id": "async-adapter"}

    monkeypatch.setattr(llm_simple_service, "get_model_manager", lambda: _MgrAsync())
    assert await llm_simple_service._get_active_adapter_id() == "async-adapter"


def test_trace_and_trim_helpers(monkeypatch):
    tracer = _Tracer()
    monkeypatch.setattr(llm_simple_service, "_get_request_tracer", lambda: tracer)
    monkeypatch.setattr(
        llm_simple_service, "_get_simple_context_char_limit", lambda _rt: 50
    )

    rid = uuid4()
    llm_simple_service._trace_simple_request(
        rid,
        SimpleChatRequest(content="x" * 40, session_id="s1"),
        _Runtime(),
        "venom-adapter-abc",
    )
    llm_simple_service._trace_context_preview(
        rid,
        [{"role": "user", "content": "x" * 2500}],
    )
    trimmed = llm_simple_service._trim_user_content_for_runtime(
        "x" * 300,
        "sys",
        _Runtime("vllm"),
        rid,
    )
    assert len(trimmed) < 300
    assert tracer.calls


@pytest.mark.asyncio
async def test_stream_simple_chunks_yields_content_and_done(monkeypatch):
    @asynccontextmanager
    async def _fake_open_stream_response(**_kwargs):
        yield _LinesResponse(
            [
                'data: {"choices":[{"delta":{"content":"A"}}]}',
                "data: [DONE]",
            ]
        )

    monkeypatch.setattr(
        llm_simple_service.llm_simple_transport,
        "open_stream_response",
        _fake_open_stream_response,
    )

    runtime = _Runtime("ollama")
    events = await _collect_events(
        llm_simple_service._stream_simple_chunks(
            completions_url="http://localhost/v1/chat/completions",
            payload={"messages": []},
            runtime=runtime,
            request_id=uuid4(),
            model_name="model-x",
        )
    )

    assert [name for name, _ in events] == ["start", "content", "done"]
    assert events[1][1]["text"] == "A"


@pytest.mark.asyncio
async def test_stream_simple_chunks_http_error_emits_error_event(monkeypatch):
    @asynccontextmanager
    async def _fake_open_stream_response(**_kwargs):
        request = httpx.Request("POST", "http://localhost/v1/chat/completions")
        response = httpx.Response(502, request=request, text="bad gateway")
        raise httpx.HTTPStatusError("bad", request=request, response=response)
        yield  # pragma: no cover

    monkeypatch.setattr(
        llm_simple_service.llm_simple_transport,
        "open_stream_response",
        _fake_open_stream_response,
    )

    runtime = _Runtime("ollama")
    events = await _collect_events(
        llm_simple_service._stream_simple_chunks(
            completions_url="http://localhost/v1/chat/completions",
            payload={"messages": []},
            runtime=runtime,
            request_id=uuid4(),
            model_name="model-x",
        )
    )

    assert [name for name, _ in events] == ["start", "error"]
    assert events[1][1]["code"] == "llm_http_error"


@pytest.mark.asyncio
async def test_stream_simple_chunks_non_stream_returns_content(monkeypatch):
    class _JsonResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {"choices": [{"message": {"content": "Witaj z multi_runtime"}}]}

    @asynccontextmanager
    async def _fake_open_stream_response(**_kwargs):
        yield _JsonResponse()

    monkeypatch.setattr(
        llm_simple_service.llm_simple_transport,
        "open_stream_response",
        _fake_open_stream_response,
    )

    runtime = _Runtime("multi_runtime")
    events = await _collect_events(
        llm_simple_service._stream_simple_chunks_non_stream(
            completions_url="http://localhost/v1/chat/completions",
            payload={"messages": []},
            runtime=runtime,
            request_id=uuid4(),
            model_name="model-x",
        )
    )

    assert [name for name, _ in events] == ["start", "content", "done"]
    assert events[1][1]["text"] == "Witaj z multi_runtime"


@pytest.mark.asyncio
async def test_stream_simple_chunks_non_stream_invalid_payload_emits_error(monkeypatch):
    class _InvalidResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return ["invalid"]

    collector_calls: list[dict[str, object]] = []

    class _Collector:
        def record_provider_request(self, **kwargs):
            collector_calls.append(kwargs)

    @asynccontextmanager
    async def _fake_open_stream_response(**_kwargs):
        yield _InvalidResponse()

    monkeypatch.setattr(
        llm_simple_service.llm_simple_transport,
        "open_stream_response",
        _fake_open_stream_response,
    )
    monkeypatch.setattr(
        llm_simple_service, "get_metrics_collector", lambda: _Collector()
    )

    runtime = _Runtime("multi_runtime")
    events = await _collect_events(
        llm_simple_service._stream_simple_chunks_non_stream(
            completions_url="http://localhost/v1/chat/completions",
            payload={"messages": []},
            runtime=runtime,
            request_id=uuid4(),
            model_name="model-x",
        )
    )

    assert [name for name, _ in events] == ["start", "error"]
    assert events[1][1]["code"] == "llm_invalid_response"
    assert collector_calls
    assert collector_calls[-1]["success"] is False


@pytest.mark.asyncio
async def test_stream_simple_chunks_non_stream_error_paths(monkeypatch):
    request = httpx.Request("POST", "http://localhost/v1/chat/completions")

    @asynccontextmanager
    async def _fake_status_error(**_kwargs):
        raise httpx.HTTPStatusError(
            "bad",
            request=request,
            response=httpx.Response(502, request=request, text="bad"),
        )
        yield  # pragma: no cover

    monkeypatch.setattr(
        llm_simple_service.llm_simple_transport,
        "open_stream_response",
        _fake_status_error,
    )
    status_events = await _collect_events(
        llm_simple_service._stream_simple_chunks_non_stream(
            completions_url="http://localhost/v1/chat/completions",
            payload={},
            runtime=_Runtime("multi_runtime"),
            request_id=uuid4(),
            model_name="m",
        )
    )
    assert [name for name, _ in status_events] == ["start", "error"]

    @asynccontextmanager
    async def _fake_http_error(**_kwargs):
        raise httpx.ConnectError("offline")
        yield  # pragma: no cover

    monkeypatch.setattr(
        llm_simple_service.llm_simple_transport,
        "open_stream_response",
        _fake_http_error,
    )
    conn_events = await _collect_events(
        llm_simple_service._stream_simple_chunks_non_stream(
            completions_url="http://localhost/v1/chat/completions",
            payload={},
            runtime=_Runtime("multi_runtime"),
            request_id=uuid4(),
            model_name="m",
        )
    )
    assert [name for name, _ in conn_events] == ["start", "error"]


@pytest.mark.asyncio
async def test_stream_simple_chat_validation_and_endpoint_guards(monkeypatch):
    monkeypatch.setattr(
        llm_simple_service,
        "get_active_llm_runtime",
        lambda: _Runtime(model_name=None),
    )
    prepared_simple_chat_request = SimpleChatRequest(content="hello")
    with pytest.raises(HTTPException) as exc_missing_model:
        await llm_simple_service.stream_simple_chat(prepared_simple_chat_request)
    assert exc_missing_model.value.status_code == 400

    runtime = _Runtime(model_name="model-x")
    monkeypatch.setattr(llm_simple_service, "get_active_llm_runtime", lambda: runtime)
    monkeypatch.setattr(
        llm_simple_service, "_build_chat_completions_url", lambda _rt: None
    )
    prepared_simple_chat_request_2 = SimpleChatRequest(content="hello")
    with pytest.raises(HTTPException) as exc_no_endpoint:
        await llm_simple_service.stream_simple_chat(prepared_simple_chat_request_2)
    assert exc_no_endpoint.value.status_code == 503


def test_emit_connection_error_and_internal_error_payloads(monkeypatch):
    class _Collector:
        def record_provider_request(self, **_kwargs):
            return None

    tracer_calls: list[tuple[str, tuple, dict]] = []

    class _Tracer:
        def add_step(self, *args, **kwargs):
            tracer_calls.append(("add_step", args, kwargs))

        def set_error_metadata(self, *args, **kwargs):
            tracer_calls.append(("set_error_metadata", args, kwargs))

        def update_status(self, *args, **kwargs):
            tracer_calls.append(("update_status", args, kwargs))

    monkeypatch.setattr(
        llm_simple_service, "get_metrics_collector", lambda: _Collector()
    )
    monkeypatch.setattr(llm_simple_service, "_get_request_tracer", lambda: _Tracer())

    runtime = _Runtime("ollama")
    connection_event = llm_simple_service._emit_connection_error_and_mark_failed(
        exc=RuntimeError("offline"),
        runtime=runtime,
        request_id=uuid4(),
        model_name="model-x",
        stream_start=0.0,
    )
    internal_event = llm_simple_service._emit_internal_error_and_mark_failed(
        exc=RuntimeError("boom"),
        runtime=runtime,
        request_id=uuid4(),
        stream_start=0.0,
    )

    assert '"code": "llm_connection_error"' in connection_event
    assert '"code": "internal_error"' in internal_event
    assert any(call[0] == "set_error_metadata" for call in tracer_calls)
    assert any(
        call[0] == "update_status"
        and len(call[1]) > 1
        and call[1][1] == llm_simple_service.TraceStatus.FAILED
        for call in tracer_calls
    )


@pytest.mark.asyncio
async def test_handle_stream_http_error_returns_retry_when_retryable(monkeypatch):
    checks: list[dict[str, object]] = []

    def _retry_checker(**kwargs):
        checks.append(kwargs)
        return True

    monkeypatch.setattr(
        llm_simple_service,
        "_is_retryable_runtime_http_error",
        _retry_checker,
    )

    async def _no_sleep(_seconds: float):
        return None

    monkeypatch.setattr(llm_simple_service.asyncio, "sleep", _no_sleep)

    runtime_telemetry = {"a": 1}
    result = await llm_simple_service._handle_stream_http_error(
        exc=httpx.ConnectError("offline"),
        runtime=_Runtime("ollama"),
        request_id=uuid4(),
        model_name="model-x",
        stream_start=0.0,
        attempt=1,
        max_attempts=2,
        retry_backoff=0.0,
        chunk_count=0,
        runtime_telemetry=runtime_telemetry,
    )

    assert result == "retry"
    assert runtime_telemetry == {}
    assert checks
    assert checks[-1]["status_code"] is None


@pytest.mark.asyncio
async def test_stream_simple_chunks_handles_http_error_and_returns_error_event(
    monkeypatch,
):
    async def _boom_stream_single_attempt(**_kwargs):
        raise httpx.ConnectError("offline")
        yield "event: content\ndata: {}\n\n"  # pragma: no cover

    monkeypatch.setattr(
        llm_simple_service,
        "_stream_single_attempt",
        _boom_stream_single_attempt,
    )
    monkeypatch.setattr(
        llm_simple_service,
        "_is_retryable_runtime_http_error",
        lambda **_kwargs: False,
    )

    runtime = _Runtime("ollama")
    events = await _collect_events(
        llm_simple_service._stream_simple_chunks(
            completions_url="http://localhost/v1/chat/completions",
            payload={"messages": []},
            runtime=runtime,
            request_id=uuid4(),
            model_name="model-x",
        )
    )

    assert [name for name, _ in events] == ["start", "error"]
    assert events[1][1]["code"] == "llm_connection_error"


@pytest.mark.asyncio
async def test_stream_simple_chat_multi_runtime_path(monkeypatch):
    monkeypatch.setattr(
        llm_simple_service,
        "get_active_llm_runtime",
        lambda: _Runtime("multi_runtime"),
    )
    monkeypatch.setattr(
        llm_simple_service,
        "_build_chat_completions_url",
        lambda _rt: "http://localhost/v1/chat/completions",
    )

    async def _fake_non_stream(**_kwargs):
        yield "event: start\ndata: {}\n\n"
        yield 'event: content\ndata: {"text":"MR"}\n\n'
        yield "event: done\ndata: {}\n\n"

    monkeypatch.setattr(
        llm_simple_service,
        "_stream_simple_chunks_non_stream",
        _fake_non_stream,
    )

    response = await llm_simple_service.stream_simple_chat(
        SimpleChatRequest(content="hej")
    )
    assert isinstance(response, StreamingResponse)
    events = await _collect_response_events(response)
    assert [name for name, _ in events] == ["start", "content", "done"]


@pytest.mark.asyncio
@pytest.mark.parametrize("upstream_stream", [True, False])
async def test_simple_onnx_worker_uses_shared_http_transport_and_native_usage(
    monkeypatch, upstream_stream
):
    runtime = _Runtime("onnx")
    runtime.service_type = "onnx"
    monkeypatch.setattr(llm_simple_service.SETTINGS, "ONNX_LLM_ENABLED", True)
    captured = []
    monkeypatch.setattr(llm_simple_service, "get_active_llm_runtime", lambda: runtime)

    async def no_adapter():
        return None

    monkeypatch.setattr(llm_simple_service, "_get_active_adapter_id", no_adapter)
    usage = {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}
    if upstream_stream:

        @asynccontextmanager
        async def open_stream(**kwargs):
            captured.append(kwargs)
            yield _LinesResponse(
                [
                    "data: "
                    + json.dumps({"choices": [{"delta": {"content": "ONNX"}}]}),
                    "data: " + json.dumps({"choices": [], "usage": usage}),
                    "data: [DONE]",
                ]
            )

        monkeypatch.setattr(
            llm_simple_service.llm_simple_transport, "open_stream_response", open_stream
        )
    else:

        class Response:
            def raise_for_status(self):
                pass

            def json(self):
                return {"choices": [{"message": {"content": "ONNX"}}], "usage": usage}

        @asynccontextmanager
        async def open_response(**kwargs):
            captured.append(kwargs)
            yield Response()

        monkeypatch.setattr(
            llm_simple_service.llm_simple_transport,
            "open_stream_response",
            open_response,
        )
    response = await llm_simple_service.stream_simple_chat(
        SimpleChatRequest(
            content="hej", model="model-x", seed=0, stream=upstream_stream
        )
    )
    events = await _collect_response_events(response)
    assert [name for name, _ in events] == ["start", "content", "done"]
    assert events[-1][1] == {"usage": usage, "usage_source": "upstream"}
    assert len(captured) == 1
    assert captured[0]["completions_url"] == runtime.endpoint + "/chat/completions"
    assert captured[0]["payload"]["seed"] == 0
    assert captured[0]["payload"]["model"] == "model-x"
    assert captured[0]["payload"]["stream"] is upstream_stream
    if upstream_stream:
        assert captured[0]["payload"]["stream_options"] == {"include_usage": True}


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["onnx", "vllm", "ollama"])
@pytest.mark.parametrize("partial", [False, True])
async def test_upstream_sse_error_never_becomes_successful_done(
    monkeypatch, provider, partial
):
    """HTTP200/SSE error after text must stay failed at the public Simple boundary."""
    packets = []
    if partial:
        packets.append('data: {"choices":[{"delta":{"content":"Partial"}}]}')
    packets.extend(
        [
            'data: {"error":{"message":"private upstream details","type":"generation_cancelled"}}',
            "data: [DONE]",
        ]
    )
    calls = []

    @asynccontextmanager
    async def open_response(**kwargs):
        calls.append(kwargs)
        yield _LinesResponse(packets)

    monkeypatch.setattr(
        llm_simple_service.llm_simple_transport, "open_stream_response", open_response
    )
    tracer = _Tracer()
    monkeypatch.setattr(llm_simple_service, "_get_request_tracer", lambda: tracer)
    events = await _collect_events(
        llm_simple_service._stream_simple_chunks(
            completions_url="http://fixture/v1/chat/completions",
            payload={"messages": []},
            runtime=_Runtime(provider),
            request_id=uuid4(),
            model_name="model-x",
        )
    )
    assert [name for name, _ in events] == (
        ["start", "content", "error"] if partial else ["start", "error"]
    )
    assert events[-1][1]["code"] == "internal_error"
    assert "private upstream details" not in json.dumps(events)
    assert len(calls) == 1
    assert any(
        name == "update_status" and args[1].name == "FAILED"
        for name, args, _ in tracer.calls
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["onnx", "vllm", "ollama"])
@pytest.mark.parametrize("partial", [False, True])
async def test_incomplete_upstream_sse_never_finishes_the_public_request(
    monkeypatch, provider, partial
):
    packets = (
        ['data: {"choices":[{"delta":{"content":"Część odpowiedzi"}}]}']
        if partial
        else []
    )
    packets.append("data: malformed-json")
    calls = []

    @asynccontextmanager
    async def open_response(**kwargs):
        calls.append(kwargs)
        yield _LinesResponse(packets)

    monkeypatch.setattr(
        llm_simple_service.llm_simple_transport, "open_stream_response", open_response
    )
    tracer = _Tracer()
    monkeypatch.setattr(llm_simple_service, "_get_request_tracer", lambda: tracer)
    events = await _collect_events(
        llm_simple_service._stream_simple_chunks(
            completions_url="http://fixture/v1/chat/completions",
            payload={"messages": []},
            runtime=_Runtime(provider),
            request_id=uuid4(),
            model_name="model-x",
        )
    )
    assert [name for name, _ in events] == (
        ["start", "content", "error"] if partial else ["start", "error"]
    )
    assert len(calls) == 1  # A partial generation cannot safely be replayed.
    assert any(
        name == "update_status" and args[1].name == "FAILED"
        for name, args, _ in tracer.calls
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("finish_reason", ["stop", "length", "tool_calls"])
async def test_explicit_finish_reason_is_a_completed_generation(finish_reason):
    response = _LinesResponse(
        [
            'data: {"choices":[{"delta":{"content":"Gotowe"}}]}',
            "data: "
            + json.dumps({"choices": [{"delta": {}, "finish_reason": finish_reason}]}),
        ]
    )
    packets = [
        packet
        async for packet in llm_simple_service.llm_simple_transport.iter_stream_packets(
            response
        )
    ]
    assert packets[-1]["choices"][0]["finish_reason"] == finish_reason


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "packet",
    [
        {},
        {"choices": "stop"},
        {"choices": ["stop"]},
        {"choices": [{"finish_reason": None}]},
        {"choices": [{"finish_reason": True}]},
        {"choices": [{"finish_reason": " "}]},
    ],
)
async def test_metadata_or_invalid_finish_marker_does_not_complete_sse(packet):
    response = _LinesResponse(["data: " + json.dumps(packet)])
    with pytest.raises(
        llm_simple_service.llm_simple_transport.UpstreamStreamError,
        match="upstream_stream_incomplete",
    ):
        _ = [
            item
            async for item in llm_simple_service.llm_simple_transport.iter_stream_packets(
                response
            )
        ]


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["onnx", "vllm", "ollama"])
@pytest.mark.parametrize("finish_reason", ["abort", "error"])
@pytest.mark.parametrize("terminal", [False, True])
@pytest.mark.parametrize("prior_finish", [False, True])
async def test_failed_generation_reason_is_not_a_successful_sse_completion(
    monkeypatch, provider, finish_reason, terminal, prior_finish
):
    packets = ['data: {"choices":[{"delta":{"content":"Partial"}}]}']
    if prior_finish:
        packets.append('data: {"choices":[{"delta":{},"finish_reason":"stop"}]}')
    packets.append(
        "data: "
        + json.dumps({"choices": [{"delta": {}, "finish_reason": finish_reason}]})
    )
    if terminal:
        packets.append("data: [DONE]")
    calls = []

    @asynccontextmanager
    async def open_response(**kwargs):
        calls.append(kwargs)
        yield _LinesResponse(packets)

    monkeypatch.setattr(
        llm_simple_service.llm_simple_transport, "open_stream_response", open_response
    )
    tracer = _Tracer()
    monkeypatch.setattr(llm_simple_service, "_get_request_tracer", lambda: tracer)
    events = await _collect_events(
        llm_simple_service._stream_simple_chunks(
            completions_url="http://fixture/v1/chat/completions",
            payload={"messages": []},
            runtime=_Runtime(provider),
            request_id=uuid4(),
            model_name="model-x",
        )
    )
    assert [name for name, _ in events] == ["start", "content", "error"]
    assert events[1][1]["text"] == "Partial"
    assert len(calls) == 1
    assert any(
        name == "update_status" and args[1].name == "FAILED"
        for name, args, _ in tracer.calls
    )


@pytest.mark.parametrize("configured,expected", [("-1", -1), ("0", 0), ("5m", "5m")])
def test_simple_payload_normalizes_keep_alive_at_transport_boundary(
    monkeypatch, configured, expected
):
    from types import SimpleNamespace

    from venom_core.api.schemas.llm_simple import SimpleChatRequest

    monkeypatch.setattr(llm_simple_service.SETTINGS, "LLM_KEEP_ALIVE", configured)
    request = SimpleChatRequest(content="fixture")
    for stream in (False, True):
        payload = llm_simple_service._build_payload(
            request,
            SimpleNamespace(provider="ollama"),
            "fixture",
            [{"role": "user", "content": "fixture"}],
            stream=stream,
        )
        assert payload["keep_alive"] == expected
        assert type(payload["keep_alive"]) is type(expected)
