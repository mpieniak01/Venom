"""PR 220A regression tests — runtime lifecycle management.

Covers:
1. ollama → multi_runtime switch releases previous stack and starts new
2. multi_runtime → ollama switch clears endpoint/cache
3. Health-check timeout leaves no partial config state
4. ONNX cleanup is best-effort and doesn't break the switch flow
5. RuntimeCapabilities contract is consistent with list_servers()
6. LifecycleSwitchState tracks switch progress correctly
7. detect_runtime_drift reports issues when config is inconsistent
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from venom_core.api.routes import system_llm as system_routes
from venom_core.config import SETTINGS
from venom_core.core.llm_server_controller import (
    LlmServerController,
    RuntimeCapabilities,
)
from venom_core.services import runtime_switch_service
from venom_core.services.runtime_switch_service import RuntimeSwitchOrchestrator
from venom_core.utils.llm_runtime import (
    LifecycleStep,
    LifecycleSwitchState,
    detect_runtime_drift,
)

OLLAMA_ENDPOINT = "http://localhost:11434"
MULTI_ENDPOINT = "http://localhost:8014"


class _DummyController:
    def __init__(self, servers):
        self._servers = servers
        self.actions: list[tuple[str, str]] = []
        self.fail_actions: set[tuple[str, str]] = set()

    def has_server(self, name):
        return any(s["name"] == name for s in self._servers)

    def list_servers(self):
        return self._servers

    def get_capabilities(self, name):
        for s in self._servers:
            if s["name"] == name:
                caps = s.get("capabilities", {})
                return RuntimeCapabilities(
                    **{
                        "supports_stop": caps.get("supports_stop", False),
                        "supports_start": caps.get("supports_start", False),
                        "supports_restart": caps.get("supports_restart", False),
                        "supports_health_wait": caps.get("supports_health_wait", False),
                        "supports_cache_flush": caps.get("supports_cache_flush", False),
                        "supports_model_unload": caps.get(
                            "supports_model_unload", False
                        ),
                        "is_in_process": caps.get("is_in_process", False),
                        "release_wait_seconds": caps.get("release_wait_seconds", 0),
                    }
                )
        raise ValueError(f"unknown: {name}")

    async def run_action(self, name, action):
        await asyncio.sleep(0)
        self.actions.append((name, action))
        if (name, action) in self.fail_actions:
            return SimpleNamespace(ok=False, exit_code=1)
        return SimpleNamespace(ok=True, exit_code=0)


class _DummyModelManager:
    def __init__(self, models):
        self._models = models

    async def list_local_models(self):
        await asyncio.sleep(0)
        return self._models


def _make_server(
    name: str,
    *,
    health_url: str = "",
    endpoint: str = "",
    supports_stop: bool = True,
    supports_start: bool = True,
    supports_health_wait: bool = False,
    supports_model_unload: bool = False,
    is_in_process: bool = False,
    release_wait_seconds: int = 0,
) -> dict[str, Any]:
    return {
        "name": name,
        "supports": {"stop": supports_stop, "start": supports_start},
        "endpoint": endpoint,
        "health_url": health_url,
        "capabilities": {
            "supports_stop": supports_stop,
            "supports_start": supports_start,
            "supports_restart": supports_stop,
            "supports_health_wait": supports_health_wait,
            "supports_cache_flush": is_in_process,
            "supports_model_unload": supports_model_unload,
            "is_in_process": is_in_process,
            "release_wait_seconds": release_wait_seconds,
        },
    }


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
def _no_real_network(monkeypatch):
    """Prevent real network calls from the orchestrator in all tests."""

    async def _fake_shutdown(_server_name, _health_url):
        return True

    async def _fake_health(_server_name, _health_url):
        return True

    monkeypatch.setattr(runtime_switch_service, "probe_until_shutdown", _fake_shutdown)
    monkeypatch.setattr(runtime_switch_service, "probe_health_ready", _fake_health)
    monkeypatch.setattr(system_routes, "_await_server_shutdown", _fake_shutdown)
    monkeypatch.setattr(system_routes, "_await_server_health", _fake_health)


# ---------------------------------------------------------------------------
# 1. RuntimeCapabilities contract
# ---------------------------------------------------------------------------


def test_runtime_capabilities_fields_for_all_servers():
    """Every server config exposes all RuntimeCapabilities fields."""
    ctrl = LlmServerController(SETTINGS)
    for server in ctrl.list_servers():
        caps = server["capabilities"]
        for field in [
            "supports_stop",
            "supports_start",
            "supports_restart",
            "supports_health_wait",
            "supports_cache_flush",
            "supports_model_unload",
            "is_in_process",
            "release_wait_seconds",
        ]:
            assert field in caps, f"{server['name']} missing capability field '{field}'"


def test_onnx_capabilities_are_in_process():
    ctrl = LlmServerController(SETTINGS)
    caps = ctrl.get_capabilities("onnx")
    assert caps.is_in_process is True
    assert caps.supports_stop is False
    assert caps.supports_cache_flush is True
    assert caps.supports_model_unload is True


def test_ollama_capabilities_support_unload():
    ctrl = LlmServerController(SETTINGS)
    caps = ctrl.get_capabilities("ollama")
    assert caps.supports_model_unload is True
    assert caps.is_in_process is False
    assert caps.release_wait_seconds > 0


def test_multi_runtime_capabilities():
    ctrl = LlmServerController(SETTINGS)
    caps = ctrl.get_capabilities("multi_runtime")
    assert caps.supports_stop is True
    assert caps.supports_health_wait is True
    assert caps.is_in_process is False


# ---------------------------------------------------------------------------
# 2. LifecycleSwitchState tracking
# ---------------------------------------------------------------------------


def test_lifecycle_switch_state_tracks_progress():
    state = LifecycleSwitchState(from_server="ollama", to_server="multi_runtime")
    assert not state.is_complete
    assert not state.is_in_partial_state

    state.mark_done(LifecycleStep.PROCESS_STOPPED)
    state.mark_done(LifecycleStep.RELEASE_DONE)
    assert not state.is_complete

    state.mark_done(LifecycleStep.CACHE_INVALIDATED)
    state.mark_done(LifecycleStep.START_DONE)
    state.mark_done(LifecycleStep.HEALTH_READY)
    state.mark_done(LifecycleStep.ENDPOINT_SWITCHED)
    state.mark_done(LifecycleStep.CONFIG_SAVED)
    assert state.is_complete
    assert not state.is_in_partial_state


def test_lifecycle_switch_state_failed_step_is_partial():
    state = LifecycleSwitchState(from_server="ollama", to_server="vllm")
    state.mark_done(LifecycleStep.PROCESS_STOPPED)
    state.mark_failed(LifecycleStep.HEALTH_READY, "timeout")
    assert state.is_in_partial_state
    assert not state.is_complete
    assert state.failed_step == LifecycleStep.HEALTH_READY


def test_lifecycle_switch_state_payload():
    state = LifecycleSwitchState(from_server="a", to_server="b")
    state.mark_done(LifecycleStep.PROCESS_STOPPED)
    payload = state.to_payload()
    assert payload["from_server"] == "a"
    assert payload["to_server"] == "b"
    assert "process_stopped" in payload["completed_steps"]
    assert payload["failed_step"] is None
    assert payload["is_complete"] is False


# ---------------------------------------------------------------------------
# 3. ollama → multi_runtime switch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ollama_to_multi_runtime_stops_ollama_starts_multi(monkeypatch):
    """Switching from ollama to multi_runtime stops ollama and starts multi_runtime."""
    servers = [
        _make_server(
            "ollama", endpoint=OLLAMA_ENDPOINT, health_url=f"{OLLAMA_ENDPOINT}/api/tags"
        ),
        _make_server(
            "multi_runtime",
            endpoint=MULTI_ENDPOINT,
            health_url=f"{MULTI_ENDPOINT}/health",
        ),
    ]
    controller = _DummyController(servers)
    updates: dict = {}
    monkeypatch.setattr(system_routes.system_deps, "_llm_controller", controller)
    monkeypatch.setattr(
        system_routes.system_deps,
        "_model_manager",
        _DummyModelManager([{"name": "gemma2:2b", "provider": "multi_runtime"}]),
    )
    monkeypatch.setattr(system_routes.system_deps, "_request_tracer", None)
    monkeypatch.setattr(
        system_routes, "_installed_local_servers", lambda: {"ollama", "multi_runtime"}
    )
    monkeypatch.setattr(
        system_routes.config_manager,
        "get_config",
        lambda **_: {
            "LAST_MODEL_GEMMA4_AUDIO": "gemma2:2b",
        },
    )
    monkeypatch.setattr(
        system_routes.config_manager, "update_config", lambda u: updates.update(u)
    )
    monkeypatch.setattr(system_routes, "_release_onnx_runtime_caches", lambda: None)

    original = _snapshot_settings()
    SETTINGS.LLM_SERVICE_TYPE = "local"
    SETTINGS.LLM_LOCAL_ENDPOINT = f"{OLLAMA_ENDPOINT}/v1"
    SETTINGS.LLM_MODEL_NAME = "phi3:mini"
    SETTINGS.ACTIVE_LLM_SERVER = "ollama"
    try:
        response = await system_routes.set_active_llm_server(
            system_routes.ActiveLlmServerRequest(server_name="multi_runtime")
        )
        assert response["status"] == "success"
        # ollama was stopped, multi_runtime was started
        assert ("ollama", "stop") in controller.actions
        assert ("multi_runtime", "start") in controller.actions
        # lifecycle state confirms all steps done
        assert "process_stopped" in response["lifecycle_state"]["completed_steps"]
        assert "health_ready" in response["lifecycle_state"]["completed_steps"]
        assert "config_saved" in response["lifecycle_state"]["completed_steps"]
    finally:
        _restore_settings(original)


# ---------------------------------------------------------------------------
# 4. multi_runtime → ollama switch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multi_runtime_to_ollama_stops_multi_starts_ollama(monkeypatch):
    """Switching from multi_runtime to ollama stops multi_runtime and starts ollama."""
    servers = [
        _make_server(
            "ollama", endpoint=OLLAMA_ENDPOINT, health_url=f"{OLLAMA_ENDPOINT}/api/tags"
        ),
        _make_server(
            "multi_runtime",
            endpoint=MULTI_ENDPOINT,
            health_url=f"{MULTI_ENDPOINT}/health",
        ),
    ]
    controller = _DummyController(servers)
    updates: dict = {}
    monkeypatch.setattr(system_routes.system_deps, "_llm_controller", controller)
    monkeypatch.setattr(
        system_routes.system_deps,
        "_model_manager",
        _DummyModelManager([{"name": "phi3:mini", "provider": "ollama"}]),
    )
    monkeypatch.setattr(system_routes.system_deps, "_request_tracer", None)
    monkeypatch.setattr(
        system_routes, "_installed_local_servers", lambda: {"ollama", "multi_runtime"}
    )
    monkeypatch.setattr(
        system_routes.config_manager,
        "get_config",
        lambda **_: {
            "LAST_MODEL_OLLAMA": "phi3:mini",
        },
    )
    monkeypatch.setattr(
        system_routes.config_manager, "update_config", lambda u: updates.update(u)
    )
    monkeypatch.setattr(system_routes, "_release_onnx_runtime_caches", lambda: None)

    original = _snapshot_settings()
    SETTINGS.LLM_SERVICE_TYPE = "local"
    SETTINGS.LLM_LOCAL_ENDPOINT = f"{MULTI_ENDPOINT}/v1"
    SETTINGS.LLM_MODEL_NAME = "gemma2:2b"
    SETTINGS.ACTIVE_LLM_SERVER = "multi_runtime"
    try:
        response = await system_routes.set_active_llm_server(
            system_routes.ActiveLlmServerRequest(server_name="ollama")
        )
        assert response["status"] == "success"
        assert ("multi_runtime", "stop") in controller.actions
        assert ("ollama", "start") in controller.actions
        # endpoint must be updated to ollama
        assert "ACTIVE_LLM_SERVER" in updates
        assert updates["ACTIVE_LLM_SERVER"] == "ollama"
    finally:
        _restore_settings(original)


# ---------------------------------------------------------------------------
# 5. Health-check timeout → no partial config written
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_check_timeout_prevents_config_write(monkeypatch):
    """If health check times out, config is NOT saved."""
    servers = [
        _make_server(
            "ollama",
            endpoint=OLLAMA_ENDPOINT,
            health_url=f"{OLLAMA_ENDPOINT}/api/tags",
            supports_health_wait=True,
        ),
        _make_server(
            "multi_runtime",
            endpoint=MULTI_ENDPOINT,
            health_url=f"{MULTI_ENDPOINT}/health",
            supports_health_wait=True,
        ),
    ]
    controller = _DummyController(servers)
    config_written = []
    monkeypatch.setattr(system_routes.system_deps, "_llm_controller", controller)
    monkeypatch.setattr(
        system_routes.system_deps,
        "_model_manager",
        _DummyModelManager([{"name": "phi3:mini", "provider": "ollama"}]),
    )
    monkeypatch.setattr(system_routes.system_deps, "_request_tracer", None)
    monkeypatch.setattr(
        system_routes, "_installed_local_servers", lambda: {"ollama", "multi_runtime"}
    )
    monkeypatch.setattr(
        system_routes.config_manager,
        "update_config",
        lambda u: config_written.append(u),
    )
    monkeypatch.setattr(system_routes, "_release_onnx_runtime_caches", lambda: None)

    # Override health probe to simulate timeout (returns False = not ready)
    async def _health_timeout(_server_name, _health_url):
        return False

    monkeypatch.setattr(runtime_switch_service, "probe_health_ready", _health_timeout)

    original = _snapshot_settings()
    SETTINGS.LLM_SERVICE_TYPE = "local"
    SETTINGS.ACTIVE_LLM_SERVER = "ollama"
    SETTINGS.LLM_MODEL_NAME = "phi3:mini"
    try:
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await system_routes.set_active_llm_server(
                system_routes.ActiveLlmServerRequest(server_name="multi_runtime")
            )
        assert exc_info.value.status_code == 503
        # Config must NOT have been written — health failed before config save.
        assert config_written == [], (
            "Config must not be written when health check fails"
        )
    finally:
        _restore_settings(original)


# ---------------------------------------------------------------------------
# 6. ONNX cleanup is best-effort — failure doesn't break switch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_onnx_cleanup_failure_does_not_break_switch(monkeypatch):
    """If ONNX cache flush raises, the switch continues successfully."""
    servers = [
        _make_server(
            "ollama", endpoint=OLLAMA_ENDPOINT, health_url=f"{OLLAMA_ENDPOINT}/api/tags"
        ),
    ]
    controller = _DummyController(servers)
    monkeypatch.setattr(system_routes.system_deps, "_llm_controller", controller)
    monkeypatch.setattr(
        system_routes.system_deps,
        "_model_manager",
        _DummyModelManager([{"name": "phi3:mini", "provider": "ollama"}]),
    )
    monkeypatch.setattr(system_routes.system_deps, "_request_tracer", None)
    monkeypatch.setattr(system_routes, "_installed_local_servers", lambda: {"ollama"})
    monkeypatch.setattr(
        system_routes.config_manager,
        "get_config",
        lambda **_: {
            "LAST_MODEL_OLLAMA": "phi3:mini",
        },
    )
    monkeypatch.setattr(system_routes.config_manager, "update_config", lambda _: None)

    def _onnx_flush_raises():
        raise RuntimeError("ONNX not available")

    monkeypatch.setattr(
        system_routes, "_release_onnx_runtime_caches", _onnx_flush_raises
    )

    original = _snapshot_settings()
    SETTINGS.LLM_SERVICE_TYPE = "local"
    SETTINGS.ACTIVE_LLM_SERVER = "onnx"
    SETTINGS.LLM_MODEL_NAME = "phi3:mini"
    try:
        response = await system_routes.set_active_llm_server(
            system_routes.ActiveLlmServerRequest(server_name="ollama")
        )
        assert response["status"] == "success"
    finally:
        _restore_settings(original)


# ---------------------------------------------------------------------------
# 7. Drift detection
# ---------------------------------------------------------------------------


def _fake_settings(**kwargs):
    defaults = {
        "ACTIVE_LLM_SERVER": "",
        "LLM_LOCAL_ENDPOINT": "",
        "LLM_MODEL_NAME": "",
        "LLM_SERVICE_TYPE": "local",
        "AI_MODE": "LOCAL",
        "VLLM_ENDPOINT": "http://localhost:8001/v1",
        "GEMMA4_AUDIO_ENDPOINT": "http://localhost:8014/v1",
        "GEMMA4_AUDIO_HOST": "localhost",
        "GEMMA4_AUDIO_PORT": 8014,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_detect_runtime_drift_no_drift():
    """No drift when ACTIVE_LLM_SERVER matches endpoint provider."""
    settings = _fake_settings(
        ACTIVE_LLM_SERVER="ollama",
        LLM_LOCAL_ENDPOINT="http://localhost:11434/v1",
        LLM_MODEL_NAME="phi3:mini",
    )
    result = detect_runtime_drift(settings)
    assert result["drift_detected"] is False
    assert result["issues"] == []


def test_detect_runtime_drift_detects_endpoint_mismatch():
    """Drift detected when ACTIVE_LLM_SERVER=ollama but endpoint points to vllm."""
    settings = _fake_settings(
        ACTIVE_LLM_SERVER="ollama",
        LLM_LOCAL_ENDPOINT="http://localhost:8001/v1",
        LLM_MODEL_NAME="phi3:mini",
    )
    result = detect_runtime_drift(settings)
    assert result["drift_detected"] is True
    assert len(result["issues"]) > 0
    assert "ollama" in result["issues"][0]


def test_detect_runtime_drift_multi_runtime_no_drift():
    """multi_runtime endpoint doesn't cause false drift."""
    settings = _fake_settings(
        ACTIVE_LLM_SERVER="multi_runtime",
        LLM_LOCAL_ENDPOINT="http://localhost:8014/v1",
        LLM_MODEL_NAME="gemma2:2b",
    )
    result = detect_runtime_drift(settings)
    assert result["drift_detected"] is False


# ---------------------------------------------------------------------------
# 8. Orchestrator — pre-stop Ollama unload is called
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_orchestrator_calls_ollama_pre_stop_unload():
    """RuntimeSwitchOrchestrator calls release_runtime_resources before stopping Ollama."""
    ollama_server = _make_server(
        "ollama",
        endpoint=OLLAMA_ENDPOINT,
        health_url=f"{OLLAMA_ENDPOINT}/api/tags",
        supports_model_unload=True,
    )
    multi_server = _make_server("multi_runtime", endpoint=MULTI_ENDPOINT)

    controller = _DummyController([ollama_server, multi_server])
    release_calls: list[tuple] = []

    async def _mock_release_resources(server_name, *, server, active_model=""):
        release_calls.append((server_name, active_model))
        return True

    orchestrator = RuntimeSwitchOrchestrator(controller)
    with patch.object(
        runtime_switch_service,
        "release_runtime_resources",
        side_effect=_mock_release_resources,
    ):
        (
            state,
            stop_results,
            shutdown_results,
            start_result,
            target,
        ) = await orchestrator.execute_lifecycle_switch(
            servers=[ollama_server, multi_server],
            target_server_name="multi_runtime",
            from_server_name="ollama",
            active_model="phi3:mini",
            onnx_flush_fn=lambda: None,
        )

    assert ("ollama", "phi3:mini") in release_calls
    assert ("ollama", "stop") in controller.actions
    assert ("multi_runtime", "start") in controller.actions
    assert state.is_complete is False  # CONFIG_SAVED not marked (caller's job)
    assert LifecycleStep.HEALTH_READY in state.completed_steps
