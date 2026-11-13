"""Bootstrap the pinned Omni training interpreter on a prepared Linux VM."""

from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import zipfile
from pathlib import Path
from urllib.request import urlopen

WORKSPACE = Path("/workspace")
PYTHON_VERSION = "3.14.8"
MANAGED_PYTHON = (
    WORKSPACE / "data/uv-python/cpython-3.14.8-linux-x86_64-gnu/bin/python3.14"
)
VENV = WORKSPACE / "omni-venv"
LOCK = WORKSPACE / "venom/requirements/locks/granite-operator-training-linux-py314.txt"
UV_PIN = Path(__file__).with_name("omni_remote_uv.json")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonicalize_python_link(link: Path, managed: Path) -> None:
    """Keep the venv symlink inside the exact base path mounted by chroot."""
    if link.resolve(strict=True) != managed.resolve(strict=True):
        raise ValueError("venv interpreter differs from pinned Python")
    if link.is_symlink() and link.readlink() != managed:
        link.unlink()
        link.symlink_to(managed)


def _uv_binary(root: Path) -> Path:
    pin = json.loads(UV_PIN.read_text(encoding="utf-8"))
    root.mkdir(parents=True, exist_ok=True)
    binary_path = root / "uv"
    if (
        binary_path.is_file()
        and _sha256(binary_path.read_bytes()) == pin["binary_sha256"]
    ):
        return binary_path
    with urlopen(pin["url"], timeout=90) as response:
        wheel = response.read()
    if _sha256(wheel) != pin["wheel_sha256"]:
        raise ValueError("uv wheel digest mismatch")
    with zipfile.ZipFile(io.BytesIO(wheel)) as archive:
        binary = archive.read(pin["member"])
    if _sha256(binary) != pin["binary_sha256"]:
        raise ValueError("uv binary digest mismatch")
    temporary = binary_path.with_suffix(".part")
    temporary.write_bytes(binary)
    temporary.chmod(0o755)
    temporary.replace(binary_path)
    return binary_path


def main() -> None:
    root = WORKSPACE / "data/bootstrap"
    uv = _uv_binary(root)
    env = dict(
        os.environ,
        UV_CACHE_DIR=str(WORKSPACE / "data/uv-cache"),
        UV_PYTHON_INSTALL_DIR=str(WORKSPACE / "data/uv-python"),
    )
    subprocess.run(
        [str(uv), "--no-config", "python", "install", "--no-bin", PYTHON_VERSION],
        check=True,
        env=env,
    )
    subprocess.run(
        [
            str(uv),
            "--no-config",
            "venv",
            "--allow-existing",
            "--python",
            str(MANAGED_PYTHON),
            str(VENV),
        ],
        check=True,
        env=env,
    )
    canonicalize_python_link(VENV / "bin/python", MANAGED_PYTHON)
    subprocess.run(
        [
            str(uv),
            "--no-config",
            "pip",
            "sync",
            "--python",
            str(VENV / "bin/python"),
            "--require-hashes",
            "--only-binary",
            ":all:",
            str(LOCK),
        ],
        check=True,
        env=env,
    )
    subprocess.run(
        [
            str(VENV / "bin/python"),
            "-c",
            "import torch, transformers, peft, accelerate; print(torch.__version__, transformers.__version__, peft.__version__, accelerate.__version__)",
        ],
        check=True,
        env=env,
    )


if __name__ == "__main__":
    main()
