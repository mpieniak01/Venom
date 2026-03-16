"""Unit tests for academy_models helper module."""

from __future__ import annotations

import json
import types
from pathlib import Path
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
    assert academy_models.get_model_non_trainable_reason("gemma-3-4b-it") is None
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
    )
    assert result == []

    academy_models.add_trainable_model_from_catalog(
        result=result,
        seen=seen,
        model_id="m1",
        provider="prov",
        label="m1 (prov)",
    )
    academy_models.add_trainable_model_from_catalog(
        result=result,
        seen=seen,
        model_id="m1",
        provider="prov",
        label="m1 (prov)",
    )
    assert len(result) == 1
    assert result[0].recommended is False


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
        model_id="gemma3:latest",
        model_metadata={"runtime": "ollama"},
        runtime_model_families={"ollama": {"gemma-3-4b-it"}},
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

    hf_compat = academy_models.resolve_runtime_compatibility(
        provider="huggingface",
        available_runtime_ids=["vllm", "ollama"],
        model_id="google/gemma-3-4b-it",
        model_metadata={"runtime": ""},
        runtime_model_families={"ollama": {"gemma-3-4b-it"}},
    )
    assert hf_compat == {"vllm": True, "ollama": True}
    assert academy_models.resolve_recommended_runtime(hf_compat) == "vllm"

    hf_without_runtime_model = academy_models.resolve_runtime_compatibility(
        provider="huggingface",
        available_runtime_ids=["vllm", "ollama"],
        model_id="unsloth/Phi-3-mini-4k-instruct",
        model_metadata={"runtime": ""},
        runtime_model_families={"ollama": {"gemma-3-4b-it"}},
    )
    assert hf_without_runtime_model == {"vllm": True, "ollama": False}

    unsloth_without_ollama_family = academy_models.resolve_runtime_compatibility(
        provider="unsloth",
        available_runtime_ids=["vllm", "ollama"],
        model_id="unsloth/Phi-3-mini-4k-instruct",
        model_metadata={"runtime": ""},
        runtime_model_families={"ollama": {"gemma-3-4b-it"}},
    )
    assert unsloth_without_ollama_family == {"vllm": True, "ollama": False}


def test_assess_runtime_base_model_compatibility_incompatible_with_alternatives():
    assessment = academy_models.assess_runtime_base_model_compatibility(
        base_model="unsloth/Phi-3-mini-4k-instruct",
        runtime_id="ollama",
        available_runtime_ids=["vllm", "ollama"],
        runtime_model_families={"ollama": {"gemma-3-4b-it"}},
    )
    assert assessment["is_compatible"] is False
    assert assessment["reason_code"] == "MODEL_RUNTIME_INCOMPATIBLE"
    assert assessment["compatible_runtimes"] == ["vllm"]


def test_assess_runtime_base_model_compatibility_no_targets():
    assessment = academy_models.assess_runtime_base_model_compatibility(
        base_model="gemma-3-4b-it",
        runtime_id="ollama",
        available_runtime_ids=[],
        runtime_model_families={},
    )
    assert assessment["is_compatible"] is False
    assert assessment["reason_code"] == "MODEL_RUNTIME_TARGETS_UNAVAILABLE"
    assert assessment["compatible_runtimes"] == []


def test_discover_runtime_model_families_maps_ollama_aliases():
    families = academy_models.discover_runtime_model_families(
        [
            {"name": "gemma3:latest", "provider": "ollama", "runtime": "ollama"},
            {"name": "phi3:mini", "provider": "ollama", "runtime": "ollama"},
            {"name": "gemma-3-4b-it", "provider": "vllm", "runtime": "vllm"},
        ]
    )

    assert families["ollama"] == {"gemma-3-4b-it", "phi-3-mini-4k-instruct"}
    assert families["vllm"] == {"gemma-3-4b-it"}


def test_resolve_effective_training_base_model_prefers_local_hf_path(tmp_path):
    model_dir = tmp_path / "gemma-3-4b-it"
    model_dir.mkdir(parents=True)
    (model_dir / "config.json").write_text("{}", encoding="utf-8")
    (model_dir / "model.safetensors").write_text("weights", encoding="utf-8")

    resolved = academy_models.resolve_effective_training_base_model(
        "gemma-3-4b-it",
        local_models=[
            {
                "name": "gemma-3-4b-it",
                "provider": "vllm",
                "runtime": "vllm",
                "path": str(model_dir),
            }
        ],
    )
    assert resolved == str(model_dir.resolve())


def test_resolve_effective_training_base_model_prefers_local_path_for_hf_repo_id(
    tmp_path,
):
    model_dir = tmp_path / "gemma-3-4b-it"
    model_dir.mkdir(parents=True)
    (model_dir / "config.json").write_text("{}", encoding="utf-8")
    (model_dir / "model.safetensors").write_text("weights", encoding="utf-8")

    resolved = academy_models.resolve_effective_training_base_model(
        "google/gemma-3-4b-it",
        local_models=[
            {
                "name": "gemma-3-4b-it",
                "provider": "vllm",
                "runtime": "vllm",
                "path": str(model_dir),
            }
        ],
    )
    assert resolved == str(model_dir.resolve())


def test_resolve_effective_training_base_model_falls_back_to_canonical_repo():
    assert (
        academy_models.resolve_effective_training_base_model("gemma-3-4b-it")
        == "google/gemma-3-4b-it"
    )


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
        available_runtime_ids=["vllm"],
        runtime_model_families={},
        result=result,
        seen=seen,
    )

    assert len(result) == 1
    assert result[0].model_id == "local-good"
    assert result[0].installed_local is True


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
    assert not any(model.provider == "config" for model in models)


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
async def test_list_trainable_models_local_hf_base_keeps_ollama_compatibility(
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
            },
            {
                "name": "gemma3:latest",
                "provider": "ollama",
                "runtime": "ollama",
                "source": "ollama",
                "type": "manifest",
            },
        ]
    )

    models = await academy_models.list_trainable_models(mgr=mgr)

    gemma = next(item for item in models if item.model_id == "gemma-3-4b-it")
    assert gemma.runtime_compatibility == {"vllm": True, "ollama": True}
    assert gemma.recommended_runtime == "vllm"


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
    adapters = academy_models.list_adapters(mgr=None)
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
        '{"metadata_version":2,"base_model":"bm","effective_base_model":"bm","requested_runtime_id":"ollama","effective_runtime_id":"ollama","created_at":"t","source_flow":"training","parameters":{"r":8}}',
        encoding="utf-8",
    )

    mgr = MagicMock()
    mgr.get_active_adapter_info.return_value = {"adapter_id": "training_001"}

    adapters = academy_models.list_adapters(mgr=mgr)

    assert len(adapters) == 1
    assert adapters[0].adapter_id == "training_001"
    assert adapters[0].is_active is True
    assert adapters[0].base_model == "bm"
    assert adapters[0].metadata_status == "canonical"


@pytest.mark.asyncio
@patch("venom_core.config.SETTINGS")
async def test_list_adapters_marks_missing_metadata_as_incomplete(
    mock_settings, tmp_path
):
    mock_settings.ACADEMY_MODELS_DIR = str(tmp_path)
    mock_settings.ACADEMY_DEFAULT_BASE_MODEL = "base-model"

    job_dir = tmp_path / "training_002"
    adapter_dir = job_dir / "adapter"
    adapter_dir.mkdir(parents=True)
    (adapter_dir / "adapter_config.json").write_text(
        json.dumps({"base_model_name_or_path": "google/gemma-3-4b-it"}),
        encoding="utf-8",
    )

    adapters = academy_models.list_adapters(mgr=None)

    assert len(adapters) == 1
    assert adapters[0].base_model == "unknown"
    assert adapters[0].created_at == "unknown"
    assert adapters[0].training_params == {}
    assert adapters[0].metadata_status == "metadata_incomplete"
    assert adapters[0].metadata_reason_code == "ADAPTER_METADATA_INCOMPLETE"


@pytest.mark.asyncio
@patch("venom_core.api.routes.academy_models._resolve_repo_root")
@patch("venom_core.config.SETTINGS")
async def test_list_adapters_does_not_rescue_self_learning_from_run_snapshot(
    mock_settings, mock_resolve_repo_root, tmp_path
):
    mock_settings.ACADEMY_MODELS_DIR = str(tmp_path / "models")
    mock_settings.ACADEMY_DEFAULT_BASE_MODEL = "base-model"
    mock_resolve_repo_root.return_value = tmp_path

    run_id = "59d9a38d-6d24-478a-8bd7-8d64e09cec65"
    training_dir = tmp_path / "models" / f"self_learning_{run_id}"
    adapter_dir = training_dir / "adapter"
    adapter_dir.mkdir(parents=True)
    (adapter_dir / "adapter_config.json").write_text(
        json.dumps({"base_model_name_or_path": "google/gemma-3-4b-it"}),
        encoding="utf-8",
    )

    runs_dir = tmp_path / "data" / "academy" / "self_learning"
    runs_dir.mkdir(parents=True)
    (runs_dir / "runs.jsonl").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "created_at": "2026-03-07T06:02:41.634093+00:00",
                "llm_config": {
                    "base_model": "google/gemma-3-4b-it",
                    "runtime_id": "ollama",
                    "lora_rank": 16,
                    "num_epochs": 3,
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    adapters = academy_models.list_adapters(mgr=None)

    assert len(adapters) == 1
    assert adapters[0].adapter_id == f"self_learning_{run_id}"
    assert adapters[0].base_model == "unknown"
    assert adapters[0].created_at == "unknown"
    assert adapters[0].training_params == {}
    assert adapters[0].metadata_status == "metadata_incomplete"


@patch("venom_core.config.SETTINGS")
def test_purge_legacy_adapters_dry_run_lists_only_noncanonical(mock_settings, tmp_path):
    mock_settings.ACADEMY_MODELS_DIR = str(tmp_path)

    legacy_dir = tmp_path / "legacy_adapter"
    (legacy_dir / "adapter").mkdir(parents=True)
    (legacy_dir / "adapter" / "adapter_config.json").write_text("{}", encoding="utf-8")

    canonical_dir = tmp_path / "canonical_adapter"
    (canonical_dir / "adapter").mkdir(parents=True)
    (canonical_dir / "metadata.json").write_text(
        json.dumps(
            {
                "metadata_version": 2,
                "effective_base_model": "gemma-3-4b-it",
                "created_at": "2026-03-07T12:00:00+00:00",
                "source_flow": "self_learning",
            }
        ),
        encoding="utf-8",
    )

    result = academy_models.purge_legacy_adapters(mgr=None, apply=False)

    assert result["mode"] == "dry-run"
    assert result["candidates"] == ["legacy_adapter"]
    assert result["removed"] == []
    assert legacy_dir.exists()
    assert canonical_dir.exists()


@patch("venom_core.config.SETTINGS")
def test_purge_legacy_adapters_apply_skips_active_by_default(mock_settings, tmp_path):
    mock_settings.ACADEMY_MODELS_DIR = str(tmp_path)

    active_legacy = tmp_path / "active_legacy"
    (active_legacy / "adapter").mkdir(parents=True)
    (active_legacy / "adapter" / "adapter_config.json").write_text(
        "{}",
        encoding="utf-8",
    )

    removable_legacy = tmp_path / "removable_legacy"
    (removable_legacy / "adapter").mkdir(parents=True)
    (removable_legacy / "adapter" / "adapter_config.json").write_text(
        "{}",
        encoding="utf-8",
    )

    mgr = MagicMock()
    mgr.get_active_adapter_info.return_value = {"adapter_id": "active_legacy"}

    result = academy_models.purge_legacy_adapters(mgr=mgr, apply=True)

    assert result["mode"] == "apply"
    assert result["removed"] == ["removable_legacy"]
    assert result["skipped_active"] == ["active_legacy"]
    assert active_legacy.exists()
    assert not removable_legacy.exists()


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
    mock_settings.ACADEMY_DEFAULT_BASE_MODEL = "phi3:latest"
    mock_settings.ACTIVE_LLM_SERVER = "ollama"
    mgr = MagicMock()

    adapter_dir = tmp_path / "ok-adapter" / "adapter"
    adapter_dir.mkdir(parents=True)
    (tmp_path / "ok-adapter" / "metadata.json").write_text(
        '{"metadata_version":2,"base_model":"phi3:latest","effective_base_model":"phi3:latest","created_at":"2026-03-07T12:00:00+00:00","source_flow":"training"}',
        encoding="utf-8",
    )
    mgr.activate_adapter.return_value = True
    mgr.create_ollama_modelfile.return_value = "venom-adapter-ok-adapter"
    mock_config_manager.get_config.return_value = {"LAST_MODEL_OLLAMA": "phi3:latest"}

    with (
        patch.object(academy_models, "SETTINGS", mock_settings),
        patch(
            "venom_core.services.academy.adapter_runtime_service._ensure_ollama_adapter_gguf",
            return_value=adapter_dir / "Adapter-F16-LoRA.gguf",
        ),
    ):
        payload = academy_models.activate_adapter(
            mgr=mgr,
            adapter_id="ok-adapter",
            runtime_id="ollama",
            model_id="phi3:latest",
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
            model_id="Qwen/Qwen2.5-Coder-7B-Instruct",
            deploy_to_chat_runtime=True,
        )

    assert payload["success"] is True
    assert payload["deployed"] is True
    assert payload["runtime_id"] == "vllm"
    deploy_vllm.assert_called_once_with(adapter_id="ok-adapter")


@patch("venom_core.config.SETTINGS")
def test_activate_adapter_with_chat_runtime_deploy_onnx_raises_metadata_incomplete(
    mock_settings, tmp_path
):
    """202D regression: ONNX deploy is no longer silently skipped.

    Pre-202D: activate with runtime_id=onnx returned deployed=False, reason=runtime_not_supported:onnx.
    Post-202D: the deploy is attempted; incomplete adapter fixture raises ADAPTER_METADATA_INCOMPLETE.
    """
    mock_settings.ACADEMY_MODELS_DIR = str(tmp_path)
    mgr = MagicMock()

    adapter_dir = tmp_path / "ok-adapter" / "adapter"
    adapter_dir.mkdir(parents=True)
    mgr.activate_adapter.return_value = True

    # With 202D, ONNX deploy is attempted — incomplete fixture raises ValueError
    import pytest as _pytest

    with _pytest.raises(ValueError, match="ADAPTER_METADATA_INCOMPLETE"):
        academy_models.activate_adapter(
            mgr=mgr,
            adapter_id="ok-adapter",
            runtime_id="onnx",
            model_id="phi3-onnx",
            deploy_to_chat_runtime=True,
        )


@patch("venom_core.config.SETTINGS")
def test_activate_adapter_with_chat_runtime_requires_explicit_runtime_before_side_effects(
    mock_settings, tmp_path
):
    mock_settings.ACADEMY_MODELS_DIR = str(tmp_path)
    mgr = MagicMock()

    adapter_dir = tmp_path / "ok-adapter" / "adapter"
    adapter_dir.mkdir(parents=True)

    with pytest.raises(ValueError, match="ADAPTER_RUNTIME_REQUIRED"):
        academy_models.activate_adapter(
            mgr=mgr,
            adapter_id="ok-adapter",
            model_id="gemma3:latest",
            deploy_to_chat_runtime=True,
        )

    mgr.activate_adapter.assert_not_called()


@patch("venom_core.config.SETTINGS")
def test_activate_adapter_with_chat_runtime_requires_explicit_model_before_side_effects(
    mock_settings, tmp_path
):
    mock_settings.ACADEMY_MODELS_DIR = str(tmp_path)
    mgr = MagicMock()

    adapter_dir = tmp_path / "ok-adapter" / "adapter"
    adapter_dir.mkdir(parents=True)

    with pytest.raises(ValueError, match="ADAPTER_RUNTIME_MODEL_REQUIRED"):
        academy_models.activate_adapter(
            mgr=mgr,
            adapter_id="ok-adapter",
            runtime_id="ollama",
            deploy_to_chat_runtime=True,
        )

    mgr.activate_adapter.assert_not_called()


@patch("venom_core.api.routes.academy_models.config_manager")
@patch("venom_core.config.SETTINGS")
def test_deactivate_adapter_with_chat_runtime_rollback_ollama(
    mock_settings, mock_config_manager
):
    mock_settings.ACTIVE_LLM_SERVER = "ollama"
    mock_settings.LLM_MODEL_NAME = "venom-adapter-self_learning_x"
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
    (adapter_dir / "adapter").mkdir(parents=True)
    (adapter_dir / "metadata.json").write_text(
        '{"metadata_version":2,"base_model":"Qwen/Qwen2.5-Coder-7B-Instruct","effective_base_model":"Qwen/Qwen2.5-Coder-7B-Instruct","created_at":"2026-03-07T12:00:00+00:00","source_flow":"training"}',
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
async def test_validate_adapter_runtime_compatibility_raises_not_found_for_missing_adapter(
    mock_settings, tmp_path
):
    mock_settings.ACADEMY_MODELS_DIR = str(tmp_path)
    mock_settings.ACADEMY_DEFAULT_BASE_MODEL = "Qwen/Qwen2.5-Coder-7B-Instruct"

    adapter_dir = tmp_path / "adapter-1"
    adapter_dir.mkdir(parents=True)

    with pytest.raises(FileNotFoundError, match="Adapter not found"):
        await academy_models.validate_adapter_runtime_compatibility(
            mgr=MagicMock(),
            adapter_id="adapter-1",
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
    (adapter_dir / "adapter").mkdir(parents=True)
    (adapter_dir / "metadata.json").write_text(
        '{"metadata_version":2,"base_model":"Qwen/Qwen2.5-Coder-7B-Instruct","effective_base_model":"Qwen/Qwen2.5-Coder-7B-Instruct","created_at":"2026-03-07T12:00:00+00:00","source_flow":"training"}',
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
        with pytest.raises(ValueError, match="ADAPTER_RUNTIME_INCOMPATIBLE"):
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
    (adapter_dir / "adapter").mkdir(parents=True)
    (adapter_dir / "metadata.json").write_text(
        '{"metadata_version":2,"base_model":"Qwen/Qwen2.5-Coder-7B-Instruct","effective_base_model":"Qwen/Qwen2.5-Coder-7B-Instruct","created_at":"2026-03-07T12:00:00+00:00","source_flow":"training"}',
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
    (adapter_dir / "adapter").mkdir(parents=True)
    (adapter_dir / "metadata.json").write_text(
        '{"metadata_version":2,"base_model":"Qwen/Qwen2.5-Coder-7B-Instruct","effective_base_model":"Qwen/Qwen2.5-Coder-7B-Instruct","created_at":"2026-03-07T12:00:00+00:00","source_flow":"training"}',
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
    (adapter_dir / "adapter").mkdir(parents=True)
    (adapter_dir / "metadata.json").write_text(
        '{"metadata_version":2,"base_model":"Qwen/Qwen2.5-Coder-7B-Instruct","effective_base_model":"Qwen/Qwen2.5-Coder-7B-Instruct","created_at":"2026-03-07T12:00:00+00:00","source_flow":"training"}',
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
        with pytest.raises(ValueError, match="ADAPTER_RUNTIME_MODEL_MISSING"):
            await academy_models.validate_adapter_runtime_compatibility(
                mgr=mgr,
                adapter_id="adapter-1",
                runtime_id="vllm",
                model_id="non-existing-model",
            )


@pytest.mark.asyncio
@patch("venom_core.config.SETTINGS")
async def test_validate_adapter_runtime_compatibility_accepts_missing_selected_model_for_onnx(
    mock_settings, tmp_path
):
    mock_settings.ACADEMY_MODELS_DIR = str(tmp_path)
    mock_settings.ACADEMY_DEFAULT_BASE_MODEL = "gemma-3-4b-it"

    adapter_dir = tmp_path / "adapter-1"
    adapter_dir.mkdir(parents=True)
    (adapter_dir / "adapter").mkdir(parents=True)
    (adapter_dir / "metadata.json").write_text(
        '{"metadata_version":2,"base_model":"gemma-3-4b-it","effective_base_model":"gemma-3-4b-it","created_at":"2026-03-07T12:00:00+00:00","source_flow":"training"}',
        encoding="utf-8",
    )

    mgr = MagicMock()
    mgr.list_local_models = AsyncMock(
        return_value=[
            {
                "name": "gemma-3-4b-it-onnx-int4",
                "provider": "onnx",
                "path": str(tmp_path / "gemma-onnx"),
            }
        ]
    )
    with patch(
        "venom_core.api.routes.academy_models.list_trainable_models",
        AsyncMock(
            return_value=[
                TrainableModelInfo(
                    model_id="gemma-3-4b-it",
                    label="Gemma 3 4B",
                    provider="huggingface",
                    trainable=True,
                    runtime_compatibility={"vllm": True, "onnx": True},
                )
            ]
        ),
    ):
        await academy_models.validate_adapter_runtime_compatibility(
            mgr=mgr,
            adapter_id="adapter-1",
            runtime_id="onnx",
            model_id="unsloth/gemma-2-2b-it",
        )


@pytest.mark.asyncio
@patch("venom_core.config.SETTINGS")
async def test_validate_adapter_runtime_compatibility_accepts_runtime_adapter_model(
    mock_settings, tmp_path
):
    mock_settings.ACADEMY_MODELS_DIR = str(tmp_path)
    mock_settings.ACADEMY_DEFAULT_BASE_MODEL = "Qwen/Qwen2.5-Coder-7B-Instruct"

    adapter_dir = tmp_path / "adapter-1"
    adapter_dir.mkdir(parents=True)
    (adapter_dir / "adapter").mkdir(parents=True)
    (adapter_dir / "metadata.json").write_text(
        '{"metadata_version":2,"base_model":"Qwen/Qwen2.5-Coder-7B-Instruct","effective_base_model":"Qwen/Qwen2.5-Coder-7B-Instruct","created_at":"2026-03-07T12:00:00+00:00","source_flow":"training"}',
        encoding="utf-8",
    )

    mgr = MagicMock()
    mgr.list_local_models = AsyncMock(
        return_value=[
            {
                "name": "venom-adapter-self_learning_test",
                "provider": "vllm",
                "path": str(tmp_path / "runtime-adapter"),
            },
            {
                "name": "Qwen/Qwen2.5-Coder-7B-Instruct",
                "provider": "vllm",
                "path": str(tmp_path / "qwen-vllm"),
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
        await academy_models.validate_adapter_runtime_compatibility(
            mgr=mgr,
            adapter_id="adapter-1",
            runtime_id="vllm",
            model_id="venom-adapter-self_learning_test",
        )


@patch("venom_core.config.SETTINGS")
def test_activate_adapter_rejects_ollama_deploy_on_base_model_mismatch(
    mock_settings, tmp_path
):
    mock_settings.ACADEMY_MODELS_DIR = str(tmp_path)
    mock_settings.ACADEMY_DEFAULT_BASE_MODEL = "Qwen/Qwen2.5-Coder-7B-Instruct"

    adapter_dir = tmp_path / "adapter-1"
    (adapter_dir / "adapter").mkdir(parents=True)
    (adapter_dir / "metadata.json").write_text(
        '{"metadata_version":2,"base_model":"Qwen/Qwen2.5-Coder-7B-Instruct","effective_base_model":"Qwen/Qwen2.5-Coder-7B-Instruct","created_at":"2026-03-07T12:00:00+00:00","source_flow":"training"}',
        encoding="utf-8",
    )

    mgr = MagicMock()
    mgr.activate_adapter.return_value = True
    mgr.create_ollama_modelfile.return_value = "venom-adapter-adapter-1"

    with patch.object(academy_models, "SETTINGS", mock_settings):
        with pytest.raises(ValueError, match="ADAPTER_BASE_MODEL_MISMATCH"):
            academy_models.activate_adapter(
                mgr=mgr,
                adapter_id="adapter-1",
                runtime_id="ollama",
                model_id="gemma-3-4b-it",
                deploy_to_chat_runtime=True,
            )

    mgr.create_ollama_modelfile.assert_not_called()


def test_runtime_helper_alias_and_provider_inference():
    assert (
        academy_models._canonical_runtime_model_id("gemma3:latest") == "gemma-3-4b-it"
    )
    assert (
        academy_models._canonical_runtime_model_id("qwen2.5-coder:3b")
        == "qwen/qwen2.5-coder-3b-instruct"
    )
    assert (
        academy_models._canonical_runtime_model_id("gemma-3-4b-it-onnx-build-test")
        == "gemma-3-4b-it"
    )
    assert academy_models._canonical_runtime_model_id("  ") == ""

    assert (
        academy_models._infer_local_runtime_provider({"provider": "ollama"}) == "ollama"
    )
    assert academy_models._infer_local_runtime_provider({"source": "onnx"}) == "onnx"
    assert (
        academy_models._infer_local_runtime_provider(
            {"name": "qwen2.5-coder:7b", "path": "/tmp/model"}
        )
        == "ollama"
    )
    assert (
        academy_models._infer_local_runtime_provider(
            {"name": "gemma-onnx", "path": "/tmp/weights/model.onnx"}
        )
        == "onnx"
    )
    assert (
        academy_models._infer_local_runtime_provider(
            {"name": "gemma-3-4b-it", "path": "/tmp/gemma"}
        )
        == "vllm"
    )


@pytest.mark.asyncio
async def test_assert_runtime_model_available_handles_direct_alias_and_missing():
    mgr = MagicMock()
    mgr.list_local_models = AsyncMock(
        return_value=[
            {"name": "gemma-3-4b-it", "provider": "vllm"},
            {"name": "qwen2.5-coder:7b", "provider": "ollama"},
        ]
    )

    await academy_models._assert_runtime_model_available(
        mgr=mgr, runtime_id="vllm", model_id="gemma-3-4b-it"
    )
    await academy_models._assert_runtime_model_available(
        mgr=mgr, runtime_id="vllm", model_id="gemma3:latest"
    )
    await academy_models._assert_runtime_model_available(
        mgr=mgr,
        runtime_id="ollama",
        model_id="Qwen/Qwen2.5-Coder-7B-Instruct",
    )

    with pytest.raises(ValueError, match="ADAPTER_RUNTIME_MODEL_MISSING"):
        await academy_models._assert_runtime_model_available(
            mgr=mgr, runtime_id="vllm", model_id="missing-model"
        )


@pytest.mark.asyncio
async def test_assert_runtime_model_available_ignores_loader_failure():
    mgr = MagicMock()
    mgr.list_local_models = AsyncMock(side_effect=RuntimeError("boom"))
    await academy_models._assert_runtime_model_available(
        mgr=mgr, runtime_id="vllm", model_id="gemma-3-4b-it"
    )


def test_require_trusted_adapter_base_model_rejects_unknown_metadata(tmp_path):
    adapter_dir = tmp_path / "legacy-adapter"
    (adapter_dir / "adapter").mkdir(parents=True)

    with pytest.raises(ValueError, match="ADAPTER_METADATA_INCOMPLETE"):
        academy_models._require_trusted_adapter_base_model(
            adapter_dir=adapter_dir,
        )


def test_require_trusted_adapter_base_model_rejects_inconsistent_metadata(tmp_path):
    adapter_dir = tmp_path / "legacy-adapter"
    (adapter_dir / "adapter").mkdir(parents=True)
    (adapter_dir / "metadata.json").write_text(
        '{"metadata_version":2,"base_model":"Qwen/Qwen2.5-Coder-7B-Instruct","effective_base_model":"gemma-3-4b-it","created_at":"2026-03-07T12:00:00+00:00","source_flow":"training"}',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="ADAPTER_METADATA_INCONSISTENT"):
        academy_models._require_trusted_adapter_base_model(
            adapter_dir=adapter_dir,
        )


@pytest.mark.asyncio
@patch("venom_core.api.routes.academy_models.SETTINGS")
async def test_audit_adapters_categorizes_unknown_mismatch_and_compatible(
    mock_settings, tmp_path
):
    mock_settings.ACADEMY_MODELS_DIR = str(tmp_path)
    mock_settings.ACADEMY_DEFAULT_BASE_MODEL = "unsloth/Phi-3-mini-4k-instruct"

    unknown_dir = tmp_path / "unknown-adapter"
    (unknown_dir / "adapter").mkdir(parents=True)

    mismatch_dir = tmp_path / "mismatch-adapter"
    (mismatch_dir / "adapter").mkdir(parents=True)
    (mismatch_dir / "metadata.json").write_text(
        '{"metadata_version":2,"base_model":"Qwen/Qwen2.5-Coder-7B-Instruct","effective_base_model":"gemma-3-4b-it","created_at":"2026-03-07T12:00:00+00:00","source_flow":"training"}',
        encoding="utf-8",
    )

    compatible_dir = tmp_path / "compatible-adapter"
    (compatible_dir / "adapter").mkdir(parents=True)
    (compatible_dir / "metadata.json").write_text(
        '{"metadata_version":2,"base_model":"Qwen/Qwen2.5-Coder-7B-Instruct","effective_base_model":"Qwen/Qwen2.5-Coder-7B-Instruct","created_at":"2026-03-07T12:00:00+00:00","source_flow":"training"}',
        encoding="utf-8",
    )

    mgr = MagicMock()
    mgr.get_active_adapter_info.return_value = {"adapter_id": "compatible-adapter"}

    payload = academy_models.audit_adapters(
        mgr=mgr,
        runtime_id="ollama",
        model_id="Qwen/Qwen2.5-Coder-7B-Instruct",
    )

    by_id = {item["adapter_id"]: item for item in payload["adapters"]}
    assert by_id["unknown-adapter"]["category"] == "blocked_unknown_base"
    assert by_id["unknown-adapter"]["reason_code"] == "ADAPTER_METADATA_INCOMPLETE"
    assert by_id["mismatch-adapter"]["category"] == "blocked_mismatch"
    assert by_id["mismatch-adapter"]["reason_code"] == "ADAPTER_METADATA_INCONSISTENT"
    assert by_id["compatible-adapter"]["category"] == "compatible"
    assert by_id["compatible-adapter"]["is_active"] is True


@pytest.mark.asyncio
@patch("venom_core.api.routes.academy_models.SETTINGS")
async def test_audit_adapters_treats_runtime_adapter_model_as_compatible_selection(
    mock_settings, tmp_path
):
    mock_settings.ACADEMY_MODELS_DIR = str(tmp_path)
    mock_settings.ACADEMY_DEFAULT_BASE_MODEL = "unsloth/gemma-2-2b-it"

    adapter_dir = tmp_path / "self_learning_adapter"
    (adapter_dir / "adapter").mkdir(parents=True)
    (adapter_dir / "metadata.json").write_text(
        '{"metadata_version":2,"base_model":"unsloth/gemma-2-2b-it","effective_base_model":"unsloth/gemma-2-2b-it","created_at":"2026-03-07T12:00:00+00:00","source_flow":"training"}',
        encoding="utf-8",
    )

    mgr = MagicMock()
    mgr.get_active_adapter_info.return_value = {"adapter_id": "self_learning_adapter"}

    payload = academy_models.audit_adapters(
        mgr=mgr,
        runtime_id="ollama",
        model_id="venom-adapter-self_learning_bdc2d5fc-f7d4-44cd-a34a-cfc892a58cd9",
    )

    by_id = {item["adapter_id"]: item for item in payload["adapters"]}
    assert by_id["self_learning_adapter"]["category"] == "compatible"


def test_runtime_resolution_helpers_and_model_dir_detection(tmp_path):
    assert academy_models._resolve_runtime_for_adapter_deploy(None) == ""
    assert academy_models._resolve_runtime_for_adapter_deploy("ollama") == "ollama"
    assert academy_models._runtime_endpoint_for_hash("onnx") is None
    assert academy_models._runtime_endpoint_for_hash("vllm")

    runtime_dir = tmp_path / "runtime-model"
    runtime_dir.mkdir(parents=True)
    assert academy_models._is_runtime_model_dir(runtime_dir) is False
    (runtime_dir / "config.json").write_text("{}", encoding="utf-8")
    (runtime_dir / "model-00001.safetensors").write_text("x", encoding="utf-8")
    assert academy_models._is_runtime_model_dir(runtime_dir) is True


@patch("venom_core.api.routes.academy_models.SETTINGS")
def test_resolve_local_runtime_model_path_by_name_search_paths(mock_settings, tmp_path):
    mock_settings.ACADEMY_MODELS_DIR = str(tmp_path / "data-models")
    mock_settings.REPO_ROOT = str(tmp_path)
    (tmp_path / "data-models").mkdir(parents=True)
    (tmp_path / "models").mkdir(parents=True)
    (tmp_path / "data-models" / "from-academy").mkdir()
    (tmp_path / "models" / "from-repo-models").mkdir()

    mgr = SimpleNamespace(models_dir=tmp_path / "custom-models")
    (tmp_path / "custom-models").mkdir()
    (tmp_path / "custom-models" / "from-manager-dir").mkdir()

    assert academy_models._resolve_local_runtime_model_path_by_name(
        mgr=mgr, model_name="from-manager-dir"
    ) == str((tmp_path / "custom-models" / "from-manager-dir"))
    assert academy_models._resolve_local_runtime_model_path_by_name(
        mgr=SimpleNamespace(models_dir="not-a-path"), model_name="from-academy"
    ) == str((tmp_path / "data-models" / "from-academy"))
    assert academy_models._resolve_local_runtime_model_path_by_name(
        mgr=SimpleNamespace(models_dir="not-a-path"), model_name="from-repo-models"
    ) == str((tmp_path / "models" / "from-repo-models"))


@patch("venom_core.api.routes.academy_models._resolve_repo_root")
def test_restart_vllm_runtime_errors_for_missing_and_non_zero(
    mock_resolve_repo_root, tmp_path
):
    mock_resolve_repo_root.return_value = tmp_path
    with pytest.raises(RuntimeError, match="service script not found"):
        academy_models._restart_vllm_runtime()

    script = tmp_path / "scripts" / "llm" / "vllm_service.sh"
    script.parent.mkdir(parents=True)
    script.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    with patch("subprocess.run") as run_mock:
        run_mock.return_value = SimpleNamespace(
            returncode=1, stderr="restart failed", stdout=""
        )
        with pytest.raises(RuntimeError, match="Failed to restart vLLM runtime"):
            academy_models._restart_vllm_runtime()


@patch("venom_core.api.routes.academy_models._restart_vllm_runtime")
@patch("venom_core.api.routes.academy_models.compute_llm_config_hash")
@patch("venom_core.api.routes.academy_models.config_manager")
@patch("venom_core.api.routes.academy_models.SETTINGS")
def test_deploy_adapter_to_vllm_runtime_updates_config_and_settings(
    mock_settings,
    mock_config_manager,
    mock_hash,
    _mock_restart,
    tmp_path,
):
    mock_settings.ACADEMY_MODELS_DIR = str(tmp_path)
    mock_settings.ACADEMY_DEFAULT_BASE_MODEL = "unsloth/Phi-3-mini-4k-instruct"
    mock_hash.return_value = "hash-vllm"
    mock_config_manager.get_config.return_value = {
        "LAST_MODEL_VLLM": "gemma-3-4b-it",
        "LLM_MODEL_NAME": "gemma-3-4b-it",
    }

    adapter_dir = tmp_path / "adapter-1"
    (adapter_dir / "adapter").mkdir(parents=True)
    (adapter_dir / "metadata.json").write_text(
        json.dumps(
            {
                "metadata_version": 2,
                "base_model": "unsloth/Phi-3-mini-4k-instruct",
                "effective_base_model": "unsloth/Phi-3-mini-4k-instruct",
                "created_at": "2026-03-07T12:00:00+00:00",
                "source_flow": "training",
            }
        ),
        encoding="utf-8",
    )
    runtime_dir = adapter_dir / "runtime_vllm"
    runtime_dir.mkdir(parents=True)
    (runtime_dir / "config.json").write_text("{}", encoding="utf-8")
    (runtime_dir / "model-00001.safetensors").write_text("x", encoding="utf-8")
    (runtime_dir / "chat_template.jinja").write_text("{{message}}", encoding="utf-8")

    with patch(
        "venom_core.api.routes.academy_models._build_vllm_runtime_model_from_adapter",
        return_value=runtime_dir,
    ):
        payload = academy_models._deploy_adapter_to_vllm_runtime(
            adapter_id="adapter-1",
        )

    assert payload["deployed"] is True
    assert payload["runtime_id"] == "vllm"
    assert payload["chat_model"] == "venom-adapter-adapter-1"
    updates = mock_config_manager.update_config.call_args[0][0]
    assert updates["ACTIVE_LLM_SERVER"] == "vllm"
    assert updates["LLM_CONFIG_HASH"] == "hash-vllm"
    assert updates["VLLM_MODEL_PATH"] == str(runtime_dir)


@patch("venom_core.config.SETTINGS")
@patch("venom_core.api.routes.academy_models.config_manager")
def test_rollback_chat_runtime_previous_model_missing(
    mock_config_manager, mock_settings
):
    mock_settings.ACTIVE_LLM_SERVER = ""
    mock_config_manager.get_config.return_value = {}
    with patch(
        "venom_core.api.routes.academy_models.get_active_llm_runtime",
        return_value=SimpleNamespace(provider="unknown"),
    ):
        payload = academy_models._rollback_chat_runtime_after_adapter_deactivation(
            mgr=MagicMock()
        )
    assert payload["rolled_back"] is False
    assert payload["reason"] == "runtime_not_local"


@patch("venom_core.api.routes.academy_models._restart_vllm_runtime")
@patch("venom_core.api.routes.academy_models.compute_llm_config_hash")
@patch("venom_core.api.routes.academy_models.config_manager")
@patch("venom_core.config.SETTINGS")
def test_rollback_chat_runtime_switches_to_vllm_when_prev_model_exists(
    mock_settings,
    mock_config_manager,
    mock_hash,
    _mock_restart,
    tmp_path,
):
    mock_settings.ACTIVE_LLM_SERVER = "vllm"
    mock_settings.LLM_MODEL_NAME = ""
    mock_hash.return_value = "hash-rollback"
    mock_config_manager.get_config.return_value = {
        "PREVIOUS_MODEL_VLLM": "gemma-3-4b-it"
    }
    fallback_dir = tmp_path / "gemma-3-4b-it"
    fallback_dir.mkdir(parents=True)
    (fallback_dir / "chat_template.jinja").write_text("{{message}}", encoding="utf-8")

    with (
        patch(
            "venom_core.api.routes.academy_models.get_active_llm_runtime",
            return_value=SimpleNamespace(provider="vllm"),
        ),
        patch(
            "venom_core.api.routes.academy_models._resolve_local_runtime_model_path_by_name",
            return_value=str(fallback_dir),
        ),
    ):
        payload = academy_models._rollback_chat_runtime_after_adapter_deactivation(
            mgr=MagicMock()
        )

    assert payload["rolled_back"] is True
    assert payload["runtime_id"] == "vllm"
    assert payload["chat_model"] == "gemma-3-4b-it"
    updates = mock_config_manager.update_config.call_args[0][0]
    assert updates["VLLM_MODEL_PATH"] == str(fallback_dir)
    assert updates["LLM_CONFIG_HASH"] == "hash-rollback"


@patch("venom_core.api.routes.academy_models.compute_llm_config_hash")
@patch("venom_core.api.routes.academy_models.config_manager")
@patch("venom_core.config.SETTINGS")
def test_activate_adapter_ollama_deploy_does_not_fallback_to_last_model_config(
    mock_settings,
    mock_config_manager,
    mock_hash,
    tmp_path,
):
    mock_settings.ACADEMY_MODELS_DIR = str(tmp_path)
    mock_settings.ACTIVE_LLM_SERVER = "ollama"
    mock_settings.LLM_MODEL_NAME = ""
    mock_hash.return_value = "hash-ollama"
    mgr = MagicMock()

    adapter_dir = tmp_path / "ok-adapter" / "adapter"
    adapter_dir.mkdir(parents=True)
    (tmp_path / "ok-adapter" / "metadata.json").write_text(
        '{"metadata_version":2,"base_model":"phi3:latest","effective_base_model":"phi3:latest","created_at":"2026-03-07T12:00:00+00:00","source_flow":"training"}',
        encoding="utf-8",
    )
    mgr.activate_adapter.return_value = True
    mgr.create_ollama_modelfile.return_value = "venom-adapter-ok-adapter"
    mock_config_manager.get_config.return_value = {
        "LAST_MODEL_OLLAMA": "legacy:last",
        "LLM_MODEL_NAME": "legacy:last",
    }

    with (
        patch(
            "venom_core.api.routes.academy_models.get_active_llm_runtime",
            return_value=SimpleNamespace(provider="", model_name=""),
        ),
        patch(
            "venom_core.services.academy.adapter_runtime_service._ensure_ollama_adapter_gguf",
            return_value=adapter_dir / "Adapter-F16-LoRA.gguf",
        ),
    ):
        payload = academy_models.activate_adapter(
            mgr=mgr,
            adapter_id="ok-adapter",
            runtime_id="ollama",
            model_id="phi3:latest",
            deploy_to_chat_runtime=True,
        )

    assert payload["success"] is True
    mgr.create_ollama_modelfile.assert_called_once_with(
        version_id="ok-adapter",
        output_name="venom-adapter-ok-adapter",
        from_model="phi3:mini",
        use_experimental=False,
    )
    updates = mock_config_manager.update_config.call_args[0][0]
    assert "PREVIOUS_MODEL_OLLAMA" not in updates


@patch("venom_core.api.routes.academy_models.compute_llm_config_hash")
@patch("venom_core.api.routes.academy_models.config_manager")
@patch("venom_core.config.SETTINGS")
def test_activate_adapter_ollama_deploy_uses_experimental_for_local_training_base(
    mock_settings,
    mock_config_manager,
    mock_hash,
    tmp_path,
):
    mock_settings.ACADEMY_MODELS_DIR = str(tmp_path)
    mock_settings.ACTIVE_LLM_SERVER = "ollama"
    mock_settings.LLM_MODEL_NAME = ""
    mock_hash.return_value = "hash-ollama"
    mgr = MagicMock()

    local_training_base = tmp_path / "models" / "gemma-3-4b-it"
    local_training_base.mkdir(parents=True)
    (local_training_base / "config.json").write_text("{}", encoding="utf-8")
    (local_training_base / "model-00001-of-00001.safetensors").write_text(
        "dummy", encoding="utf-8"
    )

    adapter_dir = tmp_path / "ok-adapter" / "adapter"
    adapter_dir.mkdir(parents=True)
    (tmp_path / "ok-adapter" / "metadata.json").write_text(
        (
            '{"metadata_version":2,"base_model":"gemma-3-4b-it",'
            '"effective_base_model":"gemma-3-4b-it","created_at":"2026-03-07T12:00:00+00:00",'
            '"source_flow":"training","parameters":{"training_base_model":"%s"}}'
        )
        % str(local_training_base),
        encoding="utf-8",
    )
    mgr.activate_adapter.return_value = True
    mgr.create_ollama_modelfile.return_value = "venom-adapter-ok-adapter"
    mock_config_manager.get_config.return_value = {}

    with (
        patch(
            "venom_core.api.routes.academy_models.get_active_llm_runtime",
            return_value=SimpleNamespace(provider="", model_name=""),
        ),
        patch(
            "venom_core.services.academy.adapter_runtime_service._ensure_ollama_adapter_gguf",
            return_value=adapter_dir / "Adapter-F16-LoRA.gguf",
        ),
    ):
        payload = academy_models.activate_adapter(
            mgr=mgr,
            adapter_id="ok-adapter",
            runtime_id="ollama",
            model_id="gemma3:latest",
            deploy_to_chat_runtime=True,
        )

    assert payload["success"] is True
    mgr.create_ollama_modelfile.assert_called_once_with(
        version_id="ok-adapter",
        output_name="venom-adapter-ok-adapter",
        from_model=str(local_training_base),
        use_experimental=True,
    )


@patch("venom_core.api.routes.academy_models.compute_llm_config_hash")
@patch("venom_core.api.routes.academy_models.config_manager")
@patch("venom_core.config.SETTINGS")
def test_activate_adapter_ollama_deploy_prepares_gguf_before_ollama_create(
    mock_settings,
    mock_config_manager,
    mock_hash,
    tmp_path,
):
    mock_settings.ACADEMY_MODELS_DIR = str(tmp_path)
    mock_settings.ACTIVE_LLM_SERVER = "ollama"
    mock_settings.LLM_MODEL_NAME = ""
    mock_hash.return_value = "hash-ollama"
    mgr = MagicMock()

    adapter_dir = tmp_path / "ok-adapter" / "adapter"
    adapter_dir.mkdir(parents=True)
    (tmp_path / "ok-adapter" / "metadata.json").write_text(
        '{"metadata_version":2,"base_model":"phi3:latest","effective_base_model":"phi3:latest","created_at":"2026-03-07T12:00:00+00:00","source_flow":"training","parameters":{"training_base_model":"phi3:latest"}}',
        encoding="utf-8",
    )
    mgr.activate_adapter.return_value = True
    mgr.create_ollama_modelfile.return_value = "venom-adapter-ok-adapter"
    mock_config_manager.get_config.return_value = {}

    with (
        patch(
            "venom_core.api.routes.academy_models.get_active_llm_runtime",
            return_value=SimpleNamespace(provider="", model_name=""),
        ),
        patch(
            "venom_core.services.academy.adapter_runtime_service._ensure_ollama_adapter_gguf",
            return_value=adapter_dir / "Adapter-F16-LoRA.gguf",
        ) as mock_prepare,
    ):
        payload = academy_models.activate_adapter(
            mgr=mgr,
            adapter_id="ok-adapter",
            runtime_id="ollama",
            model_id="phi3:latest",
            deploy_to_chat_runtime=True,
        )

    assert payload["success"] is True
    mock_prepare.assert_called_once()
    assert mock_prepare.call_args.kwargs["adapter_dir"] == tmp_path / "ok-adapter"
    assert mock_prepare.call_args.kwargs["from_model"] == "phi3:mini"


def test_build_vllm_runtime_model_from_adapter_missing_adapter_path(tmp_path: Path):
    adapter_dir = tmp_path / "adapter-missing"
    adapter_dir.mkdir(parents=True)
    with pytest.raises(FileNotFoundError, match="Adapter path not found"):
        academy_models._build_vllm_runtime_model_from_adapter(
            adapter_dir=adapter_dir,
            base_model="unsloth/Phi-3-mini-4k-instruct",
        )


def test_build_vllm_runtime_model_from_adapter_happy_path(tmp_path: Path):
    adapter_dir = tmp_path / "adapter-ok"
    adapter_path = adapter_dir / "adapter"
    adapter_path.mkdir(parents=True)
    (adapter_path / "tokenizer.json").write_text("{}", encoding="utf-8")

    monkeypatch = pytest.MonkeyPatch()

    def _fake_merge_guard(*, env: dict[str, str], **_kwargs):
        payload = json.loads(env["VENOM_ADAPTER_MERGE_PAYLOAD"])
        out_dir = Path(payload["output_dir"])
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "config.json").write_text("{}", encoding="utf-8")
        (out_dir / "model.safetensors").write_text("x", encoding="utf-8")
        (out_dir / "tokenizer.json").write_text("{}", encoding="utf-8")
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(
        academy_models._runtime_service,
        "_run_subprocess_with_memory_guard",
        _fake_merge_guard,
    )
    try:
        runtime_dir = academy_models._build_vllm_runtime_model_from_adapter(
            adapter_dir=adapter_dir,
            base_model="unsloth/Phi-3-mini-4k-instruct",
        )
    finally:
        monkeypatch.undo()

    assert runtime_dir == adapter_dir / "runtime_vllm"
    runtime_payload = json.loads(
        (runtime_dir / "venom_runtime_vllm.json").read_text(encoding="utf-8")
    )
    assert runtime_payload["runtime"] == "vllm"
    assert runtime_payload["base_model"] == "unsloth/Phi-3-mini-4k-instruct"


@patch("venom_core.api.routes.academy_models.SETTINGS")
def test_deploy_adapter_to_vllm_runtime_rejects_empty_base_model(
    mock_settings, tmp_path: Path
):
    mock_settings.ACADEMY_MODELS_DIR = str(tmp_path)
    mock_settings.ACADEMY_DEFAULT_BASE_MODEL = ""
    adapter_dir = tmp_path / "adapter-empty"
    (adapter_dir / "adapter").mkdir(parents=True)
    (adapter_dir / "metadata.json").write_text(
        json.dumps(
            {
                "metadata_version": 2,
                "base_model": "",
                "effective_base_model": "",
                "created_at": "2026-03-07T12:00:00+00:00",
                "source_flow": "training",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="ADAPTER_METADATA_INCOMPLETE"):
        academy_models._deploy_adapter_to_vllm_runtime(
            adapter_id="adapter-empty",
        )
