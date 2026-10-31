"""Retire explicitly owned engine resources; never discover processes by name."""

from __future__ import annotations

import json
import os
import re
import select
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

from scripts.dev.qualification_process import QualificationProcess, identity
from scripts.llm.component_runtime import daemon_identity, owned_identity


@dataclass
class EngineOwner:
    kind: str
    pid: int
    observed: dict[str, Any]
    service: tuple[str, ...] = ()
    component: QualificationProcess | None = None
    receipts: tuple[tuple[Path, bytes], ...] = ()


def _service(
    root: Path, values: Mapping[str, str], kind: str, key: str, scope_key: str
) -> EngineOwner | None:
    unit = values.get(key)
    if not unit:
        return None
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.@-]*\.service", unit):
        raise ValueError("Invalid configured engine systemd unit")
    scope = values.get(scope_key, "user")
    if scope not in {"user", "system"}:
        raise ValueError("Invalid configured engine systemd scope")
    command = ("systemctl", *(("--user",) if scope == "user" else ()))
    result = subprocess.run(
        [*command, "show", "--property=MainPID", "--value", "--", unit],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode:
        raise ValueError(f"Cannot verify configured {kind} service")
    pid = int(result.stdout.strip() or "0")
    if pid == 0:
        return None
    observed = identity(pid)
    proc = Path(f"/proc/{pid}")
    if proc.stat().st_uid != root.stat().st_uid:
        raise ValueError("Engine service belongs to another OS user")
    command_bytes = (proc / "cmdline").read_bytes()
    token = {"ollama": b"ollama", "vllm": b"vllm", "multi_runtime": b"multi_runtime"}[
        kind
    ]
    if token not in command_bytes:
        raise ValueError("Configured engine service command identity differs")
    return EngineOwner(kind, pid, observed, (*command, "stop", "--", unit))


def _receipt_files(*paths: Path) -> tuple[tuple[Path, bytes], ...]:
    result = []
    for path in paths:
        if path.is_symlink():
            raise ValueError("Engine ownership receipt cannot be a symlink")
        if path.is_file():
            result.append((path, path.read_bytes()))
    return tuple(result)


def engine_owners(
    root: Path, values: Mapping[str, str], kinds: frozenset[str] | None = None
) -> list[EngineOwner]:
    selected = (
        kinds if kinds is not None else frozenset({"ollama", "vllm", "multi_runtime"})
    )
    owners = []
    for kind, unit, scope, enabled in [
        ("ollama", "OLLAMA_SYSTEMD_UNIT", "OLLAMA_SYSTEMD_SCOPE", True),
        (
            "vllm",
            "VLLM_SYSTEMD_UNIT",
            "VLLM_SYSTEMD_SCOPE",
            values.get("VLLM_USE_SYSTEMD", "false").lower() in {"true", "1", "yes"},
        ),
        (
            "multi_runtime",
            "GEMMA4_AUDIO_SYSTEMD_UNIT",
            "GEMMA4_AUDIO_SYSTEMD_SCOPE",
            values.get("MULTI_RUNTIME_USE_SYSTEMD", "false").lower()
            in {"true", "1", "yes"},
        ),
    ]:
        if enabled and kind in selected:
            owner = _service(root, values, kind, unit, scope)
            if owner:
                owners.append(owner)
    state = Path(
        values.get("VLLM_COMPONENT_STATE_DIR", str(root / ".venom_runtime/components"))
    )
    component_owner = values.get("VLLM_COMPONENT_OWNER", "vllm")
    if "vllm" in selected and (state / f"{component_owner}.process.json").exists():
        process = QualificationProcess(state, component_owner)
        observed = owned_identity(process)
        if observed:
            owners.append(
                EngineOwner(
                    "vllm",
                    observed["pid"],
                    observed,
                    component=process,
                    receipts=_receipt_files(process.record),
                )
            )
    pid_file = Path(
        values.get(
            "GEMMA4_AUDIO_PID_PATH", str(root / ".venom_runtime/multi_runtime.pid")
        )
    )
    if not pid_file.is_absolute():
        pid_file = root / pid_file
    if "multi_runtime" in selected:
        if pid_file.is_symlink():
            raise ValueError("Engine PID receipt cannot be a symlink")
        if pid_file.exists():
            receipt = Path(str(pid_file) + ".identity.json")
            pid = int(pid_file.read_text().strip())
            if Path(f"/proc/{pid}").exists():
                if not receipt.is_file():
                    raise ValueError("Engine has no verifiable ownership receipt")
                python = Path(
                    values.get(
                        "MULTI_RUNTIME_COMPONENT_PYTHON",
                        str(root / ".venv-components/multi-runtime/bin/python"),
                    )
                )
                try:
                    observed = daemon_identity(python, pid, receipt)
                except ProcessLookupError:
                    observed = None
                if observed:
                    owners.append(
                        EngineOwner(
                            "multi_runtime",
                            pid,
                            observed,
                            receipts=_receipt_files(pid_file, receipt),
                        )
                    )
    ollama_pid = root / "logs/ollama.pid"
    if "ollama" in selected:
        if ollama_pid.is_symlink():
            raise ValueError("Engine PID receipt cannot be a symlink")
        if ollama_pid.exists():
            pid = int(ollama_pid.read_text().strip())
            if Path(f"/proc/{pid}").exists() and pid not in {o.pid for o in owners}:
                receipt = Path(str(ollama_pid) + ".identity.json")
                try:
                    observed = identity(pid)
                except ProcessLookupError:
                    observed = None
                if observed:
                    if (
                        receipt.is_symlink()
                        or not receipt.is_file()
                        or json.loads(receipt.read_text()) != observed
                    ):
                        raise ValueError(
                            "Unverified Ollama PID; explicit ownership migration required"
                        )
                    owners.append(
                        EngineOwner(
                            "ollama",
                            pid,
                            observed,
                            receipts=_receipt_files(ollama_pid, receipt),
                        )
                    )
    validate_listeners(values, owners, selected)
    return owners


def validate_listeners(
    values: Mapping[str, str],
    owners: list[EngineOwner],
    kinds: frozenset[str] | None = None,
) -> None:
    from scripts.dev.stack_profile import descendants

    owned = {pid for owner in owners for pid in [owner.pid, *descendants(owner.pid)]}
    ports = set()
    for kind, key, default in [
        ("ollama", "OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
        ("vllm", "VLLM_ENDPOINT", "http://127.0.0.1:8001"),
        ("multi_runtime", "MULTI_RUNTIME_ENDPOINT", "http://127.0.0.1:8014"),
    ]:
        if kinds is not None and kind not in kinds:
            continue
        endpoint = urlsplit(values.get(key, default))
        if endpoint.hostname in {"localhost", "127.0.0.1", "::1"}:
            ports.add(endpoint.port or 80)
    result = subprocess.run(
        ["ss", "-H", "-ltnp"], capture_output=True, text=True, check=True, timeout=10
    )
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) < 4:
            continue
        port = int(fields[3].rsplit(":", 1)[-1])
        if port not in ports:
            continue
        listeners = {int(pid) for pid in re.findall(r"pid=(\d+)", line)}
        if not listeners or not listeners.issubset(owned):
            raise ValueError(
                "Configured engine listener has no verified owner; no processes were signalled"
            )


def claim_started_ollama(root: Path, values: Mapping[str, str]) -> None:
    # Systemd has its own owner identity. A newly spawned manual daemon needs one.
    if values.get("OLLAMA_SYSTEMD_UNIT"):
        return
    path = root / "logs/ollama.pid"
    if not path.exists() or path.is_symlink():
        return
    pid = int(path.read_text().strip())
    proc = Path(f"/proc/{pid}")
    if proc.stat().st_uid != root.stat().st_uid or str((proc / "cwd").resolve()) != str(
        root.resolve()
    ):
        raise ValueError("Manual engine checkout or owner differs")
    if (
        b"ollama" not in (proc / "cmdline").read_bytes()
        or b"serve" not in (proc / "cmdline").read_bytes()
    ):
        raise ValueError("Manual engine command differs")
    receipt = Path(str(path) + ".identity.json")
    if receipt.is_symlink():
        raise ValueError("Engine identity receipt cannot be a symlink")
    with tempfile.NamedTemporaryFile(
        mode="w", dir=receipt.parent, prefix=".engine-owner-", delete=False
    ) as output:
        temporary = Path(output.name)
        os.fchmod(output.fileno(), 0o600)
        json.dump(identity(pid), output)
    try:
        temporary.replace(receipt)
    finally:
        temporary.unlink(missing_ok=True)


def _same(owner: EngineOwner) -> bool:
    try:
        observed = identity(owner.pid)
    except (OSError, ProcessLookupError):
        return False
    if observed != owner.observed:
        raise ValueError("Engine PID was reused; refusing to signal")
    return True


def _descends_from(pid: int, parent: int) -> bool:
    seen = set()
    while pid > 1 and pid not in seen:
        seen.add(pid)
        if pid == parent:
            return True
        try:
            pid = int(
                Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[1]
            )
        except (OSError, ValueError, IndexError):
            return False
    return False


def capture_engine_tree(owner: EngineOwner) -> list[int]:
    """Bind kernel handles before final identity checks; never adopt a reused PID."""
    from scripts.dev.stack_profile import descendants

    handles: list[int] = []
    if not hasattr(os, "pidfd_open") or not hasattr(signal, "pidfd_send_signal"):
        raise ValueError("Verified engine stop requires Linux pidfd support")
    if not _same(owner):
        return handles
    try:
        for pid in [owner.pid, *descendants(owner.pid)]:
            try:
                handle = os.pidfd_open(pid)
            except ProcessLookupError:
                continue
            try:
                observed = identity(pid)
                if pid == owner.pid and observed != owner.observed:
                    raise ValueError("Engine PID was reused during tree capture")
                if pid != owner.pid and not _descends_from(pid, owner.pid):
                    os.close(handle)
                    continue
            except (OSError, ProcessLookupError):
                os.close(handle)
                continue
            except BaseException:
                os.close(handle)
                raise
            handles.append(handle)
        if not _same(owner):
            raise ValueError(
                "Engine leader exited during tree capture; stop cannot prove quiescence"
            )
        return handles
    except BaseException:
        for handle in handles:
            os.close(handle)
        raise


def wait_engine_exit(handles: list[int], timeout: float = 30) -> None:
    deadline = time.monotonic() + timeout
    pending = set(handles)
    while pending:
        left = deadline - time.monotonic()
        if left <= 0:
            raise ValueError(
                "Owned engine descendants did not exit; variant stop incomplete"
            )
        exited, _, _ = select.select(list(pending), [], [], left)
        pending.difference_update(exited)


def stop_engines(owners: list[EngineOwner]) -> None:
    for owner in owners:
        handles = capture_engine_tree(owner)
        try:
            if not handles:
                continue
            if owner.service:
                subprocess.run(list(owner.service), check=True, timeout=30)
            else:
                for handle in reversed(handles):
                    try:
                        signal.pidfd_send_signal(handle, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
            wait_engine_exit(handles)
            if all(
                not path.is_symlink() and path.exists() and path.read_bytes() == content
                for path, content in owner.receipts
            ):
                for path, _ in owner.receipts:
                    path.unlink(missing_ok=True)
        finally:
            for handle in handles:
                os.close(handle)


def main() -> None:
    import argparse

    from dotenv import dotenv_values

    parser = argparse.ArgumentParser(
        description="Explicit verified Ollama component ownership"
    )
    parser.add_argument(
        "action", choices=["verify-ollama", "claim-ollama", "stop-ollama"]
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    env_file = Path(os.environ.get("ENV_FILE", str(root / ".env.dev")))
    prefixes = ("OLLAMA_", "VLLM_", "MULTI_RUNTIME_", "GEMMA4_AUDIO_")
    values = {
        key: str(value)
        for key, value in dotenv_values(env_file).items()
        if value is not None and key.startswith(prefixes)
    }
    values.update(
        {key: value for key, value in os.environ.items() if key.startswith(prefixes)}
    )
    if args.action == "claim-ollama":
        claim_started_ollama(root, values)
    else:
        owners = engine_owners(root, values, frozenset({"ollama"}))
        if args.action == "stop-ollama":
            stop_engines(owners)
            if engine_owners(root, values, frozenset({"ollama"})):
                raise ValueError("Ollama stop incomplete")
    print(json.dumps({"action": args.action, "verified": True}))


if __name__ == "__main__":
    main()
