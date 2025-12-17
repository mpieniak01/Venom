"""Testy dla kontrolera serwerów LLM."""

from types import SimpleNamespace

import pytest

from venom_core.core.llm_server_controller import LlmServerController


def _dummy_settings(**kwargs):
    base = {
        "LLM_LOCAL_ENDPOINT": "http://localhost:8001/v1",
        "LLM_MODEL_NAME": "models/test",
        "VLLM_START_COMMAND": "echo start",
        "VLLM_STOP_COMMAND": "",
        "VLLM_RESTART_COMMAND": "",
        "OLLAMA_START_COMMAND": "",
        "OLLAMA_STOP_COMMAND": "",
        "OLLAMA_RESTART_COMMAND": "",
        "LLM_SERVICE_TYPE": "local",
        "OPENAI_API_KEY": "",
        "ENABLE_SANDBOX": False,
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_list_servers_contains_known_entries():
    controller = LlmServerController(_dummy_settings())
    servers = controller.list_servers()
    names = {srv["name"] for srv in servers}
    assert "vllm" in names
    assert "ollama" in names


@pytest.mark.asyncio
async def test_run_action_executes_command():
    controller = LlmServerController(
        _dummy_settings(VLLM_START_COMMAND="echo controller-test")
    )
    result = await controller.run_action("vllm", "start")
    assert result.ok
    assert "controller-test" in result.stdout


@pytest.mark.asyncio
async def test_run_action_missing_command():
    controller = LlmServerController(_dummy_settings(VLLM_START_COMMAND=""))
    with pytest.raises(ValueError):
        await controller.run_action("vllm", "start")
