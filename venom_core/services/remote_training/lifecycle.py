"""Durable per-run control; provider provisioning never enters this module."""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import math
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ACTIVE = frozenset({"starting", "running", "stopping", "orphaned"})
TERMINAL = frozenset({"succeeded", "failed", "stopped", "timed_out"})
RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
LOG_LIMIT = 1_048_576


def validate_run_id(run_id: str) -> None:
    """IDs are path components, not shell expressions or user-selected paths."""
    if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
        raise ValueError("remote_training_invalid_run_id")


def atomic_json(path: Path, value: Any) -> None:
    """Write a private state record without exposing intermediate JSON."""
    from .paths import data_directory, operator_path

    path = operator_path(path)
    raw = json.dumps(value, sort_keys=True, allow_nan=False, indent=2) + "\n"
    name = path.name
    temporary = name + ".tmp"
    with data_directory(path.parent) as directory_fd:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW,
            0o600,
            dir_fd=directory_fd,
        )
        with os.fdopen(descriptor, "w") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
        os.fsync(directory_fd)


@contextlib.contextmanager
def file_lock(path: Path, *, blocking: bool = True):
    """Private advisory locks reject symlinks rather than following them."""
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        flags = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
        fcntl.flock(descriptor, flags)
        yield descriptor
    finally:
        os.close(descriptor)


def log_base(path: Path) -> tuple[int, bool]:
    """Read cursor metadata under the log lock; detect interrupted publication."""
    metadata = path.with_suffix(".offset.json")
    if metadata.is_symlink():
        raise ValueError("remote_training_log_symlink")
    if not metadata.exists():
        return 0, False
    if metadata.stat().st_size > 4096:
        raise ValueError("remote_training_log_offset_invalid")
    saved = json.loads(metadata.read_text())
    if not isinstance(saved, dict):
        raise ValueError("remote_training_log_offset_invalid")
    base = saved.get("base_offset")
    if type(base) is not int or base < 0:
        raise ValueError("remote_training_log_offset_invalid")
    stat = path.stat()
    if saved.get("inode") != stat.st_ino or saved.get("device") != stat.st_dev:
        atomic_json(
            metadata, {"base_offset": 0, "inode": stat.st_ino, "device": stat.st_dev}
        )
        return 0, True
    return base, False


def process_identity(pid: int) -> dict[str, Any] | None:
    """Bind a PID to a boot and Linux start tick, never command lines or env."""
    if type(pid) is not int or pid <= 0:
        return None
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
        fields = stat[stat.rfind(")") + 2 :].split()
        if fields[0] == "Z":
            return None
        boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        return {
            "pid": pid,
            "start_ticks": int(fields[19]),
            "boot_id": boot,
            "process_group": int(fields[2]),
        }
    except (OSError, ValueError, IndexError):
        return None


def identity_alive(identity: dict[str, Any] | None) -> bool:
    """Unknown identity never authorizes signalling or replacing a live process."""
    return identity is not None and process_identity(identity["pid"]) == identity


def pid_may_exist(pid: int) -> bool:
    """Permission denial is unknown, not evidence that an owner exited."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def group_alive(group: int) -> bool:
    """Ignore reparented zombies, which no longer execute or own GPU resources."""
    for entry in Path("/proc").iterdir():
        if entry.name.isdecimal():
            identity = process_identity(int(entry.name))
            if identity and identity["process_group"] == group:
                return True
    return False


def signal_group(identity: dict[str, Any], sig: int) -> None:
    """Only an owned session leader or its still-existing group may be signalled."""
    group = identity["process_group"]
    if group != identity["pid"] or group == os.getpgrp():
        raise RuntimeError("remote_training_unowned_process_group")
    current = process_identity(identity["pid"])
    if current is not None and current != identity:
        raise RuntimeError("remote_training_process_identity_changed")
    if group_alive(group):
        try:
            os.killpg(group, sig)
        except ProcessLookupError:
            pass


def account_elapsed(state: dict[str, Any]) -> None:
    """Persist consumed attempt time once; resuming never replenishes the run budget."""
    started = state.get("attempt_started_at")
    if started is not None:
        state["elapsed_seconds"] = state.get("elapsed_before", 0) + max(
            0, time.time() - started
        )


class JobStore:
    """Idempotent run creation and explicit attempt transitions under flock."""

    def __init__(self, root: Path):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if (self.root / "runs").is_symlink():
            raise ValueError("remote_training_symlink_runs")
        (self.root / "runs").mkdir(exist_ok=True, mode=0o700)

    def directory(self, run_id: str) -> Path:
        validate_run_id(run_id)
        path = self.root / "runs" / run_id
        if path.is_symlink():
            raise ValueError("remote_training_symlink_run")
        return path

    def prepare(self, manifest: dict[str, Any]) -> dict[str, Any]:
        run_id = manifest.get("run_id")
        if not isinstance(run_id, str):
            raise ValueError("remote_training_invalid_run_id")
        validate_run_id(run_id)
        checksum = hashlib.sha256(
            json.dumps(manifest, sort_keys=True, allow_nan=False).encode()
        ).hexdigest()
        directory = self.directory(run_id)
        directory.mkdir(exist_ok=True, mode=0o700)
        with file_lock(directory / ".state.lock"):
            path = directory / "state.json"
            if path.exists():
                state = json.loads(path.read_text())
                if state["manifest_sha256"] != checksum:
                    raise ValueError("remote_training_run_identity_changed")
                return state
            atomic_json(directory / "manifest.json", manifest)
            state = {
                "run_id": run_id,
                "manifest_sha256": checksum,
                "status": "prepared",
                "attempt": 0,
                "stage": None,
                "checkpoint": None,
                "attempt_root": None,
                "supervisor": None,
                "worker": None,
                "exit_code": None,
                "error": None,
                "updated_at": time.time(),
                "elapsed_seconds": 0.0,
            }
            atomic_json(path, state)
            return state

    def _read(self, directory: Path) -> dict[str, Any]:
        path = directory / "state.json"
        if not path.is_file() or path.is_symlink():
            raise ValueError("remote_training_run_not_prepared")
        return json.loads(path.read_text())

    def _refresh(self, directory: Path, state: dict[str, Any]) -> dict[str, Any]:
        if state["status"] in ACTIVE and not identity_alive(state.get("supervisor")):
            owner = state.get("supervisor")
            if (
                owner
                and process_identity(owner["pid"]) is None
                and pid_may_exist(owner["pid"])
            ):
                state.update(status="orphaned", error="supervisor_identity_unavailable")
                atomic_json(directory / "state.json", state)
                return state
            worker = state.get("worker")
            if worker and group_alive(worker["process_group"]):
                state.update(
                    status="orphaned", error="supervisor_lost_worker_still_active"
                )
            else:
                self._recover_attempt(directory, state)
            state["updated_at"] = time.time()
            atomic_json(directory / "state.json", state)
        return state

    def _recover_attempt(self, directory: Path, state: dict[str, Any]) -> None:
        from .milestones import read_attempt, verify_seal

        account_elapsed(state)
        state.update(status="failed", error="supervisor_lost", exit_code=None)
        outcome = directory / "attempts" / f"{state['attempt']:04d}" / "outcome.json"
        if not outcome.exists():
            return
        try:
            proof = read_attempt(directory, state["attempt"])
            verify_seal(directory, proof)
        except (OSError, ValueError, KeyError):
            state["error"] = "sealed_attempt_invalid"
            return
        state.update(
            status=proof["status"],
            exit_code=proof["exit_code"],
            error=None
            if proof["status"] == "succeeded"
            else "recovered_terminal_attempt",
        )
        if proof.get("elapsed_seconds") is not None:
            state["elapsed_seconds"] = proof["elapsed_seconds"]

    def status(self, run_id: str) -> dict[str, Any]:
        directory = self.directory(run_id)
        with file_lock(directory / ".state.lock"):
            state = self._refresh(directory, self._read(directory))
            from .milestones import seal_attempt

            seal_attempt(directory, state)
            return state

    def attempt_status(self, run_id: str, attempt: int) -> dict[str, Any]:
        from .milestones import read_attempt

        state = self.status(run_id)
        if type(attempt) is not int or attempt < 1:
            raise ValueError("remote_training_attempt_selector_invalid")
        if state["attempt"] == attempt:
            return state
        return read_attempt(self.directory(run_id), attempt)

    def attempts(self, run_id: str) -> list[dict[str, Any]]:
        from .milestones import read_attempt

        self.status(run_id)
        directory = self.directory(run_id)
        results = []
        for path in sorted((directory / "attempts").glob("[0-9]*")):
            if not path.name.isdigit() or not (path / "outcome.json").is_file():
                continue
            attempt = int(path.name)
            if path.name != f"{attempt:04d}":
                continue
            try:
                proof = read_attempt(directory, attempt)
            except (OSError, ValueError):
                proof = {
                    "run_id": run_id,
                    "attempt": attempt,
                    "status": "invalid",
                    "error": "remote_training_attempt_outcome_unreadable",
                }
            results.append(proof)
        return results

    def _timeout(self, directory: Path, requested: float) -> float:
        manifest = json.loads((directory / "manifest.json").read_text())
        limits = manifest.get("limits", manifest.get("identity", {}).get("limits", {}))
        maximum = limits.get("max_seconds", 3600)
        if (
            type(requested) not in {int, float}
            or not math.isfinite(requested)
            or requested <= 0
            or type(maximum) not in {int, float}
            or not math.isfinite(maximum)
            or not 0 < maximum <= 86400
        ):
            raise ValueError("remote_training_timeout_invalid")
        state = self._read(directory)
        remaining = maximum - state.get("elapsed_seconds", 0)
        if remaining <= 0:
            raise ValueError("remote_training_run_budget_exhausted")
        return min(requested, remaining)

    def _spawn(self, directory: Path, attempt: int) -> subprocess.Popen:
        environment = os.environ.copy()
        repository = str(Path(__file__).resolve().parents[3])
        environment["PYTHONPATH"] = repository
        with (directory / "supervisor.log").open("ab") as log:
            return subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "venom_core.services.remote_training.supervisor",
                    str(self.root),
                    directory.name,
                    str(attempt),
                ],
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                close_fds=True,
                start_new_session=True,
                env=environment,
            )

    def start(
        self,
        run_id: str,
        stage: str = "smoke",
        checkpoint: str | None = None,
        timeout_seconds: float = 3600,
        *,
        _resume: bool = False,
        _retry_attempt: int | None = None,
        until_update: int | None = None,
    ) -> dict[str, Any]:
        if checkpoint is not None and not _resume:
            raise ValueError("remote_training_checkpoint_requires_resume")
        if stage not in {"smoke", "train"}:
            raise ValueError("remote_training_stage_invalid")
        directory = self.directory(run_id)
        with file_lock(directory / ".state.lock"):
            state = self._refresh(directory, self._read(directory))
            from .milestones import seal_attempt, target_update

            seal_attempt(directory, state)
            manifest = json.loads((directory / "manifest.json").read_text())
            until_update = target_update(manifest, stage, until_update)
            if _retry_attempt is not None:
                if (
                    state.get("retry_from") == _retry_attempt
                    and state["attempt"] == _retry_attempt + 1
                ):
                    return state
                if state["attempt"] != _retry_attempt or state[
                    "status"
                ] not in TERMINAL - {"succeeded"}:
                    raise ValueError("remote_training_retry_attempt_conflict")
            if state["status"] in ACTIVE:
                if (
                    state.get("stage") != stage
                    or state.get("checkpoint") != checkpoint
                    or state.get("until_update") != until_update
                ):
                    raise ValueError("remote_training_conflicting_active_start")
                return state
            if state["status"] == "succeeded":
                if (
                    state.get("stage") == stage
                    and state.get("checkpoint") == checkpoint
                    and state.get("until_update") == until_update
                ):
                    return state
                if not _resume and not (
                    state.get("stage") == "smoke" and stage == "train"
                ):
                    raise ValueError(
                        "remote_training_completed_attempt_requires_resume"
                    )
            elif state["status"] in TERMINAL and not _resume:
                raise ValueError("remote_training_explicit_resume_required")
            from .bundles import verify_directory

            manifest = json.loads((directory / "manifest.json").read_text())
            verify_directory(directory / "input", manifest)
            timeout = self._timeout(directory, timeout_seconds)
            attempt = state["attempt"] + 1
            attempt_root = directory / "attempts" / f"{attempt:04d}"
            attempt_root.mkdir(parents=True, exist_ok=False, mode=0o700)
            manifest = json.loads((directory / "manifest.json").read_text())
            request = {
                "run_id": run_id,
                "stage": stage,
                "checkpoint": checkpoint,
                "until_update": until_update,
                "manifest": manifest,
                "run_root": str(directory),
                "attempt_root": str(attempt_root),
                "host_root": str(self.root),
                "timeout_seconds": timeout,
                "elapsed_before": state.get("elapsed_seconds", 0),
            }
            atomic_json(attempt_root / "request.json", request)
            state.update(
                status="starting",
                attempt=attempt,
                retry_from=_retry_attempt,
                stage=stage,
                checkpoint=checkpoint,
                until_update=until_update,
                attempt_root=str(attempt_root.relative_to(self.root)),
                supervisor=None,
                worker=None,
                exit_code=None,
                error=None,
                stop_requested=False,
                elapsed_before=state.get("elapsed_seconds", 0),
                attempt_started_at=time.time(),
                updated_at=time.time(),
            )
            atomic_json(directory / "state.json", state)
            try:
                process = self._spawn(directory, attempt)
                state["supervisor"] = process_identity(process.pid)
                if not state["supervisor"]:
                    raise RuntimeError("remote_training_supervisor_start_unconfirmed")
                atomic_json(directory / "state.json", state)
            except Exception as error:
                state.update(
                    status="failed", error=type(error).__name__, updated_at=time.time()
                )
                atomic_json(directory / "state.json", state)
                raise
            return state

    def stop(self, run_id: str) -> dict[str, Any]:
        directory = self.directory(run_id)
        with file_lock(directory / ".state.lock"):
            state = self._refresh(directory, self._read(directory))
            if state["status"] not in ACTIVE:
                return state
            state.update(status="stopping", stop_requested=True, updated_at=time.time())
            atomic_json(directory / "state.json", state)
            if not identity_alive(state.get("supervisor")) and state.get("worker"):
                signal_group(state["worker"], signal.SIGTERM)
                deadline = time.monotonic() + 3
                while (
                    group_alive(state["worker"]["process_group"])
                    and time.monotonic() < deadline
                ):
                    time.sleep(0.05)
                if group_alive(state["worker"]["process_group"]):
                    signal_group(state["worker"], signal.SIGKILL)
                if not group_alive(state["worker"]["process_group"]):
                    account_elapsed(state)
                    state.update(status="stopped", finished_at=time.time())
                    atomic_json(directory / "state.json", state)
            return state

    def retry(
        self, run_id: str, from_attempt: int, timeout_seconds: float = 3600
    ) -> dict[str, Any]:
        """Explicit fresh attempt; the prior attempt token makes SSH retries idempotent."""
        if type(from_attempt) is not int or from_attempt < 1:
            raise ValueError("remote_training_retry_attempt_invalid")
        state = self.status(run_id)
        return self.start(
            run_id,
            state.get("stage") or "smoke",
            timeout_seconds=timeout_seconds,
            _resume=True,
            _retry_attempt=from_attempt,
            until_update=state.get("until_update"),
        )

    def resume(
        self,
        run_id: str,
        checkpoint: str,
        stage: str = "train",
        timeout_seconds: float = 3600,
        *,
        until_update: int | None = None,
    ) -> dict[str, Any]:
        directory = self.directory(run_id)
        path = Path(checkpoint)
        if path.is_absolute() or path.is_symlink() or ".." in path.parts:
            raise ValueError("remote_training_checkpoint_path_invalid")
        target = directory / path
        if (
            not path.parts
            or path.parts[0] != "attempts"
            or not target.resolve().is_relative_to(directory.resolve())
            or not target.is_dir()
        ):
            raise ValueError("remote_training_checkpoint_missing")
        if any(
            p.is_symlink()
            for p in [target, *target.parents]
            if p.is_relative_to(directory)
        ):
            raise ValueError("remote_training_checkpoint_symlink")
        if until_update is None:
            state = self.status(run_id)
            if state["status"] != "succeeded":
                until_update = state.get("until_update")
        return self.start(
            run_id,
            stage,
            checkpoint,
            timeout_seconds,
            _resume=True,
            until_update=until_update,
        )

    def logs(self, run_id: str, max_bytes: int = 65536) -> str:
        if type(max_bytes) is not int or not 1 <= max_bytes <= LOG_LIMIT:
            raise ValueError("remote_training_log_limit_invalid")
        state = self.status(run_id)
        if not state["attempt_root"]:
            return ""
        log = self.root / state["attempt_root"] / "worker.log"
        if not log.exists():
            return ""
        if log.is_symlink():
            raise ValueError("remote_training_log_symlink")
        with log.open("rb") as stream:
            stream.seek(max(0, log.stat().st_size - max_bytes))
            return stream.read(max_bytes).decode(errors="replace")
