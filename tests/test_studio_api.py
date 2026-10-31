"""Studio reuses Full contracts and owners; all transports/models here are fake."""

import asyncio
import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from venom_core.api import dependencies as deps
from venom_core.api.routes import chat_materials, llm_simple, system_deps
from venom_core.api.schemas.tasks import TaskResponse
from venom_core.api.studio_routes import ROUTE_MODULES, STUDIO_ROUTES, studio_routes
from venom_core.bootstrap.studio_runtime import LazyAudioEngine, StudioRuntime
from venom_core.config import SETTINGS
from venom_core.core.models import TaskStatus
from venom_core.services import model_resources
from venom_core.services.background_priority import run_drainable_thread
from venom_core.services.chat_audio import synthesize_wav
from venom_core.services.chat_materials import MaterialStore
from venom_core.services.session_store import SessionStore
from venom_core.studio_main import create_app


def test_subset_keeps_full_route_identity_openapi_schemas_and_security():
    reference = FastAPI()
    for module in ROUTE_MODULES:
        reference.include_router(module.router)
    studio = create_app()
    actual = studio.openapi()
    expected = reference.openapi()
    assert set(actual["paths"]) == set(STUDIO_ROUTES)
    for path, methods in STUDIO_ROUTES.items():
        assert set(actual["paths"][path]) == {method.lower() for method in methods}
        for method in methods:
            assert (
                actual["paths"][path][method.lower()]
                == expected["paths"][path][method.lower()]
            )
    for name, schema in actual["components"]["schemas"].items():
        assert schema == expected["components"]["schemas"][name]
    source_routes = [
        route for module in ROUTE_MODULES for route in module.router.routes
    ]
    for route in studio_routes():
        assert any(route is original for original in source_routes)
        mounted = next(
            r
            for r in studio.routes
            if isinstance(r, APIRoute)
            and r.path == route.path
            and r.methods == route.methods
        )
        assert mounted.endpoint is route.endpoint
        assert mounted.dependency_overrides_provider is studio
        original = next(
            r
            for r in reference.routes
            if isinstance(r, APIRoute)
            and r.path == route.path
            and r.methods == route.methods
        )
        assert route.endpoint is original.endpoint
        assert route.dependencies == original.dependencies
    assert "/api/v1/academy/train" not in actual["paths"]
    assert not any(
        "/rider/" in path or "/knowledge/" in path for path in actual["paths"]
    )
    assert "/api/v1/vast/environments/{plan_id}/order" not in actual["paths"]


def test_import_does_not_boot_full_or_training_optional_modules(tmp_path):
    code = """
import importlib.abc
import sys
class BlockFull(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in {"venom_core.main", "venom_core.api.routes.academy", "venom_core.api.routes.benchmark", "venom_core.api.routes.nodes", "venom_core.api.routes.calendar", "venom_core.api.routes.models_introspection", "venom_core.api.routes.vast_environments"}:
            raise AssertionError("Studio imported " + fullname)
sys.meta_path.insert(0, BlockFull())
from venom_core.studio_main import app
assert app.title == "Venom Studio"
"""
    environment = dict(os.environ, MEMORY_ROOT=str(tmp_path))
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=environment,
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.fixture
def studio(monkeypatch, tmp_path):
    from venom_core.core import (
        llm_server_controller,
        model_manager,
        model_registry,
        service_monitor,
    )

    monkeypatch.setattr(SETTINGS, "MEMORY_ROOT", str(tmp_path / "memory"))
    monkeypatch.setattr(
        SETTINGS, "STATE_FILE_PATH", str(tmp_path / "memory/state.json")
    )
    monkeypatch.setattr(SETTINGS, "ENVIRONMENT_ROLE", "dev")
    monkeypatch.setattr(SETTINGS, "ENABLE_AUDIO_INTERFACE", True)
    monkeypatch.setattr(
        llm_server_controller, "LlmServerController", lambda *args: object()
    )
    monkeypatch.setattr(model_manager, "ModelManager", lambda **kwargs: object())
    monkeypatch.setattr(model_registry, "ModelRegistry", lambda: object())
    monkeypatch.setattr(service_monitor, "ServiceRegistry", lambda: object())
    monitor = SimpleNamespace(
        get_summary=lambda: {"system_healthy": True},
        get_memory_metrics=lambda: dict.fromkeys(
            [
                "memory_usage_mb",
                "memory_total_mb",
                "memory_usage_percent",
                "vram_usage_mb",
                "vram_total_mb",
                "vram_usage_percent",
            ],
            0,
        ),
    )
    monkeypatch.setattr(service_monitor, "ServiceHealthMonitor", lambda *args: monitor)
    events = []
    monkeypatch.setattr(
        model_resources, "prepare_registered_models", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        model_resources,
        "release_registered_models",
        lambda: events.append("released") or [],
    )
    monkeypatch.setattr(
        StudioRuntime,
        "_create_audio",
        staticmethod(
            lambda: events.append("audio-created")
            or SimpleNamespace(
                voice=SimpleNamespace(is_fallback_mode=False, output_sample_rate=16000),
                speak=AsyncMock(return_value=b"\x00\x00"),
                transcribe_checked=AsyncMock(return_value="dictated"),
            )
        ),
    )
    runtime = StudioRuntime()
    app = create_app(lambda: runtime)
    return app, runtime, events


def test_minimal_start_shared_namespace_history_and_lazy_audio(studio):
    app, runtime, events = studio
    previous_state = deps._state_manager
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        assert runtime.orchestrator is None and runtime.vector_store is None
        assert events == []
        assert deps.get_state_manager() is runtime.state_manager
        assert deps.get_session_store() is runtime.session_store
        assert system_deps.get_state_manager() is runtime.state_manager
        assert runtime.state_manager._state_file_path == Path(SETTINGS.STATE_FILE_PATH)
        assert (
            runtime.session_store._store_path
            == Path(SETTINGS.MEMORY_ROOT) / "session_store.json"
        )
        assert client.get("/healthz").json() == {
            "status": "ok",
            "component": "venom-core",
        }
        assert client.get("/api/v1/system/status").json()["system_healthy"] is True
        assert client.get("/api/v1/memory/session/one").json()["history"] == []
        audio = client.post(
            "/api/v1/chat/audio/transcribe?session_id=one",
            content=b"\x00\x00",
            headers={"content-type": "application/octet-stream"},
        )
        assert audio.json()["text"] == "dictated"
        speech = client.post(
            "/api/v1/chat/audio/speak", json={"session_id": "one", "text": "answer"}
        )
        assert speech.status_code == 200 and speech.content[:4] == b"RIFF"
        assert speech.headers["x-content-type-options"] == "nosniff"
        assert events == ["audio-created"]
        assert runtime.orchestrator is None and runtime.vector_store is None
    assert events[-1] == "released"
    assert deps._state_manager is previous_state
    assert not app.dependency_overrides
    assert runtime.request_tracer._watchdog_task is None


def test_direct_same_wire_durable_history_and_header_identity(studio, monkeypatch):
    app, runtime, _ = studio
    identity = str(uuid4())

    async def fake_service(request):
        async def chunks():
            yield (
                "event: content\ndata: "
                + json.dumps({"text": "Persisted answer"})
                + "\n\n"
            )
            yield (
                "event: done\ndata: "
                + json.dumps({"cost": {"state": "unknown"}})
                + "\n\n"
            )

        return StreamingResponse(
            chunks(), media_type="text/event-stream", headers={"x-request-id": identity}
        )

    monkeypatch.setattr(llm_simple, "stream_simple_chat_service", fake_service)
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        response = client.post(
            "/api/v1/llm/simple/stream",
            json={
                "content": "Original prompt",
                "session_id": "one",
                "model": "fixture",
            },
        )
        assert response.headers["x-request-id"] == identity
        assert "unknown" in response.text and "event: done" in response.text
        history = client.get("/api/v1/memory/session/one").json()["history"]
        assert [item["content"] for item in history] == [
            "Original prompt",
            "Persisted answer",
        ]
        assert {item["request_id"] for item in history} == {identity}
        assert SessionStore().get_history("one") == history
        assert runtime.orchestrator is None


def test_material_guard_preprod_origin_and_openrouter_quote_are_unchanged(
    studio, monkeypatch, tmp_path
):
    app, _, _ = studio
    monkeypatch.setattr(
        chat_materials, "MaterialStore", lambda: MaterialStore(tmp_path / "materials")
    )
    quote = {"quote_token": "fixture-only", "estimated_usd": "0.001"}
    from venom_core.services import openrouter_chat

    monkeypatch.setattr(openrouter_chat, "quote", lambda request: quote)
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        upload = "/api/v1/chat/materials?session_id=one&name=note.txt"
        denied = client.post(
            upload,
            content=b"hi",
            headers={"content-type": "text/plain", "origin": "https://foreign.invalid"},
        )
        assert denied.status_code == 403
        monkeypatch.setattr(SETTINGS, "ENVIRONMENT_ROLE", "preprod")
        monkeypatch.setattr(SETTINGS, "ALLOW_DATA_MUTATION", False)
        assert (
            client.post(
                upload, content=b"hi", headers={"content-type": "text/plain"}
            ).json()["detail"]["reason_code"]
            == "material_environment_read_only"
        )
        monkeypatch.setattr(SETTINGS, "ENVIRONMENT_ROLE", "dev")
        created = client.post(
            upload, content=b"inert", headers={"content-type": "text/plain"}
        ).json()
        assert (
            client.get(created["preview_url"]).headers["x-content-type-options"]
            == "nosniff"
        )
        foreign = created["preview_url"].replace("session_id=one", "session_id=other")
        assert client.get(foreign).status_code == 404
        response = client.post(
            "/api/v1/openrouter/quote",
            json={"content": "quote", "session_id": "one", "model": "fixture/free"},
        )
        assert response.status_code == 200 and response.json() == quote


@pytest.mark.asyncio
async def test_external_requests_cannot_bypass_route_or_proxy_guards():
    import httpx

    app = create_app()
    transport = httpx.ASGITransport(app, client=("203.0.113.9", 1))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://localhost"
    ) as client:
        headers = {
            "x-venom-proxy": "1",
            "x-venom-client-address": "127.0.0.1",
            "x-venom-shared-entry": "0",
        }
        assert (
            await client.get("/api/v1/openrouter/status", headers=headers)
        ).status_code == 403
        assert (
            await client.get("/api/v1/chat/materials?session_id=x", headers=headers)
        ).status_code == 403


@pytest.mark.asyncio
async def test_lazy_owners_construct_once_and_reuse_vector_store(studio, monkeypatch):
    app, runtime, _ = studio
    from venom_core.core import orchestrator
    from venom_core.memory import vector_store

    vectors = []

    def make_vector():
        value = object()
        vectors.append(value)
        return value

    constructed = []

    def make_orchestrator(state, **kwargs):
        constructed.append(kwargs)
        return SimpleNamespace(active_tasks={}, emergency_stop=AsyncMock())

    monkeypatch.setattr(vector_store, "VectorStore", make_vector)
    monkeypatch.setattr(orchestrator, "Orchestrator", make_orchestrator)
    async with app.router.lifespan_context(app):
        vector = await runtime.get_vector_store()
        first, second = await asyncio.gather(
            runtime.get_orchestrator(), runtime.get_orchestrator()
        )
        assert first is second
        assert len(vectors) == len(constructed) == 1
        assert constructed[0]["vector_store"] is vector
        assert constructed[0]["session_store"] is runtime.session_store
        assert constructed[0]["request_tracer"] is runtime.request_tracer


@pytest.mark.asyncio
async def test_shutdown_waits_for_audio_native_worker_and_blocks_new_capture(
    monkeypatch,
):
    started, retire = threading.Event(), threading.Event()
    released = []

    @model_resources.model_operation
    async def work(text):
        def native():
            started.set()
            assert retire.wait(5)
            return b"\x00\x00"

        return await run_drainable_thread(native)

    native = SimpleNamespace(
        speak=work,
        voice=SimpleNamespace(is_fallback_mode=False, output_sample_rate=16000),
    )
    audio = LazyAudioEngine(lambda: native)
    runtime = StudioRuntime()
    runtime.audio_engine = audio
    runtime._owned_runtime = True
    monkeypatch.setattr(
        model_resources,
        "release_registered_models",
        lambda: released.append("released") or [],
    )
    request = asyncio.create_task(synthesize_wav(audio, "text"))
    await asyncio.to_thread(started.wait, 5)
    assert started.is_set()
    request.cancel()
    closing = asyncio.create_task(runtime.close())
    await asyncio.sleep(0.03)
    assert not closing.done() and not released
    with pytest.raises(HTTPException):
        await audio.speak("new")
    retire.set()
    with pytest.raises(asyncio.CancelledError):
        await request
    await closing
    assert released == ["released"]


@pytest.mark.parametrize("intent", ["GENERAL_CHAT", "COMPLEX_PLANNING"])
def test_normal_and_maf_keep_original_submit_sse_and_scoped_stop(
    studio, monkeypatch, intent
):
    app, runtime, _ = studio
    from venom_core.core import orchestrator
    from venom_core.memory import vector_store

    calls = []

    async def submit(request):
        calls.append(request)
        task = runtime.state_manager.create_task(request.content)
        task.status = TaskStatus.PROCESSING
        task.result = "partial"
        task.context_history = {"session": {"session_id": request.session_id}}
        return TaskResponse(task_id=task.id, status="PROCESSING")

    async def abort(task_id):
        calls.append(task_id)
        await runtime.state_manager.update_status(
            task_id, TaskStatus.FAILED, result="cancelled"
        )
        return {"success": True}

    fake = SimpleNamespace(
        submit_task=submit,
        abort_task=abort,
        active_tasks={},
        emergency_stop=AsyncMock(),
    )
    monkeypatch.setattr(vector_store, "VectorStore", lambda: object())

    def make_orchestrator(state, **kwargs):
        fake.state_manager = state
        return fake

    monkeypatch.setattr(orchestrator, "Orchestrator", make_orchestrator)
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        response = client.post(
            "/api/v1/tasks",
            json={
                "content": "normal task",
                "session_id": "one",
                "forced_intent": intent,
                "expected_runtime_id": "expected",
            },
        )
        assert response.status_code == 201
        identity = response.json()["task_id"]
        assert (
            calls[0].forced_intent == intent
            and calls[0].expected_runtime_id == "expected"
        )
        endpoint = "/api/v1/chat/tasks/" + identity + "/cancel"
        assert client.post(endpoint, json={"session_id": "other"}).status_code == 404
        assert len(calls) == 1
        assert (
            client.post(endpoint, json={"session_id": "one"}).json()["status"]
            == "cancelled"
        )
        assert (
            client.post(endpoint, json={"session_id": "one"}).json()["status"]
            == "already_finished"
        )
        assert client.get("/api/v1/tasks/" + identity).json()["status"] == "FAILED"
        assert (
            "event:task_finished"
            in client.get("/api/v1/tasks/" + identity + "/stream").text
        )


@pytest.mark.asyncio
async def test_cleanup_error_still_flushes_state_and_restores_owners(
    studio, monkeypatch
):
    app, runtime, _ = studio
    previous = deps._state_manager
    state_flush = AsyncMock()
    monkeypatch.setattr(
        model_resources,
        "release_registered_models",
        lambda: [{"category": "stt", "verified": False}],
    )
    with pytest.raises(RuntimeError, match="studio_model_resources_not_released"):
        async with app.router.lifespan_context(app):
            runtime.state_manager.shutdown = state_flush
    state_flush.assert_awaited_once()
    assert deps._state_manager is previous
    assert runtime.request_tracer._watchdog_task is None


@pytest.mark.asyncio
async def test_cancelled_stop_and_concurrent_stop_both_drain_native_cleanup(
    monkeypatch,
):
    started, retire = threading.Event(), threading.Event()
    events = []
    runtime = StudioRuntime()
    runtime._owned_runtime = True
    runtime.state_manager = SimpleNamespace(shutdown=AsyncMock())

    def release():
        started.set()
        assert retire.wait(5)
        events.append("retired")
        return []

    monkeypatch.setattr(model_resources, "release_registered_models", release)
    first = asyncio.create_task(runtime.close())
    await asyncio.to_thread(started.wait, 5)
    assert started.is_set()
    first.cancel()
    second = asyncio.create_task(runtime.close())
    await asyncio.sleep(0.02)
    assert not first.done() and not second.done() and not events
    retire.set()
    with pytest.raises(asyncio.CancelledError):
        await first
    await second
    assert events == ["retired"]
    runtime.state_manager.shutdown.assert_awaited_once()


@pytest.mark.asyncio
async def test_disabled_audio_and_failed_lazy_constructor_are_explicit(
    studio, monkeypatch
):
    app, runtime, events = studio
    monkeypatch.setattr(SETTINGS, "ENABLE_AUDIO_INTERFACE", False)
    async with app.router.lifespan_context(app):
        assert app.state.audio_engine is None and events == []
    failed = LazyAudioEngine(lambda: None)
    with pytest.raises(HTTPException) as error:
        await failed.speak("hello")
    assert error.value.detail == {"reason_code": "audio_not_ready"}


@pytest.mark.asyncio
async def test_audio_factory_uses_configured_host_constructor_without_warmup(
    monkeypatch,
):
    from venom_core.perception import audio_engine

    created = []
    monkeypatch.setattr(SETTINGS, "ENABLE_AUDIO_INTERFACE", True)

    def construct(**kwargs):
        created.append(kwargs)
        return object()

    monkeypatch.setattr(audio_engine, "AudioEngine", construct)
    assert StudioRuntime._create_audio() is not None
    assert created[0]["whisper_model_size"] == SETTINGS.WHISPER_MODEL_SIZE
    assert created[0]["tts_model_path"] == SETTINGS.TTS_MODEL_PATH


def test_studio_excludes_unexposed_classic_controls_and_global_history():
    paths = create_app().openapi()["paths"]
    assert set(paths["/api/v1/tasks"]) == {"post"}
    for path in (
        "/api/v1/memory/global",
        "/api/v1/history/requests",
        "/api/v1/history/requests/{request_id}",
        "/api/v1/feedback",
        "/api/v1/models/{model_name}/config",
        "/api/v1/system/vast-chat",
        "/api/v1/system/vast-chat/attach",
        "/api/v1/system/vast-chat/detach",
    ):
        assert path not in paths
    # Reachable session history, original streaming, ingestion and model apply remain.
    assert "get" in paths["/api/v1/memory/session/{session_id}"]
    assert "get" in paths["/api/v1/tasks/{task_id}/stream"]
    assert "post" in paths["/api/v1/memory/ingest"]
    assert "post" in paths["/api/v1/system/llm-runtime/active"]


@pytest.mark.parametrize("host, expected", [("127.0.0.1", 200), ("192.0.2.1", 403)])
def test_theme_persistence_uses_shared_config_handler_and_localhost_guard(
    studio, monkeypatch, host, expected
):
    from venom_core.api.routes import system_config

    app, _, _ = studio
    writes = []

    def update(updates):
        writes.append(updates)
        return {"success": True, "changed_keys": list(updates)}

    monkeypatch.setattr(system_config.config_manager, "update_config", update)
    with TestClient(app, client=(host, 50000)) as client:
        response = client.post(
            "/api/v1/config/runtime",
            json={"updates": {"UI_THEME_DEFAULT": "venom-light"}},
        )
    assert response.status_code == expected
    assert writes == ([{"UI_THEME_DEFAULT": "venom-light"}] if expected == 200 else [])
    if expected == 200:
        assert response.json()["updated_keys"] == ["UI_THEME_DEFAULT"]
