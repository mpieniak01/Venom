"""Fail-closed namespace checks for the isolated GitHub-hosted E2E job.

The privileged workflow records host and isolated namespace identities in a
root-owned, non-writable proof directory. The unprivileged runner compares
those identities with its own namespace handles without accessing /proc/1.
"""

from __future__ import annotations

import os
import re
import stat
import sys
from pathlib import Path

NAMESPACE_TYPES = ("net", "mnt")


def valid_identity(value: str, name: str) -> bool:
    return re.fullmatch(rf"{name}:\[[0-9]+\]", value) is not None


def read_proof_identities(path: Path, name: str) -> tuple[str, str]:
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise RuntimeError(f"Unsafe namespace proof file: {path}")
        raw = os.read(fd, 129)
    finally:
        os.close(fd)
    if len(raw) > 128:
        raise RuntimeError(f"Oversized namespace proof: {path}")
    values = raw.decode("ascii").split()
    if len(values) != 2 or not all(valid_identity(value, name) for value in values):
        raise RuntimeError(f"Invalid namespace proof: {path}")
    return values[0], values[1]


def check_private_namespace(reference: Path, name: str) -> None:
    host, expected = read_proof_identities(reference, name)
    current = os.readlink(f"/proc/self/ns/{name}")
    if not valid_identity(current, name) or current != expected or current == host:
        raise RuntimeError(f"A verified private {name} namespace is required")


def verify_proof_directory(proof: str) -> Path:
    if not proof:
        raise RuntimeError("Missing namespace proof location")
    path = Path(proof)
    if not path.is_absolute() or path.resolve(strict=True) != path:
        raise RuntimeError(
            "Namespace proof location must be an absolute non-symlink path"
        )
    if path.parent != Path("/tmp") or not path.name.startswith("venom-github-e2e-ns."):
        raise RuntimeError(
            "Namespace proof must be in the expected root-owned /tmp directory"
        )
    parent = path.parent.lstat()
    if (
        not stat.S_ISDIR(parent.st_mode)
        or parent.st_uid != 0
        or not parent.st_mode & stat.S_ISVTX
    ):
        raise RuntimeError("Namespace proof parent must be root-owned and sticky")
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
        raise RuntimeError(
            "Namespace proof directory must be root-owned and non-writable"
        )
    return path


def main() -> None:
    proof = verify_proof_directory(os.environ.get("VENOM_E2E_NS_PROOF_DIR", ""))
    for name in NAMESPACE_TYPES:
        check_private_namespace(proof / name, name)


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, UnicodeError, ValueError) as exc:
        print(f"E2E namespace verification failed: {exc}", file=sys.stderr)
        sys.exit(1)
