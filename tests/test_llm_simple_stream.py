"""Testy poprawności dla trybu prostego LLM stream."""

from __future__ import annotations

import asyncio
import json
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from venom_core.api.routes import llm_simple as llm_simple_routes
from venom_core.core.tracer import RequestTracer, TraceStatus
from venom_core.main import app


class DummyRuntime:
    def __init__(self):
        self.provider = "ollama"
        self.model_name = "gemma3:latest"
        self.endpoint = "http://localhost:11434/v1"
        self.config_hash = "dummy-hash"
        self.runtime_id = "dummy-runtime"


class DummyStreamResponse:
    def __init__(self, lines: list[str]):
        self._lines = lines

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def aiter_lines(self):
        for line in self._lines:
            yield line

    def raise_for_status(self):
        return None


class DummyAsyncClient:
    def __init__(self, *args, **kwargs):
        self._lines = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def stream(self, method: str, url: str, json: dict):
        self._lines = [
            'data: {"choices":[{"delta":{"content":"Witaj "}}]}',
            'data: {"choices":[{"delta":{"content":"świecie"}}]}',
            "data: [DONE]",
        ]
        return DummyStreamResponse(self._lines)


class RetryableHTTPStatusStreamResponse:
    def __init__(self, *, status_code: int):
        self.status_code = status_code

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def raise_for_status(self):
        req = httpx.Request("POST", "http://localhost:11434/v1/chat/completions")
        resp = httpx.Response(self.status_code, request=req, text="temporary upstream")
        raise httpx.HTTPStatusError("upstream error", request=req, response=resp)

    async def aiter_lines(self):
        if False:
            yield ""  # pragma: no cover


class SuccessfulStreamResponse:
    def __init__(self, lines: list[str]):
        self._lines = lines

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def raise_for_status(self):
        return None

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class SequencedAsyncClient:
    responses: list[object] = []
    attempt_count = 0

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def stream(self, method: str, url: str, json: dict):
        idx = SequencedAsyncClient.attempt_count
        SequencedAsyncClient.attempt_count += 1
        if idx >= len(SequencedAsyncClient.responses):
            idx = len(SequencedAsyncClient.responses) - 1
        return SequencedAsyncClient.responses[idx]


@pytest.fixture
def simple_client(monkeypatch):
    tracer = RequestTracer()
    monkeypatch.setattr(
        llm_simple_routes.system_deps,
        "get_request_tracer",
        lambda: tracer,
    )

    monkeypatch.setattr(
        "venom_core.api.routes.llm_simple.get_active_llm_runtime",
        lambda: DummyRuntime(),
    )
    monkeypatch.setattr(
        "venom_core.api.routes.llm_simple._build_chat_completions_url",
        lambda runtime: "http://localhost:11434/v1/chat/completions",
    )
    monkeypatch.setattr("httpx.AsyncClient", DummyAsyncClient)

    client = TestClient(app)
    yield client, tracer


def test_simple_stream_emits_chunks_and_traces(simple_client):
    client, tracer = simple_client

    with client.stream(
        "POST",
        "/api/v1/llm/simple/stream",
        json={"content": "Test", "session_id": "session-123"},
    ) as response:
        assert response.status_code == 200
        events = []
        for line in response.iter_lines():
            if line.startswith("event:"):
                events.append({"event": line.split(": ", 1)[1]})
            elif line.startswith("data:"):
                data_str = line.split(": ", 1)[1]
                if data_str:
                    events[-1]["data"] = json.loads(data_str)

    assert events[0]["event"] == "start"
    assert events[1]["event"] == "content"
    assert events[1]["data"]["text"] == "Witaj "
    assert events[2]["event"] == "content"
    assert events[2]["data"]["text"] == "świecie"
    assert events[3]["event"] == "done"

    request_id = response.headers.get("x-request-id")
    assert request_id
    assert response.headers.get("x-session-id") == "session-123"
    assert "text/event-stream" in response.headers.get("content-type")

    trace = tracer.get_trace(UUID(request_id))
    assert trace is not None
    assert trace.session_id == "session-123"
    assert trace.status == TraceStatus.COMPLETED
    assert trace.steps
    assert any(step.action == "request" for step in trace.steps)
    assert any(step.action == "response" for step in trace.steps)


def _parse_sse_event(frame: str) -> tuple[str, dict]:
    event_name = ""
    payload: dict = {}
    for line in frame.strip().splitlines():
        if line.startswith("event: "):
            event_name = line.split(": ", 1)[1]
        elif line.startswith("data: "):
            raw_payload = line.split(": ", 1)[1]
            payload = json.loads(raw_payload) if raw_payload else {}
    return event_name, payload


@pytest.mark.asyncio
async def test_stream_simple_chunks_retries_on_503_then_succeeds(monkeypatch):
    runtime = DummyRuntime()
    monkeypatch.setattr(llm_simple_routes.SETTINGS, "OLLAMA_RETRY_MAX_ATTEMPTS", 3)
    monkeypatch.setattr(
        llm_simple_routes.SETTINGS, "OLLAMA_RETRY_BACKOFF_SECONDS", 0.01
    )

    sleep_calls: list[float] = []

    async def _fake_sleep(delay: float):
        sleep_calls.append(delay)

    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)
    SequencedAsyncClient.responses = [
        RetryableHTTPStatusStreamResponse(status_code=503),
        SuccessfulStreamResponse(
            [
                'data: {"choices":[{"delta":{"content":"ok"}}]}',
                "data: [DONE]",
            ]
        ),
    ]
    SequencedAsyncClient.attempt_count = 0
    monkeypatch.setattr("httpx.AsyncClient", SequencedAsyncClient)

    stream = llm_simple_routes._stream_simple_chunks(
        completions_url="http://localhost:11434/v1/chat/completions",
        payload={"model": "gemma3", "messages": [], "stream": True},
        runtime=runtime,
        request_id=uuid4(),
        model_name="gemma3",
    )

    events: list[tuple[str, dict]] = []
    async for frame in stream:
        events.append(_parse_sse_event(frame))

    assert SequencedAsyncClient.attempt_count == 2
    assert sleep_calls == [0.01]
    assert [name for name, _ in events] == ["start", "content", "done"]


@pytest.mark.asyncio
async def test_stream_simple_chunks_stops_after_max_attempts(monkeypatch):
    runtime = DummyRuntime()
    monkeypatch.setattr(llm_simple_routes.SETTINGS, "OLLAMA_RETRY_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(
        llm_simple_routes.SETTINGS, "OLLAMA_RETRY_BACKOFF_SECONDS", 0.01
    )

    sleep_calls: list[float] = []

    async def _fake_sleep(delay: float):
        sleep_calls.append(delay)

    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)
    SequencedAsyncClient.responses = [
        RetryableHTTPStatusStreamResponse(status_code=503),
        RetryableHTTPStatusStreamResponse(status_code=503),
    ]
    SequencedAsyncClient.attempt_count = 0
    monkeypatch.setattr("httpx.AsyncClient", SequencedAsyncClient)

    stream = llm_simple_routes._stream_simple_chunks(
        completions_url="http://localhost:11434/v1/chat/completions",
        payload={"model": "gemma3", "messages": [], "stream": True},
        runtime=runtime,
        request_id=uuid4(),
        model_name="gemma3",
    )

    events: list[tuple[str, dict]] = []
    async for frame in stream:
        events.append(_parse_sse_event(frame))

    assert SequencedAsyncClient.attempt_count == 2
    assert sleep_calls == [0.01]
    assert [name for name, _ in events] == ["start", "error"]
    assert events[1][1]["code"] == "llm_http_error"
