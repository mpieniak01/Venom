"""Prepare a native Granite SSH training component; default is a read-only plan."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path

MODEL = "ibm-granite/granite-4.2-3b"
REVISION = "4e9c275e232f10211ec88644d106a1f6a1b60e06"
PYTHON = "3.14.8"
MODEL_RECEIPT = "model-source.json"
METADATA = (
    "import json,sys; from pathlib import Path; "
    "from venom_core.services.granite_operator.contract import snapshot_metadata; "
    "print(json.dumps(snapshot_metadata(Path(sys.argv[1]))))"
)
LOCK = "requirements/locks/granite-operator-training-linux-py314.txt"
CONTROL = "requirements-remote-training-control.txt"
DOWNLOAD = (
    "from huggingface_hub import snapshot_download; import sys; "
    "snapshot_download(repo_id=sys.argv[1],revision=sys.argv[2],local_dir=sys.argv[3],"
    "allow_patterns=['*.json','*.safetensors','*.jinja','*.model','*.txt'])"
)


def data_path(value):
    path = Path(value).expanduser().absolute()
    if any(ord(c) < 32 for c in str(value)) or ".." in path.parts:
        raise ValueError("host_path_invalid")
    forbidden = {".ssh", ".aws", ".git", ".codex", "secrets", "credentials"}
    if any(p.lower() in forbidden or p.lower().startswith(".env") for p in path.parts):
        raise ValueError("host_path_sensitive")
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("host_path_symlink")
    roots = (
        Path.home(),
        Path.cwd(),
        Path("/workspace"),
        Path("/models"),
        Path("/mnt"),
        Path("/opt"),
        Path("/srv"),
        Path("/tmp"),
    )
    if not any(len(root.parts) > 1 and path.is_relative_to(root) for root in roots):
        raise ValueError("host_path_outside_roots")
    return path


def executable(value):
    path = Path(value).expanduser().absolute()
    if not path.is_file() or not os.access(path, os.X_OK):
        raise ValueError("host_executable_missing")
    if any(ord(c) < 32 for c in str(path)):
        raise ValueError("host_executable_invalid")
    return path


def parser():
    value = argparse.ArgumentParser(description=__doc__)
    runtime = value.add_mutually_exclusive_group(required=True)
    runtime.add_argument("--python", type=executable, help="Existing Python 3.14.8")
    runtime.add_argument(
        "--uv",
        type=executable,
        help="Existing operator-installed uv; installs managed Python 3.14.8 on apply",
    )
    value.add_argument("--code-root", type=data_path, required=True)
    value.add_argument(
        "--commit", required=True, help="Exact reviewed 40-character Git commit"
    )
    value.add_argument(
        "--venv", type=data_path, default=Path("/workspace/training-venv")
    )
    value.add_argument(
        "--snapshot", type=data_path, default=Path("/workspace/models") / REVISION
    )
    value.add_argument(
        "--root", type=data_path, default=Path("/workspace/data/remote-training")
    )
    value.add_argument(
        "--admission-db",
        type=data_path,
        default=Path("/workspace/data/runtime-admission.sqlite3"),
    )
    value.add_argument(
        "--offline-model",
        action="store_true",
        help="Use existing snapshot; never contact Hugging Face",
    )
    value.add_argument(
        "--apply",
        action="store_true",
        help="Install component and download pinned model; never starts training",
    )
    return value


def validate(args):
    if not re.fullmatch(r"[0-9a-f]{40}", args.commit):
        raise ValueError("host_commit_invalid")
    if args.snapshot.name != REVISION:
        raise ValueError("host_snapshot_revision_mismatch")
    paths = [args.code_root, args.venv, args.snapshot, args.root]
    for index, path in enumerate(paths):
        data_path(path)
        if any(
            path.is_relative_to(other) or other.is_relative_to(path)
            for other in paths[index + 1 :]
        ):
            raise ValueError("host_component_paths_overlap")
    for name in (LOCK, CONTROL, "venom_core/services/remote_training/remote.py"):
        if not (args.code_root / name).is_file():
            raise ValueError("host_source_missing")
    if args.python and not re.fullmatch(
        r"python(?:3(?:[.]14(?:[.]8)?)?)?", args.python.name
    ):
        raise ValueError("host_python_executable_invalid")
    if args.uv and args.uv.name != "uv":
        raise ValueError("host_uv_executable_invalid")


def plan(args):
    validate(args)
    python = str(args.venv / "bin/python")
    return {
        "apply": args.apply,
        "code_root": str(args.code_root),
        "commit": args.commit,
        "python_version": PYTHON,
        "runtime": str(args.python or args.uv),
        "install_managed_python": bool(args.uv),
        "venv": str(args.venv),
        "requirements": [LOCK, CONTROL],
        "model": MODEL,
        "revision": REVISION,
        "snapshot": str(args.snapshot),
        "download_model": not args.offline_model,
        "root": str(args.root),
        "remote_python": str(args.root / "rpc-python"),
        "worker_python": python,
        "gpu_qualified": False,
        "training_started": False,
    }


def run(command, *, cwd, env=None, timeout=600):
    process = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if process.returncode:
        # Provider/pip output can contain credentials. Only stable errors escape.
        raise RuntimeError("host_preparation_command_failed")
    return process.stdout.strip()


def environment(code_root):
    result = dict(os.environ)
    for name in ("PYTHONHOME", "PYTHONSTARTUP", "PYTHONPATH"):
        result.pop(name, None)
    result.update(PYTHONPATH=str(code_root), ENV_FILE="/dev/null", PYTHONNOUSERSITE="1")
    return result


def payload_hashes(snapshot):
    files = {}
    for path in sorted(snapshot.rglob("*")):
        relative = path.relative_to(snapshot)
        if relative.parts[0] == ".cache" or str(relative) == MODEL_RECEIPT:
            continue
        if path.is_symlink():
            raise ValueError("host_snapshot_payload_symlink")
        if path.is_file():
            with path.open("rb") as stream:
                files[str(relative)] = hashlib.file_digest(stream, "sha256").hexdigest()
    return files


def snapshot_ready(snapshot, *, provenance=True):
    for name in ("config.json", "tokenizer.json", "tokenizer_config.json"):
        if not (snapshot / name).is_file() or not (snapshot / name).stat().st_size:
            raise ValueError("host_snapshot_incomplete")
    weights = list(snapshot.glob("*.safetensors"))
    if not weights or any(not p.is_file() or not p.stat().st_size for p in weights):
        raise ValueError("host_snapshot_weights_missing")
    index = snapshot / "model.safetensors.index.json"
    if index.is_file():
        shards = json.loads(index.read_text()).get("weight_map", {})
        if not isinstance(shards, dict) or not shards:
            raise ValueError("host_snapshot_index_invalid")
        for name in shards.values():
            if (
                not isinstance(name, str)
                or Path(name).name != name
                or not name.endswith(".safetensors")
                or not (snapshot / name).is_file()
            ):
                raise ValueError("host_snapshot_shard_missing")
    if provenance:
        receipt = snapshot / MODEL_RECEIPT
        if receipt.is_symlink() or not receipt.is_file():
            raise ValueError("host_snapshot_provenance_missing")
        value = json.loads(receipt.read_text())
        if (
            value.get("schema_version") != 1
            or value.get("model") != MODEL
            or value.get("revision") != REVISION
        ):
            raise ValueError("host_snapshot_provenance_mismatch")
        if value.get("files") != payload_hashes(snapshot):
            raise ValueError("host_snapshot_provenance_hash_mismatch")


def native_metadata(python, snapshot, code_root, env):
    value = json.loads(
        run([python, "-c", METADATA, str(snapshot)], cwd=code_root, env=env)
    )
    if (
        not isinstance(value, dict)
        or not value.get("config.json")
        or not value.get("tokenizer_config.json")
    ):
        raise ValueError("host_snapshot_metadata_invalid")
    return value


def prepare_snapshot(args, python, env):
    if not args.snapshot.exists():
        args.snapshot.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=".model-stage-", dir=args.snapshot.parent
        ) as temporary:
            stage = Path(temporary) / REVISION
            stage.mkdir(mode=0o700)
            run(
                [python, "-c", DOWNLOAD, MODEL, REVISION, str(stage)],
                cwd=args.code_root,
                env=env,
                timeout=7200,
            )
            snapshot_ready(stage, provenance=False)
            receipt = {
                "schema_version": 1,
                "model": MODEL,
                "revision": REVISION,
                "files": payload_hashes(stage),
                "native_snapshot_metadata": native_metadata(
                    python, stage, args.code_root, env
                ),
            }
            with (stage / MODEL_RECEIPT).open("w") as stream:
                json.dump(receipt, stream, indent=2)
            stage.rename(args.snapshot)
    snapshot_ready(args.snapshot)
    receipt = json.loads((args.snapshot / MODEL_RECEIPT).read_text())
    if receipt.get("native_snapshot_metadata") != native_metadata(
        python, args.snapshot, args.code_root, env
    ):
        raise ValueError("host_snapshot_native_metadata_mismatch")


@contextlib.contextmanager
def component_lock(root):
    import fcntl

    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = root / "gpu.lock"
    if path.is_symlink():
        raise ValueError("host_gpu_lock_symlink")
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("host_component_busy") from None
        yield
    finally:
        os.close(descriptor)


def apply(args):
    plan(args)
    if platform.system() != "Linux" or platform.machine() not in {"x86_64", "amd64"}:
        raise ValueError("host_platform_mismatch")
    with component_lock(args.root):
        return prepare_component(args)


def prepare_component(args):
    result = plan(args)
    env = environment(args.code_root)
    actual = run(["git", "rev-parse", "HEAD"], cwd=args.code_root)
    if actual != args.commit:
        raise ValueError("host_commit_mismatch")
    if run(
        ["git", "status", "--porcelain", "--untracked-files=no"], cwd=args.code_root
    ):
        raise ValueError("host_checkout_dirty")
    run(
        ["nvidia-smi", "--query-gpu=uuid,driver_version", "--format=csv,noheader"],
        cwd=args.code_root,
    )
    existing = args.venv.parent
    while not existing.exists():
        existing = existing.parent
    if shutil.disk_usage(existing).free < 10 * 1024**3:
        raise ValueError("host_insufficient_disk")
    runtime = args.python
    if args.uv:
        run(
            [str(args.uv), "python", "install", PYTHON],
            cwd=args.code_root,
            env=env,
            timeout=1800,
        )
        runtime = executable(
            run(
                [str(args.uv), "python", "find", "--managed-python", PYTHON],
                cwd=args.code_root,
                env=env,
            )
        )
    observed = run(
        [str(runtime), "-I", "-c", "import platform; print(platform.python_version())"],
        cwd=args.code_root,
        env=env,
    )
    if observed != PYTHON:
        raise ValueError("host_python_version_mismatch")
    python = str(args.venv / "bin/python")
    expected = {
        "worker_python": python,
        "snapshot": str(args.snapshot),
        "admission_db": str(args.admission_db),
        "code_root": str(args.code_root),
    }
    host_file = args.root / "host.json"
    if host_file.exists():
        if host_file.is_symlink():
            raise ValueError("host_config_symlink")
        host = json.loads(host_file.read_text())
        if (
            host.get("schema_version") != 1
            or not host.get("host_id")
            or any(host.get(key) != value for key, value in expected.items())
        ):
            raise ValueError("host_configuration_conflict")
    if args.offline_model or args.snapshot.exists():
        snapshot_ready(args.snapshot)
    if not args.venv.exists():
        args.venv.parent.mkdir(parents=True, exist_ok=True)
        run(
            [str(runtime), "-I", "-m", "venv", str(args.venv)],
            cwd=args.code_root,
            env=env,
        )
    elif not (args.venv / "pyvenv.cfg").is_file():
        raise ValueError("host_venv_invalid")
    python = str(args.venv / "bin/python")
    if (
        run(
            [python, "-I", "-c", "import platform; print(platform.python_version())"],
            cwd=args.code_root,
            env=env,
        )
        != PYTHON
    ):
        raise ValueError("host_venv_version_mismatch")
    run(
        [
            python,
            "-m",
            "pip",
            "install",
            "--require-hashes",
            "--only-binary=:all:",
            "-r",
            str(args.code_root / LOCK),
            "-r",
            str(args.code_root / CONTROL),
        ],
        cwd=args.code_root,
        env=env,
        timeout=3600,
    )
    run(
        [
            python,
            "-m",
            "venom_core.services.remote_training.remote_env",
            "--code-root",
            str(args.code_root),
        ],
        cwd=args.code_root,
        env=env,
    )
    prepare_snapshot(args, python, env)
    if not host_file.exists():
        run(
            [
                python,
                "-m",
                "venom_core.services.remote_training.cli",
                "host-init",
                "--root",
                str(args.root),
                "--worker-python",
                python,
                "--snapshot",
                str(args.snapshot),
                "--admission-db",
                str(args.admission_db),
                "--code-root",
                str(args.code_root),
            ],
            cwd=args.code_root,
            env=env,
        )
    # SSHTransport passes '-m ...remote'; wrapper supplies the reviewed module path.
    wrapper = args.root / "rpc-python"
    if wrapper.is_symlink():
        raise ValueError("host_rpc_wrapper_symlink")
    text = (
        "#!/bin/sh\nset -eu\nexport PYTHONPATH="
        + shlex.quote(str(args.code_root))
        + "\nexport ENV_FILE=/dev/null\nexport PYTHONNOUSERSITE=1\nexport HF_HUB_OFFLINE=1\nunset PYTHONHOME PYTHONSTARTUP\nexec "
        + shlex.quote(python)
        + ' "$@"\n'
    )
    args.root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with wrapper.open("w") as stream:
        stream.write(text)
    wrapper.chmod(0o700)
    result["prepared"] = True
    result["lock_sha256"] = hashlib.sha256(
        (args.code_root / LOCK).read_bytes()
    ).hexdigest()
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        result = apply(args) if args.apply else plan(args)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "host_preparation_failed",
                    "type": type(error).__name__,
                }
            )
        )
        return 1
    print(json.dumps({"ok": True, "result": result}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
