"""Isolation and provider preservation for the canonical stack entry point."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import Mock

import pytest

from scripts.dev import stack_profile as stack


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / ".env.dev").write_text(
        "ENVIRONMENT_ROLE=dev\nACTIVE_LLM_SERVER=ollama\nLLM_MODEL_NAME=operator-model\n"
    )
    (tmp_path / ".env.preprod").write_text("ENVIRONMENT_ROLE=preprod\n")
    return tmp_path


@pytest.mark.parametrize("profile", ["full", "light"])
@pytest.mark.parametrize("role", ["dev", "preprod"])
def test_four_combinations_isolate_without_switching_model(root, profile, role):
    config = stack.resolve(root, {"PROFILE": profile, "ENVIRONMENT": role})
    assert config["PROFILE"] == config["VENOM_RUNTIME_PROFILE"] == profile
    assert config["START_WEB_MODE"] == "turbo"
    assert config["ENVIRONMENT_ROLE"] == role
    assert config["DB_SCHEMA"] == role
    if role == "dev":
        assert config["ACTIVE_LLM_SERVER"] == "ollama"
        assert config["LLM_MODEL_NAME"] == "operator-model"
    else:
        dev = stack.resolve(root, {})
        for key in (
            "MEMORY_ROOT",
            "STATE_FILE_PATH",
            "VENOM_LOG_DIR",
            "BACKEND_LOG",
            "WEB_LOG",
            "PID_FILE",
            "WEB_PID_FILE",
            "PORT",
            "WEB_PORT",
            "NEXT_DIST_DIR",
        ):
            assert config[key] != dev[key]
        assert config["ALLOW_DATA_MUTATION"] == "false"


def test_light_keeps_local_provider_and_audio_configuration(root):
    path = root / ".env.dev"
    path.write_text(
        path.read_text()
        + "ENABLE_AUDIO_INTERFACE=true\nAUDIO_DEVICE=cuda\nWHISPER_MODEL_SIZE=medium\n"
    )
    config = stack.resolve(root, {"PROFILE": "light"})
    assert config["ACTIVE_LLM_SERVER"] == "ollama"
    assert config["AUDIO_DEVICE"] == "cuda"
    assert config["WHISPER_MODEL_SIZE"] == "medium"
    assert config["VENOM_PAUSE_BACKGROUND_TASKS"] == "true"
    assert config["LLM_WARMUP_ON_STARTUP"] == "false"


@pytest.mark.parametrize(
    "key,value",
    [
        ("MEMORY_ROOT", "data/memory"),
        ("STATE_FILE_PATH", "data/memory/state_dump.json"),
        ("VENOM_LOG_DIR", "logs"),
        ("BACKEND_LOG", "logs/backend.log"),
        ("PID_FILE", ".venom.pid"),
        ("NEXT_DIST_DIR", ".next"),
        ("CACHE_NAMESPACE", "venom"),
        ("QUEUE_NAMESPACE", "venom"),
        ("DB_SCHEMA", "dev"),
        ("PORT", "8000"),
        ("WEB_PORT", "3000"),
        ("STORAGE_PREFIX", ""),
    ],
)
def test_preprod_rejects_resources_shared_with_dev(root, key, value):
    with pytest.raises(ValueError, match="overlaps|isolated"):
        stack.resolve(root, {"ENVIRONMENT": "preprod", key: value})


def test_preprod_rejects_symlink_to_dev_database(root):
    (root / "data/memory").mkdir(parents=True)
    (root / "other").symlink_to(root / "data/memory")
    with pytest.raises(ValueError, match="MEMORY_ROOT"):
        stack.resolve(root, {"ENVIRONMENT": "preprod", "MEMORY_ROOT": "other"})


@pytest.mark.parametrize(
    "extra",
    [
        {"ENVIRONMENT": "bad"},
        {"PROFILE": "unknown"},
        {"ENVIRONMENT": "preprod", "ENV_FILE": ".env.dev"},
        {"PORT": "3000"},
        {"ENVIRONMENT": "preprod", "START_MODE": "prod"},
    ],
)
def test_invalid_contract_is_rejected_before_start(root, extra):
    with pytest.raises(ValueError):
        stack.resolve(root, extra)


def test_missing_and_reserved_environment_do_not_start(root):
    with pytest.raises(ValueError, match="Missing configuration"):
        stack.resolve(root, {"ENVIRONMENT": "prod"})
    (root / ".env.prod").write_text("")
    with pytest.raises(ValueError, match="reserved"):
        stack.resolve(root, {"ENVIRONMENT": "prod"})
    config = stack.resolve(root, {"ENVIRONMENT": "prod", "PROD_START_CONFIRM": "yes"})
    assert config["START_MODE"] == "prod"


def test_full_preserves_custom_paths_and_secrets_are_not_printed(root):
    config = stack.resolve(
        root,
        {
            "OPENROUTER_API_KEY": "private",
            "MEMORY_ROOT": "custom",
            "PORT": "8800",
            "WEB_PORT": "3300",
        },
    )
    assert config["MEMORY_ROOT"] == str(root / "custom")
    assert config["PORT"] == "8800"
    assert "private" not in str(stack.public_plan(config))


def test_profile_switch_does_not_create_another_database(root):
    for role in ("dev", "preprod"):
        full = stack.resolve(root, {"ENVIRONMENT": role, "PROFILE": "full"})
        light = stack.resolve(root, {"ENVIRONMENT": role, "PROFILE": "light"})
        for key in stack.PATH_DEFAULTS:
            assert full[key] == light[key]


def test_no_profile_can_disable_preprod_readonly(root):
    config = stack.resolve(
        root, {"ENVIRONMENT": "preprod", "ALLOW_DATA_MUTATION": "true"}
    )
    assert config["ALLOW_DATA_MUTATION"] == "false"


def test_stop_validates_all_owners_before_signalling(root, monkeypatch):
    config = stack.resolve(root, {})
    owner = Mock(side_effect=[123, ValueError("other environment")])
    monkeypatch.setattr(stack, "owned_pid", owner)
    kill = Mock()
    monkeypatch.setattr(os, "kill", kill)
    with pytest.raises(ValueError, match="other environment"):
        stack.stop(root, config)
    kill.assert_not_called()


def test_stale_pid_file_has_no_live_owner(root):
    config = stack.resolve(root, {})
    Path(config["PID_FILE"]).write_text("99999999")
    assert stack.owned_pid(root, config, "PID_FILE") is None
    stack.stop(root, config)
    assert not Path(config["PID_FILE"]).exists()
