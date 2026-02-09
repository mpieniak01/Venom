from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import venom_core.main as main_module
from venom_core.nodes.protocol import MessageType


def test_extract_available_local_models_filters_by_provider():
    models = [
        {"provider": "ollama", "name": "m1"},
        {"provider": "vllm", "name": "m2"},
        {"provider": "ollama", "name": ""},
    ]
    assert main_module._extract_available_local_models(models, "ollama") == {"m1"}


def test_select_startup_model_priority_chain():
    available = {"model-a", "model-b"}
    assert (
        main_module._select_startup_model(available, "model-a", "model-b") == "model-a"
    )
    assert (
        main_module._select_startup_model(available, "missing", "model-b") == "model-b"
    )
    assert (
        main_module._select_startup_model({"model-x"}, "missing", "missing")
        == "model-x"
    )


@pytest.mark.asyncio
async def test_handle_node_message_returns_false_when_manager_missing(monkeypatch):
    monkeypatch.setattr(main_module, "node_manager", None)
    message = SimpleNamespace(
        message_type=MessageType.HEARTBEAT, payload={"node_id": "node-1"}
    )
    assert await main_module._handle_node_message(message, "node-1") is False


@pytest.mark.asyncio
async def test_handle_node_message_heartbeat(monkeypatch):
    manager = SimpleNamespace(update_heartbeat=AsyncMock())
    monkeypatch.setattr(main_module, "node_manager", manager)
    message = SimpleNamespace(
        message_type=MessageType.HEARTBEAT,
        payload={"node_id": "node-1", "cpu_usage": 0.2, "memory_usage": 0.3},
    )
    assert await main_module._handle_node_message(message, "node-1") is True
    manager.update_heartbeat.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_node_message_response(monkeypatch):
    manager = SimpleNamespace(handle_response=AsyncMock())
    monkeypatch.setattr(main_module, "node_manager", manager)
    message = SimpleNamespace(
        message_type=MessageType.RESPONSE,
        payload={"request_id": "r1", "node_id": "node-1", "success": True},
    )
    assert await main_module._handle_node_message(message, "node-1") is True
    manager.handle_response.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_node_message_disconnect_and_unknown(monkeypatch):
    manager = SimpleNamespace(update_heartbeat=AsyncMock(), handle_response=AsyncMock())
    monkeypatch.setattr(main_module, "node_manager", manager)

    disconnect = SimpleNamespace(message_type=MessageType.DISCONNECT, payload={})
    unknown = SimpleNamespace(message_type="OTHER", payload={})

    assert await main_module._handle_node_message(disconnect, "node-1") is False
    assert await main_module._handle_node_message(unknown, "node-1") is True


@pytest.mark.asyncio
async def test_wait_for_runtime_online(monkeypatch):
    calls = {"count": 0}

    async def fake_probe(_runtime):
        calls["count"] += 1
        if calls["count"] >= 3:
            return ("online", {})
        return ("offline", {})

    monkeypatch.setattr(main_module, "probe_runtime_status", fake_probe)
    monkeypatch.setattr(main_module.asyncio, "sleep", AsyncMock())

    runtime = SimpleNamespace(provider="ollama")
    status = await main_module._wait_for_runtime_online(
        runtime, attempts=5, delay_seconds=0
    )
    assert status == "online"
    assert calls["count"] == 3


@pytest.mark.asyncio
async def test_start_local_runtime_if_needed_paths(monkeypatch):
    runtime = SimpleNamespace(provider="ollama")

    async def online_probe(_runtime):
        return ("online", {})

    monkeypatch.setattr(main_module, "probe_runtime_status", online_probe)
    assert await main_module._start_local_runtime_if_needed(runtime) == "online"

    async def offline_probe(_runtime):
        return ("offline", {})

    monkeypatch.setattr(main_module, "probe_runtime_status", offline_probe)
    monkeypatch.setattr(main_module, "_start_configured_local_server", AsyncMock())
    monkeypatch.setattr(
        main_module, "_wait_for_runtime_online", AsyncMock(return_value="online")
    )
    assert await main_module._start_local_runtime_if_needed(runtime) == "online"


@pytest.mark.asyncio
async def test_synchronize_startup_local_model_updates_config(monkeypatch):
    fake_model_manager = SimpleNamespace(
        list_local_models=AsyncMock(
            return_value=[
                {"provider": "ollama", "name": "model-1"},
                {"provider": "ollama", "name": "model-2"},
            ]
        )
    )
    monkeypatch.setattr(main_module, "model_manager", fake_model_manager)

    fake_config_manager = SimpleNamespace(
        get_config=lambda mask_secrets=False: {
            "LLM_MODEL_NAME": "missing-model",
            "LAST_MODEL_OLLAMA": "model-2",
            "PREVIOUS_MODEL_OLLAMA": "model-1",
            "HYBRID_LOCAL_MODEL": "model-2",
        },
        update_config=MagicMock(),
    )

    import venom_core.services.config_manager as config_manager_module
    import venom_core.utils.llm_runtime as llm_runtime_module

    monkeypatch.setattr(config_manager_module, "config_manager", fake_config_manager)
    monkeypatch.setattr(
        llm_runtime_module,
        "compute_llm_config_hash",
        lambda server, endpoint, model: f"{server}:{endpoint}:{model}",
    )
    monkeypatch.setattr(main_module.SETTINGS, "ACTIVE_LLM_SERVER", "ollama")
    monkeypatch.setattr(main_module.SETTINGS, "LLM_MODEL_NAME", "missing-model")
    monkeypatch.setattr(main_module.SETTINGS, "HYBRID_LOCAL_MODEL", "missing-model")
    monkeypatch.setattr(main_module.SETTINGS, "LLM_CONFIG_HASH", "")

    runtime = SimpleNamespace(provider="ollama", endpoint="http://localhost:11434")
    await main_module._synchronize_startup_local_model(runtime)

    assert fake_config_manager.update_config.call_count >= 2


@pytest.mark.asyncio
async def test_start_configured_local_server_runs_stop_and_start(monkeypatch):
    calls = []

    class DummyController:
        def has_server(self, _name):
            return True

        def list_servers(self):
            return [
                {"name": "other", "supports": {"stop": True}},
                {"name": "ollama", "supports": {"stop": True}},
            ]

        async def run_action(self, name, action):
            calls.append((name, action))

    monkeypatch.setattr(main_module, "llm_controller", DummyController())
    await main_module._start_configured_local_server("ollama")
    assert ("other", "stop") in calls
    assert ("ollama", "start") in calls


@pytest.mark.asyncio
async def test_start_configured_local_server_noop_when_server_missing(monkeypatch):
    class DummyController:
        def has_server(self, _name):
            return False

    monkeypatch.setattr(main_module, "llm_controller", DummyController())
    await main_module._start_configured_local_server("ollama")


@pytest.mark.asyncio
async def test_receive_node_handshake_parsing(monkeypatch):
    class DummyWebSocket:
        def __init__(self, payload: str):
            self.payload = payload
            self.closed = None

        async def receive_text(self):
            return self.payload

        async def close(self, code, reason):
            self.closed = (code, reason)

    handshake_payload = '{"message_type":"HANDSHAKE","payload":{"node_name":"n1","token":"t","capabilities":{}}}'
    ws_ok = DummyWebSocket(handshake_payload)
    handshake = await main_module._receive_node_handshake(ws_ok)
    assert handshake is not None
    assert ws_ok.closed is None

    ws_bad = DummyWebSocket('{"message_type":"RESPONSE","payload":{}}')
    assert await main_module._receive_node_handshake(ws_bad) is None
    assert ws_bad.closed == (1003, "Expected HANDSHAKE message")


@pytest.mark.asyncio
async def test_run_node_message_loop_handles_json_error_and_disconnect(monkeypatch):
    messages = iter(
        [
            "{bad-json",
            '{"message_type":"DISCONNECT","payload":{}}',
        ]
    )

    class DummyWebSocket:
        async def receive_text(self):
            return next(messages)

    async def fake_handle(message, _node_id):
        return message.message_type != MessageType.DISCONNECT

    monkeypatch.setattr(main_module, "_handle_node_message", fake_handle)
    await main_module._run_node_message_loop(DummyWebSocket(), "node-1")


def test_initialize_model_services_success_path(monkeypatch, tmp_path):
    class DummyModelManager:
        def __init__(self, models_dir):
            self.models_dir = models_dir

    class DummyRegistry:
        pass

    class DummyBenchmark:
        def __init__(self, **_kwargs):
            pass

    monkeypatch.setattr(main_module, "service_monitor", object())
    monkeypatch.setattr(main_module, "llm_controller", object())
    monkeypatch.setattr(
        "venom_core.core.model_manager.ModelManager", DummyModelManager, raising=True
    )
    monkeypatch.setattr(
        "venom_core.core.model_registry.ModelRegistry", DummyRegistry, raising=True
    )
    monkeypatch.setattr(
        "venom_core.services.benchmark.BenchmarkService", DummyBenchmark, raising=True
    )
    monkeypatch.setattr(
        main_module.SETTINGS, "ACADEMY_MODELS_DIR", str(tmp_path), raising=False
    )
    main_module._initialize_model_services()
    assert main_module.model_manager is not None
    assert main_module.benchmark_service is not None


def test_initialize_calendar_skill_disabled(monkeypatch):
    monkeypatch.setattr(
        main_module.SETTINGS, "ENABLE_GOOGLE_CALENDAR", False, raising=False
    )
    main_module.google_calendar_skill = "placeholder"
    main_module._initialize_calendar_skill()
    assert main_module.google_calendar_skill == "placeholder"
