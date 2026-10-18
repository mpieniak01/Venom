"""Isolated engine controller contracts using harmless real child processes."""

import json
import os
import socket
import subprocess
import sys

import pytest

from scripts.dev import qualification_process
from scripts.llm import component_runtime as runtime


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def arguments(tmp_path, action="start"):
    return runtime.parser().parse_args(
        [
            action,
            "--engine",
            "onnx-gpu",
            "--python",
            sys.executable,
            "--model",
            str(tmp_path),
            "--port",
            str(free_port()),
            "--state-dir",
            str(tmp_path / "state"),
            "--owner",
            "test-component",
            "--start-timeout",
            "5",
            "--stop-timeout",
            "2",
        ]
    )


def test_real_owned_http_child_starts_restarts_and_stops(tmp_path, monkeypatch):
    args = arguments(tmp_path)
    child = tmp_path / "harmless_http.py"
    child.write_text(
        "from http.server import BaseHTTPRequestHandler, HTTPServer\n"
        "class Handler(BaseHTTPRequestHandler):\n"
        " def do_GET(self):\n"
        "  self.send_response(200); self.end_headers(); self.wfile.write(b'ok')\n"
        " def log_message(self, *args): pass\n"
        f"HTTPServer(('127.0.0.1', {args.port}), Handler).serve_forever()\n"
    )
    monkeypatch.setattr(
        runtime, "engine_command", lambda args: [sys.executable, str(child)]
    )
    first = runtime.control(args)
    try:
        assert first["status"] == "READY"
        assert runtime.owns_listener(first["identity"]["pgid"], args.port)
        args.action = "status"
        assert runtime.control(args)["status"] == "RUNNING"
        args.action = "restart"
        second = runtime.control(args)
        assert second["identity"]["pid"] != first["identity"]["pid"]
        with pytest.raises((ProcessLookupError, FileNotFoundError)):
            runtime.identity(first["identity"]["pid"])
    finally:
        args.action = "stop"
        stopped = runtime.control(args)
    assert stopped["status"] == "STOPPED"
    assert not runtime.owns_listener(second["identity"]["pgid"], args.port)
    receipt = json.loads((args.state_dir / "test-component.stop.json").read_text())
    assert receipt["identity"]["pid"] == second["identity"]["pid"]


def test_busy_port_does_not_start_or_stop_foreign_listener(tmp_path, monkeypatch):
    args = arguments(tmp_path)
    monkeypatch.setattr(
        runtime, "engine_command", lambda args: [sys.executable, "-c", "pass"]
    )
    with socket.socket() as foreign:
        foreign.bind(("127.0.0.1", args.port))
        foreign.listen()
        with pytest.raises(OSError):
            runtime.control(args)
        assert foreign.getsockname()[1] == args.port
    assert not list(args.state_dir.glob("*.process.json"))


def test_environment_does_not_inherit_application_interpreter_or_cuda(
    tmp_path, monkeypatch
):
    python = tmp_path / "component/bin/python"
    library = tmp_path / "component/lib/python3.12/site-packages/nvidia/cublas/lib"
    library.mkdir(parents=True)
    monkeypatch.setenv("PYTHONPATH", "/operator/source")
    monkeypatch.setenv("LD_LIBRARY_PATH", "/operator/.venv/nvidia/lib")
    monkeypatch.setenv("VIRTUAL_ENV", "/operator/.venv")
    environment = runtime.component_environment(python, tmp_path)
    assert "PYTHONPATH" not in environment and "VIRTUAL_ENV" not in environment
    assert environment["LD_LIBRARY_PATH"] == f"{library}:/usr/lib/wsl/lib"
    assert environment["HF_HUB_OFFLINE"] == "1"
    assert "/operator" not in environment["LD_LIBRARY_PATH"]


def test_environment_allowlist_keeps_device_lease_but_not_credentials_or_flags(
    tmp_path, monkeypatch
):
    python = tmp_path / "component/bin/python"
    for name in (
        "OPENAI_API_KEY",
        "HF_TOKEN",
        "VLLM_ALLOW_LONG_MAX_MODEL_LEN",
        "TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD",
        "PYTHONSTARTUP",
        "LD_PRELOAD",
    ):
        monkeypatch.setenv(name, "must-not-reach-engine")
    monkeypatch.setenv("PATH", "/operator/.venv/bin:/operator/tools")
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "-1")
    monkeypatch.setenv("CUDA_DEVICE_ORDER", "PCI_BUS_ID")
    monkeypatch.setenv("LANG", "pl_PL.UTF-8")
    environment = runtime.component_environment(python, tmp_path)
    assert "must-not-reach-engine" not in environment.values()
    assert environment["CUDA_VISIBLE_DEVICES"] == "-1"
    assert environment["CUDA_DEVICE_ORDER"] == "PCI_BUS_ID"
    assert environment["LANG"] == "pl_PL.UTF-8"
    assert environment["PATH"].split(":")[0] == str(python.parent)
    assert "/operator" not in environment["PATH"]
    assert environment["VLLM_NO_USAGE_STATS"] == "1"
    assert environment["HF_HOME"] == str(tmp_path / "hf-cache")


def test_engine_command_uses_explicit_separate_interpreter(tmp_path):
    component = tmp_path / "component"
    (component / "bin").mkdir(parents=True)
    python = component / "bin/python"
    python.symlink_to(sys.executable)
    (component / "pyvenv.cfg").write_text("include-system-site-packages = false\n")
    model = tmp_path / "model"
    model.mkdir()
    (model / "genai_config.json").write_text("{}")
    args = arguments(tmp_path)
    args.python = str(python)
    args.model = str(model)
    assert runtime.engine_command(args)[:2] == [
        str(python),
        str(runtime.ROOT / "scripts/llm/onnx_gpu_bridge.py"),
    ]
    args.engine = "vllm"
    (model / "config.json").write_text("{}")
    command = runtime.engine_command(args)
    assert command[:4] == [str(python), "-m", "vllm.entrypoints.cli.main", "serve"]
    assert command[command.index("--max-num-seqs") + 1] == "1"


def test_noncomponent_interpreter_is_rejected(tmp_path):
    args = arguments(tmp_path)
    args.python = "/usr/bin/python3"
    with pytest.raises(ValueError, match="component_interpreter"):
        runtime.engine_command(args)


def test_failed_child_readiness_is_not_left_running(tmp_path, monkeypatch):
    args = arguments(tmp_path)
    monkeypatch.setattr(
        runtime,
        "engine_command",
        lambda args: [
            sys.executable,
            "-c",
            "raise RuntimeError('expected fixture failure')",
        ],
    )
    with pytest.raises(RuntimeError, match="exited_before_readiness"):
        runtime.control(args)
    assert not list(args.state_dir.glob("*.process.json"))
    manifest = json.loads(
        (args.state_dir / "test-component.component.json").read_text()
    )
    assert manifest["status"] == "START_FAILED"


@pytest.mark.parametrize("child_state", ["zombie", "reaped", "empty-command"])
def test_child_exit_before_identity_is_a_failed_start(
    tmp_path, monkeypatch, child_state
):
    """An early child exit has the same readiness contract in either /proc state."""
    args = arguments(tmp_path)
    process = runtime.QualificationProcess(args.state_dir, args.owner)
    monkeypatch.setattr(runtime, "QualificationProcess", lambda root, owner: process)
    monkeypatch.setattr(
        runtime,
        "engine_command",
        lambda args: [sys.executable, "-c", "raise SystemExit(7)"],
    )
    real_identity = qualification_process.identity

    def identity_after_exit(pid):
        assert process.process is not None
        if child_state == "reaped":
            process.process.wait(timeout=5)
        else:
            os.waitid(os.P_PID, pid, os.WEXITED | os.WNOWAIT)
            if child_state == "empty-command":
                raise qualification_process.OwnershipError("process_command_not_ready")
        return real_identity(pid)

    monkeypatch.setattr(qualification_process, "identity", identity_after_exit)
    with pytest.raises(RuntimeError, match="component_exited_before_readiness"):
        runtime.control(args)

    assert process.process is not None
    assert process.process.returncode == 7
    assert not list(args.state_dir.glob("*.process.json"))
    manifest = json.loads(
        (args.state_dir / "test-component.component.json").read_text()
    )
    assert manifest["status"] == "START_FAILED"


@pytest.mark.parametrize("opt_in", [False, True])
def test_vllm_launcher_systemd_is_explicit(tmp_path, opt_in):
    binary = tmp_path / "bin"
    binary.mkdir()
    capture = tmp_path / "command.txt"
    for name in ["python3", "systemctl"]:
        script = binary / name
        script.write_text('#!/bin/sh\nprintf "%s\n" "$0" "$@" > "$CAPTURE"\n')
        script.chmod(0o755)
    environment = {
        "PATH": f"{binary}:/usr/bin:/bin",
        "CAPTURE": str(capture),
        "ENV_FILE": str(tmp_path / "absent.env"),
        "VLLM_USE_SYSTEMD": str(opt_in).lower(),
    }
    result = subprocess.run(
        ["bash", str(runtime.ROOT / "scripts/llm/vllm_service.sh"), "status"],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    command = capture.read_text()
    assert ("systemctl" in command) is opt_in
    assert ("scripts.llm.component_runtime" in command) is not opt_in
    assert "list-unit-files" not in command
