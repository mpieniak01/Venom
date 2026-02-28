"""Lightweight coverage blocker tests for Sonar new-code gap (task 179)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from venom_core.api.routes import queue as queue_routes
from venom_core.bootstrap import model_services as model_services_module
from venom_core.bootstrap import observability as observability_module
from venom_core.core import model_registry_providers as providers_module
from venom_core.services import translation_service as translation_module
from venom_core.skills.mcp import skill_adapter as skill_adapter_module


class _Logger:
    def __init__(self) -> None:
        self.info = Mock()
        self.warning = Mock()
        self.error = Mock()
        self.debug = Mock()


def _make_client_for_queue() -> TestClient:
    app = FastAPI()
    app.include_router(queue_routes.router)
    return TestClient(app)


@pytest.mark.asyncio
async def test_observability_initialization_branches(tmp_path: Path) -> None:
    logger = _Logger()

    class _Tracer:
        def __init__(self, **_kwargs):
            self.started = False

        async def start_watchdog(self):
            self.started = True

    class _Registry:
        pass

    class _Monitor:
        def __init__(self, registry, event_broadcaster=None):
            self.registry = registry
            self.event_broadcaster = event_broadcaster

    class _Controller:
        def __init__(self, _settings):
            self.ok = True

    settings = SimpleNamespace(MEMORY_ROOT=str(tmp_path))
    event_broadcaster = object()

    (
        tracer,
        registry,
        monitor,
        controller,
    ) = await observability_module.initialize_observability(
        settings=settings,
        event_broadcaster=event_broadcaster,
        logger=logger,
        init_metrics_collector_fn=lambda: None,
        request_tracer_cls=_Tracer,
        service_registry_cls=_Registry,
        service_health_monitor_cls=_Monitor,
        llm_server_controller_cls=_Controller,
        set_event_broadcaster_fn=lambda _v: None,
    )
    assert tracer is not None and tracer.started is True
    assert isinstance(registry, _Registry)
    assert isinstance(monitor, _Monitor)
    assert isinstance(controller, _Controller)

    class _BrokenTracer:
        def __init__(self, **_kwargs):
            pass

        async def start_watchdog(self):
            raise RuntimeError("tracer-boom")

    result = await observability_module.initialize_observability(
        settings=settings,
        event_broadcaster=event_broadcaster,
        logger=logger,
        init_metrics_collector_fn=lambda: None,
        request_tracer_cls=_BrokenTracer,
        service_registry_cls=lambda: (_ for _ in ()).throw(
            RuntimeError("registry-boom")
        ),
        service_health_monitor_cls=_Monitor,
        llm_server_controller_cls=lambda _s: (_ for _ in ()).throw(
            RuntimeError("llm-boom")
        ),
        set_event_broadcaster_fn=lambda _v: None,
    )
    assert result == (None, None, None, None)


def test_model_services_branches(tmp_path: Path) -> None:
    logger = _Logger()
    settings = SimpleNamespace(ACADEMY_MODELS_DIR=str(tmp_path / "models"))

    class _Manager:
        def __init__(self, models_dir: str):
            self.models_dir = models_dir

    class _Registry:
        pass

    class _Bench:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    mod_manager = ModuleType("venom_core.core.model_manager")
    mod_manager.ModelManager = _Manager
    mod_registry = ModuleType("venom_core.core.model_registry")
    mod_registry.ModelRegistry = _Registry
    mod_bench = ModuleType("venom_core.services.benchmark")
    mod_bench.BenchmarkService = _Bench

    with pytest.MonkeyPatch.context() as mp:
        mp.setitem(__import__("sys").modules, mod_manager.__name__, mod_manager)
        mp.setitem(__import__("sys").modules, mod_registry.__name__, mod_registry)
        mp.setitem(__import__("sys").modules, mod_bench.__name__, mod_bench)

        mm, mr, bench = model_services_module.initialize_model_services(
            settings=settings,
            service_monitor=object(),
            llm_controller=object(),
            logger=logger,
        )
        assert isinstance(mm, _Manager)
        assert isinstance(mr, _Registry)
        assert isinstance(bench, _Bench)

        _, _, bench_missing = model_services_module.initialize_model_services(
            settings=settings,
            service_monitor=None,
            llm_controller=object(),
            logger=logger,
        )
        assert bench_missing is None


@pytest.mark.asyncio
async def test_model_registry_providers_branches(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    token_secret = SimpleNamespace(get_secret_value=lambda: "hf-secret")
    monkeypatch.setattr(
        providers_module, "SETTINGS", SimpleNamespace(HF_TOKEN=token_secret)
    )
    assert providers_module.resolve_hf_token() == "hf-secret"

    schema = providers_module.create_default_generation_schema()
    assert set(schema.keys()) >= {"temperature", "max_tokens", "top_p", "top_k"}

    class _OllamaClient:
        def __init__(self, endpoint: str):
            self.endpoint = endpoint
            self.list_tags = AsyncMock(
                return_value={
                    "models": [
                        {"name": "llama-3:8b", "size": 1024**3},
                        {"name": "plain-model", "size": 0},
                    ]
                }
            )
            self.pull_model = AsyncMock(return_value=True)
            self.remove_model = AsyncMock(return_value=True)

    monkeypatch.setattr(providers_module, "OllamaClient", _OllamaClient)
    ollama = providers_module.OllamaModelProvider(endpoint="http://ollama:11434")

    models = await ollama.list_available_models()
    assert len(models) == 2
    assert models[0].capabilities.generation_schema["temperature"].max == 1.0
    assert await ollama.install_model("bad name") is False
    assert await ollama.remove_model("bad name") is False
    assert await ollama.install_model("ok-model") is True
    assert await ollama.remove_model("ok-model") is True

    ollama.client.pull_model = AsyncMock(side_effect=RuntimeError("pull-boom"))
    ollama.client.remove_model = AsyncMock(side_effect=RuntimeError("rm-boom"))
    assert await ollama.install_model("ok-model") is False
    assert await ollama.remove_model("ok-model") is False
    assert await ollama.get_model_info("llama-3:8b") is not None

    class _HfClient:
        def __init__(self, token=None):
            self.token = token
            self.list_models = AsyncMock(
                return_value=[{"id": "org/model-a"}, {"modelId": "org/model-b"}, {}]
            )
            self.download_snapshot = AsyncMock(return_value=str(tmp_path / "model"))
            self.remove_cached_model = Mock(return_value=True)
            self.get_model_info = AsyncMock(return_value={"id": "org/model-a"})

    monkeypatch.setattr(providers_module, "HuggingFaceClient", _HfClient)
    hf = providers_module.HuggingFaceModelProvider(cache_dir=str(tmp_path))

    listed = await hf.list_available_models()
    assert len(listed) >= 2
    assert await hf.install_model("org/model-a") is True
    assert await hf.remove_model("org/model-a") is True
    assert await hf.get_model_info("org/model-a") is not None

    hf.client.download_snapshot = AsyncMock(return_value="")
    assert await hf.install_model("org/model-a") is False

    hf.client.get_model_info = AsyncMock(return_value=None)
    hf.client.list_models = AsyncMock(return_value=[{"id": "org/model-z"}])
    assert await hf.get_model_info("org/model-z") is not None

    hf.client.list_models = AsyncMock(side_effect=RuntimeError("hf-down"))
    fallback = await hf.list_available_models()
    assert fallback[0].name == "google/gemma-2b-it"


class _DummyRuntime:
    service_type = "local"
    provider = "local"


@pytest.mark.asyncio
async def test_translation_service_error_and_cache_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        translation_module, "get_active_llm_runtime", lambda: _DummyRuntime()
    )
    monkeypatch.setattr(
        translation_module.SETTINGS, "LLM_MODEL_NAME", "model-x", raising=False
    )
    monkeypatch.setattr(
        translation_module.SETTINGS,
        "LLM_LOCAL_ENDPOINT",
        "http://localhost:11434",
        raising=False,
    )
    monkeypatch.setattr(
        translation_module.SETTINGS, "OPENAI_API_TIMEOUT", 1.0, raising=False
    )
    monkeypatch.setattr(
        translation_module.SETTINGS, "LLM_LOCAL_API_KEY", "", raising=False
    )

    class _Client:
        def __init__(self, *args, **kwargs):
            self.calls = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def apost(self, *args, **kwargs):
            self.calls += 1
            return SimpleNamespace(
                json=lambda: {"choices": [{"message": {"content": "Czesc"}}]}
            )

    monkeypatch.setattr(translation_module, "TrafficControlledHttpClient", _Client)
    service = translation_module.TranslationService(cache_ttl_seconds=60)
    assert await service.translate_text("hello", target_lang="pl") == "Czesc"
    assert await service.translate_text("hello", target_lang="pl") == "Czesc"

    class _FailingClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def apost(self, *args, **kwargs):
            raise httpx.HTTPError("http-fail")

    monkeypatch.setattr(
        translation_module, "TrafficControlledHttpClient", _FailingClient
    )
    with pytest.raises(httpx.HTTPError):
        await service.translate_text(
            "hello-second",
            target_lang="pl",
            use_cache=False,
            allow_fallback=False,
        )


def test_queue_routes_error_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    original_orchestrator = queue_routes._orchestrator
    try:
        queue_routes.set_dependencies(None)
        client = _make_client_for_queue()

        response = client.get("/api/v1/queue/status")
        assert response.status_code == 503

        orchestrator = SimpleNamespace(
            get_queue_status=lambda: {
                "paused": False,
                "pending": 0,
                "active": 0,
                "limit": 1,
            },
            purge_queue=AsyncMock(
                return_value={"removed": 1, "success": True, "message": "ok"}
            ),
            abort_task=AsyncMock(return_value={"success": False, "message": "missing"}),
        )
        queue_routes.set_dependencies(orchestrator)

        monkeypatch.setattr(
            queue_routes, "ensure_data_mutation_allowed", lambda _op: None
        )
        ok = client.post("/api/v1/queue/purge")
        assert ok.status_code == 200

        monkeypatch.setattr(
            queue_routes,
            "ensure_data_mutation_allowed",
            lambda _op: (_ for _ in ()).throw(PermissionError("forbidden")),
        )
        forbidden = client.post("/api/v1/queue/purge")
        assert forbidden.status_code == 403

        missing = client.post(f"/api/v1/queue/task/{uuid4()}/abort")
        assert missing.status_code == 404
    finally:
        queue_routes.set_dependencies(original_orchestrator)


@pytest.mark.asyncio
async def test_skill_adapter_async_and_missing_args() -> None:
    class _Skill:
        def tool_noop(self):
            return "ok"

    _Skill.tool_noop.__kernel_function_name__ = "noop"
    _Skill.tool_noop.__kernel_function_description__ = "noop"
    _Skill.tool_noop.__kernel_function_parameters__ = [
        {"name": "x", "type_": "int", "is_required": True, "description": "arg"}
    ]

    adapter = skill_adapter_module.SkillMcpLikeAdapter(_Skill())
    tools = adapter.list_tools()
    assert tools and tools[0].input_schema["properties"]["x"]["type"] == "number"
    with pytest.raises(ValueError, match="Missing required arguments"):
        await adapter.invoke_tool("noop", {})

    class _AsyncSkill:
        async def tool_ping(self, value: str):
            await asyncio.sleep(0)
            return f"pong:{value}"

    _AsyncSkill.tool_ping.__kernel_function_name__ = "ping"
    _AsyncSkill.tool_ping.__kernel_function_description__ = "ping"
    _AsyncSkill.tool_ping.__kernel_function_parameters__ = [
        {"name": "value", "type_": "str", "is_required": True, "description": "v"}
    ]

    async_adapter = skill_adapter_module.SkillMcpLikeAdapter(_AsyncSkill())
    assert (
        await async_adapter.invoke_tool("ping", {"value": "1", "extra": "ignored"})
        == "pong:1"
    )
