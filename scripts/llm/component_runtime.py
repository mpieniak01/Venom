"""Explicit isolated engine processes; never select or signal operator services."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

# The controller imports only the stdlib ownership helper, not application settings.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.dev.qualification_process import (
    OwnershipError,
    QualificationProcess,
    identity,
)

ROOT = Path(__file__).resolve().parents[2]


def component_environment(python: Path, state: Path) -> dict[str, str]:
    # An engine receives OS/locale/device selection, not the application's
    # credentials, Python hooks or arbitrary VLLM/Torch feature overrides.
    inherited = (
        "HOME",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "TZ",
        "TMPDIR",
        "TEMP",
        "TMP",
        "CUDA_VISIBLE_DEVICES",
        "CUDA_DEVICE_ORDER",
        "NVIDIA_VISIBLE_DEVICES",
        "NVIDIA_DRIVER_CAPABILITIES",
    )
    environment = {name: os.environ[name] for name in inherited if name in os.environ}
    environment["PATH"] = os.pathsep.join(
        map(
            str,
            [
                python.parent,
                Path("/usr/local/sbin"),
                Path("/usr/local/bin"),
                Path("/usr/sbin"),
                Path("/usr/bin"),
                Path("/sbin"),
                Path("/bin"),
            ],
        )
    )
    libraries = sorted(
        python.parent.parent.glob("lib/python*/site-packages/nvidia/*/lib")
    )
    # Do not silently load CUDA from an application's old venv via inherited PATH.
    environment["LD_LIBRARY_PATH"] = ":".join(
        map(str, [*libraries, Path("/usr/lib/wsl/lib")])
    )
    environment.update(
        {
            "HF_HUB_OFFLINE": "1",
            "HF_HUB_DISABLE_TELEMETRY": "1",
            "VLLM_NO_USAGE_STATS": "1",
            "DO_NOT_TRACK": "1",
            "XDG_CACHE_HOME": str(state / "xdg-cache"),
            "CUDA_CACHE_PATH": str(state / "cuda-cache"),
            "TORCH_EXTENSIONS_DIR": str(state / "torch-extensions"),
            "HF_HOME": str(state / "hf-cache"),
            "VLLM_CACHE_ROOT": str(state / "vllm-cache"),
            "TORCHINDUCTOR_CACHE_DIR": str(state / "torch-cache"),
            "TRITON_CACHE_DIR": str(state / "triton-cache"),
            "OMP_NUM_THREADS": "2",
            "TOKENIZERS_PARALLELISM": "false",
            "PYTHONUNBUFFERED": "1",
        }
    )
    return environment


def owned_identity(process: QualificationProcess) -> dict[str, Any] | None:
    if process.record.is_symlink():
        raise OwnershipError("experiment_record_is_symlink")
    if not process.record.exists():
        return None
    expected = json.loads(process.record.read_text())
    if expected.get("owner") != process.owner:
        raise OwnershipError("wrong_experiment_owner")
    try:
        observed = identity(expected["pid"])
    except (ProcessLookupError, OSError):
        return None
    if any(observed[key] != expected.get(key) for key in observed):
        raise OwnershipError("experiment_identity_changed")
    return observed


def owns_listener(pgid: int, port: int) -> bool:
    """A 200 response alone must not qualify another service on a raced port."""
    inodes = set()
    for table in (Path("/proc/net/tcp"), Path("/proc/net/tcp6")):
        for line in table.read_text().splitlines()[1:]:
            fields = line.split()
            if fields[3] == "0A" and int(fields[1].split(":")[1], 16) == port:
                inodes.add(fields[9])
    for path in Path("/proc").iterdir():
        if not path.name.isdigit():
            continue
        try:
            if os.getpgid(int(path.name)) != pgid:
                continue
            for descriptor in (path / "fd").iterdir():
                target = os.readlink(descriptor)
                if target.startswith("socket:[") and target[8:-1] in inodes:
                    return True
        except (OSError, ProcessLookupError):
            continue
    return False


def component_python(python: Path) -> Path:
    """Validate an explicit isolated interpreter without importing its runtime."""
    if (
        not python.is_absolute()
        or not python.is_file()
        or not os.access(python, os.X_OK)
    ):
        raise ValueError("absolute_component_python_required")
    configuration = python.parent.parent / "pyvenv.cfg"
    if (
        not configuration.is_file()
        or "include-system-site-packages = false"
        not in configuration.read_text().lower()
    ):
        raise ValueError("isolated_component_interpreter_required")
    if python.parent.parent.resolve() == (ROOT / ".venv").resolve():
        raise ValueError("application_venv_is_not_an_engine_component")
    return python


def daemon_identity(
    python: Path, pid: int, receipt: Path | None = None
) -> dict[str, Any]:
    """Match the legacy PID contract, with a start identity for new launches."""
    if pid <= 1 or pid == os.getpid():
        raise OwnershipError("daemon_invalid_pid")
    command = [str(python), "-m", "services.multi_runtime.main"]
    command_hash = hashlib.sha256(
        b"\0".join(os.fsencode(value) for value in command) + b"\0"
    ).hexdigest()
    observed = identity(pid)
    if (
        observed["cwd"] != str(ROOT.resolve())
        or observed["command_sha256"] != command_hash
    ):
        raise OwnershipError("daemon_command_or_checkout_mismatch")
    if receipt is not None:
        if receipt.is_symlink():
            raise OwnershipError("daemon_receipt_is_symlink")
        if receipt.exists() and json.loads(receipt.read_text()) != observed:
            raise OwnershipError("daemon_identity_changed")
    return observed


def daemon_preflight(argv: list[str]) -> dict[str, Any]:
    """Inspect interpreter metadata or an owned daemon; never load a model."""
    result = argparse.ArgumentParser(description=daemon_preflight.__doc__)
    result.add_argument("--python", required=True, type=Path)
    result.add_argument("--pid", type=int)
    result.add_argument("--identity-file", type=Path)
    args = result.parse_args(argv)
    python = component_python(args.python)
    if args.pid is not None:
        return daemon_identity(python, args.pid, args.identity_file)
    return {"python": str(python), "venv": str(python.parent.parent)}


def engine_command(args: argparse.Namespace) -> list[str]:
    python = component_python(Path(args.python))
    model = Path(args.model).resolve(strict=True)
    if args.engine == "onnx-gpu":
        if not (model / "genai_config.json").is_file():
            raise ValueError("onnx_genai_model_required")
        return [
            str(python),
            str(ROOT / "scripts/llm/onnx_gpu_bridge.py"),
            "--model",
            str(model),
            "--host",
            args.host,
            "--port",
            str(args.port),
            "--model-name",
            args.model_name or model.name,
        ]
    if not (model / "config.json").is_file() and model.suffix != ".gguf":
        raise ValueError("local_vllm_model_required")
    command = [
        str(python),
        "-m",
        "vllm.entrypoints.cli.main",
        "serve",
        str(model),
        "--host",
        args.host,
        "--port",
        str(args.port),
        "--served-model-name",
        args.model_name or model.name,
        "--gpu-memory-utilization",
        str(args.gpu_memory_utilization),
        "--max-num-batched-tokens",
        str(args.max_num_batched_tokens),
        "--max-model-len",
        str(args.max_model_len),
        "--max-num-seqs",
        "1",
    ]
    if args.enforce_eager:
        command.append("--enforce-eager")
    if args.text_only:
        command.extend(
            ["--limit-mm-per-prompt", '{"image":0,"video":0}', "--skip-mm-profiling"]
        )
    if args.chat_template:
        command.extend(["--chat-template", args.chat_template])
    return command


def control(args: argparse.Namespace) -> dict[str, Any]:
    state = Path(args.state_dir).resolve()
    process = QualificationProcess(state, args.owner or args.engine)
    manifest = state / f"{process.owner}.component.json"
    if args.action == "status":
        current = owned_identity(process)
        return {"status": "RUNNING" if current else "STOPPED", "identity": current}
    if args.action in {"stop", "restart"}:
        previous = owned_identity(process)
        stopped = process.stop(timeout=args.stop_timeout)
        result = {"status": "STOPPED", "stopped": stopped, "identity": previous}
        (state / f"{process.owner}.stop.json").write_text(
            json.dumps(result, indent=2) + "\n"
        )
        if args.action == "stop":
            return result
    if owned_identity(process) is not None:
        raise OwnershipError("component_already_running_use_explicit_restart")
    if process.record.exists():
        process.stop()  # Remove only a dead owned receipt, never stop by port/name.
    command = engine_command(args)
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind((args.host, args.port))
    environment = component_environment(Path(args.python), state)
    info = {
        "engine": args.engine,
        "owner": process.owner,
        "python": args.python,
        "model": str(Path(args.model).resolve()),
        "host": args.host,
        "port": args.port,
        "cwd": str(ROOT),
        "command_sha256": hashlib.sha256(json.dumps(command).encode()).hexdigest(),
        "status": "STARTING",
    }
    manifest.write_text(json.dumps(info, indent=2) + "\n")
    try:
        try:
            pid = process.start(command, cwd=ROOT, environment=environment)
        except ChildProcessError as error:
            raise RuntimeError("component_exited_before_readiness") from error
        info["identity"] = owned_identity(process)
        deadline = time.monotonic() + args.start_timeout
        host = "127.0.0.1" if args.host == "0.0.0.0" else args.host
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        while time.monotonic() < deadline:
            if owned_identity(process) is None:
                raise RuntimeError("component_exited_before_readiness")
            if owns_listener(pid, args.port):
                try:
                    with opener.open(
                        f"http://{host}:{args.port}/health", timeout=1
                    ) as response:
                        if response.status == 200:
                            info["status"] = "READY"
                            manifest.write_text(json.dumps(info, indent=2) + "\n")
                            return info
                except (OSError, urllib.error.URLError):
                    pass
            time.sleep(0.1)
        raise TimeoutError("component_readiness_timeout")
    except BaseException:
        process.stop(timeout=args.stop_timeout)
        info["status"] = "START_FAILED"
        manifest.write_text(json.dumps(info, indent=2) + "\n")
        raise


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("action", choices=["start", "stop", "restart", "status"])
    result.add_argument("--engine", choices=["onnx-gpu", "vllm"], required=True)
    result.add_argument("--python", required=True)
    result.add_argument("--model", required=True)
    result.add_argument("--model-name", default="")
    result.add_argument("--host", default="127.0.0.1")
    result.add_argument("--port", type=int, required=True)
    result.add_argument(
        "--state-dir", type=Path, default=ROOT / ".venom_runtime/components"
    )
    result.add_argument("--owner", default="")
    result.add_argument("--start-timeout", type=float, default=180)
    result.add_argument("--stop-timeout", type=float, default=15)
    result.add_argument("--gpu-memory-utilization", type=float, default=0.8)
    result.add_argument("--max-num-batched-tokens", type=int, default=512)
    result.add_argument("--max-model-len", type=int, default=512)
    result.add_argument("--enforce-eager", action="store_true")
    result.add_argument("--text-only", action="store_true")
    result.add_argument("--chat-template", default="")
    return result


def main() -> int:
    try:
        if sys.argv[1:2] == ["preflight"]:
            info = daemon_preflight(sys.argv[2:])
        else:
            info = control(parser().parse_args())
        print(json.dumps(info, indent=2))
        return 0
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"Component ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
