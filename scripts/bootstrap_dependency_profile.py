#!/usr/bin/env python3
"""Install a declared hash-locked profile into an explicit isolated environment.

This bootstrap deliberately uses only the standard library. It never selects an
operator environment or starts services, and does not load project settings.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def run(
    command: list[str], *, capture: bool = False
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=True, text=True, capture_output=capture)


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


def install_profile(
    root: Path, profile: str, target: Path, *, update: bool = False
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
    if not existed:
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
        installed = {
            re.sub(r"[-_.]+", "-", item["name"]).lower()
            for item in json.loads(inventory.stdout)
        }
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
    if not existed:
        # A mapped, hash-locked toolchain bootstraps packaging for the generator.
        # Do not downgrade build tools in an already-populated application.
        run(
            [
                str(python),
                "-m",
                "pip",
                "install",
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
    args = parser.parse_args()
    # Deterministic build inputs; callers retain control over the private cache.
    os.environ.setdefault("SOURCE_DATE_EPOCH", "946684800")
    os.environ.setdefault("PYTHONHASHSEED", "0")
    try:
        install_profile(args.root, args.profile, args.venv, update=args.update)
    except (ValueError, KeyError, OSError, subprocess.SubprocessError) as error:
        print(f"Profile installation ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
