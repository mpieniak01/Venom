"""Unit tests for academy_models helper module."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from venom_core.api.routes import academy_models


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
        "Model is not in Academy trainable families list"
    )


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


@pytest.mark.asyncio
async def test_collect_local_trainable_models_filters_invalid_and_seen():
    mgr = MagicMock()
    mgr.list_local_models = AsyncMock(
        return_value=[
            {"name": "  "},
            {"name": "seen-model", "provider": "unsloth"},
            {"name": "local-good", "source": "local-cache"},
        ]
    )
    result = []
    seen = {"seen-model"}

    await academy_models.collect_local_trainable_models(
        mgr=mgr,
        default_model="local-good",
        result=result,
        seen=seen,
    )

    assert len(result) == 1
    assert result[0].model_id == "local-good"
    assert result[0].installed_local is True


def test_ensure_default_model_visible_adds_non_trainable_default():
    result = []
    seen: set[str] = set()
    academy_models.ensure_default_model_visible("gpt-4", result, seen)
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
    assert any(m.model_id == "custom-default-model" for m in models)
    assert any(m.provider == "unsloth" for m in models)


@pytest.mark.asyncio
@patch("venom_core.config.SETTINGS")
async def test_list_trainable_models_without_manager_uses_defaults(mock_settings):
    mock_settings.ACADEMY_DEFAULT_BASE_MODEL = "unsloth/Phi-3-mini-4k-instruct"
    models = await academy_models.list_trainable_models(mgr=None)
    assert models[0].recommended is True


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


def test_deactivate_adapter_variants():
    mgr = MagicMock()
    mgr.deactivate_adapter.return_value = False
    payload = academy_models.deactivate_adapter(mgr)
    assert payload["success"] is False

    mgr.deactivate_adapter.return_value = True
    payload = academy_models.deactivate_adapter(mgr)
    assert payload["success"] is True
