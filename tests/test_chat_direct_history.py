"""Direct uses the host history: no provider calls, extra store, or billing bypass."""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from contextlib import asynccontextmanager
from decimal import Decimal
from threading import Event
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from tests import test_openrouter_runtime as openrouter_fixtures
from venom_core.api.dependencies import (
    get_session_store,
    get_state_manager,
    get_vector_store,
)
from venom_core.api.routes import llm_simple, memory, tasks
from venom_core.api.schemas.llm_simple import SimpleChatRequest
from venom_core.core.tracer import RequestTrace, TraceStatus, TraceStep
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


def test_clear_waits_for_direct_index_and_rejects_late_replay(
    fake_vector_store, monkeypatch, tmp_path
):
    """Exercise both orders through HTTP with a delayed vector upsert."""
    session_id = "direct-clear"
    request_id = "direct-turn"
    store = SessionStore(str(tmp_path / "session.json"))
    store.append_turn_once(
        session_id,
        request_id,
        [
            {
                "role": "assistant",
                "mode": "direct",
                "status": "COMPLETED",
                "request_id": request_id,
                "content": "Direct index sentinel",
            }
        ],
    )
    app = application(store)
    app.dependency_overrides[get_vector_store] = lambda: fake_vector_store
    app.dependency_overrides[get_state_manager] = lambda: None
    monkeypatch.setattr(memory, "ensure_data_mutation_allowed", lambda _: None)
    client = TestClient(app)
    original_upsert = fake_vector_store.upsert
    started = Event()
    finish = Event()

    def delayed_upsert(*args, **kwargs):
        started.set()
        assert finish.wait(timeout=5)
        return original_upsert(*args, **kwargs)

    monkeypatch.setattr(fake_vector_store, "upsert", delayed_upsert)
    payload = {
        "text": "Direct index sentinel",
        "session_id": session_id,
        "scope": "session",
        "direct_request_id": request_id,
    }
    ingest_path = "/api/v1/memory/ingest"
    clear_path = f"/api/v1/memory/session/{session_id}"
    for invalid in (
        {"scope": "global"},
        {"collection": "other"},
        {"session_id": None},
    ):
        assert client.post(ingest_path, json={**payload, **invalid}).status_code == 400
    assert (
        client.post(
            ingest_path, json={**payload, "session_id": "another-session"}
        ).status_code
        == 409
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        indexing = executor.submit(client.post, ingest_path, json=payload)
        try:
            assert started.wait(timeout=3)
            clearing = executor.submit(client.delete, clear_path)
            with pytest.raises(TimeoutError):
                clearing.result(timeout=0.2)
        finally:
            finish.set()
        assert indexing.result(timeout=3).status_code == 201
        cleared = clearing.result(timeout=3)
        assert cleared.status_code == 200
        assert cleared.json()["deleted_vectors"] >= 1
    assert client.get(clear_path).json()["history"] == []
    assert client.post(ingest_path, json=payload).status_code == 409
    search = client.post("/api/v1/memory/search", json={"query": payload["text"]})
    assert all(result["text"] != payload["text"] for result in search.json()["results"])


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
        assert response.status_code == 200
        assert "event: done" in response.text
        history = client.get("/api/v1/memory/session/session").json()["history"]
    assert len(calls) == 1
    ledger.reserve.assert_called_once()
    identity = response.headers["x-request-id"]
    UUID(identity)
    assert len(history) == 2
    assert history[-1]["request_id"] == identity
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


@pytest.mark.asyncio
async def test_native_history_counts_system_and_current_prompt_in_runtime_limit(
    monkeypatch,
):
    from fastapi import HTTPException

    monkeypatch.setattr(
        llm_simple_service, "_get_simple_context_char_limit", lambda _runtime: 100
    )
    request = SimpleChatRequest(
        content="q" * 20, history=[{"role": "assistant", "content": "h" * 50}]
    )
    messages = [
        {"role": "system", "content": "s" * 10},
        {"role": "user", "content": request.content},
    ]
    runtime = SimpleNamespace(provider="vllm")
    with pytest.raises(HTTPException) as error:
        await llm_simple_service._include_simple_request_context(
            request, runtime, "model", "s" * 10, messages
        )
    assert error.value.status_code == 413
    assert error.value.detail == {"reason_code": "material_context_limit"}
    schema = application(None).openapi()
    assert "413" in schema["paths"]["/api/v1/llm/simple/stream"]["post"]["responses"]


@pytest.mark.asyncio
async def test_native_history_fits_exact_runtime_limit_and_keeps_global_history_ceiling(
    monkeypatch,
):
    from fastapi import HTTPException

    monkeypatch.setattr(
        llm_simple_service, "_get_simple_context_char_limit", lambda _runtime: 112
    )
    request = SimpleChatRequest(
        content="q" * 20, history=[{"role": "assistant", "content": "h" * 50}]
    )
    messages = [
        {"role": "system", "content": "s" * 10},
        {"role": "user", "content": request.content},
    ]
    actual = await llm_simple_service._include_simple_request_context(
        request, SimpleNamespace(provider="vllm"), "model", "s" * 10, messages
    )
    assert actual == [
        messages[0],
        {"role": "assistant", "content": "h" * 50},
        messages[1],
    ]
    monkeypatch.setattr(
        llm_simple_service, "_get_simple_context_char_limit", lambda _runtime: None
    )
    oversized = SimpleChatRequest(
        content="q",
        history=[
            {"role": "user", "content": "h" * 26000},
            {"role": "assistant", "content": "h" * 26000},
        ],
    )
    runtime = SimpleNamespace(provider="ollama")
    with pytest.raises(HTTPException) as error:
        await llm_simple_service._include_simple_request_context(
            oversized,
            runtime,
            "model",
            "",
            [{"role": "user", "content": "q"}],
        )
    assert error.value.status_code == 400
    assert error.value.detail == "vast_chat_history_limit"


def test_history_identifies_old_processing_direct_traces_for_full():
    direct = RequestTrace(
        request_id=uuid4(),
        status=TraceStatus.PROCESSING,
        prompt="stopped Direct",
        steps=[TraceStep(component="SimpleMode", action="request")],
    )
    normal = RequestTrace(
        request_id=uuid4(), status=TraceStatus.PROCESSING, prompt="queued task"
    )
    tracer = SimpleNamespace(get_all_traces=lambda **kwargs: [direct, normal])
    summary = tasks.get_request_history(tracer)
    assert [(row.request_id, row.mode) for row in summary] == [
        (direct.request_id, "direct"),
        (normal.request_id, None),
    ]


def test_studio_normal_stream_uses_host_history_and_loads_rag_only_for_notes(
    tmp_path, monkeypatch
):
    store = SessionStore(str(tmp_path / "studio-normal.json"))
    store.append_turn_once(
        "own",
        "previous",
        [
            {"request_id": "previous", "role": "user", "content": "stable user fact"},
            {"request_id": "previous", "role": "assistant", "content": "confirmed"},
        ],
    )
    store.append_turn_once(
        "own",
        "stopped",
        [
            {"request_id": "stopped", "role": "user", "content": "discarded prompt"},
            {
                "request_id": "stopped",
                "role": "assistant",
                "content": "partial",
                "status": "CANCELLED",
            },
        ],
    )
    app = application(store)
    captured = []

    async def simple_stream(request, *, system_context=""):
        captured.append((request, system_context))
        return StreamingResponse(
            consume_events(), headers={"X-Request-Id": str(uuid4())}
        )

    async def consume_events():
        yield event("content", {"text": "reply"})
        yield event("done", {})

    monkeypatch.setattr(llm_simple, "stream_simple_chat_service", simple_stream)
    client = TestClient(app)
    payload = {
        "studio_normal": True,
        "session_id": "own",
        "history": [{"role": "user", "content": "forged client history"}],
    }
    url = "/api/v1/llm/simple/stream"
    assert client.post(url, json={**payload, "content": "hello"}).status_code == 400

    vector_store = SimpleNamespace(
        search=lambda *args, **kwargs: [
            {"text": "Jasny Brzeg: 07:41", "metadata": {"session_id": "own"}},
            {"text": "Jasny Brzeg: 08:50", "metadata": {"session_id": "foreign"}},
            {"text": "Ciemny Brzeg: 09:10", "metadata": {"session_id": "own"}},
        ]
    )
    get_vectors = AsyncMock(return_value=vector_store)
    app.state.studio_runtime = SimpleNamespace(get_vector_store=get_vectors)
    assert (
        client.post(
            url, json={**payload, "content": "Napisz krótką notatkę."}
        ).status_code
        == 200
    )
    get_vectors.assert_not_awaited()
    plain, context = captured[-1]
    assert [x.content for x in plain.history] == ["stable user fact", "confirmed"]
    assert not context
    assert plain.think is False

    prompt = "Według notatki projektu Jasny Brzeg, o której godzinie jest odbiór?"
    response = client.post(url, json={**payload, "content": prompt})
    assert response.status_code == 200
    get_vectors.assert_awaited_once()
    context = captured[-1][1]
    assert "07:41" in context and "08:50" not in context and "09:10" not in context
    user, assistant = store.get_history("own")[-2:]
    assert user["content"] == prompt and user["mode"] == "studio_normal"
    assert assistant["content"] == "reply" and assistant["status"] == "COMPLETED"

    miss = "Z notatki projektu Srebrny Las podaj termin."
    assert client.post(url, json={**payload, "content": miss}).status_code == 200
    assert "no matching source" in captured[-1][1] and "07:41" not in captured[-1][1]
    assert (
        client.post(
            url, json={**payload, "content": "hello", "material_ids": ["x"]}
        ).status_code
        == 400
    )
    assert client.post(url, json={**payload, "content": "x" * 50000}).status_code == 413


def test_studio_normal_keeps_older_complete_turns_within_the_context_budget(tmp_path):
    from venom_core.services.studio_normal_chat import _recent_turns

    store = SessionStore(str(tmp_path / "studio-long-history.json"))
    for index in range(15):
        rid = str(index)
        prompt = "x" * 6000 if index == 0 else f"question {index}"
        store.append_turn_once(
            "own",
            rid,
            [
                {"request_id": rid, "role": "user", "content": prompt},
                {"request_id": rid, "role": "assistant", "content": f"answer {index}"},
            ],
        )

    history = _recent_turns(store, "own", 4096)
    assert [(message.role, message.content) for message in history] == [
        turn
        for index in range(1, 15)
        for turn in (("user", f"question {index}"), ("assistant", f"answer {index}"))
    ]
    assert _recent_turns(store, "foreign", 4096) == []


def test_explicit_note_uses_scoped_exact_lookup_before_embedding(tmp_path):
    from venom_core.memory.chat_retrieval import retrieve_chat_memory
    from venom_core.memory.vector_store import VectorStore

    embedding = Mock(embedding_dimension=3)
    embedding.get_embeddings_batch.side_effect = lambda texts: [
        [1.0, 0.0, 0.0] for _ in texts
    ]
    embedding.get_embedding.return_value = [1.0, 0.0, 0.0]
    store = VectorStore(db_path=str(tmp_path), embedding_service=embedding)
    store.upsert("Jasny Brzeg: własny kod", {"session_id": "own"})
    store.upsert("Jasny Brzeg: cudzy kod", {"session_id": "foreign"})
    query = "Według notatki projektu Jasny Brzeg, jaki jest kod?"
    notes, _ = retrieve_chat_memory(store, query, "own")
    assert "własny kod" in notes and "cudzy" not in notes
    assert retrieve_chat_memory(store, query, "new-session") == ("", [])
    embedding.get_embedding.assert_not_called()

    store.upsert("Jasny Brzeg: drugi kod", {})
    notes, _ = retrieve_chat_memory(store, query, "own")
    assert "własny kod" in notes and "drugi kod" in notes
    assert "cudzy" not in notes
    embedding.get_embedding.assert_called_once_with("Jasny Brzeg")
