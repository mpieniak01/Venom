"""Qualify minimal native remote control imports without loading a model."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from .paths import operator_path, python_path

CONTROL_REQUIREMENTS = "requirements-remote-training-control.txt"
CONTROL_IMPORTS = (
    "fastapi",
    "pydantic",
    "pydantic_settings",
    "venom_core.config",
    "venom_core.services.runtime_admission",
    "venom_core.services.granite_operator.cli",
    "venom_core.services.remote_training.worker",
    "venom_core.services.remote_training.verification",
)


def required_versions(code_root: Path) -> dict[str, str]:
    """Read the declared control layer, not application-wide optional dependencies."""
    path = code_root / CONTROL_REQUIREMENTS
    if path.is_symlink() or not path.is_file():
        raise ValueError("remote_training_control_requirements_missing")
    versions = {}
    for line in path.read_text().splitlines():
        match = re.fullmatch(r"([a-z0-9-]+)==([^\s\\]+)\s*\\?", line.strip())
        if match:
            versions[match[1]] = match[2]
    if not versions:
        raise ValueError("remote_training_control_requirements_empty")
    return versions


def inspect_control(code_root: Path) -> dict[str, Any]:
    """Check Python, pinned packages, actual control imports and pip consistency."""
    expected = required_versions(code_root)
    errors = []
    versions = {}
    python = platform.python_version()
    if python != "3.14.8":
        errors.append("python_version_mismatch")
    if platform.system() != "Linux" or platform.machine() not in {"x86_64", "amd64"}:
        errors.append("platform_mismatch")
    for name, desired in expected.items():
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            errors.append("missing_package:" + name)
            continue
        if versions[name] != desired:
            errors.append("package_version_mismatch:" + name)
    imports = {}
    for name in CONTROL_IMPORTS:
        try:
            importlib.import_module(name)
            imports[name] = "PASS"
        except Exception as error:
            # A settings validation error must not disclose environment values.
            imports[name] = type(error).__name__
            errors.append("import_failed:" + name)
    check = subprocess.run(
        [sys.executable, "-m", "pip", "check"],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if check.returncode:
        errors.append("pip_check_failed")
    return {
        "ok": not errors,
        "errors": errors,
        "python": python,
        "versions": versions,
        "imports": imports,
        "pip_check": {"exit_code": check.returncode},
        "model_loaded": False,
    }


def runtime_receipt(code_root: Path) -> dict[str, Any]:
    """Observe every locked installed version; lock bytes alone never qualify a host."""
    code_root = Path(code_root).resolve()
    from venom_core.services.granite_operator import contract

    if (
        code_root != Path(__file__).resolve().parents[3]
        or code_root != Path(contract.__file__).resolve().parents[3]
    ):
        return {"ok": False, "errors": ["code_root_mismatch"], "model_loaded": False}
    result = inspect_control(code_root)
    json_path = (
        code_root / "requirements/locks/granite-operator-training-linux-py314.json"
    )
    text_path = (
        code_root / "requirements/locks/granite-operator-training-linux-py314.txt"
    )
    if json_path.is_symlink() or text_path.is_symlink():
        raise ValueError("remote_training_lock_symlink")
    metadata = json.loads(json_path.read_text())
    actual_hash = hashlib.sha256(text_path.read_bytes()).hexdigest()
    if metadata.get("lock_sha256") != actual_hash:
        result["errors"].append("training_lock_checksum_mismatch")
    artifacts = metadata.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts:
        raise ValueError("remote_training_lock_artifacts_missing")
    for name, entry in artifacts.items():
        if not isinstance(entry, dict) or not isinstance(entry.get("version"), str):
            raise ValueError("remote_training_lock_artifact_invalid")
        try:
            actual = importlib.metadata.version(name)
            result["versions"][name] = actual
        except importlib.metadata.PackageNotFoundError:
            result["errors"].append("missing_training_package:" + name)
            continue
        if actual != entry["version"]:
            result["errors"].append("training_package_version_mismatch:" + name)
    result["training_lock_sha256"] = actual_hash
    result["control_requirements_sha256"] = hashlib.sha256(
        (code_root / CONTROL_REQUIREMENTS).read_bytes()
    ).hexdigest()
    result["ok"] = not result["errors"]
    return result


def check_control_environment(code_root: Path, python: Path) -> dict[str, Any]:
    """Probe the worker interpreter in a fresh process with no private env file."""
    python = python_path(python)
    code_root = operator_path(code_root)
    environment = {
        **os.environ,
        "PYTHONPATH": str(code_root.resolve()),
        "ENV_FILE": "/dev/null",
        "RUNTIME_ADMISSION_ENABLED": "false",
    }
    command = [
        str(python),
        "-m",
        "venom_core.services.remote_training.remote_env",
        "--probe",
        "--code-root",
        str(code_root.resolve()),
    ]
    try:
        process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=180,
            env=environment,
            check=False,
        )
        result = json.loads(process.stdout)
        if (
            not isinstance(result, dict)
            or process.returncode != 0
            or result.get("ok") is not True
        ):
            return {"ok": False, "errors": ["control_probe_failed"], "probe": result}
        return result
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        return {
            "ok": False,
            "errors": ["control_probe_failed"],
            "error_type": type(error).__name__,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--code-root", type=operator_path, required=True)
    parser.add_argument("--python", type=python_path, default=Path(sys.executable))
    parser.add_argument("--probe", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--output", type=operator_path)
    args = parser.parse_args()
    try:
        result = (
            runtime_receipt(args.code_root)
            if args.probe
            else check_control_environment(args.code_root, args.python)
        )
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        result = {
            "ok": False,
            "errors": ["control_preflight_failed"],
            "error_type": type(error).__name__,
        }
    raw = json.dumps(result, indent=2)
    if args.output:
        output = operator_path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w") as stream:
            json.dump(result, stream, indent=2)
            stream.write("\n")
    print(raw)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
