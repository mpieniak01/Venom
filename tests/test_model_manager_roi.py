import pytest

from venom_core.core import model_manager as model_manager_module
from venom_core.core.model_manager import ModelManager


def test_register_activate_and_compare_versions(tmp_path):
    manager = ModelManager(models_dir=str(tmp_path))
    manager.register_version("v1", "base", performance_metrics={"acc": 0.8})
    v2 = manager.register_version("v2", "base", performance_metrics={"acc": 0.9})

    assert manager.activate_version("v2") is True
    assert manager.get_active_version() == v2
    comparison = manager.compare_versions("v1", "v2")
    assert comparison is not None
    assert comparison["metrics_diff"]["acc"]["diff"] == pytest.approx(0.1)


def test_is_lora_adapter_checks_required_files(tmp_path):
    manager = ModelManager(models_dir=str(tmp_path))
    adapter_dir = tmp_path / "adapter"
    adapter_dir.mkdir()
    (adapter_dir / "adapter_config.json").write_text("{}")
    (adapter_dir / "adapter_model.bin").write_bytes(b"data")
    assert manager._is_lora_adapter(str(adapter_dir)) is True

    (adapter_dir / "adapter_model.bin").unlink()
    assert manager._is_lora_adapter(str(adapter_dir)) is False


def test_check_storage_quota_uses_guard(monkeypatch, tmp_path):
    manager = ModelManager(models_dir=str(tmp_path))
    monkeypatch.setattr(model_manager_module, "MAX_STORAGE_GB", 1.0)
    monkeypatch.setattr(manager, "get_models_size_gb", lambda: 0.9)
    assert manager.check_storage_quota(0.2) is False
    assert manager.check_storage_quota(0.05) is True
