from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from venom_core.agents.coder import CoderAgent
from venom_core.agents.integrator import IntegratorAgent
from venom_core.agents.release_manager import ReleaseManagerAgent
from venom_core.agents.toolmaker import ToolmakerAgent
from venom_core.api.routes import academy_conversion, governance, models_remote
from venom_core.bootstrap import runtime_stack
from venom_core.core import model_registry_providers, model_registry_runtime
from venom_core.core.orchestrator.task_pipeline.context_builder import (
    format_extra_context,
)
from venom_core.core.service_monitor import (
    ServiceHealthMonitor,
    ServiceInfo,
    ServiceStatus,
)
from venom_core.execution.onnx_llm_client import OnnxLlmClient
from venom_core.main import _extract_available_local_models, _select_startup_model
from venom_core.services import module_registry


@contextmanager
def _dummy_lock(_path: Path):
    yield


@pytest.mark.asyncio
async def test_models_remote_helpers_and_validate_publish(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("VENOM_REMOTE_MODELS_CATALOG_TTL_SECONDS", "not-int")
    assert models_remote._env_int("VENOM_REMOTE_MODELS_CATALOG_TTL_SECONDS", 7) == 7

    monkeypatch.setenv("VENOM_REMOTE_MODELS_PROVIDER_PROBE_TTL_SECONDS", "2")
    assert models_remote._provider_probe_ttl_seconds() == 10

    monkeypatch.setattr(
        models_remote.SETTINGS,
        "OPENAI_CHAT_COMPLETIONS_ENDPOINT",
        "https://example.org/v1/chat/completions",
        raising=False,
    )
    assert models_remote._openai_models_url() == "https://example.org/v1/models"

    caps = models_remote._map_google_capabilities(
        {
            "name": "models/gemini-1.5-pro",
            "supportedGenerationMethods": ["generateContent", "countTokens"],
        }
    )
    assert "token-counting" in caps
    assert "vision" in caps

    no_caps = models_remote._map_google_capabilities({"name": "models/other"})
    assert no_caps == ["chat", "text-generation"]

    published: list[dict[str, object]] = []

    class _Audit:
        def publish(self, **kwargs):
            published.append(kwargs)

    monkeypatch.setattr(models_remote, "get_audit_stream", lambda: _Audit())
    monkeypatch.setattr(
        models_remote,
        "_validate_openai_connection",
        AsyncMock(return_value=(True, "ok", 12.3)),
    )

    result = await models_remote.validate_provider(
        models_remote.ValidationRequest(provider="openai", model="gpt-4o")
    )
    assert result["status"] == "success"
    assert published and published[0]["action"] == "validate_provider"


def test_module_registry_manifest_path_helpers():
    assert module_registry._looks_like_manifest_path("manifest:./x.json") is True
    assert module_registry._looks_like_manifest_path("./x.json") is True
    assert module_registry._looks_like_manifest_path("id|a.b:router") is False


@pytest.mark.asyncio
async def test_service_monitor_http_and_summary_branches(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[dict[str, object]] = []

    class _Response:
        def __init__(self, status_code: int):
            self.status_code = status_code

    class _Client:
        def __init__(self, *, provider: str, timeout: float):
            calls.append({"provider": provider, "timeout": timeout})

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def aget(self, _url: str, headers=None, raise_for_status=False):
            assert raise_for_status is False
            calls.append({"headers": headers or {}})
            return _Response(503)

    monitor = ServiceHealthMonitor(
        registry=SimpleNamespace(
            get_all_services=lambda: [], get_critical_services=lambda: []
        )
    )
    monkeypatch.setattr(
        "venom_core.core.service_monitor.TrafficControlledHttpClient", _Client
    )
    monkeypatch.setattr(
        "venom_core.core.service_monitor.SETTINGS",
        SimpleNamespace(
            GITHUB_TOKEN=SimpleNamespace(get_secret_value=lambda: "gh-token"),
            OPENAI_API_KEY="",
        ),
    )

    service = ServiceInfo(
        name="GitHub API", service_type="api", endpoint="https://example"
    )
    await monitor._check_http_service(service)
    assert service.status == ServiceStatus.OFFLINE
    assert service.error_message == "HTTP 503"
    assert calls[0]["provider"] == "github"
    assert calls[1]["headers"]["Authorization"] == "Bearer gh-token"

    summary = monitor.get_summary()
    assert summary["total_services"] == 0


@pytest.mark.asyncio
async def test_agent_skill_manager_and_legacy_branches():
    release = ReleaseManagerAgent.__new__(ReleaseManagerAgent)
    release.skill_manager = None
    release.git_skill = SimpleNamespace(
        get_last_commit_log=AsyncMock(return_value="legacy")
    )
    release.file_skill = SimpleNamespace(write_file=AsyncMock(return_value=None))
    assert await release._invoke_git_tool("get_last_commit_log", {"n": 3}) == "legacy"
    await release._write_file("CHANGELOG.md", "x")

    release.skill_manager = SimpleNamespace(
        invoke_mcp_tool=AsyncMock(return_value="mcp")
    )
    assert await release._invoke_git_tool("get_last_commit_log", {"n": 2}) == "mcp"

    integrator = IntegratorAgent.__new__(IntegratorAgent)
    integrator.skill_manager = SimpleNamespace(
        invoke_mcp_tool=AsyncMock(return_value="ok")
    )
    integrator.git_skill = SimpleNamespace(checkout=AsyncMock(return_value="legacy"))
    assert await integrator._invoke_git_tool("checkout", {"branch_name": "x"}) == "ok"
    integrator.skill_manager = None
    assert (
        await integrator._invoke_git_tool("checkout", {"branch_name": "y"}) == "legacy"
    )

    toolmaker = ToolmakerAgent.__new__(ToolmakerAgent)
    toolmaker.skill_manager = None
    toolmaker.file_skill = SimpleNamespace(write_file=AsyncMock(return_value=None))
    await toolmaker._write_file("custom/a.py", "print(1)")

    coder = CoderAgent.__new__(CoderAgent)
    coder.skill_manager = None
    coder.file_skill = SimpleNamespace(read_file=AsyncMock(return_value="print(1)"))
    assert await coder._read_file("a.py") == "print(1)"


def test_onnx_helpers_and_model_runtime_branch(tmp_path: Path):
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
async def test_governance_permission_denied_branch(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        governance,
        "ensure_data_mutation_allowed",
        lambda _op: (_ for _ in ()).throw(PermissionError("blocked")),
    )
    with pytest.raises(HTTPException) as exc_info:
        governance.reset_usage()
    assert exc_info.value.status_code == 403


def test_context_builder_format_extra_context_and_main_helpers():
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


def test_academy_conversion_file_selection_and_media(tmp_path: Path):
    source_file = tmp_path / "src.txt"
    source_file.write_text("q\n\na", encoding="utf-8")
    converted_file = tmp_path / "out.jsonl"
    converted_file.write_text('{"instruction":"q","output":"a"}\n', encoding="utf-8")

    workspace = {
        "base_dir": tmp_path,
        "metadata_file": tmp_path / "files.json",
        "source_dir": tmp_path,
        "converted_dir": tmp_path,
    }
    items = [{"file_id": "src-id", "name": "src.txt", "category": "source"}]
    saved: dict[str, object] = {}

    source_item, converted_item = academy_conversion.convert_dataset_source_file(
        file_id="src-id",
        workspace=workspace,
        target_format="jsonl",
        check_path_traversal_fn=lambda _v: True,
        user_conversion_metadata_lock_fn=_dummy_lock,
        load_user_conversion_metadata_fn=lambda _path: items,
        save_user_conversion_metadata_fn=lambda _path, payload: saved.setdefault(
            "items", payload
        ),
        find_conversion_item_fn=lambda _items, _fid: items[0],
        resolve_workspace_file_path_fn=lambda *_args, **_kwargs: source_file,
        source_to_records_fn=lambda _path: [
            {"instruction": "q", "input": "", "output": "a"}
        ],
        write_records_as_target_fn=lambda _records, _target: converted_file,
        build_conversion_item_fn=academy_conversion.build_conversion_item,
    )
    assert source_item["file_id"] == "src-id"
    assert converted_item["category"] == "converted"
    assert saved["items"]

    with pytest.raises(ValueError):
        academy_conversion.set_conversion_training_selection(
            file_id="bad",
            selected_for_training=True,
            workspace=workspace,
            check_path_traversal_fn=lambda _v: False,
            user_conversion_metadata_lock_fn=_dummy_lock,
            load_user_conversion_metadata_fn=lambda _path: [],
            save_user_conversion_metadata_fn=lambda _path, _items: None,
            find_conversion_item_fn=lambda _items, _fid: None,
        )

    assert (
        academy_conversion.guess_media_type(tmp_path / "file.unknown")
        == "application/octet-stream"
    )


@pytest.mark.asyncio
async def test_academy_conversion_preview_branch(tmp_path: Path):
    text_path = tmp_path / "preview.txt"
    text_path.write_text("x" * 30, encoding="utf-8")
    preview, truncated = await academy_conversion.read_text_preview(
        file_path=text_path,
        max_chars=10,
    )
    assert len(preview) == 10
    assert truncated is True
