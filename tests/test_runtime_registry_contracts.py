from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from venom_core.bootstrap import runtime_stack
from venom_core.core import model_registry_providers, model_registry_runtime
from venom_core.core.orchestrator.task_pipeline.context_builder import (
    ContextBuilder,
    format_extra_context,
)
from venom_core.execution.onnx_llm_client import OnnxLlmClient
from venom_core.main import (
    _audio_disabled_status_payload,
    _build_gemma4_runtime_capabilities,
    _build_voice_runtime_alignment,
    _build_voice_runtime_state,
    _effective_audio_decoder_chain,
    _extract_available_local_models,
    _normalize_audio_decoder_chain,
    _normalize_audio_decoder_id,
    _normalize_audio_decoder_profile,
    _normalize_voice_route_profile,
    _require_localhost_request,
    _runtime_switch_state_label,
    _select_startup_model,
    _validate_voice_route_contract,
)
from venom_core.services import module_registry


def test_module_registry_manifest_path_helpers():
    assert module_registry._looks_like_manifest_path("manifest:./x.json") is True
    assert module_registry._looks_like_manifest_path("./x.json") is True
    assert module_registry._looks_like_manifest_path("id|a.b:router") is False


def test_onnx_helpers_and_model_runtime_branch(monkeypatch, tmp_path):
    assert OnnxLlmClient._normalize_execution_provider("unknown") == "cuda"
    assert OnnxLlmClient._provider_fallback_order("cpu") == ["cpu"]
    assert "DML" in OnnxLlmClient._provider_aliases("directml")

    with pytest.raises(TypeError):
        model_registry_runtime.apply_vllm_activation_updates("a", "b", {})

    meta = SimpleNamespace(local_path=str(tmp_path / "model"))
    updates: dict[str, object] = {}
    settings = SimpleNamespace(REPO_ROOT=str(tmp_path))
    model_registry_runtime.apply_vllm_activation_updates(
        "model-x", meta, updates, settings
    )
    assert updates["VLLM_SERVED_MODEL_NAME"] == "model-x"

    from venom_core import config as config_module
    from venom_core.services.config_manager import config_manager

    settings = config_module.SETTINGS
    monkeypatch.setattr(
        settings, "GEMMA4_AUDIO_ENDPOINT", "http://localhost:8014/v1", raising=False
    )
    monkeypatch.setattr(
        settings, "LLM_LOCAL_ENDPOINT", "http://localhost:11434", raising=False
    )
    monkeypatch.setattr(settings, "LLM_MODEL_NAME", "old-model", raising=False)
    monkeypatch.setattr(settings, "ACTIVE_LLM_SERVER", "ollama", raising=False)
    monkeypatch.setattr(settings, "LLM_SERVICE_TYPE", "local", raising=False)
    monkeypatch.setattr(config_manager, "update_config", MagicMock(), raising=False)

    configured = model_registry_runtime.apply_model_activation_config(
        "model-gemma4", "gemma4_audio", SimpleNamespace(local_path="")
    )
    assert configured.ACTIVE_LLM_SERVER == "multi_runtime"
    assert configured.LLM_LOCAL_ENDPOINT == "http://localhost:8014/v1"
    assert configured.LAST_MODEL_GEMMA4_AUDIO == "model-gemma4"


@pytest.mark.asyncio
async def test_restart_runtime_after_activation_paths(monkeypatch: pytest.MonkeyPatch):
    module = ModuleType("venom_core.core.llm_server_controller")

    class _Controller:
        def __init__(self, _settings):
            pass

        def has_server(self, _runtime: str) -> bool:
            return False

        async def run_action(self, _runtime: str, _action: str):
            return SimpleNamespace(ok=True, stderr="")

    module.LlmServerController = _Controller
    monkeypatch.setitem(sys.modules, module.__name__, module)
    await model_registry_runtime.restart_runtime_after_activation(
        "ollama", settings=object()
    )


@pytest.mark.asyncio
async def test_activate_model_and_metadata_branches(monkeypatch: pytest.MonkeyPatch):
    original_ensure = model_registry_runtime.ensure_model_metadata_for_activation
    registry = SimpleNamespace(
        manifest={"m1": SimpleNamespace()},
        providers={},
        _save_manifest=lambda: None,
    )

    monkeypatch.setattr(
        model_registry_runtime,
        "ensure_model_metadata_for_activation",
        AsyncMock(return_value=False),
    )
    assert (
        await model_registry_runtime.activate_model(registry, "m1", "ollama") is False
    )

    monkeypatch.setattr(
        model_registry_runtime,
        "ensure_model_metadata_for_activation",
        AsyncMock(return_value=True),
    )
    registry.manifest = {}
    assert (
        await model_registry_runtime.activate_model(registry, "m1", "ollama") is False
    )

    registry.manifest = {"m1": SimpleNamespace()}
    monkeypatch.setattr(
        model_registry_runtime,
        "apply_model_activation_config",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    assert (
        await model_registry_runtime.activate_model(registry, "m1", "ollama") is False
    )

    monkeypatch.setattr(
        model_registry_runtime,
        "apply_model_activation_config",
        lambda *_a, **_k: SimpleNamespace(),
    )
    monkeypatch.setattr(
        model_registry_runtime,
        "restart_runtime_after_activation",
        AsyncMock(return_value=None),
    )
    assert await model_registry_runtime.activate_model(registry, "m1", "ollama") is True

    # ensure_model_metadata_for_activation branches
    monkeypatch.setattr(
        model_registry_runtime,
        "ensure_model_metadata_for_activation",
        original_ensure,
    )
    registry_meta = SimpleNamespace(manifest={"m1": SimpleNamespace()}, providers={})
    assert await model_registry_runtime.ensure_model_metadata_for_activation(
        registry_meta, "m1", "ollama"
    )
    registry_meta = SimpleNamespace(manifest={}, providers={})
    assert (
        await model_registry_runtime.ensure_model_metadata_for_activation(
            registry_meta, "m1", "vllm"
        )
        is False
    )
    assert (
        await model_registry_runtime.ensure_model_metadata_for_activation(
            registry_meta, "m1", "ollama"
        )
        is False
    )

    provider = SimpleNamespace(get_model_info=AsyncMock(return_value=None))
    saved = {"count": 0}
    registry_meta = SimpleNamespace(
        manifest={},
        providers={model_registry_providers.ModelProvider.OLLAMA: provider},
        _save_manifest=lambda: saved.__setitem__("count", saved["count"] + 1),
    )
    assert (
        await model_registry_runtime.ensure_model_metadata_for_activation(
            registry_meta, "m1", "ollama"
        )
        is False
    )

    provider.get_model_info = AsyncMock(return_value=SimpleNamespace(local_path=None))
    assert await model_registry_runtime.ensure_model_metadata_for_activation(
        registry_meta, "m1", "ollama"
    )
    assert "m1" in registry_meta.manifest
    assert saved["count"] == 1

    provider.get_model_info = AsyncMock(side_effect=RuntimeError("down"))
    assert (
        await model_registry_runtime.ensure_model_metadata_for_activation(
            registry_meta, "m2", "ollama"
        )
        is False
    )


def test_context_builder_and_main_helpers():
    empty = format_extra_context(
        SimpleNamespace(files=None, links=None, paths=None, notes=None)
    )
    assert empty == ""

    populated = format_extra_context(
        SimpleNamespace(
            files=["a.py"],
            links=["https://example"],
            paths=["/tmp"],
            notes=["note"],
        )
    )
    assert "Pliki:" in populated
    assert "Notatki:" in populated

    available = _extract_available_local_models(
        [{"provider": "ollama", "name": "m1"}, {"provider": "vllm", "name": "m2"}],
        "ollama",
    )
    assert available == {"m1"}
    assert _select_startup_model({"m1", "m2"}, "m2", "m1") == "m2"


def test_runtime_stack_keyword_support_and_provider_token_resolution(
    monkeypatch: pytest.MonkeyPatch,
):
    assert (
        runtime_stack._supports_keyword_argument(
            lambda **kwargs: kwargs, "skill_manager"
        )
        is True
    )
    assert (
        runtime_stack._supports_keyword_argument(lambda x: x, "skill_manager") is False
    )
    assert runtime_stack._supports_keyword_argument(123, "x") is False

    token = SimpleNamespace(get_secret_value=lambda: "hf")
    monkeypatch.setattr(model_registry_providers.SETTINGS, "HF_TOKEN", token)
    assert model_registry_providers.resolve_hf_token() == "hf"


@pytest.mark.asyncio
async def test_context_builder_preprocess_request_with_slash_reset(monkeypatch):
    class _StateManager:
        def __init__(self):
            self.context_updates = []
            self.logs = []

        def update_context(self, task_id, payload):
            self.context_updates.append((task_id, payload))

        def add_log(self, task_id, message):
            self.logs.append((task_id, message))

    class _SessionStore:
        def __init__(self):
            self.cleared = []

        def clear_session(self, session_id):
            self.cleared.append(session_id)

    class _Tracer:
        def __init__(self):
            self.routes = []
            self.steps = []

        def set_forced_route(self, task_id, **kwargs):
            self.routes.append((task_id, kwargs))

        def add_step(self, task_id, stage, step, **kwargs):
            self.steps.append((task_id, stage, step, kwargs))

    parsed = SimpleNamespace(
        cleaned="query",
        forced_tool="shell",
        forced_provider="ollama",
        forced_intent=None,
        session_reset=True,
    )
    monkeypatch.setattr(
        "venom_core.core.orchestrator.task_pipeline.context_builder.parse_slash_command",
        lambda _content: parsed,
    )
    monkeypatch.setattr(
        "venom_core.core.orchestrator.task_pipeline.context_builder.resolve_forced_intent",
        lambda _tool: "intent-shell",
    )

    orch = SimpleNamespace(
        state_manager=_StateManager(),
        session_handler=SimpleNamespace(session_store=_SessionStore()),
        request_tracer=_Tracer(),
    )
    builder = ContextBuilder(orch)
    task_id = "task-1"
    request = SimpleNamespace(
        content="/shell query",
        forced_tool=None,
        forced_provider=None,
        forced_intent=None,
        session_id=None,
    )

    await builder.preprocess_request(task_id, request)

    assert request.content == "query"
    assert request.forced_tool == "shell"
    assert request.forced_provider == "ollama"
    assert request.forced_intent == "intent-shell"
    assert request.session_id.startswith("session-")
    assert orch.session_handler.session_store.cleared == [request.session_id]
    assert any(
        "forced_route" in str(update[1])
        for update in orch.state_manager.context_updates
    )


def test_main_voice_route_helpers_and_contracts():
    assert _normalize_voice_route_profile("  venom-agent ") == "venom-agent"
    assert _normalize_voice_route_profile("invalid") == "auto"

    assert _normalize_audio_decoder_profile("hybrid") == "hybrid"
    assert _normalize_audio_decoder_profile("unknown") == "auto"

    assert _normalize_audio_decoder_id("whisper") == "faster_whisper"
    assert _normalize_audio_decoder_id("invalid") == ""

    assert _normalize_audio_decoder_chain("whisper, gemma_native, whisper") == [
        "faster_whisper",
        "gemma_native",
    ]
    assert _normalize_audio_decoder_chain(None) == []

    assert (
        _effective_audio_decoder_chain("chat_tekstowy", "hybrid", ["gemma_native"])
        == []
    )
    assert _effective_audio_decoder_chain("auto", "hybrid", []) == [
        "gemma_native",
        "faster_whisper",
    ]
    assert _effective_audio_decoder_chain("runtime_lokalny", "hybrid", []) == [
        "faster_whisper"
    ]

    _validate_voice_route_contract(
        voice_route_profile="gemma4",
        audio_decoder_profile="hybrid",
        audio_decoder_chain=[],
    )
    with pytest.raises(HTTPException):
        _validate_voice_route_contract(
            voice_route_profile="chat_tekstowy",
            audio_decoder_profile="hybrid",
            audio_decoder_chain=[],
        )
    with pytest.raises(HTTPException):
        _validate_voice_route_contract(
            voice_route_profile="gemma4",
            audio_decoder_profile="faster_whisper",
            audio_decoder_chain=[],
        )
    with pytest.raises(HTTPException):
        _validate_voice_route_contract(
            voice_route_profile="runtime_lokalny",
            audio_decoder_profile="gemma_native",
            audio_decoder_chain=["faster_whisper"],
        )


def test_main_runtime_state_and_access_helpers(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("venom_core.main.get_last_runtime_switch_event", lambda: None)
    req = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))
    _require_localhost_request(req)
    with pytest.raises(HTTPException):
        _require_localhost_request(
            SimpleNamespace(client=SimpleNamespace(host="10.0.0.2"))
        )

    assert (
        _runtime_switch_state_label(
            runtime_switch_gate={"in_progress": True},
            last_runtime_switch=None,
        )
        == "switching"
    )
    assert (
        _runtime_switch_state_label(
            runtime_switch_gate=None,
            last_runtime_switch={"reason": "switch failed due to error"},
        )
        == "failed"
    )
    assert (
        _runtime_switch_state_label(
            runtime_switch_gate=None,
            last_runtime_switch={"reason": "manual"},
        )
        == "ready"
    )
    assert (
        _runtime_switch_state_label(runtime_switch_gate=None, last_runtime_switch=None)
        == "idle"
    )

    runtime_alignment = _build_voice_runtime_alignment(
        runtime_snapshot={"provider": "multi_runtime", "model_name": "m1"},
        latest_session={
            "audio_runtime_provider": "multi_runtime",
            "audio_runtime_model": "m1",
            "created_at": "2026-05-27T10:00:00+00:00",
        },
    )
    state = _build_voice_runtime_state(
        runtime_snapshot={
            "runtime_id": "rt-1",
            "provider": "multi_runtime",
            "model_name": "m1",
        },
        latest_session={
            "audio_runtime_provider": "multi_runtime",
            "audio_runtime_model": "m1",
            "pipeline_id": "voice-v1",
            "created_at": "2026-05-27T10:00:00+00:00",
        },
        runtime_alignment=runtime_alignment,
        runtime_switch_gate={"switch_id": "sw-1", "to_runtime": "multi_runtime"},
        last_runtime_switch={
            "reason": "manual",
            "at_utc": "2026-05-27T09:59:00+00:00",
        },
    )
    assert state["selected"]["runtime_id"] == "multi_runtime"
    assert state["active"]["runtime_id"] == "rt-1"
    assert state["response"]["fresh"] is True
    assert state["switch"]["switch_id"] == "sw-1"

    payload = _audio_disabled_status_payload(
        runtime_switch_gate={"switch_id": "sw-1"},
        last_runtime_switch={"reason": "manual"},
        runtime_snapshot={"provider": "multi_runtime", "model_name": "m1"},
    )
    assert payload["enabled"] is False
    assert payload["runtime_switch_gate"] == {"switch_id": "sw-1"}

    caps = _build_gemma4_runtime_capabilities()
    assert caps["compatibility_profile"] == "multi_runtime_native"


@pytest.mark.asyncio
async def test_context_builder_build_context_and_prepare_context(monkeypatch):
    class _StateManager:
        def __init__(self):
            self.logs = []

        def add_log(self, task_id, message):
            self.logs.append((task_id, message))

        def update_context(self, task_id, payload):  # noqa: ARG002
            return None

    class _Eyes:
        async def analyze_image(self, image, prompt):  # noqa: ARG002
            if image == "bad":
                raise RuntimeError("bad image")
            return "detected text"

    orch = SimpleNamespace(
        state_manager=_StateManager(),
        session_handler=SimpleNamespace(session_store=None),
        request_tracer=None,
        eyes=_Eyes(),
        _build_session_context_block=lambda request, task_id, include_memory: "SESSION",  # noqa: ARG005
        _get_runtime_context_char_limit=lambda _runtime: 20,
    )
    builder = ContextBuilder(orch)
    task_id = "task-2"
    request = SimpleNamespace(
        content="X" * 100,
        forced_tool=None,
        images=["good", "bad"],
        extra_context=SimpleNamespace(
            files=["a.py"], links=None, paths=None, notes=None
        ),
    )

    monkeypatch.setattr(
        "venom_core.core.orchestrator.task_pipeline.context_builder.get_active_llm_runtime",
        lambda: SimpleNamespace(provider="vllm"),
    )

    result = await builder.build_context(task_id, request, fast_path=False)
    assert len(result) <= 20
    assert any("Obraz 1 przeanalizowany" in msg for _, msg in orch.state_manager.logs)
    assert any(
        "Nie udało się przeanalizować obrazu 2" in msg
        for _, msg in orch.state_manager.logs
    )


@pytest.mark.asyncio
async def test_context_builder_add_hidden_prompts_and_perf_shortcut(monkeypatch):
    class _StateManager:
        def __init__(self):
            self.logs = []
            self.statuses = []

        def add_log(self, task_id, message):
            self.logs.append((task_id, message))

        async def update_status(self, task_id, status, result=None):
            self.statuses.append((task_id, status, result))

    class _Tracer:
        def __init__(self):
            self.statuses = []
            self.steps = []

        def update_status(self, task_id, status):
            self.statuses.append((task_id, status))

        def add_step(self, task_id, stage, step, **kwargs):
            self.steps.append((task_id, stage, step, kwargs))

    class _Collector:
        def __init__(self):
            self.completed = 0

        def increment_task_completed(self):
            self.completed += 1

    tracer = _Tracer()
    state = _StateManager()
    events = []

    async def _broadcast_event(**kwargs):
        events.append(kwargs)

    orch = SimpleNamespace(
        state_manager=state,
        request_tracer=tracer,
        intent_manager=SimpleNamespace(PERF_TEST_KEYWORDS=("perf",)),
        _get_runtime_context_char_limit=lambda _runtime: 10,
        _broadcast_event=_broadcast_event,
    )
    builder = ContextBuilder(orch)

    monkeypatch.setattr(
        "venom_core.core.orchestrator.task_pipeline.context_builder.get_active_llm_runtime",
        lambda: SimpleNamespace(provider="vllm"),
    )
    monkeypatch.setattr(
        "venom_core.core.orchestrator.task_pipeline.context_builder.SETTINGS.VLLM_MAX_MODEL_LEN",
        512,
    )
    context = await builder.add_hidden_prompts("task-3", "base context", "intent")
    assert len(context) <= 10
    assert any("Pominięto hidden prompts" in msg for _, msg in state.logs)
    assert builder.is_perf_test_prompt("PERF regression") is True

    monkeypatch.setattr(
        "venom_core.core.metrics.metrics_collector",
        _Collector(),
    )
    monkeypatch.setattr(
        "venom_core.core.orchestrator.task_pipeline.context_builder.get_utc_now_iso",
        lambda: "2026-03-03T00:00:00+00:00",
    )
    await builder.complete_perf_test_task("task-4")
    assert state.statuses
    assert tracer.steps


@pytest.mark.asyncio
async def test_runtime_stack_initializers_cover_success_paths(monkeypatch):
    logger = MagicMock()

    class _GraphStore:
        def __init__(self):
            self.loaded = False

        def load_graph(self):
            self.loaded = True

    class _LessonsStore:
        def __init__(self, vector_store=None):
            self.vector_store = vector_store
            self.lessons = ["l1"]

    orchestrator = SimpleNamespace(lessons_store=None)
    vector_store, graph_store, lessons_store = runtime_stack.initialize_memory_stores(
        logger=logger,
        vector_store_cls=lambda: {"ok": True},
        graph_store_cls=_GraphStore,
        lessons_store_cls=_LessonsStore,
        orchestrator=orchestrator,
    )
    assert vector_store == {"ok": True}
    assert graph_store.loaded is True
    assert lessons_store.lessons == ["l1"]
    assert orchestrator.lessons_store is lessons_store

    engine = runtime_stack.initialize_audio_engine_if_enabled(
        settings=SimpleNamespace(
            ENABLE_AUDIO_INTERFACE=True,
            WHISPER_MODEL_SIZE="tiny",
            TTS_MODEL_PATH="tts",
            AUDIO_DEVICE="cpu",
        ),
        logger=logger,
        audio_engine_cls=lambda **kwargs: kwargs,
    )
    assert engine["device"] == "cpu"

    class _Bridge:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def connect(self):
            return True

    bridge = await runtime_stack.initialize_hardware_bridge_if_enabled(
        settings=SimpleNamespace(
            ENABLE_IOT_BRIDGE=True,
            RIDER_PI_PASSWORD=SimpleNamespace(get_secret_value=lambda: "pw"),
            RIDER_PI_HOST="localhost",
            RIDER_PI_PORT=22,
            RIDER_PI_USERNAME="user",
            RIDER_PI_PROTOCOL="ssh",
        ),
        logger=logger,
        extract_secret_value_fn=lambda s: s.get_secret_value(),
        hardware_bridge_cls=_Bridge,
    )
    assert bridge.kwargs["password"] == "pw"

    kernel_module = ModuleType("venom_core.execution.kernel_builder")

    class _KernelBuilder:
        def build_kernel(self):
            return {"kernel": True}

    kernel_module.KernelBuilder = _KernelBuilder
    monkeypatch.setitem(sys.modules, kernel_module.__name__, kernel_module)

    operator = runtime_stack.initialize_operator_agent_if_possible(
        settings=SimpleNamespace(ENABLE_AUDIO_INTERFACE=True),
        logger=logger,
        current_audio_engine=engine,
        current_hardware_bridge=bridge,
        operator_agent_cls=lambda **kwargs: kwargs,
    )
    assert operator["kernel"]["kernel"] is True

    handler = runtime_stack.initialize_audio_stream_handler_if_possible(
        settings=SimpleNamespace(VAD_THRESHOLD=0.1, SILENCE_DURATION=0.2),
        logger=logger,
        current_audio_engine=engine,
        current_operator_agent=operator,
        audio_stream_handler_cls=lambda **kwargs: kwargs,
    )
    assert handler["silence_duration"] == 0.2


@pytest.mark.asyncio
async def test_runtime_stack_scheduler_documenter_and_shadow_disabled():
    logger = MagicMock()
    job_ids: list[str] = []

    class _Scheduler:
        def __init__(self, event_broadcaster=None):
            self.event_broadcaster = event_broadcaster

        async def start(self):
            return None

        def add_interval_job(self, *, func, minutes, job_id, description):
            assert callable(func)
            assert minutes >= 1
            assert description
            job_ids.append(job_id)

    class _AsyncioModule:
        @staticmethod
        async def to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        @staticmethod
        def create_task(coro):
            import asyncio

            return asyncio.create_task(coro)

    class _JobModule:
        @staticmethod
        async def consolidate_memory(_event_broadcaster):
            return None

        @staticmethod
        async def check_health(_event_broadcaster):
            return None

        @staticmethod
        def cleanup_runtime_files(*args, **kwargs):  # noqa: ARG004
            return None

        @staticmethod
        def should_run_runtime_retention_now(*args, **kwargs):  # noqa: ARG004
            return False

    scheduler, startup_task = await runtime_stack.initialize_background_scheduler(
        settings=SimpleNamespace(
            ENABLE_MEMORY_CONSOLIDATION=True,
            MEMORY_CONSOLIDATION_INTERVAL_MINUTES=5,
            ENABLE_HEALTH_CHECKS=True,
            HEALTH_CHECK_INTERVAL_MINUTES=5,
            ENABLE_RUNTIME_RETENTION_CLEANUP=True,
            RUNTIME_RETENTION_DAYS=7,
            RUNTIME_RETENTION_TARGETS=["logs"],
            REPO_ROOT=".",
            RUNTIME_RETENTION_INTERVAL_MINUTES=60,
        ),
        logger=logger,
        event_broadcaster=object(),
        vector_store={"ok": True},
        request_tracer=SimpleNamespace(clear_old_traces=lambda days=7: days),
        background_scheduler_cls=_Scheduler,
        job_scheduler_module=_JobModule,
        asyncio_module=_AsyncioModule,
        clear_startup_runtime_retention_task=lambda: None,
    )
    assert scheduler is not None
    assert startup_task is None
    assert {"consolidate_memory", "check_health", "cleanup_traces"} <= set(job_ids)

    class _Documenter:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def handle_code_change(self, *_args, **_kwargs):
            return None

    class _Watcher:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def start(self):
            return None

    documenter, watcher = await runtime_stack.initialize_documenter_and_watcher(
        workspace_path=Path("."),
        git_skill=object(),
        skill_manager=object(),
        event_broadcaster=object(),
        logger=logger,
        documenter_agent_cls=_Documenter,
        file_watcher_cls=_Watcher,
    )
    assert documenter is not None
    assert watcher is not None

    shadow, desktop_sensor, notifier = await runtime_stack.initialize_shadow_stack(
        settings=SimpleNamespace(ENABLE_PROACTIVE_MODE=False),
        logger=logger,
        orchestrator=SimpleNamespace(goal_store=None),
        lessons_store=None,
        event_broadcaster=SimpleNamespace(broadcast_event=AsyncMock(return_value=None)),
        system_log_event_type="system.log",
    )
    assert shadow is None
    assert desktop_sensor is None
    assert notifier is None


@pytest.mark.asyncio
async def test_ensure_model_metadata_for_gemma4_audio_known_models():
    """Znane modele gemma4_audio mogą być aktywowane bez wpisu w manifeście."""
    registry = SimpleNamespace(manifest={}, providers={})
    assert await model_registry_runtime.ensure_model_metadata_for_activation(
        registry, "google/gemma-4-E2B-it", "gemma4_audio"
    )
    assert await model_registry_runtime.ensure_model_metadata_for_activation(
        registry, "google/gemma-4-E4B-it", "gemma4_audio"
    )


@pytest.mark.asyncio
async def test_ensure_model_metadata_for_gemma4_audio_unknown_model_fails():
    """Nieznany model dla gemma4_audio (brak w manifeście) zwraca False."""
    registry = SimpleNamespace(manifest={}, providers={})
    result = await model_registry_runtime.ensure_model_metadata_for_activation(
        registry, "google/gemma-4-unknown", "gemma4_audio"
    )
    assert result is False


@pytest.mark.asyncio
async def test_ensure_model_metadata_for_gemma4_audio_manifest_entry_wins():
    """Model w manifeście zawsze zwraca True niezależnie od runtime."""
    registry = SimpleNamespace(
        manifest={"google/gemma-4-unknown": SimpleNamespace()},
        providers={},
    )
    assert await model_registry_runtime.ensure_model_metadata_for_activation(
        registry, "google/gemma-4-unknown", "gemma4_audio"
    )
