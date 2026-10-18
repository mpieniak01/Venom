"""Testy dla kontrolera serwerów LLM."""

from types import SimpleNamespace

import pytest

from venom_core.core.llm_server_controller import LlmServerController


def _dummy_settings(**kwargs):
    base = {
        "LLM_LOCAL_ENDPOINT": "http://localhost:8001/v1",
        "LLM_MODEL_NAME": "models/test",
        "VLLM_ENDPOINT": "http://localhost:8001/v1",
        "VLLM_START_COMMAND": "echo start",
        "VLLM_STOP_COMMAND": "",
        "VLLM_RESTART_COMMAND": "",
        "OLLAMA_START_COMMAND": "",
        "OLLAMA_STOP_COMMAND": "",
        "OLLAMA_RESTART_COMMAND": "",
        "GEMMA4_AUDIO_ENDPOINT": "http://localhost:8014/v1",
        "GEMMA4_AUDIO_HOST": "127.0.0.1",
        "GEMMA4_AUDIO_PORT": 8014,
        "GEMMA4_AUDIO_START_COMMAND": "",
        "GEMMA4_AUDIO_STOP_COMMAND": "",
        "GEMMA4_AUDIO_RESTART_COMMAND": "",
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
    assert "onnx" in names
    assert "multi_runtime" in names


def test_gemma4_audio_health_url_is_derived_from_stack_config():
    controller = LlmServerController(
        _dummy_settings(GEMMA4_AUDIO_HOST="gemma-host", GEMMA4_AUDIO_PORT=8123)
    )
    servers = {srv["name"]: srv for srv in controller.list_servers()}
    assert servers["multi_runtime"]["health_url"].endswith("/health")
    assert "gemma-host:8123" in servers["multi_runtime"]["health_url"]


@pytest.mark.asyncio
async def test_run_action_executes_command():
    controller = LlmServerController(
        _dummy_settings(VLLM_START_COMMAND="echo controller-test")
    )
    result = await controller.run_action("vllm", "start")
    assert result.ok
    assert "controller-test" in result.stdout


@pytest.mark.asyncio
async def test_run_action_unknown_action():
    controller = LlmServerController(_dummy_settings(VLLM_START_COMMAND=""))
    with pytest.raises(ValueError):
        await controller.run_action("vllm", "unknown")


@pytest.mark.parametrize("managed", [False, True])
@pytest.mark.parametrize(
    "policy,scheme", [("force_http", "http"), ("force_https", "https")]
)
def test_onnx_controller_describes_external_worker_truthfully(
    monkeypatch, managed, policy, scheme
):
    from venom_core.config import SETTINGS

    monkeypatch.setattr(SETTINGS, "URL_SCHEME_POLICY", policy)
    controller = LlmServerController(
        _dummy_settings(
            ONNX_LLM_ENDPOINT="http://127.0.0.1:8068/v1",
            ONNX_START_COMMAND="owned start" if managed else "",
            ONNX_STOP_COMMAND="owned stop" if managed else "",
            ONNX_RESTART_COMMAND="owned restart" if managed else "",
        )
    )
    server = next(s for s in controller.list_servers() if s["name"] == "onnx")
    assert server["endpoint"] == f"{scheme}://127.0.0.1:8068/v1"
    assert server["health_url"] == f"{scheme}://127.0.0.1:8068/health"
    assert all(value == managed for value in server["supports"].values())
    caps = controller.get_capabilities("onnx")
    assert (
        not caps.is_in_process
        and not caps.supports_cache_flush
        and not caps.supports_model_unload
    )
    assert caps.supports_health_wait
