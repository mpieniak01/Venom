"""Trusted host setup and portable Granite identities, without model loading."""

from __future__ import annotations

import importlib.metadata
import json
import os
import platform
import socket
import subprocess
import uuid
from pathlib import Path

from venom_core.services.granite_operator.contract import (
    digest,
    file_digest,
    write_json,
)

PACKAGES = ("torch", "transformers", "peft", "bitsandbytes", "trl", "datasets")


def code_identity(code_root: Path) -> str:
    """Only the reviewed Granite engine defines model semantics."""
    package = code_root / "venom_core/services/granite_operator"
    return digest({p.name: file_digest(p) for p in sorted(package.glob("*.py"))})


def tokenizer_identity(snapshot: Path) -> tuple[str, str]:
    """Bind input rendering to native tokenizer files, not a model name alone."""
    names = (
        "tokenizer.json",
        "tokenizer_config.json",
        "special_tokens_map.json",
        "chat_template.jinja",
    )
    files = {
        name: file_digest(snapshot / name)
        for name in names
        if (snapshot / name).is_file()
    }
    if "tokenizer_config.json" not in files:
        raise ValueError("remote_training_tokenizer_missing")
    config = json.loads((snapshot / "tokenizer_config.json").read_text())
    template = (
        (snapshot / "chat_template.jinja").read_text()
        if (snapshot / "chat_template.jinja").exists()
        else config.get("chat_template")
    )
    if not template:
        raise ValueError("remote_training_template_missing")
    return digest(files), digest(template)


def initialize(
    root: Path,
    *,
    worker_python: Path,
    snapshot: Path,
    admission_db: Path,
    code_root: Path,
) -> dict:
    """Explicit operator configuration; cannot be changed by uploaded input."""
    root = root.resolve()
    path = root / "host.json"
    if path.exists():
        raise ValueError("remote_training_host_already_initialized")
    if not worker_python.is_file() or not os.access(worker_python, os.X_OK):
        raise ValueError("remote_training_interpreter_missing")
    if not snapshot.is_dir() or not (code_root / "venom_core").is_dir():
        raise ValueError("remote_training_host_paths_missing")
    value = {
        "schema_version": 1,
        "host_id": uuid.uuid4().hex,
        "worker_python": str(worker_python.absolute()),
        "snapshot": str(snapshot.resolve()),
        "admission_db": str(admission_db.absolute()),
        "code_root": str(code_root.resolve()),
    }
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    write_json(path, value)
    path.chmod(0o600)
    return {"configured": True, "host_id": value["host_id"], "gpu_qualified": False}


def load_host(root: Path) -> dict:
    path = root / "host.json"
    if path.is_symlink():
        raise ValueError("remote_training_host_symlink")
    host = json.loads(path.read_text())
    if host.get("schema_version") != 1 or not host.get("host_id"):
        raise ValueError("remote_training_host_invalid")
    return host


def binding(host: dict, identity: dict) -> str:
    """A proof cannot migrate to another host, boot, engine or dependency set."""
    return digest(
        {
            "host_id": host["host_id"],
            "host": socket.gethostname(),
            "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
            "portable": identity,
            "python": platform.python_version(),
            "gpu": subprocess.check_output(
                [
                    "nvidia-smi",
                    "--query-gpu=uuid,driver_version",
                    "--format=csv,noheader",
                ],
                text=True,
                timeout=10,
            ).strip(),
            "visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
            "coordinator": {
                p.name: file_digest(p)
                for p in sorted(
                    (
                        Path(host["code_root"]) / "venom_core/services/remote_training"
                    ).glob("*.py")
                )
            },
            "versions": {name: importlib.metadata.version(name) for name in PACKAGES},
            "code": code_identity(Path(host["code_root"])),
        }
    )


def dependencies_identity(code_root: Path) -> str:
    """Bind both the native model lock and minimal remote control closure."""
    return digest(
        {
            "training": file_digest(
                code_root
                / "requirements/locks/granite-operator-training-linux-py314.txt"
            ),
            "control": file_digest(
                code_root / "requirements-remote-training-control.txt"
            ),
        }
    )
