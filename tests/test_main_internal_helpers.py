import asyncio
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
    mock_probe = AsyncMock(
        side_effect=[
            ("offline", {}),
            ("offline", {}),
            ("online", {}),
        ]
    )
    monkeypatch.setattr(main_module, "probe_runtime_status", mock_probe)
    monkeypatch.setattr(main_module.asyncio, "sleep", AsyncMock())

    runtime = SimpleNamespace(provider="ollama")
    status = await main_module._wait_for_runtime_online(
        runtime, attempts=5, delay_seconds=0
    )
    assert status == "online"
    assert mock_probe.call_count == 3


@pytest.mark.asyncio
async def test_start_local_runtime_if_needed_paths(monkeypatch):
    runtime = SimpleNamespace(provider="ollama")

    monkeypatch.setattr(
        main_module,
        "probe_runtime_status",
        AsyncMock(return_value=("online", {})),
    )
    assert await main_module._start_local_runtime_if_needed(runtime) == "online"

    monkeypatch.setattr(
        main_module,
        "probe_runtime_status",
        AsyncMock(return_value=("offline", {})),
    )
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
            await asyncio.sleep(0)
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
    handshake_payload = '{"message_type":"HANDSHAKE","payload":{"node_name":"n1","token":"t","capabilities":{}}}'
    ws_ok = MagicMock()
    ws_ok.receive_text = AsyncMock(return_value=handshake_payload)
    ws_ok.close = AsyncMock()
    handshake = await main_module._receive_node_handshake(ws_ok)
    assert handshake is not None
    ws_ok.close.assert_not_awaited()

    ws_bad = MagicMock()
    ws_bad.receive_text = AsyncMock(
        return_value='{"message_type":"RESPONSE","payload":{}}'
    )
    ws_bad.close = AsyncMock()
    assert await main_module._receive_node_handshake(ws_bad) is None
    ws_bad.close.assert_awaited_once_with(
        code=1003, reason="Expected HANDSHAKE message"
    )


@pytest.mark.asyncio
async def test_run_node_message_loop_handles_json_error_and_disconnect(monkeypatch):
    ws = MagicMock()
    ws.receive_text = AsyncMock(
        side_effect=[
            "{bad-json",
            '{"message_type":"DISCONNECT","payload":{}}',
        ]
    )

    async def fake_handle(message, _node_id):
        await asyncio.sleep(0)
        return message.message_type != MessageType.DISCONNECT

    monkeypatch.setattr(main_module, "_handle_node_message", fake_handle)
    await main_module._run_node_message_loop(ws, "node-1")


def test_initialize_model_services_success_path(monkeypatch, tmp_path):
    class DummyModelManager:
        def __init__(self, models_dir):
            self.models_dir = models_dir

    class DummyRegistry:
        pass

    class DummyBenchmark:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

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


def test_parse_node_message(monkeypatch):
    payload = '{"message_type":"HANDSHAKE","payload":{"node_name":"n1","token":"t","capabilities":{}}}'
    parsed = main_module._parse_node_message(payload)
    assert parsed.message_type.value == "HANDSHAKE"
    assert parsed.payload["node_name"] == "n1"


def test_initialize_model_services_handles_missing_monitor(monkeypatch, tmp_path):
    class DummyModelManager:
        def __init__(self, models_dir):
            self.models_dir = models_dir

    monkeypatch.setattr(main_module, "service_monitor", None)
    monkeypatch.setattr(
        "venom_core.core.model_manager.ModelManager", DummyModelManager, raising=True
    )
    monkeypatch.setattr(
        main_module.SETTINGS, "ACADEMY_MODELS_DIR", str(tmp_path), raising=False
    )
    main_module.model_registry = "sentinel"
    main_module.benchmark_service = "sentinel"

    main_module._initialize_model_services()

    assert main_module.model_manager is not None
    assert main_module.model_registry == "sentinel"
    assert main_module.benchmark_service is None


def test_storage_and_memory_store_initialization(monkeypatch, tmp_path):
    workspace = tmp_path / "workspace"
    memory = tmp_path / "memory"
    monkeypatch.setattr(main_module.SETTINGS, "WORKSPACE_ROOT", str(workspace))
    monkeypatch.setattr(main_module.SETTINGS, "MEMORY_ROOT", str(memory))

    class DummyVectorStore:
        pass

    class DummyGraphStore:
        def load_graph(self):
            return None

    class DummyLessonsStore:
        def __init__(self, vector_store):
            self.vector_store = vector_store
            self.lessons = ["l1", "l2"]

    monkeypatch.setattr(main_module, "VectorStore", DummyVectorStore)
    monkeypatch.setattr(main_module, "CodeGraphStore", DummyGraphStore)
    monkeypatch.setattr(main_module, "LessonsStore", DummyLessonsStore)
    main_module.orchestrator = SimpleNamespace(lessons_store=None)

    created_workspace = main_module._ensure_storage_dirs()
    main_module._initialize_memory_stores()

    assert created_workspace.exists()
    assert memory.exists()
    assert main_module.vector_store is not None
    assert main_module.graph_store is not None
    assert main_module.lessons_store is not None
    assert main_module.orchestrator.lessons_store is main_module.lessons_store


@pytest.mark.asyncio
async def test_initialize_gardener_and_git(monkeypatch, tmp_path):
    class DummyGardener:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.started = False

        async def start(self):
            await asyncio.sleep(0)
            self.started = True

    class DummyGitSkill:
        def __init__(self, workspace_root):
            self.workspace_root = workspace_root

    monkeypatch.setattr(main_module, "GardenerAgent", DummyGardener)
    monkeypatch.setattr(main_module, "GitSkill", DummyGitSkill)
    main_module.graph_store = object()
    main_module.orchestrator = object()
    main_module.event_broadcaster = object()

    await main_module._initialize_gardener_and_git(tmp_path)

    assert main_module.gardener_agent is not None
    assert main_module.gardener_agent.started is True
    assert str(tmp_path) == main_module.git_skill.workspace_root


@pytest.mark.asyncio
async def test_initialize_background_scheduler_registers_jobs(monkeypatch):
    class DummyScheduler:
        def __init__(self, event_broadcaster):
            self.event_broadcaster = event_broadcaster
            self.job_ids = []
            self.started = False

        async def start(self):
            await asyncio.sleep(0)
            self.started = True

        def add_interval_job(self, func, minutes, job_id, description):
            self.job_ids.append(job_id)

    class DummyTracer:
        def clear_old_traces(self, days):
            assert days == 7

    async def _noop(_event_broadcaster):
        await asyncio.sleep(0)
        return None

    monkeypatch.setattr(main_module, "BackgroundScheduler", DummyScheduler)
    monkeypatch.setattr(main_module.job_scheduler, "consolidate_memory", _noop)
    monkeypatch.setattr(main_module.job_scheduler, "check_health", _noop)
    monkeypatch.setattr(main_module.SETTINGS, "ENABLE_MEMORY_CONSOLIDATION", True)
    monkeypatch.setattr(main_module.SETTINGS, "ENABLE_HEALTH_CHECKS", True)
    monkeypatch.setattr(
        main_module.SETTINGS, "MEMORY_CONSOLIDATION_INTERVAL_MINUTES", 5
    )
    monkeypatch.setattr(main_module.SETTINGS, "HEALTH_CHECK_INTERVAL_MINUTES", 3)
    main_module.vector_store = object()
    main_module.event_broadcaster = object()
    main_module.request_tracer = DummyTracer()

    await main_module._initialize_background_scheduler()

    assert main_module.background_scheduler is not None
    assert main_module.background_scheduler.started is True
    assert "consolidate_memory" in main_module.background_scheduler.job_ids
    assert "check_health" in main_module.background_scheduler.job_ids
    assert "cleanup_traces" in main_module.background_scheduler.job_ids


@pytest.mark.asyncio
async def test_initialize_documenter_and_watcher(monkeypatch, tmp_path):
    class DummyDocumenter:
        def __init__(self, workspace_root, git_skill, event_broadcaster):
            self.workspace_root = workspace_root
            self.git_skill = git_skill
            self.event_broadcaster = event_broadcaster

        async def handle_code_change(self, _change):
            await asyncio.sleep(0)
            return None

    class DummyWatcher:
        def __init__(self, workspace_root, on_change_callback, event_broadcaster):
            self.workspace_root = workspace_root
            self.on_change_callback = on_change_callback
            self.event_broadcaster = event_broadcaster
            self.started = False

        async def start(self):
            await asyncio.sleep(0)
            self.started = True

    monkeypatch.setattr(main_module, "DocumenterAgent", DummyDocumenter)
    monkeypatch.setattr(main_module, "FileWatcher", DummyWatcher)
    main_module.git_skill = object()
    main_module.event_broadcaster = object()

    await main_module._initialize_documenter_and_watcher(tmp_path)

    assert main_module.documenter_agent is not None
    assert main_module.file_watcher is not None
    assert main_module.file_watcher.started is True
    assert main_module.file_watcher.on_change_callback is not None


@pytest.mark.asyncio
async def test_avatar_stack_helpers(monkeypatch):
    class DummyAudio:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class DummyBridge:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def connect(self):
            await asyncio.sleep(0)
            return True

    class DummyKernelBuilder:
        def build_kernel(self):
            return object()

    class DummyOperator:
        def __init__(self, kernel, hardware_bridge):
            self.kernel = kernel
            self.hardware_bridge = hardware_bridge

    class DummyAudioHandler:
        def __init__(self, audio_engine, vad_threshold, silence_duration):
            self.audio_engine = audio_engine
            self.vad_threshold = vad_threshold
            self.silence_duration = silence_duration

    monkeypatch.setattr(main_module.SETTINGS, "ENABLE_AUDIO_INTERFACE", True)
    monkeypatch.setattr(main_module.SETTINGS, "ENABLE_IOT_BRIDGE", True)
    monkeypatch.setattr(main_module, "AudioEngine", DummyAudio)
    monkeypatch.setattr(main_module, "HardwareBridge", DummyBridge)
    monkeypatch.setattr(
        "venom_core.execution.kernel_builder.KernelBuilder",
        DummyKernelBuilder,
        raising=True,
    )
    monkeypatch.setattr(main_module, "OperatorAgent", DummyOperator)
    monkeypatch.setattr(main_module, "AudioStreamHandler", DummyAudioHandler)
    monkeypatch.setattr(main_module, "extract_secret_value", lambda _secret: "pw")

    audio = main_module._initialize_audio_engine_if_enabled()
    bridge = await main_module._initialize_hardware_bridge_if_enabled()
    operator = main_module._initialize_operator_agent_if_possible(audio, bridge)
    handler = main_module._initialize_audio_stream_handler_if_possible(audio, operator)

    assert audio is not None
    assert bridge is not None
    assert operator is not None
    assert handler is not None


@pytest.mark.asyncio
async def test_ensure_local_llm_ready_local_and_non_local(monkeypatch):
    local_runtime = SimpleNamespace(service_type="local")
    cloud_runtime = SimpleNamespace(service_type="openai")

    monkeypatch.setattr(main_module, "_synchronize_startup_local_model", AsyncMock())
    monkeypatch.setattr(main_module, "_start_local_runtime_if_needed", AsyncMock())
    monkeypatch.setattr(main_module, "warmup_local_runtime", AsyncMock())

    monkeypatch.setattr(main_module, "get_active_llm_runtime", lambda: cloud_runtime)
    await main_module._ensure_local_llm_ready()
    main_module._synchronize_startup_local_model.assert_not_awaited()

    monkeypatch.setattr(main_module, "get_active_llm_runtime", lambda: local_runtime)
    monkeypatch.setattr(main_module.SETTINGS, "LLM_WARMUP_ON_STARTUP", False)
    await main_module._ensure_local_llm_ready()
    main_module._synchronize_startup_local_model.assert_awaited()
    main_module._start_local_runtime_if_needed.assert_awaited()
