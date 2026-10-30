"""Global resource release uses inert model owners, daemons and device hooks."""

import asyncio
import threading
import weakref
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from venom_core.services import model_resources as resources
from venom_core.services import runtime_admission as admission_module
from venom_core.services import runtime_release_service as service
from venom_core.services.runtime_admission import (
    RuntimeAdmission,
    RuntimeAdmissionError,
)


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setattr(resources, "_OWNERS", weakref.WeakKeyDictionary())
    monkeypatch.setattr(resources, "_ACTIVE", 0)
    monkeypatch.setattr(resources, "_RELEASING", False)
    admission = RuntimeAdmission(tmp_path / "admission.sqlite3")
    monkeypatch.setattr(admission_module, "_ADMISSION", admission)
    monkeypatch.setattr(service, "memory_snapshot", lambda: {"rss_mib": 100, "gpu": []})
    return admission


def uncertain(admission):
    def exercise_operation():
        with admission.operation(kind="runtime_switch", mutation=True):
            raise RuntimeError("transport lost")

    with pytest.raises(RuntimeError):
        exercise_operation()


def test_cleanup_is_exclusive_and_cannot_generate_or_clear_live_work(world):
    uncertain(world)
    with world.operation(kind="cleanup", mutation=True, _cleanup=True):

        def exercise_operation():
            with world.operation(kind="generation"):
                pytest.fail("cleanup must not generate")

        with pytest.raises(RuntimeAdmissionError):
            exercise_operation()
        failures = []

        def attempt():
            try:
                with world.operation(kind="generation"):
                    failures.append("admitted")
            except RuntimeAdmissionError:
                pass

        worker = threading.Thread(target=attempt)
        worker.start()
        worker.join(2)
        assert failures == []
        assert world.recover(confirm_quiescent=lambda: False) is False
        assert world.recover(confirm_quiescent=lambda: True) is True
        assert world.snapshot()["active_operations"] == 1
    assert world.snapshot()["status"] == "available"


def test_cleanup_never_erases_an_active_lease_or_host_operation(world):
    with world.operation(kind="generation"):

        def exercise_operation():
            with world.operation(kind="cleanup", mutation=True, _cleanup=True):
                pytest.fail("live operation was erased")

        with pytest.raises(RuntimeAdmissionError):
            exercise_operation()
    lease = world.acquire(
        owner="fixture", run_id="run", engine="fixture", model="fixture"
    )

    def exercise_operation():
        with world.operation(kind="cleanup", mutation=True, _cleanup=True):
            pytest.fail("owned runtime was erased")

    with pytest.raises(RuntimeAdmissionError):
        exercise_operation()
    assert lease.release()


def test_registered_owners_are_weak_and_all_categories_are_released(world):
    class Owner:
        def __init__(self, category):
            self.model = object()
            resources.register_model_resource(self, category, "release")

        def release(self):
            self.model = None
            return True

    owners = [Owner(category) for category in ["vision", "stt", "tts", "embeddings"]]
    with resources.release_barrier():
        result = resources.release_registered_models()
    assert {r["category"] for r in result} == {"vision", "stt", "tts", "embeddings"}
    assert all(r["verified"] for r in result)
    assert all(owner.model is None for owner in owners)
    reference = weakref.ref(owners.pop())
    assert reference() is None


def test_releasing_models_rejects_new_work_and_waits_for_real_thread(world):
    started, finish = threading.Event(), threading.Event()

    @resources.model_operation
    def infer():
        started.set()
        finish.wait(2)

    worker = threading.Thread(target=infer)
    worker.start()
    assert started.wait(1)
    with resources.release_barrier():
        with pytest.raises(HTTPException, match="model_resources_releasing"):
            infer()
        with pytest.raises(HTTPException):
            resources.wait_for_model_work(timeout=0)
        finish.set()
        worker.join(2)
        resources.wait_for_model_work(timeout=1)
        assert resources.release_registered_models() == []


@pytest.mark.asyncio
async def test_global_release_verifies_daemons_voice_and_vision_before_recovery(
    world, monkeypatch
):
    uncertain(world)
    events = []

    class Owner:
        def __init__(self, category):
            self.category = category
            resources.register_model_resource(self, category, "release")

        async def prepare_model_release(self):
            events.append("prepare:" + self.category)

        def release(self):
            events.append("release:" + self.category)
            return True

    owners = [Owner(c) for c in ["vision", "stt", "tts", "embeddings"]]

    async def listening(_endpoint):
        return True

    async def unload(_endpoint):
        events.append("unload:ollama")
        return ["fixture"]

    monkeypatch.setattr(service, "_listening", listening)
    monkeypatch.setattr(service, "_unload_ollama", unload)
    controller = SimpleNamespace(
        list_servers=lambda: [{"name": "ollama", "endpoint": "http://127.0.0.1:11434"}]
    )
    result = await service.release_all_runtime_models(controller)
    assert result["released"]
    assert events.index("prepare:vision") < events.index("unload:ollama")
    assert len(owners) == 4
    assert len(result["runtimes"]) == 5
    assert world.snapshot()["status"] == "available"


@pytest.mark.asyncio
async def test_partial_failure_never_claims_release_or_clears_uncertainty(
    world, monkeypatch
):
    uncertain(world)

    async def listening(_endpoint):
        return True

    async def unload(_endpoint):
        raise ValueError("daemon still owns a model")

    monkeypatch.setattr(service, "_listening", listening)
    monkeypatch.setattr(service, "_unload_ollama", unload)
    controller = SimpleNamespace(
        list_servers=lambda: [{"name": "ollama", "endpoint": "http://127.0.0.1:11434"}]
    )
    with pytest.raises(HTTPException) as error:
        await service.release_all_runtime_models(controller)
    assert error.value.status_code == 502
    assert error.value.detail["code"] == "runtime_release_failed"
    assert error.value.detail["runtimes"][0]["error"] == "runtime_release_ValueError"
    assert world.snapshot()["status"] == "quarantined"


@pytest.mark.asyncio
async def test_release_endpoint_delegates_to_global_coordinator(world, monkeypatch):
    from venom_core.api.routes import system_llm

    controller = object()
    monkeypatch.setattr(
        system_llm.system_deps, "get_llm_controller", lambda: controller
    )

    monkeypatch.setattr(system_llm, "_installed_local_servers", lambda: {"ollama"})

    async def release(value, *, runtime_ids):
        assert runtime_ids == {"ollama"}
        assert value is controller
        return {"released": True}

    monkeypatch.setattr(service, "release_all_runtime_models", release)
    assert await system_llm.release_llm_runtime() == {"released": True}


@pytest.mark.asyncio
async def test_ollama_unloads_every_loaded_model_and_verifies_empty_inventory(
    monkeypatch,
):
    import httpx

    requests = []
    original = httpx.AsyncClient

    def handler(request):
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "models": [{"name": "a"}, {"name": "b"}]
                    if len(requests) == 1
                    else []
                },
            )
        return httpx.Response(200, json={"done": True})

    monkeypatch.setattr(
        service.httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    assert await service._unload_ollama("http://127.0.0.1:11434/v1") == ["a", "b"]
    import json

    posted = [json.loads(r.content) for r in requests if r.method == "POST"]
    assert [x["model"] for x in posted] == ["a", "b"]
    assert all(x["keep_alive"] == 0 and x["stream"] is False for x in posted)


@pytest.mark.asyncio
async def test_ollama_retained_models_are_failure(monkeypatch):
    import httpx

    original = httpx.AsyncClient

    def handler(_request):
        return httpx.Response(200, json={"models": [{"name": "stuck"}]})

    monkeypatch.setattr(
        service.httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    monkeypatch.setattr(service, "_OLLAMA_UNLOAD_TIMEOUT", 0)
    with pytest.raises(ValueError, match="models_remaining"):
        await service._unload_ollama("http://127.0.0.1:11434")


@pytest.mark.asyncio
async def test_worker_stop_requires_command_success_and_closed_listener(monkeypatch):
    from unittest.mock import AsyncMock

    server = {
        "name": "multi_runtime",
        "endpoint": "http://127.0.0.1:8014",
        "supports": {"stop": True},
    }
    controller = SimpleNamespace(
        stop_for_cleanup=AsyncMock(return_value=SimpleNamespace(ok=True))
    )
    monkeypatch.setattr(service, "_listening", AsyncMock(return_value=False))
    await service._stop_worker(controller, server)
    controller.stop_for_cleanup.assert_awaited_once_with("multi_runtime")
    controller.stop_for_cleanup.return_value = SimpleNamespace(ok=False)
    with pytest.raises(ValueError, match="stop_failed"):
        await service._stop_worker(controller, server)


@pytest.mark.asyncio
async def test_closed_listener_and_remote_endpoint_are_distinguished(monkeypatch):
    async def refused(*_args):
        raise ConnectionRefusedError()

    monkeypatch.setattr(asyncio, "open_connection", refused)
    assert await service._listening("http://127.0.0.1:11434") is False
    with pytest.raises(ValueError, match="local_only"):
        await service._listening("https://external.example")


def test_memory_snapshot_reports_actual_values_without_loading_torch(monkeypatch):
    import subprocess

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout="0, 1200, 12288\n"),
    )
    result = service.memory_snapshot()
    assert result["rss_mib"] > 0
    assert result["gpu"] == [{"index": 0, "used_mib": 1200, "total_mib": 12288}]


@pytest.mark.asyncio
async def test_unconfigured_engine_is_not_mistaken_for_an_active_worker(
    world, monkeypatch
):
    from unittest.mock import AsyncMock

    monkeypatch.setattr(service, "_listening", AsyncMock(return_value=False))
    controller = SimpleNamespace(
        list_servers=lambda: [
            {"name": "ollama", "endpoint": "http://127.0.0.1:11434"},
            {"name": "onnx", "endpoint": "invalid-unconfigured-endpoint"},
        ]
    )
    result = await service.release_all_runtime_models(
        controller, runtime_ids={"ollama"}
    )
    assert result["released"]
    assert [row["runtime"] for row in result["runtimes"]] == ["ollama"]
    assert world.snapshot()["status"] == "available"


@pytest.mark.asyncio
@pytest.mark.parametrize("admission_enabled", [True, False])
async def test_global_release_does_not_require_any_llm_installation(
    world, admission_enabled
):
    world.enabled = admission_enabled

    class Voice:
        def __init__(self):
            resources.register_model_resource(self, "tts", "release")

        def release(self):
            return True

    voice = Voice()
    result = await service.release_all_runtime_models(
        SimpleNamespace(list_servers=lambda: []), runtime_ids=set()
    )
    assert result["released"]
    assert voice is not None
    assert [row["runtime"] for row in result["runtimes"]] == ["tts"]


def test_whisper_release_unloads_native_weights_without_cpu_offload(world):
    from unittest.mock import Mock

    from venom_core.perception.audio_engine import WhisperSkill

    skill = WhisperSkill()
    native = SimpleNamespace(unload_model=Mock())
    skill.model = SimpleNamespace(model=native)
    with resources.release_barrier():
        rows = resources.release_registered_models()
    native.unload_model.assert_called_once_with(to_cpu=False)
    assert skill.model is None
    assert rows[0]["category"] == "stt"
    assert rows[0]["verified"]


@pytest.mark.asyncio
async def test_release_reconciles_children_queued_by_already_admitted_work(world):
    started, finish = asyncio.Event(), asyncio.Event()

    class Owner:
        pending = False

        def __init__(self):
            resources.register_model_resource(self, "vision", "release")

        async def prepare_model_release(self):
            self.pending = False
            finish.set()

        def release(self):
            return not self.pending

    owner = Owner()

    @resources.model_operation
    async def submit():
        started.set()
        await finish.wait()
        owner.pending = True

    task = asyncio.create_task(submit())
    await started.wait()
    result = await service.release_all_runtime_models(
        SimpleNamespace(list_servers=lambda: []), runtime_ids=set()
    )
    await task
    assert result["released"]
    assert not owner.pending


@pytest.mark.asyncio
async def test_late_audio_and_control_do_not_resume_a_released_channel(world):
    from unittest.mock import AsyncMock

    from venom_core.api.audio_stream import AudioStreamHandler

    handler = AudioStreamHandler()
    handler.resources_suspended = True
    handler._start_recording = AsyncMock()
    handler._handle_audio_data(123, b"late audio", None)
    await handler._handle_control_message(123, '{"command":"start_recording"}', None)
    assert handler.resources_suspended is True
    handler._start_recording.assert_not_awaited()
    assert handler.active_connections == {}


@pytest.mark.asyncio
async def test_audio_accept_is_blocked_during_release_and_explicitly_resumes_after(
    world,
):
    from unittest.mock import AsyncMock

    from venom_core.api.audio_stream import AudioStreamHandler

    handler = AudioStreamHandler()
    socket = SimpleNamespace(accept=AsyncMock(), close=AsyncMock())
    with resources.release_barrier():
        await handler.handle_websocket(socket)
    socket.accept.assert_not_awaited()
    socket.close.assert_awaited_once_with(code=1013, reason="model_resources_releasing")
    handler.resources_suspended = True
    identity = await handler._accept_connection(socket)
    assert identity in handler.active_connections
    assert handler.resources_suspended is False


@pytest.mark.asyncio
async def test_audio_prepare_uses_a_snapshot_when_closed_connections_remove_themselves(
    world,
):
    from unittest.mock import AsyncMock

    from venom_core.api.audio_stream import AudioStreamHandler

    handler = AudioStreamHandler()
    sockets = []
    for identity in (1, 2):

        async def close(*, code, reason, cid=identity):
            assert code == 1012
            assert reason == "model_resources_released"
            handler.active_connections.pop(cid)

        socket = SimpleNamespace(close=AsyncMock(side_effect=close))
        sockets.append(socket)
        handler.active_connections[identity] = {"websocket": socket}
    await handler.prepare_model_release()
    assert handler.release_model_resource() is True
    for socket in sockets:
        socket.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_cancelled_release_keeps_barrier_until_native_unload_finishes(world):
    started, finish = threading.Event(), threading.Event()

    class Owner:
        def __init__(self):
            resources.register_model_resource(self, "vision", "release")

        def release(self):
            started.set()
            assert finish.wait(3)
            return True

    owner = Owner()

    @resources.model_operation
    def new_work():
        return "available"

    task = asyncio.create_task(
        service.release_all_runtime_models(
            SimpleNamespace(list_servers=lambda: []), runtime_ids=set()
        )
    )
    try:
        assert await asyncio.to_thread(started.wait, 2)
        for _ in range(2):
            task.cancel()
            await asyncio.sleep(0)
            with pytest.raises(HTTPException, match="model_resources_releasing"):
                new_work()
        assert owner is not None
    finally:
        finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert new_work() == "available"
    assert world.snapshot()["status"] == "available"


@pytest.mark.asyncio
async def test_ollama_waits_for_delayed_inventory_after_unload(monkeypatch):
    import httpx

    original = httpx.AsyncClient
    reads = 0

    def handle(request):
        nonlocal reads
        if request.method == "GET":
            reads += 1
            return httpx.Response(
                200, json={"models": [{"name": "fixture"}] if reads < 3 else []}
            )
        return httpx.Response(200, json={"done": True})

    monkeypatch.setattr(
        service.httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handle), **kwargs),
    )
    assert await service._unload_ollama("http://127.0.0.1:11434") == ["fixture"]
    assert reads == 3


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "peer,headers,expected",
    [
        ("127.0.0.1", {}, 200),
        ("::1", {}, 200),
        ("192.0.2.10", {}, 403),
        (
            "127.0.0.1",
            {
                "x-venom-proxy": "1",
                "x-venom-client-address": "192.0.2.10",
                "x-venom-shared-entry": "1",
            },
            403,
        ),
        (
            "192.0.2.10",
            {
                "x-venom-proxy": "1",
                "x-venom-client-address": "127.0.0.1",
                "x-venom-shared-entry": "0",
            },
            403,
        ),
        ("127.0.0.1", {"x-venom-proxy": "1"}, 403),
    ],
)
@pytest.mark.parametrize("endpoint", ["release", "recover-llm"])
async def test_global_release_obeys_transport_admin_boundary(
    monkeypatch, peer, headers, expected, endpoint
):
    from unittest.mock import AsyncMock

    import httpx
    from fastapi import FastAPI

    from venom_core.api.routes import system_llm
    from venom_core.api.transport_access import TransportAccessMiddleware
    from venom_core.config import SETTINGS

    monkeypatch.setattr(SETTINGS, "VENOM_OPERATOR_ACCESS", "secure")
    release = AsyncMock(return_value={"released": True})
    monkeypatch.setattr(service, "release_all_runtime_models", release)
    monkeypatch.setattr(system_llm.system_deps, "get_llm_controller", lambda: object())
    monkeypatch.setattr(system_llm, "_installed_local_servers", lambda: set())
    app = FastAPI()
    app.add_middleware(TransportAccessMiddleware)
    app.include_router(system_llm.router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=(peer, 1234)),
        base_url="http://localhost",
    ) as client:
        response = await client.post(
            f"/api/v1/system/models/{endpoint}", headers=headers
        )
    assert response.status_code == expected
    assert release.await_count == (1 if expected == 200 else 0)
    if expected == 200 and endpoint == "recover-llm":
        assert release.await_args.kwargs["include_registered"] is False


def test_batch_embedding_keeps_release_barrier_until_native_encode_finishes(world):
    import numpy as np

    from venom_core.memory.embedding_service import EmbeddingService

    started, finish = threading.Event(), threading.Event()
    outputs = []

    class BatchModel:
        def encode(self, texts, **kwargs):
            started.set()
            assert finish.wait(3)
            return np.ones((len(texts), 2))

    owner = EmbeddingService(service_type="local")
    owner._model = BatchModel()
    worker = threading.Thread(
        target=lambda: outputs.append(owner.get_embeddings_batch(["a", "b"]))
    )
    worker.start()
    try:
        assert started.wait(2)
        with resources.release_barrier():
            with pytest.raises(HTTPException) as caught:
                resources.wait_for_model_work(timeout=0)
            assert caught.value.detail["code"] == "model_resources_work_not_drained"
            with pytest.raises(HTTPException) as rejected:
                owner.get_embeddings_batch(["late"])
            assert rejected.value.detail["code"] == "model_resources_releasing"
            assert owner._model is not None
            finish.set()
            worker.join(2)
            assert not worker.is_alive()
            resources.wait_for_model_work(timeout=0)
            rows = resources.release_registered_models()
            assert all(row["verified"] for row in rows)
            assert owner._model is None
        assert outputs == [[[1.0, 1.0], [1.0, 1.0]]]
    finally:
        finish.set()
        worker.join(3)


@pytest.mark.asyncio
async def test_llm_recovery_clears_uncertainty_without_touching_rider_or_voice(
    world, monkeypatch
):
    from unittest.mock import AsyncMock, Mock

    class Owner:
        async def prepare_model_release(self):
            pytest.fail("LLM-only recovery must not pause Rider or voice")

        def release(self):
            pytest.fail("LLM-only recovery must not unload Rider or voice")

    owners = [Owner(), Owner()]
    resources.register_model_resource(owners[0], "vision", "release")
    resources.register_model_resource(owners[1], "voice_sessions", "release")
    uncertain(world)
    monkeypatch.setattr(service, "_listening", AsyncMock(return_value=True))
    unload = AsyncMock(return_value=["fixture-model"])
    monkeypatch.setattr(service, "_unload_ollama", unload)
    controller = SimpleNamespace(
        list_servers=Mock(
            return_value=[{"name": "ollama", "endpoint": "http://127.0.0.1:11434"}]
        )
    )
    result = await service.release_all_runtime_models(
        controller, runtime_ids={"ollama"}, include_registered=False
    )
    assert result["released"] is True
    assert world.snapshot()["status"] == "available"
    assert {row["runtime"] for row in result["runtimes"]} == {"ollama"}
    unload.assert_awaited_once()


@pytest.mark.asyncio
async def test_llm_recovery_keeps_unrelated_uncertainty(world, monkeypatch):
    from unittest.mock import Mock

    with pytest.raises(RuntimeError, match="vision failed"):
        with world.operation(kind="vision"):
            raise RuntimeError("vision failed")
    controller = SimpleNamespace(list_servers=Mock(return_value=[]))
    with pytest.raises(HTTPException) as error:
        await service.release_all_runtime_models(
            controller, runtime_ids={"ollama"}, include_registered=False
        )
    assert error.value.detail["code"] == "runtime_release_failed"
    assert world.snapshot()["status"] == "quarantined"


@pytest.mark.asyncio
async def test_llm_recovery_requires_an_observed_daemon_even_for_a_matching_kind(world):
    from unittest.mock import Mock

    uncertain(world)
    with pytest.raises(HTTPException):
        await service.release_all_runtime_models(
            SimpleNamespace(list_servers=Mock(return_value=[])),
            runtime_ids={"ollama"},
            include_registered=False,
        )
    assert world.snapshot()["status"] == "quarantined"
