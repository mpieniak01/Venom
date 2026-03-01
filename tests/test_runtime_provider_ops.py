from __future__ import annotations

from types import SimpleNamespace

from venom_core.services import runtime_provider_ops as ops


class _SubprocessStub:
    DEVNULL = object()

    def __init__(self) -> None:
        self.popen_args = None
        self.run_args = None

    def Popen(self, args, **kwargs):  # noqa: N802
        self.popen_args = (args, kwargs)
        return SimpleNamespace(pid=1)

    def run(self, args, **kwargs):
        self.run_args = (args, kwargs)
        return SimpleNamespace(returncode=0, stderr="")


def test_start_ollama_uses_tokenized_command_arguments() -> None:
    subprocess_stub = _SubprocessStub()

    result = ops.start_ollama(
        command="ollama serve",
        get_service_status_fn=lambda _service: SimpleNamespace(status="running"),
        ollama_service_type="ollama",
        service_status_running="running",
        subprocess_module=subprocess_stub,
        time_module=SimpleNamespace(sleep=lambda _seconds: None),
        refresh_runtime_version_fn=lambda: None,
    )

    assert result["success"] is True
    assert subprocess_stub.popen_args is not None
    args, kwargs = subprocess_stub.popen_args
    assert args == ["ollama", "serve"]
    assert kwargs.get("start_new_session") is True


def test_start_ollama_returns_error_for_invalid_command_syntax() -> None:
    subprocess_stub = _SubprocessStub()

    result = ops.start_ollama(
        command='ollama "serve',
        get_service_status_fn=lambda _service: SimpleNamespace(status="running"),
        ollama_service_type="ollama",
        service_status_running="running",
        subprocess_module=subprocess_stub,
        time_module=SimpleNamespace(sleep=lambda _seconds: None),
        refresh_runtime_version_fn=lambda: None,
    )

    assert result["success"] is False
    assert "Błąd uruchamiania Ollama" in result["message"]


def test_stop_vllm_uses_tokenized_command_arguments() -> None:
    subprocess_stub = _SubprocessStub()

    result = ops.stop_vllm(
        command="pkill -f vllm",
        subprocess_module=subprocess_stub,
    )

    assert result["success"] is True
    assert subprocess_stub.run_args is not None
    args, kwargs = subprocess_stub.run_args
    assert args == ["pkill", "-f", "vllm"]
    assert kwargs["capture_output"] is True
    assert kwargs["text"] is True


def test_start_ollama_rejects_blank_command_after_tokenization() -> None:
    subprocess_stub = _SubprocessStub()

    result = ops.start_ollama(
        command="   ",
        get_service_status_fn=lambda _service: SimpleNamespace(status="running"),
        ollama_service_type="ollama",
        service_status_running="running",
        subprocess_module=subprocess_stub,
        time_module=SimpleNamespace(sleep=lambda _seconds: None),
        refresh_runtime_version_fn=lambda: None,
    )

    assert result["success"] is False
    assert "Brak skonfigurowanego OLLAMA_START_COMMAND" in result["message"]
    assert subprocess_stub.popen_args is None


def test_stop_vllm_rejects_blank_command_after_tokenization() -> None:
    subprocess_stub = _SubprocessStub()

    result = ops.stop_vllm(command="  ", subprocess_module=subprocess_stub)

    assert result["success"] is False
    assert "Brak skonfigurowanego VLLM_STOP_COMMAND" in result["message"]
    assert subprocess_stub.run_args is None
