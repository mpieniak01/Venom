"""Resolve Full/Light and environment once, before importing the application."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import shlex
import socket
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Mapping
from urllib.parse import urlsplit

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
    "VENOM_RUNTIME_STATE_ROOT": ".venom_runtime",
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
    from dotenv import dotenv_values

    return {
        key: value for key, value in dotenv_values(path).items() if value is not None
    }


def http_target(value: str) -> tuple[str, int]:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "http"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or any(char.isspace() for char in value)
    ):
        raise ValueError(
            "API_PROXY_TARGET must be a plain HTTP origin without credentials"
        )
    host = parsed.hostname.lower()
    if host in {"localhost", "127.0.0.1"}:
        host = "127.0.0.1"
    port = parsed.port if parsed.port is not None else 80
    if port < 1:
        raise ValueError("API_PROXY_TARGET port must be between 1 and 65535")
    return host, port


def resolve(
    root: Path,
    overrides: Mapping[str, str],
    *,
    require_env_file: bool = True,
    allow_example: bool = False,
) -> dict[str, str]:
    role = overrides.get("ENVIRONMENT", "dev").lower()
    if role not in {"dev", "preprod", "prod"}:
        raise ValueError("ENVIRONMENT must be dev|preprod|prod")
    env_file = Path(absolute(root, overrides.get("ENV_FILE", f".env.{role}")))
    if not env_file.is_file() and allow_example and env_file == root / f".env.{role}":
        example = root / f".env.{role}.example"
        if example.is_file():
            env_file = example
    if env_file.is_file():
        values = file_values(env_file)
    elif require_env_file:
        raise ValueError(
            f"Missing configuration: {env_file}; create it explicitly from its example"
        )
    else:
        values = {}
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
        "GEMMA4_AUDIO_LOG_PATH": "logs/gemma4_audio_service.log"
        if role == "dev"
        else f"logs/{role}/gemma4_audio_service.log",
        "PID_FILE": ".venom.pid" if role == "dev" else f".venom-{role}.pid",
        "WEB_PID_FILE": ".web-next.pid" if role == "dev" else f".web-next-{role}.pid",
    }
    for key, default in derived.items():
        values[key] = absolute(root, values.get(key, default))
    for key, name in (("BACKEND_LOG", "backend.log"), ("WEB_LOG", "web-next.log")):
        values[key] = absolute(
            root, values.get(key, str(Path(values["VENOM_LOG_DIR"]) / name))
        )
    if role == "dev" and "PORT" not in values and values.get("API_PROXY_TARGET"):
        configured_proxy = urlsplit(values["API_PROXY_TARGET"])
        if (
            configured_proxy.hostname in {"127.0.0.1", "localhost"}
            and configured_proxy.port
        ):
            values["PORT"] = str(configured_proxy.port)
    values.setdefault("PORT", {"dev": "8000", "preprod": "8100", "prod": "8200"}[role])
    values.setdefault(
        "WEB_PORT", {"dev": "3000", "preprod": "3100", "prod": "3200"}[role]
    )
    values.setdefault("NEXT_DIST_DIR", ".next" if role == "dev" else f".next-{role}")
    values.setdefault("START_WEB_MODE", "turbo")
    values.setdefault("START_MODE", "prod" if role == "prod" else "dev")
    if role != "prod" and values["START_MODE"] != "dev":
        raise ValueError("dev/preprod use the current Turbo development stack")
    display = values.get("HOST_DISPLAY", "127.0.0.1")
    display = (
        f"[{display}]" if ":" in display and not display.startswith("[") else display
    )
    own_proxy = f"http://{display}:{values['PORT']}"
    values.setdefault("API_PROXY_TARGET", own_proxy)
    if http_target(values["API_PROXY_TARGET"]) != http_target(own_proxy):
        raise ValueError("API_PROXY_TARGET must point to this environment API")
    values["API_PROXY_TARGET"] = own_proxy
    # Browser traffic must use the streaming same-origin proxy, not .env.local.
    values["NEXT_PUBLIC_API_BASE"] = ""
    values["NEXT_PUBLIC_WS_BASE"] = ""
    values["NEXT_PUBLIC_ENVIRONMENT_ROLE"] = role
    if role != "dev":
        dev = resolve(root, {"ENVIRONMENT": "dev"}, require_env_file=False)
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
    from scripts.dev.stack_variant import apply_variant

    apply_variant(root, values, overrides)
    return values


def public_plan(values: Mapping[str, str]) -> dict[str, str]:
    # Never print the merged environment or credentials.
    keys = (
        "PROFILE",
        "VENOM_VARIANT",
        "API_APP",
        "WEB_DIR",
        "VENOM_UI_READY_PATH",
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


def process_stamp(pid: int) -> tuple[str, int]:
    proc = Path("/proc") / str(pid)
    stat = (proc / "stat").read_text().rsplit(")", 1)[1].split()
    return stat[19], proc.stat().st_uid


def record_pid(root: Path, values: Mapping[str, str], key: str) -> None:
    path = Path(values[key])
    pid = int(path.read_text().strip())
    stamp, uid = process_stamp(pid)
    record = dict(
        pid=pid,
        stamp=stamp,
        uid=uid,
        root=str(root.resolve()),
        role=values["ENVIRONMENT"],
        profile=values["PROFILE"],
        variant=values.get("VENOM_VARIANT", "venom"),
        env_file=values["ENV_FILE"],
        local_runtime=values.get("VENOM_STARTED_LOCAL_RUNTIME", "none"),
    )
    target = Path(str(path) + ".identity.json")
    target.write_text(json.dumps(record))
    target.chmod(0o600)
    registry = host_file(root, ".host-api-owners.json")
    entries = json.loads(registry.read_text()) if registry.exists() else []
    entries = [
        entry
        for entry in entries
        if entry.get("pid") != pid and running(entry.get("pid", 0))
    ]
    registry.write_text(json.dumps([*entries, record]))
    private_owner(root, registry)


def owned_pid(
    root: Path, values: Mapping[str, str], key: str, *, reuse: bool = False
) -> int | None:
    path = Path(values[key])
    if not path.exists():
        return None
    try:
        pid = int(path.read_text().strip())
        if not Path(f"/proc/{pid}").exists():
            return None
        identity = json.loads(Path(str(path) + ".identity.json").read_text())
        stamp, uid = process_stamp(pid)
        if key == "WEB_PID_FILE":
            nested = json.loads(identity.get("identity", "{}"))
            web_root = absolute(root, values.get("WEB_DIR", "web-next"))
            expected = dict(
                root=web_root,
                role=values["ENVIRONMENT"],
                dist=str(Path(web_root) / values["NEXT_DIST_DIR"]),
                port=int(values["WEB_PORT"]),
                host=values.get("WEB_HOST", "0.0.0.0"),
            )
            valid = (
                identity.get("pid") == pid
                and identity.get("ticks") == stamp
                and all(nested.get(k) == v for k, v in expected.items())
            )
        else:
            expected = dict(
                pid=pid,
                stamp=stamp,
                uid=uid,
                root=str(root.resolve()),
                role=values["ENVIRONMENT"],
                env_file=values["ENV_FILE"],
            )
            valid = all(identity.get(k) == v for k, v in expected.items())
            if identity.get("variant", "venom") != values.get("VENOM_VARIANT", "venom"):
                raise ValueError(
                    "Different application variant owns API; stop its owning variant first"
                )
            if reuse and identity.get("profile") != values["PROFILE"]:
                raise ValueError(
                    "Different profile already running; stop this environment before restart"
                )
        if not valid:
            raise ValueError("PID identity differs; refusing to reuse or stop")
        return pid
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Cannot verify PID ownership; no automatic adoption") from exc


def descendants(pid: int) -> list[int]:
    result = []
    children = Path(f"/proc/{pid}/task/{pid}/children")
    for child in children.read_text().split() if children.exists() else []:
        result.extend(descendants(int(child)))
        result.append(int(child))
    return result


def running(pid: int) -> bool:
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0] != "Z"
    except FileNotFoundError:
        return False


@dataclass(frozen=True)
class _StopReceipt:
    payload: bytes
    fingerprint: tuple[int, int, int, int, int]


def _stop_receipt(path: Path) -> _StopReceipt | None:
    def fingerprint(info: os.stat_result) -> tuple[int, int, int, int, int]:
        return (
            info.st_dev,
            info.st_ino,
            info.st_size,
            info.st_mtime_ns,
            info.st_ctime_ns,
        )

    try:
        with os.fdopen(
            os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb"
        ) as source:
            before = os.fstat(source.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise ValueError("Stop receipt must be a regular file")
            payload = source.read()
            after = os.fstat(source.fileno())
            if fingerprint(before) != fingerprint(after):
                raise ValueError("Stop receipt changed during snapshot")
            return _StopReceipt(payload, fingerprint(after))
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ValueError("Cannot verify stop receipt") from exc


def _assert_stop_receipts(
    receipts: tuple[tuple[Path, _StopReceipt | None], ...],
) -> None:
    for path, captured in receipts:
        if _stop_receipt(path) != captured:
            raise ValueError("Stop receipt changed; preserving current owner records")


def _remove_stop_receipts(
    receipts: tuple[tuple[Path, _StopReceipt | None], ...],
) -> None:
    # Launchers serialize writers with startup_lock. Revalidate after awaited
    # process retirement and before each unlink; do not claim atomic file CAS.
    _assert_stop_receipts(receipts)
    for path, captured in receipts:
        _assert_stop_receipts(((path, captured),))
        if captured is not None:
            try:
                path.unlink()
            except FileNotFoundError as exc:
                raise ValueError("Stop receipt disappeared during cleanup") from exc


def _assert_expected_stop_owner(
    receipts: tuple[tuple[Path, _StopReceipt | None], ...],
    pid: int | None,
    expected: tuple[int, str],
) -> None:
    pid_receipt, identity_receipt = receipts[0][1], receipts[1][1]
    if pid_receipt is None or identity_receipt is None:
        raise ValueError("Expected stop owner has no captured receipts")
    try:
        record = json.loads(identity_receipt.payload)
        observed_owner = (
            int(pid_receipt.payload.strip()),
            str(record.get("stamp", record.get("ticks"))),
        )
        record_pid = record.get("pid")
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("Cannot verify expected stop owner") from exc
    if (
        observed_owner != expected
        or record_pid != expected[0]
        or (pid is not None and pid != expected[0])
    ):
        raise ValueError(
            "Expected stop owner changed; preserving current owner records"
        )


def stop(
    root: Path,
    values: Mapping[str, str],
    keys: tuple[str, ...] = ("WEB_PID_FILE", "PID_FILE"),
    *,
    expected: Mapping[str, tuple[int, str]] | None = None,
) -> None:
    receipts = {
        key: tuple(
            (path, _stop_receipt(path))
            for path in (Path(values[key]), Path(values[key] + ".identity.json"))
        )
        for key in keys
    }
    # Validate every owner before signalling any process, then bind that result
    # to the exact file pair captured before owned_pid read it.
    owners = [(key, owned_pid(root, values, key)) for key in keys]
    for captured in receipts.values():
        _assert_stop_receipts(captured)
    for key, pid in owners:
        if expected is not None and key in expected:
            _assert_expected_stop_owner(receipts[key], pid, expected[key])
    for key, pid in owners:
        captured = receipts[key]
        _assert_stop_receipts(captured)
        if pid is not None and key == "WEB_PID_FILE":
            subprocess.run(
                ["node", str(root / "web-next/scripts/web-lifecycle.mjs"), "stop"],
                env=dict(values),
                check=True,
                timeout=30,
            )
            continue
        if pid is not None:
            from scripts.dev.qualification_process import identity
            from scripts.dev.runtime_teardown import EngineOwner, stop_engines

            observed = identity(pid)
            pid_receipt, identity_receipt = captured[0][1], captured[1][1]
            if pid_receipt is None or identity_receipt is None:
                raise ValueError("API owner has no captured stop receipts")
            record = json.loads(identity_receipt.payload)
            if (
                int(pid_receipt.payload.strip()) != pid
                or record["pid"] != pid
                or observed["start_ticks"] != record["stamp"]
            ):
                raise ValueError("API PID identity changed before stop")
            _assert_stop_receipts(captured)
            stop_engines([EngineOwner("api", pid, observed)])
        _remove_stop_receipts(captured)


def spawn_api(root: Path, values: dict[str, str]) -> dict[str, int | str]:
    from scripts.llm.with_gpu_libraries import command_python

    command = values.get("UVICORN", str(root / ".venv/bin/uvicorn"))
    python = command_python(command, root)
    flags = (
        values.get("UVICORN_DEV_FLAGS", "--reload")
        if values.get("START_MODE") != "prod" and values.get("BACKEND_RELOAD") == "1"
        else values.get("UVICORN_PROD_FLAGS", "--no-server-header")
    )
    extra_flags = shlex.split(flags)
    if values.get("VENOM_VARIANT") and "--timeout-graceful-shutdown" not in extra_flags:
        extra_flags += ["--timeout-graceful-shutdown", "10"]
    for key in ("BACKEND_LOG", "PID_FILE"):
        Path(values[key]).parent.mkdir(parents=True, exist_ok=True)
    with Path(values["BACKEND_LOG"]).open("a") as log:
        child = subprocess.Popen(
            [
                python,
                str(root / "scripts/llm/with_gpu_libraries.py"),
                command,
                values.get("API_APP", "venom_core.main:app"),
                "--host",
                values.get("HOST", "0.0.0.0"),
                "--port",
                values["PORT"],
                *extra_flags,
            ],
            cwd=root,
            env=values,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    # Capture creation identity from this Popen, not from a later mutable PID file.
    stamp, _ = process_stamp(child.pid)
    receipt: dict[str, int | str] = {"pid": child.pid, "stamp": stamp}
    try:
        Path(values["PID_FILE"]).write_text(str(child.pid) + "\n")
        record_pid(root, values, "PID_FILE")
    except Exception:
        from scripts.dev.startup_rollback import retire_unrecorded_api

        retire_unrecorded_api(root, receipt)
        raise
    return receipt


def component(root: Path, values: dict[str, str], name: str) -> None:
    web = {
        "web-build": ["build"],
        "web": ["start"],
        "web-dev": ["dev", "webpack"],
        "web-dev-turbo": ["dev", "turbo"],
        "web-dev-turbo-debug": ["dev", "turbo-debug"],
    }
    if name in web:
        os.execvpe(
            "node",
            ["node", str(root / "web-next/scripts/web-lifecycle.mjs"), *web[name]],
            values,
        )
    elif name in {"api", "api-dev"}:
        preflight(root, values)
        existing = owned_pid(root, values, "PID_FILE", reuse=True)
        if existing is not None:
            try:
                with urllib.request.urlopen(
                    values["API_PROXY_TARGET"] + "/api/v1/system/status", timeout=1
                ) as response:
                    if response.status == 200 and running(existing):
                        print("API already ready; existing owner preserved")
                        return
            except (OSError, urllib.error.URLError):
                pass
            raise ValueError(
                "Owned API is not ready; stop this environment explicitly before retry"
            )
        if name == "api-dev":
            values["BACKEND_RELOAD"] = "1"
        receipt = spawn_api(root, values)
        url = values["API_PROXY_TARGET"] + "/api/v1/system/status"
        try:
            for _ in range(60):
                pid = owned_pid(root, values, "PID_FILE")
                if pid is None or not running(pid):
                    raise ValueError("API process exited before readiness")
                if pid != receipt["pid"] or process_stamp(pid)[0] != receipt["stamp"]:
                    raise ValueError("Original API startup owner changed")
                try:
                    with urllib.request.urlopen(url, timeout=1) as response:
                        if response.status == 200:
                            print("API ready")
                            return
                except (OSError, urllib.error.URLError):
                    time.sleep(0.2)
            raise ValueError("API readiness timeout")
        except BaseException:
            from scripts.dev.startup_rollback import rollback_api

            rollback_api(root, values, receipt)
            raise
    elif name in {"api-stop", "web-stop"}:
        stop(root, values, ("PID_FILE",) if name == "api-stop" else ("WEB_PID_FILE",))
    else:
        raise ValueError("Unknown component action")


def preflight(root: Path, values: Mapping[str, str]) -> None:
    for key, port_key in (("PID_FILE", "PORT"), ("WEB_PID_FILE", "WEB_PORT")):
        with socket.socket() as probe:
            probe.settimeout(0.2)
            if (
                probe.connect_ex(
                    (values.get("HOST_DISPLAY", "127.0.0.1"), int(values[port_key]))
                )
                == 0
            ):
                if not owned_pid(root, values, key, reuse=True):
                    raise ValueError(f"{port_key} occupied by unowned listener")


def private_owner(root: Path, path: Path) -> None:
    path.chmod(0o600)
    if os.geteuid() == 0:
        os.chown(path, root.stat().st_uid, root.stat().st_gid)


def host_file(root: Path, name: str) -> Path:
    directory = root / ".venom_runtime"
    directory.mkdir(exist_ok=True)
    return directory / name


@contextmanager
def startup_lock(root: Path) -> Iterator[None]:
    path = host_file(root, ".host-start.lock")
    with path.open("a") as lock:
        private_owner(root, path)
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("Another environment startup is in progress") from exc
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def check_variant_peers(root: Path, values: Mapping[str, str]) -> None:
    registry = host_file(root, ".host-api-owners.json")
    entries = json.loads(registry.read_text()) if registry.exists() else []
    own = owned_pid(root, values, "PID_FILE", reuse=True)
    for record in entries:
        pid = record.get("pid", 0)
        if pid != own and running(pid) and process_stamp(pid)[0] == record.get("stamp"):
            raise ValueError(
                "Another environment owns shared runtime resources; stop it before switching variants"
            )


def check_shared_runtime(root: Path, values: Mapping[str, str]) -> None:
    selected = values.get("VENOM_STARTED_LOCAL_RUNTIME", "none")
    if selected == "none":
        return
    registry = host_file(root, ".host-api-owners.json")
    entries = json.loads(registry.read_text()) if registry.exists() else []
    for record in entries:
        pid = record.get("pid", 0)
        if running(pid) and process_stamp(pid)[0] == record.get("stamp"):
            peer = record.get("local_runtime", "none")
            if peer not in {"none", selected}:
                raise ValueError(
                    "Another environment owns a different local runtime; choose the same engine or a remote provider"
                )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Full/Light in dev/preprod (prod reserved)"
    )
    parser.add_argument(
        "action",
        choices=(
            "start",
            "stop",
            "status",
            "plan",
            "record-api",
            "launch-api",
            "component",
            "runtime-check",
        ),
    )
    parser.add_argument("component_name", nargs="?")
    args = parser.parse_args()
    try:
        values = resolve(
            ROOT,
            os.environ,
            allow_example=args.action == "component"
            and args.component_name == "web-build",
        )
        if args.action == "plan":
            print(json.dumps(public_plan(values), indent=2))
        elif args.action == "runtime-check":
            check_shared_runtime(ROOT, values)
        elif args.action == "launch-api":
            print(json.dumps(spawn_api(ROOT, values)))
        elif args.action == "record-api":
            record_pid(ROOT, values, "PID_FILE")
        elif args.action == "component":
            if args.component_name in {"api", "api-dev"}:
                with startup_lock(ROOT):
                    selected = subprocess.check_output(
                        [
                            sys.executable,
                            "-c",
                            "from venom_core.utils.llm_runtime import get_startup_local_server; print(get_startup_local_server())",
                        ],
                        env=values,
                        text=True,
                    ).strip()
                    values["VENOM_STARTED_LOCAL_RUNTIME"] = selected
                    check_shared_runtime(ROOT, values)
                    component(ROOT, values, args.component_name)
            else:
                component(ROOT, values, args.component_name or "")
        elif args.action == "stop":
            if "VENOM_VARIANT" in values:
                from scripts.dev.runtime_teardown import engine_owners, stop_engines

                with startup_lock(ROOT):
                    check_variant_peers(ROOT, values)
                    engines = engine_owners(ROOT, values)
                    stop(ROOT, values)
                    stop_engines(engines)
                    if engine_owners(ROOT, values):
                        raise ValueError(
                            "Owned engines remain; variant stop incomplete"
                        )
            else:
                stop(ROOT, values)
        elif args.action == "status":
            for key in ("PID_FILE", "WEB_PID_FILE"):
                print(f"{key}: {owned_pid(ROOT, values, key) or 'stopped'}")
        else:
            preflight(ROOT, values)
            for key in (
                "VENOM_LOG_DIR",
                "BACKEND_LOG",
                "WEB_LOG",
                "PID_FILE",
                "WEB_PID_FILE",
            ):
                Path(values[key]).parent.mkdir(parents=True, exist_ok=True)
            os.chdir(ROOT)
            with startup_lock(ROOT):
                if "VENOM_VARIANT" in values:
                    from scripts.dev.runtime_teardown import engine_owners

                    check_variant_peers(ROOT, values)
                    engines = engine_owners(ROOT, values)
                    if (
                        engines
                        and owned_pid(ROOT, values, "PID_FILE", reuse=True) is None
                    ):
                        raise ValueError(
                            "Owned local engines remain; run stop-venom or stop-studio before starting a variant"
                        )
                from scripts.dev.startup_rollback import run_start_stack

                run_start_stack(
                    ROOT, values, engines if "VENOM_VARIANT" in values else None
                )
    except ValueError as exc:
        parser.exit(2, f"{exc}\n")


if __name__ == "__main__":
    main()
