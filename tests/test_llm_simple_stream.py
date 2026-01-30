"""Testy poprawności dla trybu prostego LLM stream."""

from __future__ import annotations

from uuid import UUID

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


@pytest.fixture
def simple_client(monkeypatch):
    tracer = RequestTracer()
    llm_simple_routes.set_dependencies(tracer)

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

    llm_simple_routes.set_dependencies(None)


def test_simple_stream_emits_chunks_and_traces(simple_client):
    client, tracer = simple_client

    with client.stream(
        "POST",
        "/api/v1/llm/simple/stream",
        json={"content": "Test", "session_id": "session-123"},
    ) as response:
        assert response.status_code == 200
        # Parse SSE events
        events = []
        for line in response.iter_lines():
            if line.startswith("event:"):
                events.append({"event": line.split(": ", 1)[1]})
            elif line.startswith("data:"):
                import json

                data_str = line.split(": ", 1)[1]
                if data_str:
                    events[-1]["data"] = json.loads(data_str)

    # Verify events
    # Expected sequence: start -> content -> content -> done
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
