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
    with pytest.raises(RuntimeError):
        with admission.operation(kind="runtime_switch", mutation=True):
            raise RuntimeError("transport lost")


def test_cleanup_is_exclusive_and_cannot_generate_or_clear_live_work(world):
    uncertain(world)
    with world.operation(kind="cleanup", mutation=True, _cleanup=True):
        with pytest.raises(RuntimeAdmissionError):
            with world.operation(kind="generation"):
                pytest.fail("cleanup must not generate")
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
        with pytest.raises(RuntimeAdmissionError):
            with world.operation(kind="cleanup", mutation=True, _cleanup=True):
                pytest.fail("live operation was erased")
    lease = world.acquire(
        owner="fixture", run_id="run", engine="fixture", model="fixture"
    )
    with pytest.raises(RuntimeAdmissionError):
        with world.operation(kind="cleanup", mutation=True, _cleanup=True):
            pytest.fail("owned runtime was erased")
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
    assert len(owners) == 4 and len(result["runtimes"]) == 5
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
    assert world.snapshot()["status"] == "quarantined"


@pytest.mark.asyncio
async def test_release_endpoint_delegates_to_global_coordinator(world, monkeypatch):
    from venom_core.api.routes import system_llm

    controller = object()
    monkeypatch.setattr(
        system_llm.system_deps, "get_llm_controller", lambda: controller
    )

    async def release(value):
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
