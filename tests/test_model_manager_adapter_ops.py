"""Unit tests for extracted ModelManager adapter ops helpers."""

from venom_core.core import model_manager_adapter_ops as adapter_ops
from venom_core.core.model_manager import ModelManager


class _DummyLogger:
    def info(self, msg, *args, **kwargs):  # pragma: no cover - trivial shim
        return None

    def warning(self, msg, *args, **kwargs):  # pragma: no cover - trivial shim
        return None

    def error(self, msg, *args, **kwargs):  # pragma: no cover - trivial shim
        return None


def test_adapter_state_roundtrip(tmp_path):
    state_path = tmp_path / "active_adapter.json"
    logger = _DummyLogger()

    adapter_ops.save_active_adapter_state(
        state_path=state_path,
        adapter_id="training_roundtrip",
        adapter_path="/tmp/path",
        base_model="base",
    )

    loaded = adapter_ops.load_active_adapter_state(state_path=state_path, logger=logger)
    assert loaded is not None
    assert loaded["adapter_id"] == "training_roundtrip"
    assert loaded["base_model"] == "base"

    adapter_ops.clear_active_adapter_state(state_path=state_path, logger=logger)
    assert not state_path.exists()


def test_restore_active_adapter_clears_missing_adapter_file(tmp_path):
    logger = _DummyLogger()
    models_dir = tmp_path / "models"
    manager = ModelManager(models_dir=str(models_dir))

    adapter_ops.save_active_adapter_state(
        state_path=manager.active_adapter_state_path,
        adapter_id="training_missing",
        adapter_path=str(models_dir / "training_missing" / "adapter"),
        base_model="academy-base",
    )

    restored = adapter_ops.restore_active_adapter(manager=manager, logger=logger)
    assert restored is False
    assert not manager.active_adapter_state_path.exists()


def test_activate_adapter_rejects_non_academy_path(tmp_path):
    logger = _DummyLogger()
    manager = ModelManager(models_dir=str(tmp_path / "models"))
    external_adapter = tmp_path / "external" / "adapter"
    external_adapter.mkdir(parents=True)

    success = adapter_ops.activate_adapter(
        manager=manager,
        adapter_id="training_001",
        adapter_path=str(external_adapter),
        base_model="academy-base",
        logger=logger,
    )

    assert success is False
    assert manager.active_version is None


def test_get_active_adapter_info_no_active_version(tmp_path):
    manager = ModelManager(models_dir=str(tmp_path / "models"))
    info = adapter_ops.get_active_adapter_info(manager=manager)
    assert info is None
