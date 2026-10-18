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
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
GIB = 1024**3
# Reserve room for downloads, unpacking/builds and the installed environment.
# A caller may increase these floors, but cannot lower them to bypass the guard.
MINIMUM_FREE_GIB = {
    "light": 2,
    "ci": 3,
    "build": 1,
    "full": 16,
    "full-ci": 20,
    "multi-runtime-cuda": 12,
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


def checked_artifact_path(lock: Path, name: str, artifact: dict[str, Any]) -> str:
    """Bind source/build artifacts to the exact official-source hash-lock entry."""
    version, digest, url = (
        artifact.get("version"),
        artifact.get("sha256"),
        artifact.get("url"),
    )
    if (
        re.sub(r"[-_.]+", "-", name).lower() != name
        or not isinstance(version, str)
        or not isinstance(digest, str)
        or not re.fullmatch(r"[a-f0-9]{64}", digest)
        or not isinstance(url, str)
    ):
        raise ValueError(f"Invalid source/build artifact metadata: {name}")
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "files.pythonhosted.org"
        or parsed.username
        or parsed.password
    ):
        raise ValueError(f"Unapproved source/build artifact URL: {name}")
    lines = lock.read_text().splitlines()
    expected = [f"{name}=={version} " + "\\", f"    --hash=sha256:{digest}"]
    if not any(lines[index : index + 2] == expected for index in range(len(lines))):
        raise ValueError(f"Source/build artifact does not match hash-lock: {name}")
    return parsed.path


def check_source_build_toolchain(
    policy: dict[str, Any], build_lock: Path, artifacts: dict[str, Any]
) -> None:
    """Reject stale build seeds before they can mutate an existing target."""
    declared = {}
    for line in policy.get("groups", {}).get("build", []):
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([^ ;]+)", line)
        if match is None:
            raise ValueError("Source build toolchain requires exact policy pins")
        name, version = match.groups()
        declared[re.sub(r"[-_.]+", "-", name).lower()] = version
    toolchain = json.loads(build_lock.with_suffix(".json").read_text()).get(
        "artifacts", {}
    )
    required = {"pip", "setuptools", "wheel", "packaging"}
    if set(toolchain) != required or set(declared) != required:
        raise ValueError("Source builds require the complete locked build toolchain")
    for name, artifact in toolchain.items():
        if artifact.get("version") != declared[name]:
            raise ValueError(
                f"Source build toolchain is stale relative to policy: {name}"
            )
        if not checked_artifact_path(build_lock, name, artifact).endswith(".whl"):
            raise ValueError(f"Source build toolchain must contain wheels: {name}")
        if name in artifacts and artifacts[name]["version"] != artifact["version"]:
            raise ValueError(f"Source build toolchain conflicts with profile: {name}")


def source_install_options(
    policy: dict[str, Any], lock: Path, build_lock: Path
) -> list[str]:
    """Permit only declared exact sdists, with a complete wheel-only build seed."""
    options = ["--only-binary=:all:"]
    artifacts = json.loads(lock.with_suffix(".json").read_text()).get("artifacts", {})
    allowed = policy.get("source_distributions", {})
    sources = []
    for name, artifact in artifacts.items():
        url = artifact.get("url", "")
        if isinstance(url, str) and urlsplit(url).path.endswith(".whl"):
            continue
        if name not in allowed or artifact.get("version") != allowed[name]:
            raise ValueError(f"Unapproved source distribution or version: {name}")
        path = checked_artifact_path(lock, name, artifact)
        if not path.endswith((".tar.gz", ".zip", ".tar.bz2", ".tar.xz")):
            raise ValueError(f"Unsupported source artifact format: {name}")
        sources.append(name)
    if not sources:
        return options
    check_source_build_toolchain(policy, build_lock, artifacts)
    if "evdev" in sources:
        print(
            "Approved evdev source build requires a C compiler and Linux input headers."
        )
    return options + [
        "--no-binary=" + ",".join(sorted(sources)),
        "--no-build-isolation",
    ]


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
        if profile in policy.get("deferred_profiles", {}):
            reason = policy["deferred_profiles"][profile]["reason"]
            raise ValueError(f"Dependency profile '{profile}' is deferred: {reason}")
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
    if (
        policy.get("python_target")
        and platform.python_version() != policy["python_target"]
    ):
        raise ValueError(
            f"Profile requires Python {policy['python_target']}; "
            f"bootstrap uses {platform.python_version()}"
        )
    lock = checked_lock(root, policy, profile)
    build_lock = checked_lock(root, policy, "build")
    install_options = source_install_options(policy, lock, build_lock)
    source_builds = "--no-build-isolation" in install_options
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
    if policy.get("python_target"):
        probe = run(
            [
                str(python),
                "-c",
                "import json,platform; print(json.dumps(dict(python=platform.python_version(), system=platform.system(), machine=platform.machine())))",
            ],
            capture=True,
        )
        expected = {
            "python": policy["python_target"],
            "system": policy["platform"]["system"],
            "machine": policy["platform"]["machine"],
        }
        if json.loads(probe.stdout) != expected:
            raise ValueError(
                "Target interpreter does not match the selected profile; use a fresh venv"
            )
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
    if existed and not source_builds:
        refresh_bootstrap_tools(
            python,
            build_lock,
            lock,
            installed_versions,
            target=target,
            required_bytes=required_bytes,
            storage_root=storage_root,
        )
    if not existed or source_builds:
        # Sources require this complete hash-locked seed even during --update.
        # Source preflight rejects any conflicting profile-owned tool pins.
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
                "--only-binary=:all:",
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
    command.extend(install_options)
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
