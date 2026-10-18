"""Isolated engine controller contracts using harmless real child processes."""

import hashlib
import json
import os
import shutil
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


def isolated_python(tmp_path):
    python = tmp_path / "component/bin/python"
    python.parent.mkdir(parents=True)
    python.symlink_to(sys.executable)
    (python.parent.parent / "pyvenv.cfg").write_text(
        "include-system-site-packages = false\n"
    )
    return python


def test_component_preflight_rejects_application_venv_alias(tmp_path, monkeypatch):
    python = isolated_python(tmp_path)
    monkeypatch.setattr(runtime, "ROOT", tmp_path)
    (tmp_path / ".venv").symlink_to(python.parent.parent, target_is_directory=True)
    with pytest.raises(ValueError, match="application_venv"):
        runtime.component_python(python)


@pytest.mark.parametrize(
    "configuration",
    [
        "include-system-site-packages = true\n",
        "# include-system-site-packages = false\ninclude-system-site-packages = true\n",
    ],
)
def test_component_preflight_rejects_system_site_packages(tmp_path, configuration):
    python = isolated_python(tmp_path)
    (python.parent.parent / "pyvenv.cfg").write_text(configuration)
    with pytest.raises(ValueError, match="isolated_component"):
        runtime.component_python(python)


@pytest.mark.parametrize("changed", [None, "cwd", "command_sha256", "start_ticks"])
def test_daemon_identity_requires_exact_command_and_receipt(
    tmp_path, monkeypatch, changed
):
    python = isolated_python(tmp_path)
    command = [str(python), "-m", "services.multi_runtime.main"]
    observed = {
        "pid": 23456,
        "pgid": 23456,
        "start_ticks": "123",
        "cwd": str(runtime.ROOT),
        "command_sha256": hashlib.sha256(
            b"\0".join(os.fsencode(value) for value in command) + b"\0"
        ).hexdigest(),
    }
    receipt = tmp_path / "identity.json"
    receipt.write_text(json.dumps(observed))
    current = dict(observed)
    if changed:
        current[changed] = "foreign"
    monkeypatch.setattr(runtime, "identity", lambda _pid: current)
    if changed:
        with pytest.raises(runtime.OwnershipError, match="daemon_"):
            runtime.daemon_identity(python, 23456, receipt)
    else:
        assert runtime.daemon_identity(python, 23456) == observed
        assert runtime.daemon_identity(python, 23456, receipt) == observed


def launcher_environment(tmp_path):
    return {
        "PATH": "/usr/bin:/bin",
        "ENV_FILE": str(tmp_path / "absent.env"),
        "VENOM_COMPONENTS_DIR": str(tmp_path / "components"),
        "GEMMA4_AUDIO_PID_PATH": str(tmp_path / "daemon.pid"),
        "GEMMA4_AUDIO_LOG_PATH": str(tmp_path / "daemon.log"),
    }


def run_daemon_launcher(action, environment, root=None):
    return subprocess.run(
        [
            "bash",
            str((root or runtime.ROOT) / "scripts/llm/multi_runtime_service.sh"),
            action,
        ],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )


def test_daemon_preflight_has_no_application_python_fallback(tmp_path):
    environment = launcher_environment(tmp_path)
    result = run_daemon_launcher("preflight", environment)
    assert result.returncode == 1
    assert "MULTI_RUNTIME_COMPONENT_PYTHON" in result.stderr
    assert str(tmp_path / "components/multi-runtime/bin/python") in result.stderr
    assert "isolated" in result.stderr.lower()
    assert not (tmp_path / "daemon.pid").exists()


def test_daemon_preflight_env_file_and_explicit_override(tmp_path):
    python = isolated_python(tmp_path)
    environment = launcher_environment(tmp_path)
    env_file = tmp_path / "daemon.env"
    env_file.write_text(f"MULTI_RUNTIME_COMPONENT_PYTHON={python}\n")
    environment["ENV_FILE"] = str(env_file)
    result = run_daemon_launcher("preflight", environment)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["python"] == str(python)
    environment["MULTI_RUNTIME_COMPONENT_PYTHON"] = str(tmp_path / "absent")
    result = run_daemon_launcher("preflight", environment)
    assert result.returncode == 1
    assert str(tmp_path / "absent") in result.stderr


@pytest.mark.parametrize("matching", [False, True])
def test_daemon_systemd_requires_opt_in_and_matching_interpreter(tmp_path, matching):
    python = isolated_python(tmp_path)
    environment = launcher_environment(tmp_path)
    environment["MULTI_RUNTIME_COMPONENT_PYTHON"] = str(python)
    binary = tmp_path / "bin"
    binary.mkdir()
    capture = tmp_path / "systemctl.txt"
    systemctl = binary / "systemctl"
    systemctl.write_text(
        '#!/bin/sh\nprintf "%s\n" "$*" >> "$CAPTURE"\n'
        'if [ "$1" = show ]; then printf "%s\n" "$EXEC_START"; fi\n'
    )
    systemctl.chmod(0o755)
    environment.update(
        PATH=f"{binary}:/usr/bin:/bin",
        CAPTURE=str(capture),
        EXEC_START=(
            f"{{ path={python if matching else runtime.ROOT / '.venv/bin/python'} ; "
            f"argv[]={python if matching else runtime.ROOT / '.venv/bin/python'} "
            "-m services.multi_runtime.main ; ignore_errors=no ; }"
        ),
    )
    result = run_daemon_launcher("preflight", environment)
    assert result.returncode == 0, result.stderr
    assert not capture.exists()
    environment["MULTI_RUNTIME_USE_SYSTEMD"] = "true"
    result = run_daemon_launcher("start", environment)
    assert result.returncode == (0 if matching else 1), result.stderr
    commands = capture.read_text().splitlines()
    assert commands[0].startswith("show ")
    assert any(line.startswith("start ") for line in commands) is matching
    assert not any("list-unit-files" in line for line in commands)


def test_daemon_stop_refuses_foreign_pid_without_signalling(tmp_path):
    python = isolated_python(tmp_path)
    environment = launcher_environment(tmp_path)
    environment["MULTI_RUNTIME_COMPONENT_PYTHON"] = str(python)
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        pid_file = tmp_path / "daemon.pid"
        pid_file.write_text(str(process.pid))
        result = run_daemon_launcher("stop", environment)
        assert result.returncode == 1
        assert "daemon_" in result.stderr
        assert process.poll() is None
        assert pid_file.read_text() == str(process.pid)
    finally:
        process.terminate()
        process.wait(timeout=5)


@pytest.mark.parametrize("device", ["cuda", "cpu"])
def test_daemon_launcher_preserves_flags_in_own_interpreter(tmp_path, device):
    # The fixture module only records its environment and sleeps; no model imports.
    root = tmp_path / "repo"
    for relative in [
        "scripts/llm/multi_runtime_service.sh",
        "scripts/llm/component_runtime.py",
        "scripts/dev/qualification_process.py",
        "scripts/lib/env_contract.sh",
    ]:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(runtime.ROOT / relative, target)
    module = root / "services/multi_runtime/main.py"
    module.parent.mkdir(parents=True)
    module.write_text(
        "import json, os, time\n"
        "from pathlib import Path\n"
        "Path(os.environ['CAPTURE']).write_text(json.dumps(dict(os.environ)))\n"
        "time.sleep(30)\n"
    )
    binary = tmp_path / "bin"
    binary.mkdir()
    curl = binary / "curl"
    curl.write_text(
        "#!/bin/sh\ncat <<JSON\n" + json.dumps({"status": "ok"}) + "\nJSON\n"
    )
    curl.chmod(0o755)
    python = isolated_python(tmp_path)
    capture = tmp_path / "environment.json"
    environment = launcher_environment(tmp_path)
    environment.update(
        PATH=f"{binary}:/usr/bin:/bin",
        MULTI_RUNTIME_COMPONENT_PYTHON=str(python),
        CAPTURE=str(capture),
        GEMMA4_AUDIO_DEVICE=device,
        GEMMA4_AUDIO_DEVICE_TARGET=device,
        GEMMA4_AUDIO_PRECISION="bfloat16",
        GEMMA4_AUDIO_PROBE_ENABLED="true",
        GEMMA4_AUDIO_CACHE_DIR="cache",
        VENOM_INTROSPECTION_PROBE_MAX_TOP_K="7",
        PYTHONPATH="/application/contamination",
        VIRTUAL_ENV="/application/venv",
    )
    try:
        result = run_daemon_launcher("start", environment, root)
        assert result.returncode == 0, result.stderr
        actual = json.loads(capture.read_text())
        assert actual["GEMMA4_AUDIO_DEVICE"] == device
        assert actual["GEMMA4_AUDIO_DEVICE_TARGET"] == device
        assert actual["GEMMA4_AUDIO_PRECISION"] == "bfloat16"
        assert actual["GEMMA4_AUDIO_PROBE_ENABLED"] == "true"
        assert actual["VENOM_INTROSPECTION_PROBE_MAX_TOP_K"] == "7"
        assert "PYTHONPATH" not in actual
        assert "VIRTUAL_ENV" not in actual
        assert (tmp_path / "daemon.pid.identity.json").is_file()
    finally:
        result = run_daemon_launcher("stop", environment, root)
        assert result.returncode == 0, result.stderr
