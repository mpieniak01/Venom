#!/usr/bin/env python3
"""Install a declared hash-locked profile into an explicit isolated environment.

This bootstrap deliberately uses only the standard library. It never selects an
operator environment or starts services, and does not load project settings.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
GIB = 1024**3
# Reserve room for downloads, unpacking/builds and the installed environment.
# A caller may increase these floors, but cannot lower them to bypass the guard.
MINIMUM_FREE_GIB = {
    "light": 2,
    "ci": 3,
    "full": 24,
    "full-ci": 24,
    "vllm": 24,
    "onnx-gpu": 12,
    "academy": 24,
    "build": 1,
}


def positive_gib(value: str) -> float:
    try:
        result = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "Free-space threshold must be a number"
        ) from error
    if not math.isfinite(result) or result <= 0:
        raise argparse.ArgumentTypeError("Free-space threshold must be finite and > 0")
    return result


def required_storage_bytes(profile: str, minimum_free_gib: float | None) -> int:
    floor: float = MINIMUM_FREE_GIB[profile]
    if minimum_free_gib is not None:
        if not math.isfinite(minimum_free_gib) or minimum_free_gib <= 0:
            raise ValueError("Free-space threshold must be finite and > 0")
        floor = max(floor, minimum_free_gib)
    return math.ceil(floor * GIB)


def check_storage_space(
    target: Path, required_bytes: int, *, storage_root: Path | None = None
) -> None:
    locations = [target]
    if storage_root is not None:
        # Never silently fall back to the guest volume for a missing host mount.
        storage_root = storage_root.resolve(strict=True)
        if not storage_root.is_dir():
            raise ValueError("Storage root must be an existing directory")
        locations.append(storage_root)
    checked = set()
    for location in locations:
        probe = location
        while not probe.exists():
            probe = probe.parent
        if not probe.is_dir():
            raise ValueError(f"Storage location is not a directory: {probe}")
        if probe in checked:
            continue
        checked.add(probe)
        free = shutil.disk_usage(probe).free
        if free < required_bytes:
            raise OSError(
                f"Insufficient free space at {probe}: {free / GIB:.2f} GiB available; "
                f"{required_bytes / GIB:.2f} GiB required. Installation stopped."
            )


def source_build_environment() -> dict[str, str]:
    """Deterministic release build inputs, scoped to child processes only."""
    environment = dict(os.environ)
    environment.setdefault("SOURCE_DATE_EPOCH", "946684800")
    environment.setdefault("PYTHONHASHSEED", "0")
    # CPython's default -g embeds temporary source/venv paths in native wheels.
    # Keep caller optimization flags while omitting those debug-only sections.
    for name in ("CFLAGS", "CXXFLAGS"):
        flags = environment.get(name, "").strip()
        if not flags.endswith("-g0"):
            flags = f"{flags} -g0".strip()
        environment[name] = flags
    return environment


def run(
    command: list[str], *, capture: bool = False
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        env=source_build_environment(),
        check=True,
        text=True,
        capture_output=capture,
    )


def checked_lock(root: Path, policy: dict[str, Any], profile: str) -> Path:
    spec = policy["profiles"][profile]
    path = (root / spec["lock"]).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Lock must remain inside repository")
    receipt = json.loads(path.with_suffix(".json").read_text())
    if (
        receipt.get("profile") != profile
        or receipt.get("lock_sha256") != hashlib.sha256(path.read_bytes()).hexdigest()
    ):
        raise ValueError(f"Invalid hash-lock receipt for {profile}")
    return path


def refresh_bootstrap_tools(
    python: Path,
    build_lock: Path,
    profile_lock: Path,
    installed: dict[str, str],
    *,
    target: Path,
    required_bytes: int,
    storage_root: Path | None,
) -> None:
    """Refresh only existing bootstrap additions; preserve engine-owned pins."""
    profile_packages = {
        re.sub(r"[-_.]+", "-", match.group(1)).lower()
        for line in profile_lock.read_text().splitlines()
        if (match := re.match(r"^([A-Za-z0-9_.-]+)==", line))
    }
    entries = build_lock.read_text().splitlines()
    selected = []
    for index, line in enumerate(entries):
        match = re.match(r"^([A-Za-z0-9_.-]+)==([^ \\]+)", line)
        if match is None:
            continue
        name, version = match.groups()
        name = re.sub(r"[-_.]+", "-", name).lower()
        if (
            name in profile_packages
            or name not in installed
            or installed[name] == version
        ):
            continue
        digest = entries[index + 1].strip() if index + 1 < len(entries) else ""
        if not re.fullmatch(r"--hash=sha256:[a-f0-9]{64}", digest):
            raise ValueError("Bootstrap lock entry requires a valid artifact hash")
        selected.append(line + "\n    " + digest + "\n")
    if not selected:
        return
    check_storage_space(target, required_bytes, storage_root=storage_root)
    with tempfile.TemporaryDirectory(prefix="venom-bootstrap-tools-") as scratch:
        requirements = Path(scratch) / "requirements.txt"
        requirements.write_text(
            "--index-url https://pypi.org/simple\n" + "".join(selected)
        )
        run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--no-cache-dir",
                "--require-hashes",
                "--disable-pip-version-check",
                "--only-binary=:all:",
                "-r",
                str(requirements),
            ]
        )


def install_profile(
    root: Path,
    profile: str,
    target: Path,
    *,
    update: bool = False,
    storage_root: Path | None = None,
    minimum_free_gib: float | None = None,
) -> None:
    policy = json.loads((root / "config/dependency-profiles.json").read_text())
    if profile not in policy["profiles"]:
        raise ValueError(f"Unknown dependency profile: {profile}")
    actual = {
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
        "system": platform.system(),
        "machine": platform.machine(),
    }
    if actual != policy["platform"]:
        raise ValueError(
            f"Profile requires {policy['platform']}; bootstrap uses {actual}"
        )
    lock = checked_lock(root, policy, profile)
    build_lock = checked_lock(root, policy, "build")
    target = target.resolve()
    if target in {Path("/"), Path(sys.base_prefix).resolve(), root.resolve()}:
        raise ValueError(
            "Choose a separate target venv; system interpreter/repository root is forbidden"
        )
    spec = policy["profiles"][profile]
    if spec["kind"] == "component" and target == (root / ".venv").resolve():
        raise ValueError(
            "Engine/training components cannot replace the application .venv"
        )
    existed = target.exists()
    if existed and not update:
        raise ValueError(
            "Target already exists; use an explicit --update or choose a fresh path"
        )
    if existed and not (target / "pyvenv.cfg").is_file():
        raise ValueError("Existing target is not a virtual environment")
    required_bytes = required_storage_bytes(profile, minimum_free_gib)
    if not existed:
        check_storage_space(target, required_bytes, storage_root=storage_root)
        run([sys.executable, "-m", "venv", str(target)])
    python = target / "bin/python"
    if not python.is_file():
        raise ValueError("Target virtual environment has no Python executable")
    isolation = run(
        [
            str(python),
            "-c",
            "import sys; from pathlib import Path; print((Path(sys.prefix)/'pyvenv.cfg').read_text())",
        ],
        capture=True,
    )
    if "include-system-site-packages = false" not in isolation.stdout.lower():
        raise ValueError("System-site-packages is forbidden for profile installations")
    owner_path = target / ".venom-dependency-profile.json"
    if owner_path.exists():
        owner = json.loads(owner_path.read_text())
        previous = policy["profiles"].get(owner.get("profile"), {})
        if previous.get("kind") != spec["kind"]:
            raise ValueError(
                "Cannot change application/component ownership of an existing venv"
            )
    if existed:
        inventory = run(
            [
                str(python),
                "-m",
                "pip",
                "list",
                "--format=json",
                "--disable-pip-version-check",
            ],
            capture=True,
        )
        installed_versions = {
            re.sub(r"[-_.]+", "-", item["name"]).lower(): item["version"]
            for item in json.loads(inventory.stdout)
        }
        installed = set(installed_versions)
        if spec["kind"] == "application":
            forbidden = installed.intersection(policy["forbidden_application_packages"])
            if forbidden:
                raise ValueError(
                    f"Existing environment contains legacy/engine packages {sorted(forbidden)}; use a fresh application venv"
                )
        if profile == "onnx-gpu" and installed.intersection(
            {"onnxruntime", "onnxruntime-genai"}
        ):
            raise ValueError(
                "CPU/GPU ONNX namespaces cannot coexist; use a fresh worker venv"
            )
        allowed = {
            re.sub(r"[-_.]+", "-", match.group(1)).lower()
            for path in (lock, build_lock)
            for line in path.read_text().splitlines()
            if (match := re.match(r"^([A-Za-z0-9_.-]+)==", line))
        }
        unexpected = installed - allowed
        if unexpected:
            raise ValueError(
                f"Existing environment has packages outside the selected profile {sorted(unexpected)}; use a fresh venv rather than retaining another profile"
            )
    if existed:
        refresh_bootstrap_tools(
            python,
            build_lock,
            lock,
            installed_versions,
            target=target,
            required_bytes=required_bytes,
            storage_root=storage_root,
        )
    if not existed:
        # A mapped, hash-locked toolchain bootstraps packaging for the generator.
        # Do not downgrade build tools in an already-populated application.
        check_storage_space(target, required_bytes, storage_root=storage_root)
        run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--no-cache-dir",
                "--require-hashes",
                "--disable-pip-version-check",
                "-r",
                str(build_lock),
            ]
        )
    inspector = str(root / "scripts/dev/dependency_profiles.py")
    run([str(python), inspector, "generate", "--check", "--root", str(root)])
    run([str(python), inspector, "audit-locks", "--root", str(root)])
    command = [
        str(python),
        "-m",
        "pip",
        "install",
        "--no-cache-dir",
        "--require-hashes",
        "--disable-pip-version-check",
        "-r",
        str(lock),
    ]
    if profile in {"full", "full-ci"}:
        command.extend(
            ["--build-constraint", str(root / "requirements-build-constraints.txt")]
        )
    else:
        command.append("--only-binary=:all:")
    check_storage_space(target, required_bytes, storage_root=storage_root)
    run(command)
    run(
        [
            str(python),
            inspector,
            "verify",
            "--root",
            str(root),
            "--profile",
            profile,
            "--python",
            str(python),
        ]
    )
    owner_path.write_text(
        json.dumps(
            {
                "profile": profile,
                "lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest(),
                "source_build_environment": {
                    key: source_build_environment()[key]
                    for key in (
                        "SOURCE_DATE_EPOCH",
                        "PYTHONHASHSEED",
                        "CFLAGS",
                        "CXXFLAGS",
                    )
                },
            },
            indent=2,
        )
        + "\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--venv", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--update", action="store_true")
    parser.add_argument(
        "--storage-root",
        type=Path,
        help="Also check the physical backing volume (for WSL, e.g. /mnt/f)",
    )
    parser.add_argument(
        "--min-free-gib",
        type=positive_gib,
        help="Increase the profile's minimum free space in GiB (cannot lower it)",
    )
    args = parser.parse_args()
    try:
        install_profile(
            args.root,
            args.profile,
            args.venv,
            update=args.update,
            storage_root=args.storage_root,
            minimum_free_gib=args.min_free_gib,
        )
    except (ValueError, KeyError, OSError, subprocess.SubprocessError) as error:
        print(f"Profile installation ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
