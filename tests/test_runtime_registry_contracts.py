from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from venom_core.bootstrap import runtime_stack
from venom_core.core import model_registry_providers, model_registry_runtime
from venom_core.core.orchestrator.task_pipeline.context_builder import (
    ContextBuilder,
    format_extra_context,
)
from venom_core.execution.onnx_llm_client import OnnxLlmClient
from venom_core.main import _extract_available_local_models, _select_startup_model
from venom_core.services import module_registry


def test_module_registry_manifest_path_helpers():
    assert module_registry._looks_like_manifest_path("manifest:./x.json") is True
    assert module_registry._looks_like_manifest_path("./x.json") is True
    assert module_registry._looks_like_manifest_path("id|a.b:router") is False


def test_onnx_helpers_and_model_runtime_branch(tmp_path):
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
