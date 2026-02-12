"""Tests for config_manager service."""

from pathlib import Path

import pytest

from venom_core.services.config_manager import ConfigManager, ConfigUpdateRequest


@pytest.fixture
def config_manager(tmp_path: Path) -> ConfigManager:
    manager = ConfigManager()
    manager.project_root = tmp_path
    manager.env_file = tmp_path / ".env"
    manager.env_history_dir = tmp_path / "config" / "env-history"
    manager.env_history_dir.mkdir(parents=True, exist_ok=True)
    return manager


def test_get_config_masks_secrets(config_manager: ConfigManager):
    config_manager.env_file.write_text(
        "OPENAI_API_KEY=secret1234\nLLM_MODEL_NAME=model\n", encoding="utf-8"
    )

    masked = config_manager.get_config(mask_secrets=True)
    assert masked["OPENAI_API_KEY"] == "secr**1234"
    assert masked["LLM_MODEL_NAME"] == "model"

    unmasked = config_manager.get_config(mask_secrets=False)
    assert unmasked["OPENAI_API_KEY"] == "secret1234"


def test_get_effective_config_with_sources_uses_defaults(config_manager: ConfigManager):
    config_manager.env_file.write_text("AI_MODE=HYBRID\n", encoding="utf-8")

    config, sources = config_manager.get_effective_config_with_sources(
        mask_secrets=False
    )

    assert config["AI_MODE"] == "HYBRID"
    assert sources["AI_MODE"] == "env"
    assert config["ENABLE_ACADEMY"] in {"true", "false"}
    assert sources["ENABLE_ACADEMY"] == "default"


def test_update_config_writes_and_backs_up(config_manager: ConfigManager):
    config_manager.env_file.write_text(
        "# header\nLLM_MODEL_NAME=old\n", encoding="utf-8"
    )

    result = config_manager.update_config(
        {"LLM_MODEL_NAME": "new", "ENABLE_HIVE": "true"}
    )

    assert result["success"] is True
    assert "LLM_MODEL_NAME" in result["changed_keys"]
    env_contents = config_manager.env_file.read_text(encoding="utf-8")
    assert env_contents.count("LLM_MODEL_NAME=new") == 1
    assert any(config_manager.env_history_dir.iterdir())


def test_update_config_rejects_invalid_key(config_manager: ConfigManager):
    result = config_manager.update_config({"NOT_ALLOWED": "x"})
    assert result["success"] is False
    assert "Błąd walidacji" in result["message"]


def test_config_update_request_validates_ranges():
    with pytest.raises(ValueError) as exc:
        ConfigUpdateRequest(
            updates={
                "REDIS_PORT": "70000",
                "SHADOW_CONFIDENCE_THRESHOLD": "2.0",
                "ENABLE_HIVE": "maybe",
                "REDIS_DB": "-1",
                "AI_MODE": "WRONG",
                "LLM_SERVICE_TYPE": "bad",
            }
        )

    message = str(exc.value)
    assert "REDIS_PORT" in message
    assert "SHADOW_CONFIDENCE_THRESHOLD" in message
    assert "ENABLE_HIVE" in message
    assert "REDIS_DB" in message
    assert "AI_MODE" in message
    assert "LLM_SERVICE_TYPE" in message


def test_config_update_request_rejects_non_dict_updates():
    with pytest.raises(ValueError) as exc:
        ConfigUpdateRequest(updates=["bad", "payload"])  # type: ignore[arg-type]

    assert "musi być mapą klucz->wartość" in str(exc.value)


def test_cleanup_old_backups_removes_excess(config_manager: ConfigManager):
    for idx in range(3):
        (config_manager.env_history_dir / f".env-20250101-00000{idx}").write_text(
            "LLM_MODEL_NAME=backup\n", encoding="utf-8"
        )

    config_manager._cleanup_old_backups(max_keep=1)
    remaining = list(config_manager.env_history_dir.glob(".env-*"))
    assert len(remaining) == 1


def test_restore_backup_replaces_env(config_manager: ConfigManager):
    config_manager.env_file.write_text("LLM_MODEL_NAME=current\n", encoding="utf-8")
    backup_file = config_manager.env_history_dir / ".env-20250101-000000"
    backup_file.write_text("LLM_MODEL_NAME=restored\n", encoding="utf-8")

    result = config_manager.restore_backup(".env-20250101-000000")

    assert result["success"] is True
    assert "restart_required" in result
    restored = config_manager.env_file.read_text(encoding="utf-8").strip()
    assert restored == "LLM_MODEL_NAME=restored"


def test_restore_backup_rejects_invalid_name(config_manager: ConfigManager):
    result = config_manager.restore_backup("../.env")
    assert result["success"] is False
    assert "Nieprawidłowa nazwa" in result["message"]


def test_get_backup_list_returns_metadata(config_manager: ConfigManager):
    for idx in range(2):
        (config_manager.env_history_dir / f".env-20250101-00000{idx}").write_text(
            "LLM_MODEL_NAME=backup\n", encoding="utf-8"
        )

    backups = config_manager.get_backup_list(limit=5)
    assert len(backups) == 2
    assert backups[0]["filename"].startswith(".env-")
