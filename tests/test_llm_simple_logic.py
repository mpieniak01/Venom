from __future__ import annotations

import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from tests.helpers.url_fixtures import MOCK_HTTP, http_url
from venom_core.main import app
from venom_core.services import llm_simple_service, llm_simple_stream_service
from venom_core.services.llm_simple_stream_service import SimpleStreamState


class DummyRuntime:
    def __init__(self, provider: str = "ollama", model_name: str | None = "model-x"):
        self.provider = provider
        self.model_name = model_name
        self.endpoint = http_url("localhost", 1234)
        self.service_type = "local"
        self.config_hash = "cfg"
        self.runtime_id = "rid"


class DummyTracer:
    def __init__(self):
        self.calls = []
        self.statuses = []
        self.error_meta = []

    def create_trace(self, *args, **kwargs):
        self.calls.append(("create_trace", args, kwargs))

    def set_llm_metadata(self, *args, **kwargs):
        self.calls.append(("set_llm_metadata", args, kwargs))

    def update_status(self, request_id, status):
        self.statuses.append((request_id, status))

    def add_step(self, *args, **kwargs):
        self.calls.append(("add_step", args, kwargs))

    def set_error_metadata(self, request_id, payload):
        self.error_meta.append((request_id, payload))


class ErrorStreamResponse:
    _lines: tuple[str, ...] = ()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def raise_for_status(self):
        request = httpx.Request("POST", MOCK_HTTP)
        response = httpx.Response(502, request=request, text="bad gateway")
        raise httpx.HTTPStatusError("bad", request=request, response=response)

    async def aiter_lines(self):
        # Intencjonalnie brak danych: ten test double reprezentuje odpowiedź z błędem HTTP.
        for line in self._lines:
            yield line


class DummyClientHttpStatus:
    def __init__(self, *args, **kwargs):
        # Zachowujemy kompatybilność z sygnaturą httpx.AsyncClient.
        self._args = args
        self._kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def stream(self, method: str, url: str, json: dict):
        return ErrorStreamResponse()


class DummyClientConnectionError:
    def __init__(self, *args, **kwargs):
        # Zachowujemy kompatybilność z sygnaturą httpx.AsyncClient.
        self._args = args
        self._kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def stream(self, method: str, url: str, json: dict):
        raise httpx.ConnectError("offline")


class DummyClientInternalError:
    def __init__(self, *args, **kwargs):
        # Zachowujemy kompatybilność z sygnaturą httpx.AsyncClient.
        self._args = args
        self._kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def stream(self, method: str, url: str, json: dict):
        raise RuntimeError("boom")


class DummyNonStreamResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("POST", MOCK_HTTP)
            response = httpx.Response(
                self.status_code, request=request, text="upstream failed"
            )
            raise httpx.HTTPStatusError("bad", request=request, response=response)

    def json(self):
        return self._payload


class DummyTrafficControlledClient:
    def __init__(self, *args, **kwargs):
        self._args = args
        self._kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url: str, **kwargs):
        return DummyNonStreamResponse(
            {
                "choices": [
                    {"message": {"content": "Witaj z multi_runtime"}},
                ]
            }
        )

    async def apost(self, url: str, **kwargs):
        return DummyNonStreamResponse(
            {
                "choices": [
                    {"message": {"content": "Witaj z multi_runtime"}},
                ]
            }
        )


class StreamLinesResponse:
    def __init__(self, lines):
        self._lines = lines

    async def aiter_lines(self):
        for line in self._lines:
            yield line


def _collect_sse_events(response):
    events: list[dict] = []
    for line in response.iter_lines():
        if line.startswith("event:"):
            events.append({"event": line.split(": ", 1)[1]})
            continue
        if line.startswith("data:"):
            payload = line.split(": ", 1)[1]
            if payload:
                events[-1]["data"] = json.loads(payload)
    return events


def test_get_simple_context_char_limit(monkeypatch):
    monkeypatch.setattr(llm_simple_service.SETTINGS, "VLLM_MAX_MODEL_LEN", 1024)
    assert (
        llm_simple_service._get_simple_context_char_limit(DummyRuntime("ollama"))
        is None
    )
    assert (
        llm_simple_service._get_simple_context_char_limit(DummyRuntime("vllm")) == 3072
    )
    monkeypatch.setattr(llm_simple_service.SETTINGS, "VLLM_MAX_MODEL_LEN", 0)
    assert (
        llm_simple_service._get_simple_context_char_limit(DummyRuntime("vllm")) is None
    )


def test_build_preview_messages_and_payload(monkeypatch):
    assert llm_simple_service._build_preview("abc", max_chars=2) == "ab..."
    assert llm_simple_service._build_preview("ab", max_chars=2) == "ab"

    messages = llm_simple_service._build_messages("sys", "user")
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"

    monkeypatch.setattr(llm_simple_service.SETTINGS, "LLM_KEEP_ALIVE", "30m")
    monkeypatch.setattr(llm_simple_service.SETTINGS, "OLLAMA_ENABLE_THINK", True)
    req = llm_simple_service.SimpleChatRequest(
        content="x",
        max_tokens=42,
        temperature=0.3,
        response_format={"json_schema": {"schema": {"type": "object"}}},
        tools=[{"type": "function", "function": {"name": "ping"}}],
        tool_choice="auto",
        think=True,
    )
    payload = llm_simple_service._build_payload(
        req, DummyRuntime(provider="ollama"), "m1", messages
    )
    assert payload["keep_alive"] == "30m"
    assert payload["max_tokens"] == 42
    assert payload["temperature"] == pytest.approx(0.3, abs=1e-12)
    assert payload["format"] == {"type": "object"}
    assert payload["tool_choice"] == "auto"
    assert payload["think"] is True
    assert payload["tools"][0]["function"]["name"] == "ping"
    assert payload["options"]["num_ctx"] > 0


def test_build_llm_http_error_and_stream_headers():
    request = httpx.Request("POST", MOCK_HTTP)
    response = httpx.Response(502, request=request, text="upstream error")
    exc = httpx.HTTPStatusError("bad gateway", request=request, response=response)

    error_message, error_details, error_payload = (
        llm_simple_service._build_llm_http_error(exc, DummyRuntime(), "model-x")
    )
    headers = llm_simple_service._build_streaming_headers("rid", "sid")

    assert "LLM HTTP 502" in error_message
    assert error_details["status_code"] == 502
    assert error_payload["code"] == "llm_http_error"
    assert headers["X-Request-Id"] == "rid"
    assert headers["X-Session-Id"] == "sid"


@pytest.mark.asyncio
async def test_read_http_error_response_text_returns_body():
    request = httpx.Request("POST", MOCK_HTTP)
    response = httpx.Response(502, request=request, content=b"upstream error")
    text = await llm_simple_service._read_http_error_response_text(response)
    assert "upstream error" in text


def test_trim_user_content_for_runtime_adds_trace_step(monkeypatch):
    monkeypatch.setattr(llm_simple_service.SETTINGS, "VLLM_MAX_MODEL_LEN", 64)
    captured = {"steps": []}

    class DummyTracer:
        def add_step(self, *args, **kwargs):
            captured["steps"].append((args, kwargs))

    monkeypatch.setattr(llm_simple_service, "get_request_tracer", lambda: DummyTracer())

    trimmed = llm_simple_service._trim_user_content_for_runtime(
        "x" * 200, "sys", DummyRuntime("vllm"), request_id="rid"
    )
    assert len(trimmed) < 200
    assert captured["steps"]


def test_extract_sse_contents_filters_invalid_packets():
    packet = {
        "choices": [
            {"delta": {"content": "A"}},
            {"delta": {"content": ""}},
            {"delta": "not-dict"},
            {},
        ]
    }
    assert llm_simple_service._extract_sse_contents(packet) == ["A"]


def test_extract_sse_tool_calls_and_telemetry():
    packet = {
        "choices": [{"delta": {"tool_calls": [{"id": "c1"}]}}],
        "load_duration": 3_000_000,
        "prompt_eval_count": 12,
        "eval_count": 21,
    }
    tool_calls = llm_simple_service._extract_sse_tool_calls(packet)
    telemetry = llm_simple_service._extract_runtime_telemetry(packet)
    assert tool_calls == [{"id": "c1"}]
    assert telemetry["prompt_eval_count"] == 12
    assert llm_simple_service._normalize_ns_to_ms(3_000_000) == 3.0


@pytest.mark.asyncio
async def test_iter_stream_contents_parses_and_stops_on_done():
    resp = StreamLinesResponse(
        [
            "",
            "event: ignored",
            "data:",
            "data: not-json",
            'data: {"choices":[{"delta":{"content":"A"}}]}',
            "data: [DONE]",
            'data: {"choices":[{"delta":{"content":"B"}}]}',
        ]
    )
    chunks: list[str] = []
    async for packet in llm_simple_service._iter_stream_packets(resp):
        chunks.extend(llm_simple_service._extract_sse_contents(packet))
    assert chunks == ["A"]


def test_trace_helpers_and_error_metadata(monkeypatch):
    tracer = DummyTracer()
    monkeypatch.setattr(llm_simple_service, "get_request_tracer", lambda: tracer)

    request = llm_simple_service.SimpleChatRequest(content="hello", session_id="s1")
    llm_simple_service._trace_simple_request("rid", request, DummyRuntime(), "model")
    llm_simple_service._trace_context_preview(
        "rid", [{"role": "user", "content": "x" * 2100}]
    )
    llm_simple_service._trace_first_chunk("rid", 0.0, "content")
    llm_simple_service._trace_stream_completion("rid", "abc", 2, 0.0)
    llm_simple_service._record_simple_error(
        "rid",
        error_code="e1",
        error_message="msg",
        error_details={"x": 1},
        retryable=False,
    )

    assert tracer.calls
    assert tracer.statuses
    assert tracer.error_meta


def test_stream_simple_chat_returns_400_without_model(monkeypatch):
    monkeypatch.setattr(
        llm_simple_service,
        "get_active_llm_runtime",
        lambda: DummyRuntime(model_name=None),
    )
    client = TestClient(app)

    response = client.post("/api/v1/llm/simple/stream", json={"content": "hello"})
    assert response.status_code == 400


def test_stream_simple_chat_returns_503_without_endpoint(monkeypatch):
    monkeypatch.setattr(
        llm_simple_service, "get_active_llm_runtime", lambda: DummyRuntime()
    )
    monkeypatch.setattr(
        llm_simple_service, "_build_chat_completions_url", lambda _rt: None
    )
    client = TestClient(app)

    response = client.post("/api/v1/llm/simple/stream", json={"content": "hello"})
    assert response.status_code == 503


def test_stream_simple_chat_http_status_error_emits_error_event(monkeypatch):
    monkeypatch.setattr(
        llm_simple_service, "get_active_llm_runtime", lambda: DummyRuntime()
    )
    monkeypatch.setattr(
        llm_simple_service,
        "_build_chat_completions_url",
        lambda _rt: http_url("localhost", path="/v1/chat/completions"),
    )
    monkeypatch.setattr("httpx.AsyncClient", DummyClientHttpStatus)
    client = TestClient(app)

    with client.stream(
        "POST",
        "/api/v1/llm/simple/stream",
        json={"content": "hello"},
    ) as response:
        assert response.status_code == 200
        events = _collect_sse_events(response)

    assert events[0]["event"] == "start"
    assert events[1]["event"] == "error"
    assert events[1]["data"]["code"] == "llm_http_error"


def test_stream_simple_chat_connection_error_emits_error_event(monkeypatch):
    monkeypatch.setattr(
        llm_simple_service, "get_active_llm_runtime", lambda: DummyRuntime()
    )
    monkeypatch.setattr(
        llm_simple_service,
        "_build_chat_completions_url",
        lambda _rt: http_url("localhost", path="/v1/chat/completions"),
    )
    monkeypatch.setattr("httpx.AsyncClient", DummyClientConnectionError)
    client = TestClient(app)

    with client.stream(
        "POST",
        "/api/v1/llm/simple/stream",
        json={"content": "hello"},
    ) as response:
        assert response.status_code == 200
        events = _collect_sse_events(response)

    assert events[0]["event"] == "start"
    assert events[1]["event"] == "error"
    assert events[1]["data"]["code"] == "llm_connection_error"


def test_stream_simple_chat_internal_error_emits_error_event(monkeypatch):
    monkeypatch.setattr(
        llm_simple_service, "get_active_llm_runtime", lambda: DummyRuntime()
    )
    monkeypatch.setattr(
        llm_simple_service,
        "_build_chat_completions_url",
        lambda _rt: http_url("localhost", path="/v1/chat/completions"),
    )
    monkeypatch.setattr("httpx.AsyncClient", DummyClientInternalError)
    client = TestClient(app)

    with client.stream(
        "POST",
        "/api/v1/llm/simple/stream",
        json={"content": "hello"},
    ) as response:
        events = _collect_sse_events(response)
    assert events[1]["data"]["code"] == "internal_error"


def test_stream_simple_chat_onnx_streams_without_http_endpoint(monkeypatch):
    runtime = DummyRuntime(provider="onnx")
    runtime.service_type = "onnx"
    runtime.endpoint = None
    monkeypatch.setattr(llm_simple_service, "get_active_llm_runtime", lambda: runtime)
    monkeypatch.setattr(
        llm_simple_service, "_build_chat_completions_url", lambda _rt: None
    )

    class FakeOnnxClient:
        def stream_generate(self, **_kwargs):
            yield "A"
            yield "B"

    monkeypatch.setattr(llm_simple_service, "OnnxLlmClient", lambda: FakeOnnxClient())
    client = TestClient(app)

    with client.stream(
        "POST",
        "/api/v1/llm/simple/stream",
        json={"content": "hello"},
    ) as response:
        assert response.status_code == 200
        events = _collect_sse_events(response)

    assert [event["event"] for event in events] == [
        "start",
        "content",
        "content",
        "done",
    ]
    assert events[1]["data"]["text"] == "A"
    assert events[2]["data"]["text"] == "B"


def test_stream_simple_chat_multi_runtime_uses_non_stream_upstream(monkeypatch):
    runtime = DummyRuntime(provider="multi_runtime")
    monkeypatch.setattr(llm_simple_service, "get_active_llm_runtime", lambda: runtime)
    monkeypatch.setattr(
        llm_simple_service,
        "_build_chat_completions_url",
        lambda _rt: http_url("localhost", path="/v1/chat/completions"),
    )

    @asynccontextmanager
    async def _fake_open_stream_response(**_kwargs):
        yield DummyNonStreamResponse(
            {
                "choices": [
                    {"message": {"content": "Witaj z multi_runtime"}},
                ]
            }
        )

    monkeypatch.setattr(
        llm_simple_service.llm_simple_transport,
        "open_stream_response",
        _fake_open_stream_response,
    )
    client = TestClient(app)

    with client.stream(
        "POST",
        "/api/v1/llm/simple/stream",
        json={"content": "hello"},
    ) as response:
        assert response.status_code == 200
        events = _collect_sse_events(response)

    assert [event["event"] for event in events] == [
        "start",
        "content",
        "done",
    ]
    assert events[1]["data"]["text"] == "Witaj z multi_runtime"


@pytest.mark.asyncio
async def test_service_handles_missing_model_and_endpoint(monkeypatch):
    runtime = DummyRuntime(provider="ollama", model_name=None)
    monkeypatch.setattr(llm_simple_service, "get_active_llm_runtime", lambda: runtime)

    async def _no_adapter():
        return None

    monkeypatch.setattr(llm_simple_service, "_get_active_adapter_id", _no_adapter)

    with pytest.raises(llm_simple_service.HTTPException) as missing_model:
        await llm_simple_service.stream_simple_chat(
            llm_simple_service.SimpleChatRequest(content="x")
        )
    assert missing_model.value.status_code == 400

    runtime = DummyRuntime(provider="ollama", model_name="model-x")
    runtime.endpoint = None
    monkeypatch.setattr(llm_simple_service, "get_active_llm_runtime", lambda: runtime)
    monkeypatch.setattr(llm_simple_service, "_get_active_adapter_id", _no_adapter)
    monkeypatch.setattr(
        llm_simple_service, "_build_chat_completions_url", lambda _rt: None
    )
    with pytest.raises(llm_simple_service.HTTPException) as missing_endpoint:
        await llm_simple_service.stream_simple_chat(
            llm_simple_service.SimpleChatRequest(content="x")
        )
    assert missing_endpoint.value.status_code == 503


@pytest.mark.asyncio
async def test_service_non_stream_invalid_json_path(monkeypatch):
    class _BadResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return ["invalid"]

    @asynccontextmanager
    async def _fake_open_stream_response(**_kwargs):
        yield _BadResponse()

    monkeypatch.setattr(
        llm_simple_service.llm_simple_transport,
        "open_stream_response",
        _fake_open_stream_response,
    )

    events = []
    async for event in llm_simple_service._stream_simple_chunks_non_stream(
        completions_url="http://localhost/v1/chat/completions",
        payload={"messages": []},
        runtime=DummyRuntime(provider="multi_runtime"),
        request_id=llm_simple_service.uuid4(),
        model_name="model-x",
    ):
        events.append(event)

    assert events[0].startswith("event: start")
    assert events[-1].startswith("event: done")


def test_service_resolve_post_attempt_action_retry_and_done(monkeypatch):
    state_retry = SimpleStreamState(chunks=[], retry_requested=True)
    action_retry = llm_simple_service._resolve_post_attempt_action(
        runtime=DummyRuntime(),
        request_id=llm_simple_service.uuid4(),
        stream_start=0.0,
        state=state_retry,
        runtime_telemetry={},
    )
    assert action_retry == "retry"
    assert llm_simple_service._apply_post_attempt_action(action_retry) == (True, False)

    collector_calls = []
    monkeypatch.setattr(
        llm_simple_service,
        "get_metrics_collector",
        lambda: SimpleNamespace(
            record_provider_request=lambda **kwargs: collector_calls.append(kwargs),
            record_runtime_sample=lambda **_kwargs: None,
        ),
    )
    state_done = SimpleStreamState(chunks=["A"], chunk_count=1, completed=True)
    action_done = llm_simple_service._resolve_post_attempt_action(
        runtime=DummyRuntime(),
        request_id=llm_simple_service.uuid4(),
        stream_start=0.0,
        state=state_done,
        runtime_telemetry={},
    )
    assert action_done == "done"
    assert llm_simple_service._apply_post_attempt_action(action_done) == (False, True)
    assert collector_calls and collector_calls[-1]["success"] is True


@pytest.mark.asyncio
async def test_service_onnx_stream_success_and_error(monkeypatch):
    collector_calls = []
    monkeypatch.setattr(
        llm_simple_service,
        "get_metrics_collector",
        lambda: SimpleNamespace(
            record_provider_request=lambda **kwargs: collector_calls.append(kwargs),
            record_runtime_sample=lambda **_kwargs: None,
        ),
    )
    monkeypatch.setattr(
        llm_simple_service,
        "_get_onnx_simple_client",
        lambda: SimpleNamespace(stream_generate=lambda **_kwargs: iter(())),
    )

    async def _fake_stream_ok(*_args, **_kwargs):
        yield "A"

    monkeypatch.setattr(llm_simple_service, "_aiter_sync_onnx_stream", _fake_stream_ok)
    ok_events = []
    async for event in llm_simple_service._stream_simple_chunks_onnx(
        runtime=DummyRuntime(provider="onnx"),
        request_id=llm_simple_service.uuid4(),
        model_name="onnx-model",
        messages=[{"role": "user", "content": "x"}],
        max_tokens=8,
        temperature=0.2,
    ):
        ok_events.append(event)
    assert ok_events[-1].startswith("event: done")

    async def _fake_stream_boom(*_args, **_kwargs):
        raise RuntimeError("boom")
        yield  # pragma: no cover

    monkeypatch.setattr(
        llm_simple_service, "_aiter_sync_onnx_stream", _fake_stream_boom
    )
    err_events = []
    async for event in llm_simple_service._stream_simple_chunks_onnx(
        runtime=DummyRuntime(provider="onnx"),
        request_id=llm_simple_service.uuid4(),
        model_name="onnx-model",
        messages=[{"role": "user", "content": "x"}],
        max_tokens=8,
        temperature=0.2,
    ):
        err_events.append(event)
    assert err_events[-1].startswith("event: error")


def test_service_helper_branches_and_emitters(monkeypatch):
    class _Tracer:
        def __init__(self):
            self.steps = []
            self.errors = []
            self.status = []

        def add_step(self, *args, **kwargs):
            self.steps.append((args, kwargs))

        def set_error_metadata(self, *args, **kwargs):
            self.errors.append((args, kwargs))

        def update_status(self, *args, **kwargs):
            self.status.append((args, kwargs))

    tracer = _Tracer()
    monkeypatch.setattr(llm_simple_service, "_get_request_tracer", lambda: tracer)

    assert (
        llm_simple_service._get_simple_context_char_limit(DummyRuntime("ollama"))
        is None
    )
    monkeypatch.setattr(llm_simple_service.SETTINGS, "VLLM_MAX_MODEL_LEN", 128)
    assert (
        llm_simple_service._get_simple_context_char_limit(DummyRuntime("vllm"))
        is not None
    )
    monkeypatch.setattr(llm_simple_service.SETTINGS, "VLLM_MAX_MODEL_LEN", 0)
    assert (
        llm_simple_service._get_simple_context_char_limit(DummyRuntime("vllm")) is None
    )

    assert llm_simple_service._call_tracer(None, "add_step") is False
    assert llm_simple_service._build_preview("abcd", max_chars=2) == "ab..."

    request_id = uuid4()
    llm_simple_service._trace_context_preview(
        request_id,
        [{"role": "user", "content": "x" * 2500}],
    )
    llm_simple_service._record_simple_error(
        request_id,
        error_code="code",
        error_message="msg",
        error_details={"k": "v"},
    )

    monkeypatch.setattr(
        llm_simple_service,
        "_get_simple_context_char_limit",
        lambda _rt: 16,
    )
    trimmed = llm_simple_service._trim_user_content_for_runtime(
        "x" * 200, "sys", DummyRuntime("vllm"), request_id
    )
    assert len(trimmed) < 200
    assert tracer.steps

    collector_calls = []
    monkeypatch.setattr(
        llm_simple_service,
        "get_metrics_collector",
        lambda: SimpleNamespace(
            record_provider_request=lambda **kwargs: collector_calls.append(kwargs),
            record_runtime_sample=lambda **_kwargs: None,
        ),
    )
    emit1 = llm_simple_service._emit_connection_error_and_mark_failed(
        exc=httpx.ConnectError("offline"),
        runtime=DummyRuntime(),
        request_id=request_id,
        model_name="model-x",
        stream_start=0.0,
    )
    emit2 = llm_simple_service._emit_internal_error_and_mark_failed(
        exc=RuntimeError("boom"),
        runtime=DummyRuntime(),
        request_id=request_id,
        stream_start=0.0,
    )
    assert emit1.startswith("event: error")
    assert emit2.startswith("event: error")
    assert collector_calls


@pytest.mark.asyncio
async def test_service_stream_single_attempt_wrapper_covers_retry_config(monkeypatch):
    captured = {}

    async def _fake_impl(**kwargs):
        captured.update(kwargs)
        yield 'event: content\ndata: {"text":"x"}\n\n'
        kwargs["state"].retry_requested = True

    monkeypatch.setattr(llm_simple_service, "_stream_single_attempt_impl", _fake_impl)
    monkeypatch.setattr(
        llm_simple_service.llm_simple_transport,
        "httpx_module",
        lambda: httpx,
    )

    state = SimpleStreamState(chunks=[])
    runtime_telemetry = {"prompt_eval_count": 3}
    events = []
    async for event in llm_simple_service._stream_single_attempt(
        completions_url="http://localhost/v1/chat/completions",
        payload={"messages": []},
        runtime=DummyRuntime("ollama"),
        request_id=uuid4(),
        model_name="model-x",
        stream_start=0.0,
        attempt=1,
        max_attempts=2,
        retry_backoff=0.1,
        state=state,
        runtime_telemetry=runtime_telemetry,
    ):
        events.append(event)

    assert events and events[0].startswith("event: content")
    assert captured["retry"].max_attempts == 2
    assert runtime_telemetry == {}


def test_service_release_onnx_client_handles_close_error(monkeypatch):
    class _Client:
        def __init__(self, boom: bool):
            self.boom = boom
            self.closed = False

        def close(self):
            self.closed = True
            if self.boom:
                raise RuntimeError("close failed")

    client_ok = _Client(False)
    monkeypatch.setattr(llm_simple_service, "_ONNX_SIMPLE_CLIENT", client_ok)
    llm_simple_service.release_onnx_simple_client()
    assert client_ok.closed is True

    client_boom = _Client(True)
    monkeypatch.setattr(llm_simple_service, "_ONNX_SIMPLE_CLIENT", client_boom)
    llm_simple_service.release_onnx_simple_client()
    assert client_boom.closed is True


@pytest.mark.asyncio
async def test_service_non_stream_http_status_error_branch(monkeypatch):
    request = httpx.Request("POST", MOCK_HTTP)
    response = httpx.Response(502, request=request, text="upstream failed")

    class _BadResponse:
        def raise_for_status(self):
            raise httpx.HTTPStatusError("bad", request=request, response=response)

        def json(self):
            return {}

    @asynccontextmanager
    async def _fake_open_stream_response(**_kwargs):
        yield _BadResponse()

    monkeypatch.setattr(
        llm_simple_service.llm_simple_transport,
        "open_stream_response",
        _fake_open_stream_response,
    )

    events = []
    async for event in llm_simple_service._stream_simple_chunks_non_stream(
        completions_url="http://localhost/v1/chat/completions",
        payload={"messages": []},
        runtime=DummyRuntime(),
        request_id=uuid4(),
        model_name="model-x",
    ):
        events.append(event)
    assert events[-1].startswith("event: error")


@pytest.mark.asyncio
async def test_service_handle_stream_http_error_retry_and_emit(monkeypatch):
    request = httpx.Request("POST", MOCK_HTTP)
    response = httpx.Response(503, request=request, text="retry me")
    err = httpx.HTTPStatusError("bad", request=request, response=response)

    monkeypatch.setattr(
        llm_simple_service,
        "_is_retryable_runtime_http_error",
        lambda **kwargs: kwargs["attempt_no"] < kwargs["max_retries"],
    )
    retry_result = await llm_simple_service._handle_stream_http_error(
        exc=err,
        runtime=DummyRuntime("ollama"),
        request_id=uuid4(),
        model_name="model-x",
        stream_start=0.0,
        attempt=1,
        max_attempts=2,
        retry_backoff=0.0,
        chunk_count=0,
        runtime_telemetry={},
    )
    assert retry_result == "retry"

    emit_result = await llm_simple_service._handle_stream_http_error(
        exc=err,
        runtime=DummyRuntime("ollama"),
        request_id=uuid4(),
        model_name="model-x",
        stream_start=0.0,
        attempt=2,
        max_attempts=2,
        retry_backoff=0.0,
        chunk_count=0,
        runtime_telemetry={},
    )
    assert emit_result.startswith("event: error")


def test_stream_service_packet_update_and_post_attempt_branches() -> None:
    state = llm_simple_stream_service.SimpleStreamState(chunks=[])
    first_chunk_seen = {"called": 0}

    def _on_first(_content: str) -> None:
        first_chunk_seen["called"] += 1

    events = llm_simple_stream_service.update_stream_state_from_packet(
        packet={"choices": [{"delta": {"content": "A"}}]},
        runtime=SimpleNamespace(provider="ollama"),
        state=state,
        runtime_telemetry=None,
        extract_runtime_telemetry_fn=None,
        extract_sse_tool_calls_fn=lambda _packet: [{"id": "t1"}],
        extract_sse_contents_fn=lambda _packet: ["A"],
        on_first_chunk_fn=_on_first,
        ollama_telemetry={},
        extract_ollama_telemetry_fn=lambda _packet: {"eval_count": 1},
    )
    assert first_chunk_seen["called"] == 1
    assert any(event.startswith("event: tool_calls") for event in events)
    assert any(event.startswith("event: content") for event in events)

    stop_action = llm_simple_stream_service.resolve_post_attempt_action(
        state=llm_simple_stream_service.SimpleStreamState(chunks=[], failed=True),
        finalize_success_fn=lambda: None,
    )
    unknown_apply = llm_simple_stream_service.apply_post_attempt_action("stop")
    assert stop_action == "stop"
    assert unknown_apply == (False, False)
