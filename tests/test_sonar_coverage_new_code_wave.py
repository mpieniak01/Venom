from __future__ import annotations

import asyncio
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from venom_core.bootstrap import model_services as model_services_module
from venom_core.bootstrap import observability as observability_module
from venom_core.bootstrap import runtime_stack as runtime_stack_module
from venom_core.core import model_registry_operations as operations_module
from venom_core.core import model_registry_providers as providers_module
from venom_core.core import model_registry_runtime as runtime_module
from venom_core.core.model_registry_types import (
    ModelMetadata,
    ModelOperation,
    ModelProvider,
    OperationStatus,
)
from venom_core.core.service_monitor import (
    ServiceHealthMonitor,
    ServiceInfo,
    ServiceRegistry,
    ServiceStatus,
)
from venom_core.services import translation_service as translation_module
from venom_core.skills.mcp import skill_adapter as skill_adapter_module


class _Logger:
    def __init__(self):
        self.info = Mock()
        self.warning = Mock()
        self.error = Mock()
        self.debug = Mock()


@pytest.mark.asyncio
async def test_observability_success_and_failure_paths(tmp_path: Path):
    logger = _Logger()
    calls = {"metrics": 0, "set_broadcaster": 0}

    class Tracer:
        def __init__(self, watchdog_timeout_minutes, trace_file_path):
            self.watchdog_timeout_minutes = watchdog_timeout_minutes
            self.trace_file_path = trace_file_path
            self.started = False

        async def start_watchdog(self):
            self.started = True

    class Registry:
        pass

    class Monitor:
        def __init__(self, registry, event_broadcaster=None):
            self.registry = registry
            self.event_broadcaster = event_broadcaster

    class LlmController:
        def __init__(self, _settings):
            self.ok = True

    settings = SimpleNamespace(MEMORY_ROOT=str(tmp_path))
    event_broadcaster = object()

    result = await observability_module.initialize_observability(
        settings=settings,
        event_broadcaster=event_broadcaster,
        logger=logger,
        init_metrics_collector_fn=lambda: calls.__setitem__("metrics", 1),
        request_tracer_cls=Tracer,
        service_registry_cls=Registry,
        service_health_monitor_cls=Monitor,
        llm_server_controller_cls=LlmController,
        set_event_broadcaster_fn=lambda _v: calls.__setitem__("set_broadcaster", 1),
    )
    tracer, registry, monitor, controller = result
    assert calls["metrics"] == 1
    assert calls["set_broadcaster"] == 1
    assert tracer.started is True
    assert isinstance(registry, Registry)
    assert isinstance(monitor, Monitor)
    assert isinstance(controller, LlmController)

    class BrokenTracer:
        def __init__(self, *_a, **_k):
            raise RuntimeError("tracer-fail")

    result_failed = await observability_module.initialize_observability(
        settings=settings,
        event_broadcaster=event_broadcaster,
        logger=logger,
        init_metrics_collector_fn=lambda: None,
        request_tracer_cls=BrokenTracer,
        service_registry_cls=lambda: (_ for _ in ()).throw(
            RuntimeError("registry-fail")
        ),
        service_health_monitor_cls=Monitor,
        llm_server_controller_cls=lambda _s: (_ for _ in ()).throw(
            RuntimeError("llm-fail")
        ),
        set_event_broadcaster_fn=lambda _v: None,
    )
    assert result_failed == (None, None, None, None)


def test_model_services_success_and_guard_paths(monkeypatch, tmp_path: Path):
    logger = _Logger()
    settings = SimpleNamespace(ACADEMY_MODELS_DIR=str(tmp_path / "models"))

    class DummyModelManager:
        def __init__(self, models_dir):
            self.models_dir = models_dir

    class DummyRegistry:
        pass

    class DummyBenchmark:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    module_manager = ModuleType("venom_core.core.model_manager")
    module_manager.ModelManager = DummyModelManager
    module_registry = ModuleType("venom_core.core.model_registry")
    module_registry.ModelRegistry = DummyRegistry
    module_bench = ModuleType("venom_core.services.benchmark")
    module_bench.BenchmarkService = DummyBenchmark

    with pytest.MonkeyPatch.context() as mp:
        mp.setitem(__import__("sys").modules, module_manager.__name__, module_manager)
        mp.setitem(__import__("sys").modules, module_registry.__name__, module_registry)
        mp.setitem(__import__("sys").modules, module_bench.__name__, module_bench)

        model_manager, model_registry, benchmark = (
            model_services_module.initialize_model_services(
                settings=settings,
                service_monitor=object(),
                llm_controller=object(),
                logger=logger,
            )
        )
        assert isinstance(model_manager, DummyModelManager)
        assert isinstance(model_registry, DummyRegistry)
        assert isinstance(benchmark, DummyBenchmark)

        _mm, _mr, benchmark_missing = model_services_module.initialize_model_services(
            settings=settings,
            service_monitor=None,
            llm_controller=object(),
            logger=logger,
        )
        assert benchmark_missing is None


def test_provider_schema_and_token_resolution(monkeypatch):
    schema = providers_module.create_default_generation_schema()
    assert "temperature" in schema

    monkeypatch.setattr(providers_module, "SETTINGS", SimpleNamespace(HF_TOKEN=None))
    assert providers_module.resolve_hf_token() is None

    token_holder = SimpleNamespace(get_secret_value=lambda: "hf-secret")
    monkeypatch.setattr(
        providers_module, "SETTINGS", SimpleNamespace(HF_TOKEN=token_holder)
    )
    assert providers_module.resolve_hf_token() == "hf-secret"


@pytest.mark.asyncio
async def test_ollama_provider_branches(monkeypatch):
    provider = providers_module.OllamaModelProvider(endpoint="http://ollama:11434")

    provider.client = SimpleNamespace(
        list_tags=AsyncMock(
            return_value={
                "models": [
                    {"name": "llama-3:8b", "size": 1024**3},
                    {"name": "plain-model", "size": 0},
                ]
            }
        ),
        pull_model=AsyncMock(return_value=True),
        remove_model=AsyncMock(return_value=True),
    )

    models = await provider.list_available_models()
    assert len(models) == 2
    llama_schema = models[0].capabilities.generation_schema or {}
    assert llama_schema["temperature"].max == 1.0

    assert await provider.install_model("bad/name", None) is False
    assert await provider.remove_model("bad/name") is False

    provider.client.pull_model = AsyncMock(side_effect=RuntimeError("pull-fail"))
    assert await provider.install_model("valid-model", None) is False

    provider.client.remove_model = AsyncMock(side_effect=RuntimeError("rm-fail"))
    assert await provider.remove_model("valid-model") is False


@pytest.mark.asyncio
async def test_hf_provider_branches(tmp_path: Path):
    provider = providers_module.HuggingFaceModelProvider(cache_dir=str(tmp_path))

    provider.client = SimpleNamespace(
        list_models=AsyncMock(return_value=[]),
        download_snapshot=AsyncMock(return_value=str(tmp_path / "model")),
        remove_cached_model=Mock(return_value=True),
        get_model_info=AsyncMock(return_value={"id": "org/model-x"}),
    )

    fallback_models = await provider.list_available_models()
    assert len(fallback_models) >= 1

    called = {"progress": False}

    async def _progress(_msg: str):
        called["progress"] = True

    assert (
        await provider.install_model("org/model-x", progress_callback=_progress) is True
    )
    assert called["progress"] is True

    assert await provider.remove_model("org/model-x") is True

    info = await provider.get_model_info("org/model-x")
    assert info is not None
    assert info.name == "org/model-x"

    provider.client.get_model_info = AsyncMock(return_value=None)
    provider.client.list_models = AsyncMock(return_value=[{"id": "org/model-z"}])
    info_from_list = await provider.get_model_info("org/model-z")
    assert info_from_list is not None

    provider.client.list_models = AsyncMock(side_effect=RuntimeError("hf-down"))
    error_fallback = await provider.list_available_models()
    assert error_fallback[0].name == "google/gemma-2b-it"


@pytest.mark.asyncio
async def test_runtime_module_additional_branches(monkeypatch, tmp_path: Path):
    registry = SimpleNamespace(manifest={}, providers={}, _save_manifest=Mock())
    assert (
        await runtime_module.ensure_model_metadata_for_activation(registry, "m", "vllm")
        is False
    )

    registry.providers = {ModelProvider.OLLAMA: None}
    assert (
        await runtime_module.ensure_model_metadata_for_activation(
            registry, "m", "ollama"
        )
        is False
    )

    provider = SimpleNamespace(get_model_info=AsyncMock(return_value=None))
    registry.providers = {ModelProvider.OLLAMA: provider}
    assert (
        await runtime_module.ensure_model_metadata_for_activation(
            registry, "m", "ollama"
        )
        is False
    )

    provider.get_model_info = AsyncMock(side_effect=RuntimeError("boom"))
    assert (
        await runtime_module.ensure_model_metadata_for_activation(
            registry, "m", "ollama"
        )
        is False
    )

    missing_meta_registry = SimpleNamespace(
        manifest={}, providers={}, _save_manifest=Mock()
    )
    monkeypatch.setattr(
        runtime_module,
        "ensure_model_metadata_for_activation",
        AsyncMock(return_value=True),
    )
    assert (
        await runtime_module.activate_model(missing_meta_registry, "m", "ollama")
        is False
    )

    existing_registry = SimpleNamespace(
        manifest={
            "m": ModelMetadata(
                name="m",
                provider=ModelProvider.OLLAMA,
                display_name="m",
                runtime="ollama",
            )
        }
    )
    monkeypatch.setattr(
        runtime_module,
        "ensure_model_metadata_for_activation",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        runtime_module,
        "apply_model_activation_config",
        Mock(side_effect=RuntimeError("cfg")),
    )
    assert (
        await runtime_module.activate_model(existing_registry, "m", "ollama") is False
    )

    settings = SimpleNamespace(REPO_ROOT=str(tmp_path))
    updates: dict[str, object] = {}
    meta = ModelMetadata(
        name="m-vllm",
        provider=ModelProvider.HUGGINGFACE,
        display_name="m-vllm",
        runtime="vllm",
        local_path="relative/model-path",
    )
    runtime_module.apply_vllm_activation_updates(
        SimpleNamespace(), "m-vllm", meta, updates, settings
    )
    assert updates["VLLM_CHAT_TEMPLATE"] == ""


@pytest.mark.asyncio
async def test_operations_module_additional_branches():
    lock = AsyncMock()
    lock.__aenter__.return_value = None
    lock.__aexit__.return_value = None

    provider_obj = SimpleNamespace(
        install_model=AsyncMock(side_effect=RuntimeError("install-boom")),
        remove_model=AsyncMock(return_value=False),
    )
    registry = SimpleNamespace(
        providers={ModelProvider.OLLAMA: provider_obj},
        operations={},
        manifest={},
        _runtime_locks={"ollama": lock},
        _background_tasks=set(),
        _save_manifest=Mock(),
    )

    op = ModelOperation(
        operation_id="op-install",
        model_name="m",
        operation_type="install",
        status=OperationStatus.PENDING,
    )
    await operations_module._install_model_task(
        registry, op, ModelProvider.OLLAMA, "ollama"
    )
    assert op.status == OperationStatus.FAILED
    assert "install-boom" in (op.error or "")

    op_remove = ModelOperation(
        operation_id="op-remove",
        model_name="m",
        operation_type="remove",
        status=OperationStatus.PENDING,
    )
    await operations_module._remove_model_task(
        registry, op_remove, ModelProvider.OLLAMA
    )
    assert op_remove.status == OperationStatus.FAILED

    provider_obj.remove_model = AsyncMock(side_effect=RuntimeError("remove-boom"))
    op_remove_exc = ModelOperation(
        operation_id="op-remove-exc",
        model_name="m",
        operation_type="remove",
        status=OperationStatus.PENDING,
    )
    await operations_module._remove_model_task(
        registry, op_remove_exc, ModelProvider.OLLAMA
    )
    assert op_remove_exc.status == OperationStatus.FAILED


@pytest.mark.asyncio
async def test_runtime_stack_guard_and_exception_paths(tmp_path: Path):
    logger = _Logger()

    settings = SimpleNamespace(ENABLE_NEXUS=False)
    assert (
        await runtime_stack_module.initialize_node_manager(
            settings=settings, logger=logger
        )
        is None
    )

    settings = SimpleNamespace(
        ENABLE_NEXUS=True,
        NEXUS_SHARED_TOKEN=SimpleNamespace(get_secret_value=lambda: ""),
        NEXUS_HEARTBEAT_TIMEOUT=5,
    )
    assert (
        await runtime_stack_module.initialize_node_manager(
            settings=settings, logger=logger
        )
        is None
    )

    class BrokenNodeManager:
        def __init__(self, **_kwargs):
            raise RuntimeError("nm-boom")

    nm_module = ModuleType("venom_core.core.node_manager")
    nm_module.NodeManager = BrokenNodeManager
    with pytest.MonkeyPatch.context() as mp:
        mp.setitem(__import__("sys").modules, nm_module.__name__, nm_module)
        settings = SimpleNamespace(
            ENABLE_NEXUS=True,
            NEXUS_SHARED_TOKEN=SimpleNamespace(get_secret_value=lambda: "tok"),
            NEXUS_HEARTBEAT_TIMEOUT=5,
        )
        assert (
            await runtime_stack_module.initialize_node_manager(
                settings=settings, logger=logger
            )
            is None
        )

    vector, graph, lessons = runtime_stack_module.initialize_memory_stores(
        settings=SimpleNamespace(),
        logger=logger,
        vector_store_cls=lambda: (_ for _ in ()).throw(RuntimeError("vec")),
        graph_store_cls=lambda: (_ for _ in ()).throw(RuntimeError("graph")),
        lessons_store_cls=lambda **_kw: (_ for _ in ()).throw(RuntimeError("lessons")),
        orchestrator=None,
    )
    assert vector is None and graph is None and lessons is None

    gardener, git = await runtime_stack_module.initialize_gardener_and_git(
        workspace_path=tmp_path,
        graph_store=None,
        orchestrator=None,
        event_broadcaster=None,
        logger=logger,
        gardener_agent_cls=lambda **_kwargs: (_ for _ in ()).throw(
            RuntimeError("gardener")
        ),
        git_skill_cls=lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("git")),
    )
    assert gardener is None and git is None

    scheduler, startup = await runtime_stack_module.initialize_background_scheduler(
        settings=SimpleNamespace(),
        logger=logger,
        event_broadcaster=None,
        vector_store=None,
        request_tracer=None,
        background_scheduler_cls=lambda **_kw: (_ for _ in ()).throw(
            RuntimeError("sched")
        ),
        job_scheduler_module=SimpleNamespace(),
        asyncio_module=asyncio,
        clear_startup_runtime_retention_task=lambda: None,
    )
    assert scheduler is None and startup is None

    assert (
        runtime_stack_module.initialize_audio_engine_if_enabled(
            settings=SimpleNamespace(ENABLE_AUDIO_INTERFACE=False),
            logger=logger,
            audio_engine_cls=lambda **_k: object(),
        )
        is None
    )


@pytest.mark.asyncio
async def test_skill_adapter_additional_branches(tmp_path: Path):
    assert skill_adapter_module._map_json_type("list[str]") == "array"
    assert skill_adapter_module._map_json_type("int") == "number"
    assert skill_adapter_module._map_json_type("bool") == "boolean"
    assert skill_adapter_module._map_json_type("custom") == "string"

    class DummySkill:
        def sync_tool(self, value: str = "x"):
            return f"sync:{value}"

    DummySkill.sync_tool.__kernel_function_name__ = "sync_tool"
    DummySkill.sync_tool.__kernel_function_description__ = "sync desc"
    DummySkill.sync_tool.__kernel_function_parameters__ = [
        {
            "name": "value",
            "type_": "str",
            "description": "value",
            "default_value": "x",
            "is_required": False,
        }
    ]
    skill = DummySkill()

    adapter = skill_adapter_module.SkillMcpLikeAdapter(skill)
    tools = adapter.list_tools()
    assert tools[0].name == "sync_tool"
    result = await adapter.invoke_tool("sync_tool", {"value": "ok", "extra": 1})
    assert result == "sync:ok"

    class MissingArgSkill:
        async def async_tool(self, required: str):
            return required

    MissingArgSkill.async_tool.__kernel_function_name__ = "async_tool"
    MissingArgSkill.async_tool.__kernel_function_description__ = "async desc"
    MissingArgSkill.async_tool.__kernel_function_parameters__ = [
        {
            "name": "required",
            "type_": "str",
            "description": "required",
            "is_required": True,
        }
    ]
    skill2 = MissingArgSkill()
    adapter2 = skill_adapter_module.SkillMcpLikeAdapter(skill2)
    with pytest.raises(ValueError, match="Missing required arguments"):
        await adapter2.invoke_tool("async_tool", {})


@pytest.mark.asyncio
async def test_service_monitor_additional_branches():
    registry = ServiceRegistry()
    registry.services = {
        "A": ServiceInfo(name="A", service_type="api", status=ServiceStatus.ONLINE),
        "B": ServiceInfo(name="B", service_type="api", status=ServiceStatus.OFFLINE),
        "C": ServiceInfo(name="C", service_type="api", status=ServiceStatus.DEGRADED),
    }
    monitor = ServiceHealthMonitor(registry)
    summary = monitor.get_summary()
    assert summary["total_services"] == 3
    assert summary["online"] == 1
    assert summary["offline"] == 1
    assert summary["degraded"] == 1

    unknown = ServiceInfo(name="X", service_type="mystery")
    checked = await monitor._check_service_health(unknown)
    assert checked.status == ServiceStatus.UNKNOWN
    assert checked.last_check is not None


@pytest.mark.asyncio
async def test_translation_service_non_dict_payload_and_no_fallback(monkeypatch):
    monkeypatch.setattr(
        translation_module.SETTINGS, "LLM_MODEL_NAME", "test-model", raising=False
    )
    monkeypatch.setattr(
        translation_module.SETTINGS,
        "LLM_LOCAL_ENDPOINT",
        "http://localhost:8000/v1",
        raising=False,
    )
    monkeypatch.setattr(
        translation_module.SETTINGS, "OPENAI_API_TIMEOUT", 1.0, raising=False
    )
    monkeypatch.setattr(
        translation_module,
        "get_active_llm_runtime",
        lambda: SimpleNamespace(service_type="local"),
    )

    class _ClientNonDict:
        def __init__(self, *args, **kwargs):
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def apost(self, *args, **kwargs):
            return SimpleNamespace(json=lambda: ["not-dict"])

    monkeypatch.setattr(
        translation_module, "TrafficControlledHttpClient", _ClientNonDict
    )
    service = translation_module.TranslationService(cache_ttl_seconds=0)
    result = await service.translate_text("hello", target_lang="pl")
    assert result == "hello"

    class _ClientBoom:
        def __init__(self, *args, **kwargs):
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def apost(self, *args, **kwargs):
            raise RuntimeError("translate-boom")

    monkeypatch.setattr(translation_module, "TrafficControlledHttpClient", _ClientBoom)
    with pytest.raises(RuntimeError, match="translate-boom"):
        await service.translate_text("hello", target_lang="pl", allow_fallback=False)
