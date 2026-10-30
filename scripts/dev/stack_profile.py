"""Resolve Full/Light and environment once, before importing the application."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Mapping

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from venom_core.services.profile_config import (  # noqa: E402
    PROFILE_DEFINITIONS,
    RuntimeProfile,
)

PATH_DEFAULTS = {
    "WORKSPACE_ROOT": "workspace",
    "MEMORY_ROOT": "data/memory",
    "PROMPTS_DIR": "data/prompts",
    "ACADEMY_TRAINING_DIR": "data/training",
    "ACADEMY_MODELS_DIR": "data/models",
    "DREAMING_OUTPUT_DIR": "data/synthetic_training",
    "CHRONOS_TIMELINES_DIR": "data/timelines",
    "VENOM_TRANSPORT_IDENTITY_FILE": "data/transport",
}
LEGACY = {
    "privacy": "light",
    "local": "light",
    "beast": "full",
    "extended": "full",
    "api": "light",
    "cloud": "light",
    "llm_off": "light",
}


def absolute(root: Path, raw: str) -> str:
    path = Path(raw).expanduser()
    return str((root / path).resolve() if not path.is_absolute() else path.resolve())


def file_values(path: Path) -> dict[str, str]:
    return {
        key: value for key, value in dotenv_values(path).items() if value is not None
    }


def resolve(root: Path, overrides: Mapping[str, str]) -> dict[str, str]:
    role = overrides.get("ENVIRONMENT", "dev").lower()
    if role not in {"dev", "preprod", "prod"}:
        raise ValueError("ENVIRONMENT must be dev|preprod|prod")
    env_file = Path(absolute(root, overrides.get("ENV_FILE", f".env.{role}")))
    if not env_file.is_file():
        raise ValueError(
            f"Missing configuration: {env_file}; create it explicitly from its example"
        )
    values = file_values(env_file)
    values.update(overrides)
    configured_role = values.get("ENVIRONMENT_ROLE", role)
    if configured_role != role:
        raise ValueError("ENV_FILE/ENVIRONMENT_ROLE does not match ENVIRONMENT")
    raw = values.get("PROFILE", values.get("VENOM_RUNTIME_PROFILE", "full")).lower()
    profile = LEGACY.get(raw, raw)
    if profile not in {"full", "light"}:
        raise ValueError("PROFILE must be full|light")
    if role == "prod" and values.get("PROD_START_CONFIRM") != "yes":
        raise ValueError(
            "prod is reserved and unused; explicit PROD_START_CONFIRM=yes required"
        )
    values.update(
        ENV_FILE=str(env_file),
        ENVIRONMENT=role,
        ENVIRONMENT_ROLE=role,
        PROFILE=profile,
        VENOM_RUNTIME_PROFILE=profile,
    )
    # Compatibility only: selection of a provider is no longer a third profile.
    if raw in {"api", "cloud", "llm_off"}:
        values["ACTIVE_LLM_SERVER"] = "none"
    for key, value in PROFILE_DEFINITIONS[
        RuntimeProfile(profile)
    ].env_overrides.items():
        values[key] = value
    suffix = "" if role == "dev" else role
    prefix = values.setdefault("STORAGE_PREFIX", suffix)
    if role != "dev" and (not prefix or prefix in {".", ".."} or "/" in prefix):
        raise ValueError("Non-dev STORAGE_PREFIX must be an isolated single namespace")
    for key in ("DB_SCHEMA", "CACHE_NAMESPACE", "QUEUE_NAMESPACE"):
        values.setdefault(key, role if role != "dev" or key == "DB_SCHEMA" else "venom")
    if role == "preprod":
        # Administrative backup/restore use their separate, explicit mutation lane.
        values["ALLOW_DATA_MUTATION"] = "false"
    for key, base in PATH_DEFAULTS.items():
        default = str(Path(base) / prefix) if prefix else base
        if key == "VENOM_TRANSPORT_IDENTITY_FILE":
            default += "/identity.json"
        values[key] = absolute(root, values.get(key, default))
    derived = {
        "STATE_FILE_PATH": str(Path(values["MEMORY_ROOT"]) / "state_dump.json"),
        "ACADEMY_USER_DATA_DIR": str(
            Path(values["ACADEMY_TRAINING_DIR"]) / "user_data"
        ),
        "ACADEMY_CONVERSION_OUTPUT_DIR": str(
            Path(values["ACADEMY_TRAINING_DIR"]) / "user_data/_converted_pool"
        ),
        "ASSETS_DIR": str(Path(values["WORKSPACE_ROOT"]) / "assets"),
        "SIMULATION_LOGS_DIR": str(Path(values["WORKSPACE_ROOT"]) / "simulation_logs"),
        "VENOM_LOG_DIR": "logs" if role == "dev" else f"logs/{role}",
        "PID_FILE": ".venom.pid" if role == "dev" else f".venom-{role}.pid",
        "WEB_PID_FILE": ".web-next.pid" if role == "dev" else f".web-next-{role}.pid",
    }
    for key, default in derived.items():
        values[key] = absolute(root, values.get(key, default))
    for key, name in (("BACKEND_LOG", "backend.log"), ("WEB_LOG", "web-next.log")):
        values[key] = absolute(
            root, values.get(key, str(Path(values["VENOM_LOG_DIR"]) / name))
        )
    values.setdefault("PORT", {"dev": "8000", "preprod": "8100", "prod": "8200"}[role])
    values.setdefault(
        "WEB_PORT", {"dev": "3000", "preprod": "3100", "prod": "3200"}[role]
    )
    values.setdefault("NEXT_DIST_DIR", ".next" if role == "dev" else f".next-{role}")
    values.setdefault("START_WEB_MODE", "turbo")
    values.setdefault("START_MODE", "prod" if role == "prod" else "dev")
    if role != "prod" and values["START_MODE"] != "dev":
        raise ValueError("dev/preprod use the current Turbo development stack")
    values.setdefault("API_PROXY_TARGET", f"http://127.0.0.1:{values['PORT']}")
    if role != "dev":
        dev = resolve(root, {"ENVIRONMENT": "dev"})
        for key in (*PATH_DEFAULTS, *derived, "BACKEND_LOG", "WEB_LOG"):
            candidate, original = Path(values[key]), Path(dev[key])
            if candidate == original or candidate in original.parents:
                raise ValueError(f"{key} overlaps dev resources")
        for key in (
            "DB_SCHEMA",
            "CACHE_NAMESPACE",
            "QUEUE_NAMESPACE",
            "PORT",
            "WEB_PORT",
            "NEXT_DIST_DIR",
        ):
            if not values[key] or values[key] == dev[key]:
                raise ValueError(f"{key} overlaps dev resources")
    if values["PORT"] == values["WEB_PORT"]:
        raise ValueError("API and UI ports must differ")
    return values


def public_plan(values: Mapping[str, str]) -> dict[str, str]:
    # Never print the merged environment or credentials.
    keys = (
        "PROFILE",
        "ENVIRONMENT",
        "ENV_FILE",
        "DB_SCHEMA",
        "STORAGE_PREFIX",
        "CACHE_NAMESPACE",
        "QUEUE_NAMESPACE",
        "PORT",
        "WEB_PORT",
        "NEXT_DIST_DIR",
        "ALLOW_DATA_MUTATION",
        *PATH_DEFAULTS,
        "STATE_FILE_PATH",
        "VENOM_LOG_DIR",
        "BACKEND_LOG",
        "WEB_LOG",
        "PID_FILE",
        "WEB_PID_FILE",
        "START_MODE",
        "START_WEB_MODE",
    )
    return {key: values[key] for key in keys if key in values}


def owned_pid(root: Path, values: Mapping[str, str], key: str) -> int | None:
    path = Path(values[key])
    if not path.exists():
        return None
    try:
        pid = int(path.read_text().strip())
        proc = Path("/proc") / str(pid)
        if not proc.exists():
            return None
        process_env = dict(
            item.split("=", 1)
            for item in (proc / "environ").read_bytes().decode().split("\0")
            if "=" in item
        )
        if (proc / "cwd").resolve() not in {
            root.resolve(),
            (root / "web-next").resolve(),
        }:
            raise ValueError("PID cwd belongs to a different instance")
        if process_env.get("ENVIRONMENT_ROLE", "dev") != values["ENVIRONMENT"]:
            raise ValueError("PID belongs to a different environment")
        if (
            process_env.get("ENV_FILE")
            and absolute(root, process_env["ENV_FILE"]) != values["ENV_FILE"]
        ):
            raise ValueError("PID uses a different ENV_FILE")
        return pid
    except (OSError, UnicodeError) as exc:
        raise ValueError("Cannot verify PID ownership") from exc


def stop(root: Path, values: Mapping[str, str]) -> None:
    # Validate all owners before stopping anything. No shared LLM/containers killed.
    owners = [
        (key, owned_pid(root, values, key)) for key in ("WEB_PID_FILE", "PID_FILE")
    ]
    for key, pid in owners:
        if pid is not None:
            # Process tree restricted to descendants of the verified owner.
            subprocess.run(["pkill", "-TERM", "-P", str(pid)], check=False)
            os.kill(pid, signal.SIGTERM)
            for _ in range(100):
                if not Path(f"/proc/{pid}").exists():
                    break
                time.sleep(0.1)
            else:
                raise ValueError(
                    f"PID {pid} did not stop; no global force-kill performed"
                )
        Path(values[key]).unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Full/Light in dev/preprod (prod reserved)"
    )
    parser.add_argument("action", choices=("start", "stop", "status", "plan"))
    args = parser.parse_args()
    try:
        values = resolve(ROOT, os.environ)
        if args.action == "plan":
            print(json.dumps(public_plan(values), indent=2))
        elif args.action == "stop":
            stop(ROOT, values)
        elif args.action == "status":
            for key in ("PID_FILE", "WEB_PID_FILE"):
                print(f"{key}: {owned_pid(ROOT, values, key) or 'stopped'}")
        else:
            for key in (
                "VENOM_LOG_DIR",
                "BACKEND_LOG",
                "WEB_LOG",
                "PID_FILE",
                "WEB_PID_FILE",
            ):
                Path(values[key]).parent.mkdir(parents=True, exist_ok=True)
            os.chdir(ROOT)
            os.execve(
                "/bin/bash",
                ["bash", str(ROOT / "scripts/dev/start_stack.sh")],
                {**values, "VENOM_STACK_RESOLVED": "1"},
            )
    except ValueError as exc:
        parser.exit(2, f"{exc}\n")


if __name__ == "__main__":
    main()
