"""Unit tests for active LLM server selection (PR 069)."""

import asyncio
from types import SimpleNamespace

import pytest

from tests.helpers.url_fixtures import LOCALHOST_11434_V1
from venom_core.api.routes import system_llm as system_routes
from venom_core.config import SETTINGS


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


@pytest.fixture(autouse=True)
def _skip_real_shutdown_wait(monkeypatch):
    async def _fake_shutdown(_server_name: str, _health_url: str) -> bool:
        return True

    monkeypatch.setattr(system_routes, "_await_server_shutdown", _fake_shutdown)


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
    monkeypatch.setattr(system_routes.config_manager, "update_config", updates.update)

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
    monkeypatch.setattr(system_routes.config_manager, "update_config", updates.update)

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
    monkeypatch.setattr(system_routes.config_manager, "update_config", updates.update)

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
async def test_set_active_llm_server_raises_without_models(monkeypatch):
    config = {
        "LAST_MODEL_OLLAMA": "missing",
        "PREVIOUS_MODEL_OLLAMA": "",
        "LLM_MODEL_NAME": "missing",
    }
    monkeypatch.setattr(
        system_routes.config_manager, "get_config", lambda **_: config.copy()
    )
    monkeypatch.setattr(system_routes.config_manager, "update_config", lambda *_: None)

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
    monkeypatch.setattr(system_routes.config_manager, "update_config", updates.update)

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
    monkeypatch.setattr(system_routes.config_manager, "update_config", updates.update)

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

    async def _noop_probe(_servers):
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

    async def _noop_probe(_servers):
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

    async def _noop_probe(_servers):
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
            system_routes.config_manager, "update_config", updates.update
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
        monkeypatch.setattr(
            system_routes.config_manager,
            "update_config",
            lambda *_args, **_kwargs: None,
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

    async def _noop_probe(_servers):
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
    monkeypatch.setattr(system_routes.config_manager, "update_config", updates.update)

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
    monkeypatch.setattr(system_routes.config_manager, "update_config", updates.update)

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
    monkeypatch.setattr(system_routes.config_manager, "update_config", updates.update)

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
