from unittest.mock import MagicMock, patch

import pytest

from tests.helpers.url_fixtures import LOCALHOST_8001_V1, LOCALHOST_11434_V1, http_url
from venom_core.services.config_manager import ConfigManager


@pytest.fixture
def mock_config_manager():
    with (
        patch(
            "venom_core.services.config_manager.ConfigManager._read_env_file"
        ) as mock_read,
        patch(
            "venom_core.services.config_manager.ConfigManager._write_env_file"
        ) as mock_write,
        patch(
            "venom_core.services.config_manager.ConfigManager._backup_env_file"
        ) as mock_backup,
    ):
        # Setup initial state
        mock_read.return_value = {
            "ACTIVE_LLM_SERVER": "vllm",
            "LLM_LOCAL_ENDPOINT": LOCALHOST_8001_V1,
            "VLLM_ENDPOINT": LOCALHOST_8001_V1,
        }
        mock_backup.return_value = MagicMock(name="backup_path")

        manager = ConfigManager()
        yield manager, mock_write


def test_auto_sync_ollama(mock_config_manager):
    manager, mock_write = mock_config_manager

    # Request switch to Ollama
    result = manager.update_config({"ACTIVE_LLM_SERVER": "ollama"})

    assert result["success"] is True
    # Verify write call checks for 11434
    args, _ = mock_write.call_args
    env_values = args[0]
    assert env_values["ACTIVE_LLM_SERVER"] == "ollama"
    assert env_values["LLM_LOCAL_ENDPOINT"] == LOCALHOST_11434_V1


def test_auto_sync_vllm(mock_config_manager):
    manager, mock_write = mock_config_manager

    # Request switch to vLLM
    result = manager.update_config({"ACTIVE_LLM_SERVER": "vllm"})

    assert result["success"] is True
    args, _ = mock_write.call_args
    env_values = args[0]
    assert env_values["ACTIVE_LLM_SERVER"] == "vllm"
    assert env_values["LLM_LOCAL_ENDPOINT"] == LOCALHOST_8001_V1


def test_explicit_override_respected(mock_config_manager):
    manager, mock_write = mock_config_manager

    # Switch to Ollama but FORCE a custom endpoint
    result = manager.update_config(
        {
            "ACTIVE_LLM_SERVER": "ollama",
            "LLM_LOCAL_ENDPOINT": http_url("custom-server", 1234, "/v1"),
        }
    )

    assert result["success"] is True
    args, _ = mock_write.call_args
    env_values = args[0]
    assert env_values["ACTIVE_LLM_SERVER"] == "ollama"
    assert env_values["LLM_LOCAL_ENDPOINT"] == http_url("custom-server", 1234, "/v1")
