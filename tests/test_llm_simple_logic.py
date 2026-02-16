from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from tests.helpers.url_fixtures import MOCK_HTTP, http_url
from venom_core.api.routes import llm_simple as llm_simple_routes
from venom_core.main import app


class DummyRuntime:
    def __init__(self, provider: str = "ollama", model_name: str | None = "model-x"):
        self.provider = provider
        self.model_name = model_name
        self.endpoint = http_url("localhost", 1234)
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
    monkeypatch.setattr(llm_simple_routes.SETTINGS, "VLLM_MAX_MODEL_LEN", 1024)
    assert (
        llm_simple_routes._get_simple_context_char_limit(DummyRuntime("ollama")) is None
    )
    assert (
        llm_simple_routes._get_simple_context_char_limit(DummyRuntime("vllm")) == 3072
    )
    monkeypatch.setattr(llm_simple_routes.SETTINGS, "VLLM_MAX_MODEL_LEN", 0)
    assert (
        llm_simple_routes._get_simple_context_char_limit(DummyRuntime("vllm")) is None
    )


def test_build_preview_messages_and_payload(monkeypatch):
    assert llm_simple_routes._build_preview("abc", max_chars=2) == "ab..."
    assert llm_simple_routes._build_preview("ab", max_chars=2) == "ab"

    messages = llm_simple_routes._build_messages("sys", "user")
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"

    monkeypatch.setattr(llm_simple_routes.SETTINGS, "LLM_KEEP_ALIVE", "30m")
    monkeypatch.setattr(llm_simple_routes.SETTINGS, "OLLAMA_ENABLE_THINK", True)
    req = llm_simple_routes.SimpleChatRequest(
        content="x",
        max_tokens=42,
        temperature=0.3,
        response_format={"json_schema": {"schema": {"type": "object"}}},
        tools=[{"type": "function", "function": {"name": "ping"}}],
        tool_choice="auto",
        think=True,
    )
    payload = llm_simple_routes._build_payload(
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
        llm_simple_routes._build_llm_http_error(exc, DummyRuntime(), "model-x")
    )
    headers = llm_simple_routes._build_streaming_headers("rid", "sid")

    assert "LLM HTTP 502" in error_message
    assert error_details["status_code"] == 502
    assert error_payload["code"] == "llm_http_error"
    assert headers["X-Request-Id"] == "rid"
    assert headers["X-Session-Id"] == "sid"


@pytest.mark.asyncio
async def test_read_http_error_response_text_returns_body():
    request = httpx.Request("POST", MOCK_HTTP)
    response = httpx.Response(502, request=request, content=b"upstream error")
    text = await llm_simple_routes._read_http_error_response_text(response)
    assert "upstream error" in text


def test_trim_user_content_for_runtime_adds_trace_step(monkeypatch):
    monkeypatch.setattr(llm_simple_routes.SETTINGS, "VLLM_MAX_MODEL_LEN", 64)
    captured = {"steps": []}

    class DummyTracer:
        def add_step(self, *args, **kwargs):
            captured["steps"].append((args, kwargs))

    monkeypatch.setattr(llm_simple_routes, "_request_tracer", DummyTracer())

    trimmed = llm_simple_routes._trim_user_content_for_runtime(
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
    assert llm_simple_routes._extract_sse_contents(packet) == ["A"]


def test_extract_sse_tool_calls_and_telemetry():
    packet = {
        "choices": [{"delta": {"tool_calls": [{"id": "c1"}]}}],
        "load_duration": 3_000_000,
        "prompt_eval_count": 12,
        "eval_count": 21,
    }
    tool_calls = llm_simple_routes._extract_sse_tool_calls(packet)
    telemetry = llm_simple_routes._extract_ollama_telemetry(packet)
    assert tool_calls == [{"id": "c1"}]
    assert telemetry["prompt_eval_count"] == 12
    assert llm_simple_routes._normalize_ns_to_ms(3_000_000) == 3.0


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
    chunks = [c async for c in llm_simple_routes._iter_stream_contents(resp)]
    assert chunks == ["A"]


def test_trace_helpers_and_error_metadata(monkeypatch):
    tracer = DummyTracer()
    monkeypatch.setattr(llm_simple_routes, "_request_tracer", tracer)

    request = llm_simple_routes.SimpleChatRequest(content="hello", session_id="s1")
    llm_simple_routes._trace_simple_request("rid", request, DummyRuntime(), "model")
    llm_simple_routes._trace_context_preview(
        "rid", [{"role": "user", "content": "x" * 2100}]
    )
    llm_simple_routes._trace_first_chunk("rid", 0.0, "content")
    llm_simple_routes._trace_stream_completion("rid", "abc", 2, 0.0)
    llm_simple_routes._record_simple_error(
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
        llm_simple_routes,
        "get_active_llm_runtime",
        lambda: DummyRuntime(model_name=None),
    )
    client = TestClient(app)

    response = client.post("/api/v1/llm/simple/stream", json={"content": "hello"})
    assert response.status_code == 400


def test_stream_simple_chat_returns_503_without_endpoint(monkeypatch):
    monkeypatch.setattr(
        llm_simple_routes, "get_active_llm_runtime", lambda: DummyRuntime()
    )
    monkeypatch.setattr(
        llm_simple_routes, "_build_chat_completions_url", lambda _rt: None
    )
    client = TestClient(app)

    response = client.post("/api/v1/llm/simple/stream", json={"content": "hello"})
    assert response.status_code == 503


def test_stream_simple_chat_http_status_error_emits_error_event(monkeypatch):
    monkeypatch.setattr(
        llm_simple_routes, "get_active_llm_runtime", lambda: DummyRuntime()
    )
    monkeypatch.setattr(
        llm_simple_routes,
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
        llm_simple_routes, "get_active_llm_runtime", lambda: DummyRuntime()
    )
    monkeypatch.setattr(
        llm_simple_routes,
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
        llm_simple_routes, "get_active_llm_runtime", lambda: DummyRuntime()
    )
    monkeypatch.setattr(
        llm_simple_routes,
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
