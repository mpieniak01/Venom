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


def test_restore_active_adapter_invalid_state_payload_clears_file(tmp_path):
    logger = _DummyLogger()
    manager = ModelManager(models_dir=str(tmp_path / "models"))
    manager.active_adapter_state_path.parent.mkdir(parents=True, exist_ok=True)
    manager.active_adapter_state_path.write_text(
        '{"adapter_id": "", "adapter_path": ""}', encoding="utf-8"
    )

    restored = adapter_ops.restore_active_adapter(manager=manager, logger=logger)
    assert restored is False
    assert not manager.active_adapter_state_path.exists()


def test_activate_adapter_existing_version_saves_state(tmp_path):
    logger = _DummyLogger()
    manager = ModelManager(models_dir=str(tmp_path / "models"))
    adapter_path = manager.models_dir / "training_existing" / "adapter"
    adapter_path.mkdir(parents=True, exist_ok=True)
    manager.register_version(
        version_id="training_existing",
        base_model="academy-base",
        adapter_path=str(adapter_path),
    )

    success = adapter_ops.activate_adapter(
        manager=manager,
        adapter_id="training_existing",
        adapter_path=str(adapter_path),
        base_model="academy-base",
        logger=logger,
    )
    assert success is True
    assert manager.active_adapter_state_path.exists()


def test_deactivate_adapter_clears_active_version_and_state(tmp_path):
    logger = _DummyLogger()
    manager = ModelManager(models_dir=str(tmp_path / "models"))
    adapter_path = manager.models_dir / "training_deactivate" / "adapter"
    adapter_path.mkdir(parents=True, exist_ok=True)
    manager.register_version(
        version_id="training_deactivate",
        base_model="academy-base",
        adapter_path=str(adapter_path),
    )
    manager.activate_version("training_deactivate")
    adapter_ops.save_active_adapter_state(
        state_path=manager.active_adapter_state_path,
        adapter_id="training_deactivate",
        adapter_path=str(adapter_path),
        base_model="academy-base",
    )

    success = adapter_ops.deactivate_adapter(manager=manager, logger=logger)
    assert success is True
    assert manager.active_version is None
    assert not manager.active_adapter_state_path.exists()


def test_adapter_ops_error_and_info_paths(tmp_path, monkeypatch):
    logger = _DummyLogger()
    manager = ModelManager(models_dir=str(tmp_path / "models"))

    # Invalid JSON should be handled gracefully.
    manager.active_adapter_state_path.parent.mkdir(parents=True, exist_ok=True)
    manager.active_adapter_state_path.write_text("{bad", encoding="utf-8")
    assert (
        adapter_ops.load_active_adapter_state(
            state_path=manager.active_adapter_state_path,
            logger=logger,
        )
        is None
    )

    # Existing version info path.
    adapter_path = manager.models_dir / "training_info" / "adapter"
    adapter_path.mkdir(parents=True, exist_ok=True)
    manager.register_version(
        version_id="training_info",
        base_model="academy-base",
        adapter_path=str(adapter_path),
    )
    manager.activate_version("training_info")
    info = adapter_ops.get_active_adapter_info(manager=manager)
    assert info is not None
    assert info["adapter_id"] == "training_info"
    assert info["is_active"] is True

    # clear_active_adapter_state should swallow unlink exceptions.
    from pathlib import Path

    original_unlink = Path.unlink
    monkeypatch.setattr(
        Path,
        "unlink",
        lambda self, **_kwargs: (_ for _ in ()).throw(RuntimeError("unlink-error"))
        if self == manager.active_adapter_state_path
        else original_unlink(self, **_kwargs),
    )
    adapter_ops.clear_active_adapter_state(
        state_path=manager.active_adapter_state_path,
        logger=logger,
    )
