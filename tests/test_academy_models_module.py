"""Unit tests for academy_models helper module."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from venom_core.api.routes import academy_models
from venom_core.api.schemas.academy import TrainableModelInfo


def test_get_model_non_trainable_reason_variants():
    assert (
        academy_models.get_model_non_trainable_reason(
            model_id="any",
            provider="openai",
        )
        == "External API models do not support local Academy LoRA training"
    )
    assert "inference-focused" in str(
        academy_models.get_model_non_trainable_reason(
            model_id="llama",
            provider="ollama",
        )
    )
    assert academy_models.get_model_non_trainable_reason("gpt-4") == (
        "Model family does not support local Academy LoRA training"
    )
    assert academy_models.get_model_non_trainable_reason("unsloth/Phi-3-mini") is None
    assert academy_models.get_model_non_trainable_reason("totally-unknown-model") == (
        "Model capability cannot be verified for Academy LoRA training"
    )


def test_get_model_non_trainable_reason_uses_local_artifacts():
    assert (
        academy_models.get_model_non_trainable_reason(
            model_id="gemma-3-4b-it-onnx-int4",
            provider="onnx",
            model_metadata={
                "name": "gemma-3-4b-it-onnx-int4",
                "provider": "onnx",
                "type": "folder",
                "runtime": "onnx",
                "path": "models/gemma-3-4b-it-onnx-int4",
            },
        )
        == "ONNX runtime artifacts are inference-only in Academy LoRA pipeline"
    )


def test_get_model_non_trainable_reason_accepts_valid_local_hf_artifacts(tmp_path):
    model_dir = tmp_path / "gemma-3-4b-it"
    model_dir.mkdir(parents=True)
    (model_dir / "config.json").write_text("{}", encoding="utf-8")
    (model_dir / "model.safetensors").write_text("weights", encoding="utf-8")

    reason = academy_models.get_model_non_trainable_reason(
        model_id="gemma-3-4b-it",
        provider="vllm",
        model_metadata={
            "name": "gemma-3-4b-it",
            "provider": "vllm",
            "type": "folder",
            "path": str(model_dir),
            "source": "models",
        },
    )
    assert reason is None


def test_add_trainable_model_from_catalog_skips_empty_and_duplicates():
    result = []
    seen: set[str] = set()

    academy_models.add_trainable_model_from_catalog(
        result=result,
        seen=seen,
        model_id="",
        provider="x",
        label="x",
        default_model="d",
    )
    assert result == []

    academy_models.add_trainable_model_from_catalog(
        result=result,
        seen=seen,
        model_id="m1",
        provider="prov",
        label="m1 (prov)",
        default_model="m1",
    )
    academy_models.add_trainable_model_from_catalog(
        result=result,
        seen=seen,
        model_id="m1",
        provider="prov",
        label="m1 (prov)",
        default_model="m1",
    )
    assert len(result) == 1
    assert result[0].recommended is True


def test_priority_bucket_policy_local_first_then_cloud():
    assert (
        academy_models.resolve_model_priority_bucket(
            source_type="local",
            cost_tier="free",
            installed_local=True,
        )
        == 0
    )
    assert (
        academy_models.resolve_model_priority_bucket(
            source_type="local",
            cost_tier="free",
            installed_local=False,
        )
        == 1
    )
    assert (
        academy_models.resolve_model_priority_bucket(
            source_type="cloud",
            cost_tier="free",
            installed_local=False,
        )
        == 2
    )
    assert (
        academy_models.resolve_model_priority_bucket(
            source_type="cloud",
            cost_tier="unknown",
            installed_local=False,
        )
        == 3
    )
    assert (
        academy_models.resolve_model_priority_bucket(
            source_type="cloud",
            cost_tier="paid",
            installed_local=False,
        )
        == 4
    )


def test_discover_available_runtime_targets_from_local_catalog():
    runtimes = academy_models.discover_available_runtime_targets(
        [
            {"name": "qwen2.5-coder:7b", "provider": "ollama", "source": "ollama"},
            {"name": "gemma-3-4b-it", "provider": "vllm", "runtime": "vllm"},
            {"name": "gemma-3-4b-it-onnx-int4", "provider": "onnx", "runtime": "onnx"},
        ]
    )
    assert runtimes == ["vllm", "ollama", "onnx"]


def test_runtime_compatibility_resolution_and_recommended_runtime():
    vllm_compat = academy_models.resolve_runtime_compatibility(
        provider="vllm",
        available_runtime_ids=["vllm", "onnx"],
        model_metadata={"runtime": "vllm"},
    )
    assert vllm_compat == {"vllm": True, "onnx": False}
    assert academy_models.resolve_recommended_runtime(vllm_compat) == "vllm"

    ollama_compat = academy_models.resolve_runtime_compatibility(
        provider="ollama",
        available_runtime_ids=["ollama"],
        model_metadata={"runtime": "ollama"},
    )
    assert ollama_compat == {"ollama": True}
    assert academy_models.resolve_recommended_runtime(ollama_compat) == "ollama"

    unknown_compat = academy_models.resolve_runtime_compatibility(
        provider="unknown",
        available_runtime_ids=["onnx"],
        model_metadata={"runtime": ""},
    )
    assert unknown_compat == {"onnx": False}
    assert academy_models.resolve_recommended_runtime(unknown_compat) is None


def test_collect_local_trainable_models_filters_invalid_and_seen():
    local_models = [
        {"name": "  "},
        {"name": "seen-model", "provider": "unsloth"},
        {"name": "local-good", "source": "local-cache"},
    ]
    result = []
    seen = {"seen-model"}

    academy_models.collect_local_trainable_models(
        local_models=local_models,
        default_model="local-good",
        available_runtime_ids=["vllm"],
        result=result,
        seen=seen,
    )

    assert len(result) == 1
    assert result[0].model_id == "local-good"
    assert result[0].installed_local is True


def test_ensure_default_model_visible_adds_non_trainable_default():
    result = []
    seen: set[str] = set()
    academy_models.ensure_default_model_visible(
        "gpt-4",
        ["vllm"],
        result,
        seen,
    )
    assert len(result) == 1
    assert result[0].provider == "config"
    assert result[0].trainable is False
    assert result[0].reason_if_not_trainable is not None


@pytest.mark.asyncio
@patch("venom_core.config.SETTINGS")
async def test_list_trainable_models_handles_catalog_exception(mock_settings):
    mock_settings.ACADEMY_DEFAULT_BASE_MODEL = "custom-default-model"
    mgr = MagicMock()
    mgr.list_local_models = AsyncMock(side_effect=RuntimeError("boom"))

    models = await academy_models.list_trainable_models(mgr=mgr)

    assert models
    assert not any(m.model_id == "custom-default-model" for m in models)
    assert any(m.provider == "unsloth" for m in models)


@pytest.mark.asyncio
@patch("venom_core.config.SETTINGS")
async def test_list_trainable_models_without_manager_uses_defaults(mock_settings):
    mock_settings.ACADEMY_DEFAULT_BASE_MODEL = "unsloth/Phi-3-mini-4k-instruct"
    models = await academy_models.list_trainable_models(mgr=None)
    assert models[0].recommended is True


@pytest.mark.asyncio
@patch("venom_core.config.SETTINGS")
async def test_list_trainable_models_sorts_local_before_cloud_free(
    mock_settings, tmp_path
):
    mock_settings.ACADEMY_DEFAULT_BASE_MODEL = "unsloth/Phi-3-mini-4k-instruct"
    model_dir = tmp_path / "gemma-3-4b-it"
    model_dir.mkdir(parents=True)
    (model_dir / "config.json").write_text("{}", encoding="utf-8")
    (model_dir / "model.safetensors").write_text("weights", encoding="utf-8")

    mgr = MagicMock()
    mgr.list_local_models = AsyncMock(
        return_value=[
            {
                "name": "gemma-3-4b-it",
                "provider": "vllm",
                "runtime": "vllm",
                "source": "models",
                "type": "folder",
                "path": str(model_dir),
            }
        ]
    )

    models = await academy_models.list_trainable_models(mgr=mgr)

    assert models
    assert models[0].model_id == "gemma-3-4b-it"
    assert models[0].source_type == "local"
    assert models[0].cost_tier == "free"
    assert models[0].priority_bucket == 0
    assert models[0].runtime_compatibility == {"vllm": True}
    assert models[0].recommended_runtime == "vllm"
    assert any(
        model.model_id == "unsloth/Phi-3-mini-4k-instruct"
        and model.source_type == "local"
        and model.cost_tier == "free"
        and model.priority_bucket == 1
        and model.runtime_compatibility == {"vllm": True}
        and model.recommended_runtime == "vllm"
        for model in models
    )


@pytest.mark.asyncio
@patch("venom_core.config.SETTINGS")
async def test_list_trainable_models_deduplicates_model_family_entries(
    mock_settings, tmp_path
):
    mock_settings.ACADEMY_DEFAULT_BASE_MODEL = "unsloth/Phi-3-mini-4k-instruct"
    model_dir = tmp_path / "gemma-3-4b-it"
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "config.json").write_text("{}", encoding="utf-8")
    (model_dir / "model.safetensors").write_text("weights", encoding="utf-8")
    mgr = MagicMock()
    mgr.list_local_models = AsyncMock(
        return_value=[
            {
                "name": "gemma-3-4b-it",
                "provider": "vllm",
                "runtime": "vllm",
                "source": "models",
                "path": str(model_dir),
                "type": "folder",
            }
        ]
    )

    models = await academy_models.list_trainable_models(mgr=mgr)
    gemma_family = [
        item for item in models if item.model_id.lower().endswith("gemma-3-4b-it")
    ]

    assert len(gemma_family) == 1
    assert gemma_family[0].model_id == "gemma-3-4b-it"
    assert gemma_family[0].installed_local is True


@pytest.mark.asyncio
@patch("venom_core.config.SETTINGS")
async def test_list_trainable_models_uses_prefetched_local_models(mock_settings):
    mock_settings.ACADEMY_DEFAULT_BASE_MODEL = "unsloth/Phi-3-mini-4k-instruct"
    mgr = MagicMock()
    mgr.list_local_models = AsyncMock()
    prefetched = [
        {
            "name": "Qwen/Qwen2.5-Coder-3B-Instruct",
            "provider": "vllm",
            "runtime": "vllm",
            "source": "models",
        }
    ]

    models = await academy_models.list_trainable_models(
        mgr=mgr,
        local_models=prefetched,
    )

    mgr.list_local_models.assert_not_called()
    model_ids = {item.model_id for item in models}
    assert "Qwen/Qwen2.5-Coder-3B-Instruct" in model_ids
    qwen = next(
        item for item in models if item.model_id == "Qwen/Qwen2.5-Coder-3B-Instruct"
    )
    assert qwen.runtime_compatibility.get("vllm") is True


@pytest.mark.asyncio
@patch("venom_core.config.SETTINGS")
async def test_list_adapters_returns_empty_when_models_dir_missing(
    mock_settings, tmp_path
):
    mock_settings.ACADEMY_MODELS_DIR = str(tmp_path / "does-not-exist")
    mock_settings.ACADEMY_DEFAULT_BASE_MODEL = "base-model"
    adapters = await academy_models.list_adapters(mgr=None)
    assert adapters == []


@pytest.mark.asyncio
@patch("venom_core.config.SETTINGS")
async def test_list_adapters_skips_invalid_dirs_and_marks_active(
    mock_settings, tmp_path
):
    mock_settings.ACADEMY_MODELS_DIR = str(tmp_path)
    mock_settings.ACADEMY_DEFAULT_BASE_MODEL = "base-model"

    (tmp_path / "file.txt").write_text("x", encoding="utf-8")
    (tmp_path / "job-without-adapter").mkdir()
    job_dir = tmp_path / "training_001"
    (job_dir / "adapter").mkdir(parents=True)
    (job_dir / "metadata.json").write_text(
        '{"base_model":"bm","created_at":"t","parameters":{"r":8}}',
        encoding="utf-8",
    )

    mgr = MagicMock()
    mgr.get_active_adapter_info.return_value = {"adapter_id": "training_001"}

    adapters = await academy_models.list_adapters(mgr=mgr)

    assert len(adapters) == 1
    assert adapters[0].adapter_id == "training_001"
    assert adapters[0].is_active is True
    assert adapters[0].base_model == "bm"


@patch("venom_core.config.SETTINGS")
def test_activate_adapter_variants(mock_settings, tmp_path):
    mock_settings.ACADEMY_MODELS_DIR = str(tmp_path)
    mgr = MagicMock()

    with pytest.raises(FileNotFoundError):
        academy_models.activate_adapter(mgr=mgr, adapter_id="missing")

    adapter_dir = tmp_path / "ok-adapter" / "adapter"
    adapter_dir.mkdir(parents=True)
    mgr.activate_adapter.return_value = False
    with pytest.raises(RuntimeError):
        academy_models.activate_adapter(mgr=mgr, adapter_id="ok-adapter")

    mgr.activate_adapter.return_value = True
    payload = academy_models.activate_adapter(mgr=mgr, adapter_id="ok-adapter")
    assert payload["success"] is True
    assert payload["adapter_id"] == "ok-adapter"


@patch("venom_core.config.SETTINGS")
def test_activate_adapter_rejects_path_traversal(mock_settings, tmp_path):
    mock_settings.ACADEMY_MODELS_DIR = str(tmp_path)
    mgr = MagicMock()

    with pytest.raises(ValueError, match="outside of models directory"):
        academy_models.activate_adapter(mgr=mgr, adapter_id="../outside")


def test_deactivate_adapter_variants():
    mgr = MagicMock()
    mgr.deactivate_adapter.return_value = False
    payload = academy_models.deactivate_adapter(mgr)
    assert payload["success"] is False

    mgr.deactivate_adapter.return_value = True
    payload = academy_models.deactivate_adapter(mgr)
    assert payload["success"] is True


@patch("venom_core.api.routes.academy_models.config_manager")
@patch("venom_core.config.SETTINGS")
def test_activate_adapter_with_chat_runtime_deploy_ollama(
    mock_settings, mock_config_manager, tmp_path
):
    mock_settings.ACADEMY_MODELS_DIR = str(tmp_path)
    mock_settings.ACTIVE_LLM_SERVER = "ollama"
    mgr = MagicMock()

    adapter_dir = tmp_path / "ok-adapter" / "adapter"
    adapter_dir.mkdir(parents=True)
    mgr.activate_adapter.return_value = True
    mgr.create_ollama_modelfile.return_value = "venom-adapter-ok-adapter"
    mock_config_manager.get_config.return_value = {"LAST_MODEL_OLLAMA": "phi3:latest"}

    payload = academy_models.activate_adapter(
        mgr=mgr,
        adapter_id="ok-adapter",
        runtime_id="ollama",
        deploy_to_chat_runtime=True,
    )
    assert payload["success"] is True
    assert payload["deployed"] is True
    assert payload["runtime_id"] == "ollama"
    assert payload["chat_model"] == "venom-adapter-ok-adapter"
    assert mock_config_manager.update_config.call_count >= 1


@patch("venom_core.config.SETTINGS")
def test_activate_adapter_with_chat_runtime_deploy_vllm(mock_settings, tmp_path):
    mock_settings.ACADEMY_MODELS_DIR = str(tmp_path)
    mgr = MagicMock()

    adapter_dir = tmp_path / "ok-adapter" / "adapter"
    adapter_dir.mkdir(parents=True)
    mgr.activate_adapter.return_value = True

    with patch(
        "venom_core.api.routes.academy_models._deploy_adapter_to_vllm_runtime",
        return_value={
            "deployed": True,
            "runtime_id": "vllm",
            "chat_model": "venom-adapter-ok-adapter",
        },
    ) as deploy_vllm:
        payload = academy_models.activate_adapter(
            mgr=mgr,
            adapter_id="ok-adapter",
            runtime_id="vllm",
            deploy_to_chat_runtime=True,
        )

    assert payload["success"] is True
    assert payload["deployed"] is True
    assert payload["runtime_id"] == "vllm"
    deploy_vllm.assert_called_once_with(mgr=mgr, adapter_id="ok-adapter")


@patch("venom_core.config.SETTINGS")
def test_activate_adapter_with_chat_runtime_deploy_onnx_skipped(
    mock_settings, tmp_path
):
    mock_settings.ACADEMY_MODELS_DIR = str(tmp_path)
    mgr = MagicMock()

    adapter_dir = tmp_path / "ok-adapter" / "adapter"
    adapter_dir.mkdir(parents=True)
    mgr.activate_adapter.return_value = True

    payload = academy_models.activate_adapter(
        mgr=mgr,
        adapter_id="ok-adapter",
        runtime_id="onnx",
        deploy_to_chat_runtime=True,
    )

    assert payload["success"] is True
    assert payload["deployed"] is False
    assert payload["reason"] == "runtime_not_supported:onnx"


@patch("venom_core.api.routes.academy_models.config_manager")
@patch("venom_core.config.SETTINGS")
def test_deactivate_adapter_with_chat_runtime_rollback_ollama(
    mock_settings, mock_config_manager
):
    mock_settings.ACTIVE_LLM_SERVER = "ollama"
    mgr = MagicMock()
    mgr.deactivate_adapter.return_value = True
    mock_config_manager.get_config.return_value = {
        "PREVIOUS_MODEL_OLLAMA": "phi3:latest"
    }

    payload = academy_models.deactivate_adapter(
        mgr,
        deploy_to_chat_runtime=True,
    )
    assert payload["success"] is True
    assert payload["rolled_back"] is True
    assert payload["runtime_id"] == "ollama"
    assert payload["chat_model"] == "phi3:latest"
    assert mock_config_manager.update_config.call_count >= 1


@patch("venom_core.api.routes.academy_models.config_manager")
@patch("venom_core.config.SETTINGS")
def test_deactivate_adapter_with_chat_runtime_rollback_vllm(
    mock_settings, mock_config_manager, tmp_path
):
    mock_settings.ACTIVE_LLM_SERVER = "vllm"
    mgr = MagicMock()
    mgr.deactivate_adapter.return_value = True
    fallback_runtime_dir = tmp_path / "vllm-fallback"
    fallback_runtime_dir.mkdir(parents=True)
    mock_config_manager.get_config.return_value = {
        "PREVIOUS_MODEL_VLLM": "qwen2.5-coder:7b",
    }

    with (
        patch(
            "venom_core.api.routes.academy_models.get_active_llm_runtime",
            return_value=SimpleNamespace(provider="vllm"),
        ),
        patch(
            "venom_core.api.routes.academy_models._resolve_local_runtime_model_path_by_name",
            return_value=str(fallback_runtime_dir),
        ),
        patch(
            "venom_core.api.routes.academy_models._restart_vllm_runtime",
            return_value=None,
        ),
    ):
        payload = academy_models.deactivate_adapter(
            mgr,
            deploy_to_chat_runtime=True,
        )

    assert payload["success"] is True
    assert payload["rolled_back"] is True
    assert payload["runtime_id"] == "vllm"
    assert payload["chat_model"] == "qwen2.5-coder:7b"
    assert mock_config_manager.update_config.call_count >= 1


@pytest.mark.asyncio
@patch("venom_core.config.SETTINGS")
async def test_validate_adapter_runtime_compatibility_rejects_non_local_runtime(
    mock_settings, tmp_path
):
    mock_settings.ACADEMY_MODELS_DIR = str(tmp_path)
    mock_settings.ACADEMY_DEFAULT_BASE_MODEL = "Qwen/Qwen2.5-Coder-7B-Instruct"

    adapter_dir = tmp_path / "adapter-1"
    adapter_dir.mkdir(parents=True)
    (adapter_dir / "metadata.json").write_text(
        '{"base_model":"Qwen/Qwen2.5-Coder-7B-Instruct"}',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="supports only local runtimes"):
        await academy_models.validate_adapter_runtime_compatibility(
            mgr=MagicMock(),
            adapter_id="adapter-1",
            runtime_id="openai",
        )


@pytest.mark.asyncio
@patch("venom_core.config.SETTINGS")
async def test_validate_adapter_runtime_compatibility_rejects_path_traversal(
    mock_settings, tmp_path
):
    mock_settings.ACADEMY_MODELS_DIR = str(tmp_path)
    mock_settings.ACADEMY_DEFAULT_BASE_MODEL = "Qwen/Qwen2.5-Coder-7B-Instruct"

    with pytest.raises(ValueError, match="outside of models directory"):
        await academy_models.validate_adapter_runtime_compatibility(
            mgr=MagicMock(),
            adapter_id="../outside",
            runtime_id="vllm",
        )


@pytest.mark.asyncio
@patch("venom_core.config.SETTINGS")
async def test_validate_adapter_runtime_compatibility_rejects_incompatible_runtime(
    mock_settings, tmp_path
):
    mock_settings.ACADEMY_MODELS_DIR = str(tmp_path)
    mock_settings.ACADEMY_DEFAULT_BASE_MODEL = "Qwen/Qwen2.5-Coder-7B-Instruct"

    adapter_dir = tmp_path / "adapter-1"
    adapter_dir.mkdir(parents=True)
    (adapter_dir / "metadata.json").write_text(
        '{"base_model":"Qwen/Qwen2.5-Coder-7B-Instruct"}',
        encoding="utf-8",
    )

    with patch(
        "venom_core.api.routes.academy_models.list_trainable_models",
        AsyncMock(
            return_value=[
                TrainableModelInfo(
                    model_id="Qwen/Qwen2.5-Coder-7B-Instruct",
                    label="Qwen 2.5 Coder 7B",
                    provider="huggingface",
                    trainable=True,
                    runtime_compatibility={"vllm": True, "onnx": False},
                )
            ]
        ),
    ):
        with pytest.raises(ValueError, match="Compatible runtimes: vllm"):
            await academy_models.validate_adapter_runtime_compatibility(
                mgr=MagicMock(),
                adapter_id="adapter-1",
                runtime_id="onnx",
            )


@pytest.mark.asyncio
@patch("venom_core.config.SETTINGS")
async def test_validate_adapter_runtime_compatibility_accepts_compatible_runtime(
    mock_settings, tmp_path
):
    mock_settings.ACADEMY_MODELS_DIR = str(tmp_path)
    mock_settings.ACADEMY_DEFAULT_BASE_MODEL = "Qwen/Qwen2.5-Coder-7B-Instruct"

    adapter_dir = tmp_path / "adapter-1"
    adapter_dir.mkdir(parents=True)
    (adapter_dir / "metadata.json").write_text(
        '{"base_model":"Qwen/Qwen2.5-Coder-7B-Instruct"}',
        encoding="utf-8",
    )

    with patch(
        "venom_core.api.routes.academy_models.list_trainable_models",
        AsyncMock(
            return_value=[
                TrainableModelInfo(
                    model_id="Qwen/Qwen2.5-Coder-7B-Instruct",
                    label="Qwen 2.5 Coder 7B",
                    provider="huggingface",
                    trainable=True,
                    runtime_compatibility={"vllm": True, "onnx": False},
                )
            ]
        ),
    ):
        await academy_models.validate_adapter_runtime_compatibility(
            mgr=MagicMock(),
            adapter_id="adapter-1",
            runtime_id="vllm",
        )


@pytest.mark.asyncio
@patch("venom_core.config.SETTINGS")
async def test_validate_adapter_runtime_compatibility_rejects_mismatched_model_id(
    mock_settings, tmp_path
):
    mock_settings.ACADEMY_MODELS_DIR = str(tmp_path)
    mock_settings.ACADEMY_DEFAULT_BASE_MODEL = "Qwen/Qwen2.5-Coder-7B-Instruct"

    adapter_dir = tmp_path / "adapter-1"
    adapter_dir.mkdir(parents=True)
    (adapter_dir / "metadata.json").write_text(
        '{"base_model":"Qwen/Qwen2.5-Coder-7B-Instruct"}',
        encoding="utf-8",
    )

    mgr = MagicMock()
    mgr.list_local_models = AsyncMock(
        return_value=[
            {
                "name": "Qwen/Qwen2.5-Coder-7B-Instruct",
                "provider": "vllm",
                "path": str(tmp_path / "qwen-vllm"),
            },
            {
                "name": "gemma-3-4b-it",
                "provider": "vllm",
                "path": str(tmp_path / "gemma-vllm"),
            },
        ]
    )
    with patch(
        "venom_core.api.routes.academy_models.list_trainable_models",
        AsyncMock(
            return_value=[
                TrainableModelInfo(
                    model_id="Qwen/Qwen2.5-Coder-7B-Instruct",
                    label="Qwen 2.5 Coder 7B",
                    provider="huggingface",
                    trainable=True,
                    runtime_compatibility={"vllm": True, "onnx": False},
                )
            ]
        ),
    ):
        with pytest.raises(
            ValueError, match="Adapter base model does not match selected runtime model"
        ):
            await academy_models.validate_adapter_runtime_compatibility(
                mgr=mgr,
                adapter_id="adapter-1",
                runtime_id="vllm",
                model_id="gemma-3-4b-it",
            )


@pytest.mark.asyncio
@patch("venom_core.config.SETTINGS")
async def test_validate_adapter_runtime_compatibility_rejects_missing_runtime_model(
    mock_settings, tmp_path
):
    mock_settings.ACADEMY_MODELS_DIR = str(tmp_path)
    mock_settings.ACADEMY_DEFAULT_BASE_MODEL = "Qwen/Qwen2.5-Coder-7B-Instruct"

    adapter_dir = tmp_path / "adapter-1"
    adapter_dir.mkdir(parents=True)
    (adapter_dir / "metadata.json").write_text(
        '{"base_model":"Qwen/Qwen2.5-Coder-7B-Instruct"}',
        encoding="utf-8",
    )

    mgr = MagicMock()
    mgr.list_local_models = AsyncMock(
        return_value=[
            {
                "name": "Qwen/Qwen2.5-Coder-7B-Instruct",
                "provider": "vllm",
                "path": str(tmp_path / "qwen-vllm"),
            }
        ]
    )
    with patch(
        "venom_core.api.routes.academy_models.list_trainable_models",
        AsyncMock(
            return_value=[
                TrainableModelInfo(
                    model_id="Qwen/Qwen2.5-Coder-7B-Instruct",
                    label="Qwen 2.5 Coder 7B",
                    provider="huggingface",
                    trainable=True,
                    runtime_compatibility={"vllm": True, "onnx": False},
                )
            ]
        ),
    ):
        with pytest.raises(
            ValueError, match="Selected model is not available on runtime"
        ):
            await academy_models.validate_adapter_runtime_compatibility(
                mgr=mgr,
                adapter_id="adapter-1",
                runtime_id="vllm",
                model_id="non-existing-model",
            )
