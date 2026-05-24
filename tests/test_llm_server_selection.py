"""Unit tests for active LLM server selection (PR 069)."""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

import venom_core.main as main_module
from tests.helpers.url_fixtures import LOCALHOST_11434_V1
from venom_core.api.routes import system_llm as system_routes
from venom_core.config import SETTINGS
from venom_core.services import runtime_switch_gate as gate
from venom_core.services import runtime_switch_service
from venom_core.services.runtime_switch_telemetry import (
    assert_runtime_switch_source_allowed,
    normalize_runtime_switch_source,
)


class _FakeResponse:
    def __init__(self, status_code: int, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class _FakeAsyncClient:
    def __init__(self, responses):
        self._responses = list(responses)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, _url):
        if self._responses:
            return self._responses.pop(0)
        return _FakeResponse(503, {"status": "error"})


class DummyController:
    def __init__(self, servers):
        self._servers = servers
        self.actions = []
        self.fail_actions = set()

    def has_server(self, name):
        return any(server["name"] == name for server in self._servers)

    def list_servers(self):
        return self._servers

    async def run_action(self, name, action):
        await asyncio.sleep(0)
        self.actions.append((name, action))
        if (name, action) in self.fail_actions:
            return SimpleNamespace(ok=False, exit_code=1)
        return SimpleNamespace(ok=True, exit_code=0)


class DummyModelManager:
    def __init__(self, models):
        self._models = models

    async def list_local_models(self):
        await asyncio.sleep(0)
        return self._models


def _snapshot_settings():
    return {
        "service_type": SETTINGS.LLM_SERVICE_TYPE,
        "endpoint": SETTINGS.LLM_LOCAL_ENDPOINT,
        "model": SETTINGS.LLM_MODEL_NAME,
        "active": SETTINGS.ACTIVE_LLM_SERVER,
        "runtime_profile": SETTINGS.VENOM_RUNTIME_PROFILE,
        "config_hash": getattr(SETTINGS, "LLM_CONFIG_HASH", None),
        "onnx_enabled": getattr(SETTINGS, "ONNX_LLM_ENABLED", False),
    }


def _restore_settings(snapshot):
    SETTINGS.LLM_SERVICE_TYPE = snapshot["service_type"]
    SETTINGS.LLM_LOCAL_ENDPOINT = snapshot["endpoint"]
    SETTINGS.LLM_MODEL_NAME = snapshot["model"]
    SETTINGS.ACTIVE_LLM_SERVER = snapshot["active"]
    SETTINGS.VENOM_RUNTIME_PROFILE = snapshot["runtime_profile"]
    SETTINGS.ONNX_LLM_ENABLED = snapshot["onnx_enabled"]
    if snapshot["config_hash"] is not None:
        SETTINGS.LLM_CONFIG_HASH = snapshot["config_hash"]


def _capture_update_config(updates: dict[str, object]):
    def _update(payload: dict[str, object]):
        updates.update(payload)
        return {
            "success": True,
            "message": "ok",
            "restart_required": [],
            "changed_keys": list(payload.keys()),
        }

    return _update


@pytest.fixture(autouse=True)
def _skip_real_shutdown_wait(monkeypatch):
    async def _fake_shutdown(_server_name: str, _health_url: str) -> bool:
        return True

    monkeypatch.setattr(system_routes, "_await_server_shutdown", _fake_shutdown)
    # Also patch the orchestrator's probe function to prevent real network calls.
    monkeypatch.setattr(runtime_switch_service, "probe_until_shutdown", _fake_shutdown)


@pytest.mark.asyncio
async def test_await_server_health_gemma4_audio_waits_for_ready(monkeypatch):
    responses = [
        _FakeResponse(200, {"status": "warming"}),
        _FakeResponse(200, {"status": "ok"}),
    ]

    async def _fast_sleep(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        system_routes.httpx,
        "AsyncClient",
        lambda timeout=2.0: _FakeAsyncClient(responses),
    )
    monkeypatch.setattr(system_routes.asyncio, "sleep", _fast_sleep)

    assert (
        await system_routes._await_server_health(
            "multi_runtime", "http://localhost:8014/health"
        )
        is True
    )


@pytest.mark.asyncio
async def test_await_server_health_non_gemma_accepts_http_200(monkeypatch):
    responses = [_FakeResponse(200, {"status": "error"})]
    monkeypatch.setattr(
        system_routes.httpx,
        "AsyncClient",
        lambda timeout=2.0: _FakeAsyncClient(responses),
    )

    assert (
        await system_routes._await_server_health("ollama", "http://localhost:11434")
        is True
    )


@pytest.mark.asyncio
async def test_await_server_shutdown_waits_until_unhealthy(monkeypatch):
    responses = [
        _FakeResponse(200, {"status": "ok"}),
        _FakeResponse(200, {"status": "ok"}),
        _FakeResponse(503, {"status": "down"}),
    ]

    async def _fast_sleep(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        system_routes.httpx,
        "AsyncClient",
        lambda timeout=2.0: _FakeAsyncClient(responses),
    )
    monkeypatch.setattr(system_routes.asyncio, "sleep", _fast_sleep)

    assert (
        await system_routes._await_server_shutdown(
            "multi_runtime", "http://localhost:8014/health"
        )
        is True
    )


def test_extract_health_status_handles_non_json_response():
    response = _FakeResponse(200, ValueError("invalid json"))
    assert system_routes._extract_health_status(response) is None


@pytest.mark.asyncio
async def test_set_active_llm_server_uses_last_model(tmp_path, monkeypatch):
    config = {
        "LAST_MODEL_OLLAMA": "phi3:mini",
        "PREVIOUS_MODEL_OLLAMA": "phi3:old",
        "LLM_MODEL_NAME": "phi3:mini",
    }
    updates = {}
    monkeypatch.setattr(
        system_routes.config_manager, "get_config", lambda **_: config.copy()
    )
    monkeypatch.setattr(
        system_routes.config_manager, "update_config", _capture_update_config(updates)
    )

    servers = [
        {
            "name": "ollama",
            "supports": {"start": True, "stop": True},
            "endpoint": "",
            "health_url": "http://localhost:11434/api/tags",
        },
        {
            "name": "vllm",
            "supports": {"start": True, "stop": True},
            "endpoint": "",
            "health_url": "http://localhost:8001/models",
        },
    ]
    models = [{"name": "phi3:mini", "provider": "ollama"}]
    monkeypatch.setattr(
        system_routes.system_deps, "_llm_controller", DummyController(servers)
    )
    monkeypatch.setattr(
        system_routes.system_deps, "_model_manager", DummyModelManager(models)
    )
    monkeypatch.setattr(system_routes.system_deps, "_request_tracer", None)
    monkeypatch.setattr(
        system_routes,
        "_installed_local_servers",
        lambda: {"ollama", "vllm"},
    )

    original = _snapshot_settings()
    SETTINGS.LLM_SERVICE_TYPE = "local"
    SETTINGS.LLM_LOCAL_ENDPOINT = LOCALHOST_11434_V1
    SETTINGS.LLM_MODEL_NAME = "phi3:mini"
    SETTINGS.ACTIVE_LLM_SERVER = "ollama"

    request = system_routes.ActiveLlmServerRequest(server_name="ollama")
    response = await system_routes.set_active_llm_server(request)
    assert response["active_model"] == "phi3:mini"
    assert response["shutdown_results"]["vllm"]["ok"] is True
    assert updates["LLM_MODEL_NAME"] == "phi3:mini"

    _restore_settings(original)


@pytest.mark.asyncio
async def test_set_active_llm_server_fallbacks_to_previous(monkeypatch):
    config = {
        "LAST_MODEL_OLLAMA": "missing",
        "PREVIOUS_MODEL_OLLAMA": "phi3:old",
        "LLM_MODEL_NAME": "missing",
    }
    updates = {}
    monkeypatch.setattr(
        system_routes.config_manager, "get_config", lambda **_: config.copy()
    )
    monkeypatch.setattr(
        system_routes.config_manager, "update_config", _capture_update_config(updates)
    )

    servers = [
        {"name": "ollama", "supports": {"start": True, "stop": True}, "endpoint": ""}
    ]
    models = [{"name": "phi3:old", "provider": "ollama"}]
    monkeypatch.setattr(
        system_routes.system_deps, "_llm_controller", DummyController(servers)
    )
    monkeypatch.setattr(
        system_routes.system_deps, "_model_manager", DummyModelManager(models)
    )
    monkeypatch.setattr(system_routes.system_deps, "_request_tracer", None)
    monkeypatch.setattr(
        system_routes,
        "_installed_local_servers",
        lambda: {"ollama"},
    )

    original = _snapshot_settings()
    SETTINGS.LLM_SERVICE_TYPE = "local"
    SETTINGS.LLM_LOCAL_ENDPOINT = LOCALHOST_11434_V1
    SETTINGS.LLM_MODEL_NAME = "missing"
    SETTINGS.ACTIVE_LLM_SERVER = "ollama"
    try:
        request = system_routes.ActiveLlmServerRequest(server_name="ollama")
        response = await system_routes.set_active_llm_server(request)
        assert response["active_model"] == "phi3:old"
        assert updates["LAST_MODEL_OLLAMA"] == "phi3:old"
    finally:
        _restore_settings(original)


@pytest.mark.asyncio
async def test_set_active_llm_server_waits_for_previous_runtime_shutdown_before_start(
    monkeypatch,
):
    config = {
        "LAST_MODEL_OLLAMA": "phi3:mini",
        "PREVIOUS_MODEL_OLLAMA": "",
        "LLM_MODEL_NAME": "phi3:mini",
    }
    updates = {}
    shutdown_calls = []
    monkeypatch.setattr(
        system_routes.config_manager, "get_config", lambda **_: config.copy()
    )
    monkeypatch.setattr(
        system_routes.config_manager, "update_config", _capture_update_config(updates)
    )

    servers = [
        {
            "name": "ollama",
            "supports": {"start": True, "stop": True},
            "endpoint": "",
            "health_url": "http://localhost:11434/api/tags",
        },
        {
            "name": "vllm",
            "supports": {"start": True, "stop": True},
            "endpoint": "",
            "health_url": "http://localhost:8001/models",
        },
    ]
    models = [{"name": "phi3:mini", "provider": "ollama"}]
    controller = DummyController(servers)
    monkeypatch.setattr(system_routes.system_deps, "_llm_controller", controller)
    monkeypatch.setattr(
        system_routes.system_deps, "_model_manager", DummyModelManager(models)
    )
    monkeypatch.setattr(system_routes.system_deps, "_request_tracer", None)
    monkeypatch.setattr(
        system_routes,
        "_installed_local_servers",
        lambda: {"ollama", "vllm"},
    )

    async def _fake_shutdown(server_name: str, health_url: str) -> bool:
        shutdown_calls.append((server_name, health_url))
        return True

    monkeypatch.setattr(system_routes, "_await_server_shutdown", _fake_shutdown)
    monkeypatch.setattr(runtime_switch_service, "probe_until_shutdown", _fake_shutdown)

    original = _snapshot_settings()
    SETTINGS.LLM_SERVICE_TYPE = "local"
    SETTINGS.LLM_LOCAL_ENDPOINT = LOCALHOST_11434_V1
    SETTINGS.LLM_MODEL_NAME = "phi3:mini"
    SETTINGS.ACTIVE_LLM_SERVER = "ollama"
    try:
        request = system_routes.ActiveLlmServerRequest(server_name="ollama")
        response = await system_routes.set_active_llm_server(request)
        assert response["status"] == "success"
        assert shutdown_calls == [("vllm", "http://localhost:8001/models")]
        assert controller.actions == [("vllm", "stop"), ("ollama", "start")]
    finally:
        _restore_settings(original)


@pytest.mark.asyncio
async def test_set_active_llm_server_waits_for_active_runtime_requests_to_drain(
    monkeypatch,
):
    entered = asyncio.Event()
    release = asyncio.Event()

    async def _active_request():
        async with gate.runtime_request_guard(
            request_kind="voice_chat",
            provider="ollama",
            model="qwen3.5:latest",
        ):
            entered.set()
            await release.wait()

    task = asyncio.create_task(_active_request())
    await entered.wait()

    config = {
        "LAST_MODEL_OLLAMA": "phi3:mini",
        "PREVIOUS_MODEL_OLLAMA": "",
        "LLM_MODEL_NAME": "phi3:mini",
    }
    updates = {}
    monkeypatch.setattr(
        system_routes.config_manager, "get_config", lambda **_: config.copy()
    )
    monkeypatch.setattr(
        system_routes.config_manager, "update_config", _capture_update_config(updates)
    )
    controller = DummyController(
        [
            {
                "name": "ollama",
                "supports": {"start": True, "stop": True},
                "endpoint": "",
                "health_url": "http://localhost:11434/api/tags",
            }
        ]
    )
    monkeypatch.setattr(system_routes.system_deps, "_llm_controller", controller)
    monkeypatch.setattr(
        system_routes.system_deps,
        "_model_manager",
        DummyModelManager([{"name": "phi3:mini", "provider": "ollama"}]),
    )
    monkeypatch.setattr(system_routes.system_deps, "_request_tracer", None)
    monkeypatch.setattr(system_routes, "_installed_local_servers", lambda: {"ollama"})

    class _DummySwitchState:
        def __init__(self):
            self.completed = []

        def mark_done(self, step):
            self.completed.append(step)

        def to_payload(self):
            return {
                "completed_steps": [step.value for step in self.completed],
                "is_complete": True,
            }

    class _DummyOrchestrator:
        def __init__(self, _controller):
            self._controller = _controller

        async def execute_lifecycle_switch(self, **_kwargs):
            return (
                _DummySwitchState(),
                {},
                {},
                {"ok": True},
                {
                    "name": "ollama",
                    "endpoint": "",
                },
            )

    monkeypatch.setattr(system_routes, "RuntimeSwitchOrchestrator", _DummyOrchestrator)

    original = _snapshot_settings()
    SETTINGS.LLM_SERVICE_TYPE = "local"
    SETTINGS.LLM_LOCAL_ENDPOINT = LOCALHOST_11434_V1
    SETTINGS.LLM_MODEL_NAME = "phi3:mini"
    SETTINGS.ACTIVE_LLM_SERVER = "ollama"
    SETTINGS.VENOM_RUNTIME_PROFILE = "full"

    request = system_routes.ActiveLlmServerRequest(server_name="ollama")
    try:
        response_task = asyncio.create_task(
            system_routes.set_active_llm_server(request)
        )
        await asyncio.sleep(0.05)
        assert not response_task.done()

        with pytest.raises(HTTPException) as exc_info:
            async with gate.runtime_request_guard(request_kind="simple_chat"):
                pass
        assert exc_info.value.status_code == 409

        release.set()
        response = await response_task
        assert response["status"] == "success"
    finally:
        release.set()
        await task
        _restore_settings(original)


@pytest.mark.asyncio
async def test_audio_status_endpoint_marks_latest_session_as_stale_after_runtime_switch(
    monkeypatch,
):
    class DummyHandler:
        def get_status(self, operator_agent=None):
            return {
                "enabled": True,
                "connected_clients": 1,
                "active_recordings": 0,
                "message": "ok",
            }

        def get_latest_voice_session(self):
            return {
                "session_id": "session-1",
                "created_at": "2026-05-24T09:00:00+00:00",
                "audio_runtime_provider": "multi_runtime",
                "audio_runtime_model": "google/gemma-4-E2B-it",
            }

    monkeypatch.setattr(main_module, "audio_stream_handler", DummyHandler())
    monkeypatch.setattr(main_module, "operator_agent", object())
    monkeypatch.setattr(
        main_module,
        "_build_voice_runtime_snapshot",
        AsyncMock(
            return_value={
                "runtime_id": "ollama@localhost",
                "provider": "ollama",
                "model_name": "qwen3.5:latest",
            }
        ),
    )
    monkeypatch.setattr(
        main_module,
        "get_last_runtime_switch_event",
        lambda: {"at_utc": "2026-05-24T09:10:00+00:00"},
    )
    request = SimpleNamespace(url_for=lambda name: f"https://example.test/{name}")

    status = await main_module.audio_status_endpoint(request)

    assert status["runtime_alignment"]["latest_session_before_runtime_switch"] is True
    assert status["runtime_alignment"]["response_runtime_fresh"] is False
    assert status["runtime_alignment"]["response_runtime_matches_active"] is False


def test_main_voice_runtime_alignment_helpers_cover_parse_and_identity(monkeypatch):
    assert main_module._parse_iso_datetime(None) is None
    assert main_module._parse_iso_datetime("2026-05-24T09:10:00Z") == datetime(
        2026, 5, 24, 9, 10, tzinfo=UTC
    )
    assert (
        main_module._same_runtime_identity(
            " Ollama ",
            " Qwen3.5:Latest ",
            "ollama",
            "qwen3.5:latest",
        )
        is True
    )

    monkeypatch.setattr(
        main_module,
        "get_last_runtime_switch_event",
        lambda: {"at_utc": "2026-05-24T09:10:00+00:00"},
    )
    alignment = main_module._build_voice_runtime_alignment(
        runtime_snapshot={"provider": "ollama", "model_name": "qwen3.5:latest"},
        latest_session=None,
    )

    assert alignment["latest_session_created_at"] is None
    assert alignment["latest_session_before_runtime_switch"] is False
    assert alignment["response_runtime_fresh"] is False
    assert alignment["response_runtime_matches_active"] is None


@pytest.mark.asyncio
async def test_set_active_llm_server_raises_without_models(monkeypatch):
    config = {
        "LAST_MODEL_OLLAMA": "missing",
        "PREVIOUS_MODEL_OLLAMA": "",
        "LLM_MODEL_NAME": "missing",
    }
    updates = {}
    monkeypatch.setattr(
        system_routes.config_manager, "get_config", lambda **_: config.copy()
    )
    monkeypatch.setattr(
        system_routes.config_manager, "update_config", _capture_update_config(updates)
    )

    servers = [
        {"name": "ollama", "supports": {"start": True, "stop": True}, "endpoint": ""}
    ]
    models = [{"name": "phi3:mini", "provider": "vllm"}]
    monkeypatch.setattr(
        system_routes.system_deps, "_llm_controller", DummyController(servers)
    )
    monkeypatch.setattr(
        system_routes.system_deps, "_model_manager", DummyModelManager(models)
    )
    monkeypatch.setattr(system_routes.system_deps, "_request_tracer", None)
    monkeypatch.setattr(
        system_routes,
        "_installed_local_servers",
        lambda: {"ollama"},
    )

    original = _snapshot_settings()
    SETTINGS.LLM_SERVICE_TYPE = "local"
    SETTINGS.LLM_LOCAL_ENDPOINT = LOCALHOST_11434_V1
    SETTINGS.LLM_MODEL_NAME = "missing"
    SETTINGS.ACTIVE_LLM_SERVER = "ollama"
    try:
        request = system_routes.ActiveLlmServerRequest(server_name="ollama")
        with pytest.raises(system_routes.HTTPException) as exc:
            await system_routes.set_active_llm_server(request)
        assert exc.value.status_code == 400
    finally:
        _restore_settings(original)


@pytest.mark.asyncio
async def test_set_active_llm_server_uses_available_ollama_model_when_requested_model_is_stale(
    monkeypatch,
):
    config = {
        "LAST_MODEL_OLLAMA": "missing",
        "PREVIOUS_MODEL_OLLAMA": "",
        "LLM_MODEL_NAME": "missing",
    }
    updates = {}
    monkeypatch.setattr(
        system_routes.config_manager, "get_config", lambda **_: config.copy()
    )
    monkeypatch.setattr(
        system_routes.config_manager, "update_config", _capture_update_config(updates)
    )

    servers = [
        {"name": "ollama", "supports": {"start": True, "stop": True}, "endpoint": ""},
        {"name": "vllm", "supports": {"start": True, "stop": True}, "endpoint": ""},
    ]
    models = [
        {"name": "phi3:mini", "provider": "ollama"},
        {"name": "phi3:small", "provider": "ollama"},
    ]
    controller = DummyController(servers)
    monkeypatch.setattr(system_routes.system_deps, "_llm_controller", controller)
    monkeypatch.setattr(
        system_routes.system_deps, "_model_manager", DummyModelManager(models)
    )
    monkeypatch.setattr(system_routes.system_deps, "_request_tracer", None)
    monkeypatch.setattr(
        system_routes,
        "_installed_local_servers",
        lambda: {"ollama", "vllm"},
    )

    original = _snapshot_settings()
    SETTINGS.LLM_SERVICE_TYPE = "local"
    SETTINGS.LLM_LOCAL_ENDPOINT = LOCALHOST_11434_V1
    SETTINGS.LLM_MODEL_NAME = "missing"
    SETTINGS.ACTIVE_LLM_SERVER = "ollama"
    try:
        request = system_routes.ActiveLlmServerRequest(
            server_name="ollama",
            model="gemma4_audio_only_model",
        )
        response = await system_routes.set_active_llm_server(request)
        assert response["status"] == "success"
        assert response["active_model"] in {"phi3:mini", "phi3:small"}
        assert updates["LLM_MODEL_NAME"] in {"phi3:mini", "phi3:small"}
        assert ("vllm", "stop") in controller.actions
    finally:
        _restore_settings(original)


@pytest.mark.asyncio
async def test_set_active_llm_server_continues_when_stopping_other_server_fails(
    monkeypatch,
):
    config = {
        "LAST_MODEL_OLLAMA": "phi3:mini",
        "PREVIOUS_MODEL_OLLAMA": "",
        "LLM_MODEL_NAME": "phi3:mini",
    }
    updates = {}
    monkeypatch.setattr(
        system_routes.config_manager, "get_config", lambda **_: config.copy()
    )
    monkeypatch.setattr(
        system_routes.config_manager, "update_config", _capture_update_config(updates)
    )

    servers = [
        {"name": "ollama", "supports": {"start": True, "stop": True}, "endpoint": ""},
        {"name": "vllm", "supports": {"start": True, "stop": True}, "endpoint": ""},
    ]
    models = [{"name": "phi3:mini", "provider": "ollama"}]
    controller = DummyController(servers)
    controller.fail_actions.add(("vllm", "stop"))
    monkeypatch.setattr(system_routes.system_deps, "_llm_controller", controller)
    monkeypatch.setattr(
        system_routes.system_deps, "_model_manager", DummyModelManager(models)
    )
    monkeypatch.setattr(system_routes.system_deps, "_request_tracer", None)
    monkeypatch.setattr(
        system_routes,
        "_installed_local_servers",
        lambda: {"ollama", "vllm"},
    )

    original = _snapshot_settings()
    SETTINGS.LLM_SERVICE_TYPE = "local"
    SETTINGS.LLM_LOCAL_ENDPOINT = LOCALHOST_11434_V1
    SETTINGS.LLM_MODEL_NAME = "phi3:mini"
    SETTINGS.ACTIVE_LLM_SERVER = "ollama"
    try:
        request = system_routes.ActiveLlmServerRequest(server_name="ollama")
        response = await system_routes.set_active_llm_server(request)
        assert response["status"] == "success"
        assert response["active_model"] == "phi3:mini"
        assert response["stop_results"]["vllm"]["ok"] is False
    finally:
        _restore_settings(original)


@pytest.mark.asyncio
async def test_get_llm_servers_filters_vllm_outside_full_profile(monkeypatch):
    servers = [
        {
            "name": "ollama",
            "display_name": "Ollama",
            "supports": {"start": True, "stop": True},
            "endpoint": "",
        },
        {
            "name": "vllm",
            "display_name": "vLLM",
            "supports": {"start": True, "stop": True},
            "endpoint": "",
        },
    ]
    monkeypatch.setattr(
        system_routes.system_deps, "_llm_controller", DummyController(servers)
    )
    monkeypatch.setattr(system_routes.system_deps, "_service_monitor", None)
    monkeypatch.setattr(
        system_routes,
        "_installed_local_servers",
        lambda: {"ollama", "vllm"},
    )

    async def _noop_probe(_servers, _active_server_name=None):
        return None

    monkeypatch.setattr(system_routes, "_probe_servers", _noop_probe)

    original = _snapshot_settings()
    SETTINGS.VENOM_RUNTIME_PROFILE = "light"
    try:
        response = await system_routes.get_llm_servers()
        names = [entry["name"] for entry in response["servers"]]
        assert names == ["ollama"]
    finally:
        _restore_settings(original)


@pytest.mark.asyncio
async def test_get_llm_servers_includes_onnx_when_enabled(monkeypatch):
    servers = [
        {
            "name": "ollama",
            "display_name": "Ollama",
            "supports": {"start": True, "stop": True},
            "endpoint": "",
        },
        {
            "name": "vllm",
            "display_name": "vLLM",
            "supports": {"start": True, "stop": True},
            "endpoint": "",
        },
    ]
    monkeypatch.setattr(
        system_routes.system_deps, "_llm_controller", DummyController(servers)
    )
    monkeypatch.setattr(system_routes.system_deps, "_service_monitor", None)
    monkeypatch.setattr(
        system_routes,
        "_installed_local_servers",
        lambda: {"ollama", "vllm", "onnx"},
    )
    monkeypatch.setattr(
        system_routes,
        "_build_onnx_server_payload",
        lambda: {
            "name": "onnx",
            "display_name": "ONNX Runtime",
            "supports": {"start": False, "stop": False, "restart": False},
            "endpoint": None,
            "provider": "onnx",
            "status": "online",
        },
    )

    async def _noop_probe(_servers, _active_server_name=None):
        return None

    monkeypatch.setattr(system_routes, "_probe_servers", _noop_probe)

    original = _snapshot_settings()
    SETTINGS.VENOM_RUNTIME_PROFILE = "full"
    SETTINGS.ONNX_LLM_ENABLED = True
    try:
        response = await system_routes.get_llm_servers()
        names = [entry["name"] for entry in response["servers"]]
        assert "onnx" in names
    finally:
        _restore_settings(original)


@pytest.mark.asyncio
async def test_set_active_llm_server_rejects_vllm_for_light_profile():
    original = _snapshot_settings()
    SETTINGS.VENOM_RUNTIME_PROFILE = "light"
    try:
        request = system_routes.ActiveLlmServerRequest(server_name="vllm")
        with pytest.raises(system_routes.HTTPException) as exc:
            await system_routes.set_active_llm_server(request)
        assert exc.value.status_code == 403
        assert exc.value.detail["decision"] == "block"
        assert exc.value.detail["reason_code"] == "PERMISSION_DENIED"
        assert (
            exc.value.detail["technical_context"]["operation"]
            == "system.llm.server_allowed"
        )
    finally:
        _restore_settings(original)


@pytest.mark.asyncio
async def test_get_llm_servers_deduplicates_onnx(monkeypatch):
    servers = [
        {
            "name": "ollama",
            "display_name": "Ollama",
            "supports": {"start": True, "stop": True},
            "endpoint": "",
        },
        {
            "name": "onnx",
            "display_name": "ONNX (controller)",
            "supports": {"start": False, "stop": False},
            "endpoint": None,
        },
    ]
    monkeypatch.setattr(
        system_routes.system_deps, "_llm_controller", DummyController(servers)
    )
    monkeypatch.setattr(system_routes.system_deps, "_service_monitor", None)
    monkeypatch.setattr(
        system_routes,
        "_installed_local_servers",
        lambda: {"ollama", "onnx"},
    )
    monkeypatch.setattr(
        system_routes,
        "_build_onnx_server_payload",
        lambda: {
            "name": "onnx",
            "display_name": "ONNX Runtime",
            "supports": {"start": False, "stop": False, "restart": False},
            "endpoint": None,
            "provider": "onnx",
            "status": "online",
        },
    )

    async def _noop_probe(_servers, _active_server_name=None):
        return None

    monkeypatch.setattr(system_routes, "_probe_servers", _noop_probe)

    original = _snapshot_settings()
    SETTINGS.VENOM_RUNTIME_PROFILE = "full"
    SETTINGS.ONNX_LLM_ENABLED = True
    try:
        response = await system_routes.get_llm_servers()
        names = [entry["name"] for entry in response["servers"]]
        assert names.count("onnx") == 1
    finally:
        _restore_settings(original)


@pytest.mark.asyncio
async def test_set_active_llm_server_onnx_in_process(monkeypatch):
    original = _snapshot_settings()
    SETTINGS.VENOM_RUNTIME_PROFILE = "full"
    SETTINGS.ONNX_LLM_ENABLED = True
    try:
        controller = DummyController(
            [
                {
                    "name": "ollama",
                    "supports": {"start": True, "stop": True},
                    "endpoint": "",
                },
                {
                    "name": "vllm",
                    "supports": {"start": True, "stop": True},
                    "endpoint": "",
                },
                {
                    "name": "onnx",
                    "supports": {"start": False, "stop": False},
                    "endpoint": None,
                },
            ]
        )
        monkeypatch.setattr(system_routes.system_deps, "_llm_controller", controller)
        monkeypatch.setattr(
            system_routes.config_manager,
            "get_config",
            lambda **_: {"LAST_MODEL_ONNX": "models/phi35-local-onnx"},
        )
        monkeypatch.setattr(
            system_routes,
            "_installed_local_servers",
            lambda: {"onnx"},
        )
        updates = {}
        monkeypatch.setattr(
            system_routes.config_manager,
            "update_config",
            _capture_update_config(updates),
        )
        dummy_client = SimpleNamespace(
            ensure_ready=lambda: None,
            config=SimpleNamespace(model_path="models/phi35-local-onnx"),
        )
        monkeypatch.setattr(system_routes, "OnnxLlmClient", lambda: dummy_client)

        request = system_routes.ActiveLlmServerRequest(server_name="onnx")
        response = await system_routes.set_active_llm_server(request)
        assert response["status"] == "success"
        assert response["active_server"] == "onnx"
        assert updates["LLM_SERVICE_TYPE"] == "onnx"
        assert ("ollama", "stop") in controller.actions
        assert ("vllm", "stop") in controller.actions
        assert response["stop_results"]["ollama"]["ok"] is True
        assert response["stop_results"]["vllm"]["ok"] is True
    finally:
        _restore_settings(original)


@pytest.mark.asyncio
async def test_set_active_llm_server_onnx_fails_when_other_server_stop_fails(
    monkeypatch,
):
    original = _snapshot_settings()
    SETTINGS.VENOM_RUNTIME_PROFILE = "full"
    SETTINGS.ONNX_LLM_ENABLED = True
    try:
        controller = DummyController(
            [
                {
                    "name": "ollama",
                    "supports": {"start": True, "stop": True},
                    "endpoint": "",
                },
                {
                    "name": "onnx",
                    "supports": {"start": False, "stop": False},
                    "endpoint": None,
                },
            ]
        )
        controller.fail_actions.add(("ollama", "stop"))
        monkeypatch.setattr(system_routes.system_deps, "_llm_controller", controller)
        monkeypatch.setattr(
            system_routes.config_manager,
            "get_config",
            lambda **_: {"LAST_MODEL_ONNX": "models/phi35-local-onnx"},
        )
        monkeypatch.setattr(
            system_routes,
            "_installed_local_servers",
            lambda: {"onnx"},
        )
        updates = {}
        monkeypatch.setattr(
            system_routes.config_manager,
            "update_config",
            _capture_update_config(updates),
        )
        dummy_client = SimpleNamespace(
            ensure_ready=lambda: None,
            config=SimpleNamespace(model_path="models/phi35-local-onnx"),
        )
        monkeypatch.setattr(system_routes, "OnnxLlmClient", lambda: dummy_client)

        request = system_routes.ActiveLlmServerRequest(server_name="onnx")
        response = await system_routes.set_active_llm_server(request)
        assert response["status"] == "success"
        assert response["active_server"] == "onnx"
        assert response["stop_results"]["ollama"]["ok"] is False
    finally:
        _restore_settings(original)


@pytest.mark.asyncio
async def test_get_llm_servers_excludes_not_installed_runtime(monkeypatch):
    servers = [
        {
            "name": "ollama",
            "display_name": "Ollama",
            "supports": {"start": True, "stop": True},
            "endpoint": "",
        },
        {
            "name": "vllm",
            "display_name": "vLLM",
            "supports": {"start": True, "stop": True},
            "endpoint": "",
        },
    ]
    monkeypatch.setattr(
        system_routes.system_deps, "_llm_controller", DummyController(servers)
    )
    monkeypatch.setattr(system_routes.system_deps, "_service_monitor", None)
    monkeypatch.setattr(
        system_routes,
        "_installed_local_servers",
        lambda: {"ollama"},
    )

    async def _noop_probe(_servers, _active_server_name=None):
        return None

    monkeypatch.setattr(system_routes, "_probe_servers", _noop_probe)

    original = _snapshot_settings()
    SETTINGS.VENOM_RUNTIME_PROFILE = "full"
    SETTINGS.ONNX_LLM_ENABLED = True
    try:
        response = await system_routes.get_llm_servers()
        names = [entry["name"] for entry in response["servers"]]
        assert names == ["ollama"]
    finally:
        _restore_settings(original)


@pytest.mark.asyncio
async def test_set_active_llm_server_releases_onnx_caches_when_switching_to_ollama(
    monkeypatch,
):
    config = {
        "LAST_MODEL_OLLAMA": "phi3:mini",
        "PREVIOUS_MODEL_OLLAMA": "",
        "LLM_MODEL_NAME": "phi3:mini",
    }
    updates = {}
    monkeypatch.setattr(
        system_routes.config_manager, "get_config", lambda **_: config.copy()
    )
    monkeypatch.setattr(
        system_routes.config_manager, "update_config", _capture_update_config(updates)
    )

    controller = DummyController(
        [
            {
                "name": "ollama",
                "supports": {"start": True, "stop": True},
                "endpoint": "",
            },
            {
                "name": "onnx",
                "supports": {"start": False, "stop": False},
                "endpoint": None,
            },
        ]
    )
    monkeypatch.setattr(system_routes.system_deps, "_llm_controller", controller)
    monkeypatch.setattr(
        system_routes.system_deps,
        "_model_manager",
        DummyModelManager([{"name": "phi3:mini", "provider": "ollama"}]),
    )
    monkeypatch.setattr(system_routes.system_deps, "_request_tracer", None)
    monkeypatch.setattr(system_routes, "_installed_local_servers", lambda: {"ollama"})

    releases: list[bool] = []
    monkeypatch.setattr(
        system_routes, "_release_onnx_runtime_caches", lambda: releases.append(True)
    )

    original = _snapshot_settings()
    SETTINGS.VENOM_RUNTIME_PROFILE = "full"
    SETTINGS.LLM_SERVICE_TYPE = "local"
    SETTINGS.ACTIVE_LLM_SERVER = "onnx"
    SETTINGS.LLM_MODEL_NAME = "phi3:mini"
    try:
        request = system_routes.ActiveLlmServerRequest(server_name="ollama")
        response = await system_routes.set_active_llm_server(request)
        assert response["status"] == "success"
        assert releases == [True]
    finally:
        _restore_settings(original)


@pytest.mark.asyncio
async def test_set_active_llm_server_normalizes_gemma4_audio_alias(monkeypatch):
    config = {
        "LAST_MODEL_GEMMA4_AUDIO": "google/gemma-4-E2B-it",
        "PREVIOUS_MODEL_GEMMA4_AUDIO": "",
        "LLM_MODEL_NAME": "google/gemma-4-E2B-it",
    }
    updates = {}
    monkeypatch.setattr(
        system_routes.config_manager, "get_config", lambda **_: config.copy()
    )
    monkeypatch.setattr(
        system_routes.config_manager, "update_config", _capture_update_config(updates)
    )

    controller = DummyController(
        [
            {
                "name": "ollama",
                "supports": {"start": True, "stop": True},
                "endpoint": "",
            },
            {
                "name": "multi_runtime",
                "supports": {"start": True, "stop": True},
                "endpoint": "",
            },
        ]
    )
    monkeypatch.setattr(system_routes.system_deps, "_llm_controller", controller)
    monkeypatch.setattr(
        system_routes.system_deps,
        "_model_manager",
        DummyModelManager(
            [{"name": "google/gemma-4-E2B-it", "provider": "multi_runtime"}]
        ),
    )
    monkeypatch.setattr(system_routes.system_deps, "_request_tracer", None)
    monkeypatch.setattr(
        system_routes,
        "_installed_local_servers",
        lambda: {"ollama", "multi_runtime"},
    )

    original = _snapshot_settings()
    SETTINGS.VENOM_RUNTIME_PROFILE = "full"
    SETTINGS.LLM_SERVICE_TYPE = "local"
    SETTINGS.LLM_LOCAL_ENDPOINT = LOCALHOST_11434_V1
    SETTINGS.LLM_MODEL_NAME = "google/gemma-4-E2B-it"
    SETTINGS.ACTIVE_LLM_SERVER = "ollama"
    try:
        request = system_routes.ActiveLlmServerRequest(
            server_name="gemma4_audio",
            model="google/gemma-4-E2B-it",
        )
        response = await system_routes.set_active_llm_server(request)
        assert response["status"] == "success"
        assert response["active_server"] == "multi_runtime"
        assert response["active_model"] == "google/gemma-4-E2B-it"
        assert ("ollama", "stop") in controller.actions
        assert ("multi_runtime", "start") in controller.actions
        assert updates["ACTIVE_LLM_SERVER"] == "multi_runtime"
        assert updates["GEMMA4_AUDIO_ENABLED"] == "true"
        assert updates["GEMMA4_AUDIO_MODEL_ID"] == "google/gemma-4-E2B-it"
    finally:
        _restore_settings(original)


@pytest.mark.asyncio
async def test_set_active_llm_server_fails_when_persistence_fails(monkeypatch):
    config = {
        "LAST_MODEL_GEMMA4_AUDIO": "google/gemma-4-E2B-it",
        "PREVIOUS_MODEL_GEMMA4_AUDIO": "",
        "LLM_MODEL_NAME": "google/gemma-4-E2B-it",
    }
    monkeypatch.setattr(
        system_routes.config_manager, "get_config", lambda **_: config.copy()
    )
    monkeypatch.setattr(
        system_routes.config_manager,
        "update_config",
        lambda *_args, **_kwargs: {"success": False, "message": "disk full"},
    )

    controller = DummyController(
        [
            {
                "name": "multi_runtime",
                "supports": {"start": True, "stop": True},
                "endpoint": "",
            },
        ]
    )
    monkeypatch.setattr(system_routes.system_deps, "_llm_controller", controller)
    monkeypatch.setattr(
        system_routes.system_deps,
        "_model_manager",
        DummyModelManager(
            [{"name": "google/gemma-4-E2B-it", "provider": "multi_runtime"}]
        ),
    )
    monkeypatch.setattr(system_routes.system_deps, "_request_tracer", None)
    monkeypatch.setattr(
        system_routes,
        "_installed_local_servers",
        lambda: {"multi_runtime"},
    )

    original = _snapshot_settings()
    SETTINGS.VENOM_RUNTIME_PROFILE = "full"
    SETTINGS.LLM_SERVICE_TYPE = "local"
    SETTINGS.LLM_LOCAL_ENDPOINT = "http://localhost:8014/v1"
    SETTINGS.LLM_MODEL_NAME = "google/gemma-4-E2B-it"
    SETTINGS.ACTIVE_LLM_SERVER = "multi_runtime"
    try:
        request = system_routes.ActiveLlmServerRequest(
            server_name="gemma4_audio",
            model="google/gemma-4-E2B-it",
        )
        with pytest.raises(system_routes.HTTPException) as exc:
            await system_routes.set_active_llm_server(request)
        assert exc.value.status_code == 500
        assert "Nie udało się zapisać endpointu dla runtime 'multi_runtime'" in str(
            exc.value.detail
        )
    finally:
        _restore_settings(original)


@pytest.mark.asyncio
async def test_set_active_llm_server_resolves_feedback_loop_alias_to_primary(
    monkeypatch,
):
    from venom_core.services.feedback_loop_policy import FeedbackLoopGuardResult

    config = {
        "LAST_MODEL_OLLAMA": "phi3:mini",
        "PREVIOUS_MODEL_OLLAMA": "",
        "LLM_MODEL_NAME": "phi3:mini",
    }
    updates = {}
    monkeypatch.setattr(
        system_routes.config_manager, "get_config", lambda **_: config.copy()
    )
    monkeypatch.setattr(
        system_routes.config_manager, "update_config", _capture_update_config(updates)
    )

    controller = DummyController(
        [
            {
                "name": "ollama",
                "supports": {"start": True, "stop": True},
                "endpoint": "",
            }
        ]
    )
    monkeypatch.setattr(system_routes.system_deps, "_llm_controller", controller)
    monkeypatch.setattr(
        system_routes.system_deps,
        "_model_manager",
        DummyModelManager(
            [
                {"name": "qwen2.5-coder:7b", "provider": "ollama"},
                {"name": "qwen2.5-coder:3b", "provider": "ollama"},
            ]
        ),
    )
    monkeypatch.setattr(system_routes.system_deps, "_request_tracer", None)
    monkeypatch.setattr(system_routes, "_installed_local_servers", lambda: {"ollama"})

    async def _guard_ok(**_kwargs):
        return FeedbackLoopGuardResult(True, None, None)

    monkeypatch.setattr(
        system_routes,
        "_evaluate_feedback_loop_resource_guard",
        _guard_ok,
    )

    original = _snapshot_settings()
    SETTINGS.VENOM_RUNTIME_PROFILE = "full"
    SETTINGS.LLM_SERVICE_TYPE = "local"
    SETTINGS.ACTIVE_LLM_SERVER = "ollama"
    SETTINGS.LLM_MODEL_NAME = "phi3:mini"
    try:
        request = system_routes.ActiveLlmServerRequest(
            server_name="ollama",
            model_alias="OpenCodeInterpreter-Qwen2.5-7B",
        )
        response = await system_routes.set_active_llm_server(request)
        assert response["active_model"] == "qwen2.5-coder:7b"
        assert response["requested_model_alias"] == "OpenCodeInterpreter-Qwen2.5-7B"
        assert response["resolved_model_id"] == "qwen2.5-coder:7b"
        assert response["resolution_reason"] == "exact"
    finally:
        _restore_settings(original)


@pytest.mark.asyncio
async def test_set_active_llm_server_feedback_loop_alias_fallback_on_resource_guard(
    monkeypatch,
):
    from venom_core.services.feedback_loop_policy import FeedbackLoopGuardResult

    config = {
        "LAST_MODEL_OLLAMA": "phi3:mini",
        "PREVIOUS_MODEL_OLLAMA": "",
        "LLM_MODEL_NAME": "phi3:mini",
    }
    updates = {}
    monkeypatch.setattr(
        system_routes.config_manager, "get_config", lambda **_: config.copy()
    )
    monkeypatch.setattr(
        system_routes.config_manager, "update_config", _capture_update_config(updates)
    )

    controller = DummyController(
        [
            {
                "name": "ollama",
                "supports": {"start": True, "stop": True},
                "endpoint": "",
            }
        ]
    )
    monkeypatch.setattr(system_routes.system_deps, "_llm_controller", controller)
    monkeypatch.setattr(
        system_routes.system_deps,
        "_model_manager",
        DummyModelManager(
            [
                {"name": "qwen2.5-coder:7b", "provider": "ollama"},
                {"name": "qwen2.5-coder:3b", "provider": "ollama"},
            ]
        ),
    )
    monkeypatch.setattr(system_routes.system_deps, "_request_tracer", None)
    monkeypatch.setattr(system_routes, "_installed_local_servers", lambda: {"ollama"})

    async def _guard_block(**_kwargs):
        return FeedbackLoopGuardResult(
            False,
            "resource_guard",
            "fallback to qwen2.5-coder:3b",
        )

    monkeypatch.setattr(
        system_routes,
        "_evaluate_feedback_loop_resource_guard",
        _guard_block,
    )

    original = _snapshot_settings()
    SETTINGS.VENOM_RUNTIME_PROFILE = "full"
    SETTINGS.LLM_SERVICE_TYPE = "local"
    SETTINGS.ACTIVE_LLM_SERVER = "ollama"
    SETTINGS.LLM_MODEL_NAME = "phi3:mini"
    try:
        request = system_routes.ActiveLlmServerRequest(
            server_name="ollama",
            model_alias="OpenCodeInterpreter-Qwen2.5-7B",
        )
        response = await system_routes.set_active_llm_server(request)
        assert response["active_model"] == "qwen2.5-coder:3b"
        assert response["resolution_reason"] == "resource_guard"
        assert response["requested_model_alias"] == "OpenCodeInterpreter-Qwen2.5-7B"
    finally:
        _restore_settings(original)


def test_switch_source_defaults_to_ui():
    assert normalize_runtime_switch_source(None) == "ui"
    assert normalize_runtime_switch_source("") == "ui"


def test_switch_source_rejects_unmanaged():
    with pytest.raises(system_routes.HTTPException) as exc:
        assert_runtime_switch_source_allowed("manual_shell")
    assert exc.value.status_code == 403


def test_switch_source_allows_make_start():
    assert assert_runtime_switch_source_allowed("make_start") == "make_start"


def test_select_model_for_server_prefers_runtime_active_model(monkeypatch):
    config = {
        "LAST_MODEL_OLLAMA": "stale:model",
        "PREVIOUS_MODEL_OLLAMA": "older:model",
    }
    models = [{"name": "live:model", "provider": "ollama"}]
    monkeypatch.setattr(
        system_routes.config_manager,
        "get_runtime_snapshot",
        lambda **_: {"active_model_id": "live:model"},
    )
    selected, _, _ = system_routes._select_model_for_server(  # noqa: SLF001
        server_name="ollama",
        config=config,
        models=models,
    )
    assert selected == "live:model"


def test_fallback_model_selection_prefers_runtime_model_over_config(monkeypatch):
    config = {
        "LAST_MODEL_OLLAMA": "config:model",
        "PREVIOUS_MODEL_OLLAMA": "prev:model",
    }
    models = [
        {"name": "runtime:model", "provider": "ollama"},
        {"name": "config:model", "provider": "ollama"},
    ]
    monkeypatch.setattr(
        system_routes.config_manager,
        "get_runtime_snapshot",
        lambda **_: {"active_model_id": "runtime:model"},
    )
    selected, _ = system_routes._fallback_model_selection(  # noqa: SLF001
        request=system_routes.ActiveLlmServerRequest(server_name="ollama"),
        server_name="ollama",
        config=config,
        models=models,
    )
    assert selected == "runtime:model"


def test_vllm_autofix_context_uses_runtime_provider_not_config(monkeypatch):
    monkeypatch.setattr(system_routes.config_manager, "get_runtime_snapshot", None)
    monkeypatch.setattr(
        system_routes.config_manager,
        "get_config",
        lambda **_: {"ACTIVE_LLM_SERVER": "ollama", "VLLM_MODEL_PATH": "/bad/path"},
    )
    monkeypatch.setattr(
        system_routes,
        "get_active_llm_runtime",
        lambda: SimpleNamespace(provider="vllm", model_name="live:model"),
    )
    monkeypatch.setattr(
        system_routes,
        "_is_vllm_runtime_model_entry",
        lambda _model: True,
    )
    context = system_routes._build_vllm_runtime_autofix_context(  # noqa: SLF001
        local_models=[{"name": "live:model", "path": "/valid/path"}]
    )
    assert context is not None
