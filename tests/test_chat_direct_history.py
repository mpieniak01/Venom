"""Direct uses the host history: no provider calls, extra store, or billing bypass."""

import asyncio
import json
from contextlib import asynccontextmanager
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from tests import test_openrouter_runtime as openrouter_fixtures
from venom_core.api.dependencies import get_session_store
from venom_core.api.routes import llm_simple, memory
from venom_core.api.schemas.llm_simple import SimpleChatRequest
from venom_core.services import (
    chat_material_payload,
    llm_simple_service,
    openrouter_chat,
    openrouter_runtime,
)
from venom_core.services.chat_history import persist_direct_response
from venom_core.services.chat_materials import MaterialStore
from venom_core.services.session_store import SessionStore

configured = openrouter_fixtures.configured


def application(store):
    app = FastAPI()
    app.include_router(llm_simple.router)
    app.include_router(memory.router)
    app.dependency_overrides[get_session_store] = lambda: store
    return app


def event(kind, value):
    return "event: " + kind + "\ndata: " + json.dumps(value) + "\n\n"


async def consume(response):
    return "".join([chunk async for chunk in response.body_iterator])


def test_native_direct_full_wire_reloads_from_same_host_session_store(
    monkeypatch, tmp_path
):
    store = SessionStore(str(tmp_path / "history.json"))
    materials = MaterialStore(tmp_path / "materials")
    material = materials.save(
        "one", "context.txt", "text/plain", b"PRIVATE DOCUMENT ONLY IN PROMPT"
    )
    monkeypatch.setattr(chat_material_payload, "MaterialStore", lambda: materials)
    runtime = SimpleNamespace(
        provider="ollama",
        model_name="selected",
        endpoint="http://127.0.0.1:11434/v1",
        service_type="local",
        config_hash="cfg",
        runtime_id="runtime",
    )
    monkeypatch.setattr(llm_simple_service, "get_active_llm_runtime", lambda: runtime)
    monkeypatch.setattr(
        llm_simple_service, "_get_active_adapter_id", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(openrouter_runtime, "selection", lambda: None)
    monkeypatch.setattr(
        llm_simple_service,
        "get_metrics_collector",
        lambda: SimpleNamespace(
            record_provider_request=lambda **kw: None,
            record_runtime_sample=lambda **kw: None,
        ),
    )
    captured = []

    class Response:
        def raise_for_status(self):
            pass

        async def aiter_lines(self):
            yield "data: " + json.dumps(
                {"choices": [{"delta": {"content": "Durable answer"}}]}
            )
            yield "data: [DONE]"

    @asynccontextmanager
    async def transport(**kwargs):
        captured.append(kwargs)
        yield Response()

    monkeypatch.setattr(
        llm_simple_service.llm_simple_transport, "open_stream_response", transport
    )
    with TestClient(application(store)) as client:
        response = client.post(
            "/api/v1/llm/simple/stream",
            json={
                "content": "Original question",
                "session_id": "one",
                "model": "selected",
                "material_ids": [material.id],
            },
        )
        assert response.status_code == 200
        assert "event: done" in response.text
        identity = response.headers["x-request-id"]
        UUID(identity)
        loaded = client.get("/api/v1/memory/session/one").json()
        assert [entry["content"] for entry in loaded["history"]] == [
            "Original question",
            "Durable answer",
        ]
        assert all(entry["request_id"] == identity for entry in loaded["history"])
        assert all(entry["timestamp"] for entry in loaded["history"])
        assert loaded["history"][0]["material_ids"] == [material.id]
        assert all(entry["status"] == "COMPLETED" for entry in loaded["history"])
        assert client.get("/api/v1/memory/session/other").json()["history"] == []
    assert (
        "PRIVATE DOCUMENT ONLY IN PROMPT"
        in captured[0]["payload"]["messages"][-1]["content"]
    )
    raw = (tmp_path / "history.json").read_text()
    assert "PRIVATE DOCUMENT ONLY IN PROMPT" not in raw
    assert "data:image" not in raw
    assert (
        SessionStore(str(tmp_path / "history.json")).get_history("one")
        == loaded["history"]
    )


@pytest.mark.asyncio
async def test_turn_is_durable_before_done_and_replayed_identity_is_idempotent(
    tmp_path,
):
    store = SessionStore(str(tmp_path / "history.json"))
    identity = str(uuid4())

    async def source():
        yield event("start", {})
        yield event("content", {"text": "answer"})
        yield event("done", {})

    value = SimpleChatRequest(
        content="question", session_id="one", material_ids=[str(uuid4())]
    )
    response = persist_direct_response(
        StreamingResponse(source(), headers={"X-Request-Id": identity}), value, store
    )
    assert response.headers["x-request-id"] == identity
    await anext(response.body_iterator)
    await anext(response.body_iterator)
    assert store.get_history("one") == []
    done = await anext(response.body_iterator)
    assert "event: done" in done
    assert len(SessionStore(str(tmp_path / "history.json")).get_history("one")) == 2
    await response.body_iterator.aclose()
    replay = persist_direct_response(
        StreamingResponse(source(), headers={"X-Request-Id": identity}), value, store
    )
    await consume(replay)
    assert len(store.get_history("one")) == 2


@pytest.mark.asyncio
async def test_partial_close_persists_cancelled_and_keeps_unknown_cost_pending(
    tmp_path,
):
    store = SessionStore(str(tmp_path / "history.json"))
    closed = []

    async def source():
        try:
            yield event(
                "cost",
                {"state": "pending", "reported_usd": None, "reserved_usd": "0.01"},
            )
            yield event("start", {})
            yield event("content", {"text": "partial answer"})
            await asyncio.Event().wait()
        finally:
            closed.append(True)

    response = persist_direct_response(
        StreamingResponse(source()),
        SimpleChatRequest(content="question", session_id="one"),
        store,
    )
    UUID(response.headers["x-request-id"])
    for _ in range(3):
        await anext(response.body_iterator)
    await response.body_iterator.aclose()
    history = SessionStore(str(tmp_path / "history.json")).get_history("one")
    assert history[-1]["content"] == "partial answer"
    assert history[-1]["status"] == "CANCELLED"
    assert history[-1]["cost"] == {
        "state": "pending",
        "reported_usd": None,
        "reserved_usd": "0.01",
    }
    assert closed == [True]


@pytest.mark.asyncio
async def test_persistence_failure_preserves_old_file_memory_and_never_emits_done(
    monkeypatch, tmp_path
):
    import venom_core.services.session_store as session_module

    store = SessionStore(str(tmp_path / "history.json"))
    store.append_message("one", {"role": "user", "content": "existing"})
    before = (tmp_path / "history.json").read_bytes()
    closed = []

    async def source():
        try:
            yield event("start", {"cost": {"state": "pending", "reported_usd": None}})
            yield event("content", {"text": "new answer"})
            yield event("done", {"cost": {"state": "pending", "reported_usd": None}})
        finally:
            closed.append(True)

    def full_disk(*_args):
        raise OSError("disk full")

    monkeypatch.setattr(session_module.os, "replace", full_disk)
    response = persist_direct_response(
        StreamingResponse(source()),
        SimpleChatRequest(content="new question", session_id="one"),
        store,
    )
    wire = await consume(response)
    assert "chat_history_persistence_failed" in wire
    assert "event: done" not in wire
    assert '"reported_usd": null' in wire
    assert store.get_history("one") == [{"role": "user", "content": "existing"}]
    assert (tmp_path / "history.json").read_bytes() == before
    assert list(tmp_path.glob(".session-turn-*")) == []
    assert closed == [True]


@pytest.mark.asyncio
async def test_denial_before_start_is_not_a_completed_or_failed_generation(tmp_path):
    store = SessionStore(str(tmp_path / "history.json"))

    async def source():
        yield event(
            "error",
            {
                "code": "openrouter_budget_exceeded",
                "cost": {"state": "settled", "reported_usd": "0"},
            },
        )

    response = persist_direct_response(
        StreamingResponse(source()),
        SimpleChatRequest(content="question", session_id="one"),
        store,
    )
    assert "openrouter_budget_exceeded" in await consume(response)
    assert store.get_history("one") == []


@pytest.mark.parametrize("settled", [False, True])
def test_openrouter_history_retains_original_reservation_and_actual_cost(
    configured, monkeypatch, tmp_path, settled
):
    core, ledger, _ = configured
    core.SSEDecoder = lambda: openrouter_fixtures.Decoder(
        "settled" if settled else "pending"
    )
    calls = []

    def endpoint(request):
        calls.append(request)
        return httpx.Response(200, content=b"fixture")

    monkeypatch.setattr(
        openrouter_chat,
        "client_factory",
        lambda **kw: httpx.AsyncClient(transport=httpx.MockTransport(endpoint), **kw),
    )
    store = SessionStore(str(tmp_path / "history.json"))
    value = openrouter_fixtures.authorized_request()
    with TestClient(application(store)) as client:
        response = client.post("/api/v1/llm/simple/stream", json=value.model_dump())
        assert response.status_code == 200 and "event: done" in response.text
        history = client.get("/api/v1/memory/session/session").json()["history"]
    assert len(calls) == 1
    ledger.reserve.assert_called_once()
    identity = response.headers["x-request-id"]
    UUID(identity)
    assert len(history) == 2 and history[-1]["request_id"] == identity
    assert history[-1]["status"] == "COMPLETED"
    assert history[-1]["cost"]["reported_usd"] == ("0.0001" if settled else None)
    assert history[-1]["cost"]["state"] == ("settled" if settled else "pending")
    ledger.settle.assert_called_once_with(
        ledger.reserve.call_args.args[0], Decimal("0.0001") if settled else None
    )
    assert "test-secret" not in (tmp_path / "history.json").read_text()


@pytest.mark.asyncio
async def test_legacy_direct_function_without_dependency_keeps_existing_contract(
    monkeypatch,
):
    response = StreamingResponse(iter([event("done", {})]))
    monkeypatch.setattr(
        llm_simple, "stream_simple_chat_service", AsyncMock(return_value=response)
    )
    result = await llm_simple.stream_simple_chat(
        SimpleChatRequest(content="legacy", session_id="one")
    )
    assert result is response


@pytest.mark.asyncio
async def test_stop_drains_existing_disk_worker_and_keeps_authoritative_completion(
    monkeypatch, tmp_path
):
    import threading

    store = SessionStore(str(tmp_path / "history.json"))
    entered, release = threading.Event(), threading.Event()
    original = store._save_atomic

    def blocked_save():
        entered.set()
        assert release.wait(2)
        original()

    monkeypatch.setattr(store, "_save_atomic", blocked_save)

    async def source():
        yield event("start", {})
        yield event("content", {"text": "finished output"})
        yield event("done", {})

    response = persist_direct_response(
        StreamingResponse(source()),
        SimpleChatRequest(content="question", session_id="one"),
        store,
    )
    await anext(response.body_iterator)
    await anext(response.body_iterator)
    completing = asyncio.create_task(anext(response.body_iterator))
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        completing.cancel()
        await asyncio.sleep(0)
        # The event loop still runs while fsync is blocked, but Stop cannot
        # abandon that worker or rewrite confirmed completion as cancellation.
        assert not completing.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await completing
    finally:
        release.set()
    history = SessionStore(str(tmp_path / "history.json")).get_history("one")
    assert history[-1]["status"] == "COMPLETED"
    assert history[-1]["content"] == "finished output"
