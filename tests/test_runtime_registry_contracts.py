from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

import pytest

from venom_core.bootstrap import runtime_stack
from venom_core.core import model_registry_providers, model_registry_runtime
from venom_core.core.orchestrator.task_pipeline.context_builder import (
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
