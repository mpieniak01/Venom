"""Process ownership for isolated qualification; never stop by name or port."""

from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import subprocess
import time
from pathlib import Path
from typing import Any


class OwnershipError(RuntimeError):
    """The process no longer matches the recorded experiment ownership."""


def identity(pid: int) -> dict[str, Any]:
    process = Path("/proc") / str(pid)
    fields = (process / "stat").read_text().split(") ", 1)[1].split()
    if fields[0] == "Z":
        raise ProcessLookupError(pid)
    observed = {
        "pid": pid,
        "pgid": os.getpgid(pid),
        "start_ticks": fields[19],
        "cwd": os.readlink(process / "cwd"),
        "command_sha256": hashlib.sha256(
            (process / "cmdline").read_bytes()
        ).hexdigest(),
    }
    # Exit can clear cmdline after the first stat read. Recheck state before
    # treating that harmless shutdown transition as an ownership change.
    final_fields = (process / "stat").read_text().split(") ", 1)[1].split()
    if final_fields[0] == "Z":
        raise ProcessLookupError(pid)
    if final_fields[19] != fields[19]:
        raise OwnershipError("process_identity_changed_during_read")
    return observed


class QualificationProcess:
    """Own one trusted experiment command with an exact PID/session/start identity."""

    def __init__(self, root: Path, owner: str):
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,39}", owner):
            raise ValueError("invalid_experiment_owner")
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.owner = owner
        self.record = self.root / f"{owner}.process.json"
        self.process: subprocess.Popen | None = None

    def start(self, argv: list[str], *, cwd: Path, environment: dict[str, str]) -> int:
        if self.record.exists() or self.record.is_symlink():
            raise OwnershipError("experiment_record_already_exists")
        if not argv or not Path(argv[0]).is_absolute():
            raise ValueError("absolute_executable_required")
        cwd = cwd.resolve(strict=True)
        with (self.root / f"{self.owner}.log").open("ab") as log:
            self.process = subprocess.Popen(
                argv,
                cwd=cwd,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        try:
            observed = identity(self.process.pid)
            if observed["pgid"] != self.process.pid:
                raise OwnershipError("process_is_not_session_owner")
            observed["owner"] = self.owner
            temporary = self.record.with_suffix(".tmp")
            with temporary.open("x") as output:
                os.chmod(temporary, 0o600)
                json.dump(observed, output)
            temporary.replace(self.record)
        except Exception:
            self.process.terminate()
            self.process.wait(timeout=5)
            raise
        return self.process.pid

    def stop(self, *, timeout: float = 5.0) -> bool:
        if self.record.is_symlink():
            raise OwnershipError("experiment_record_is_symlink")
        if not self.record.exists():
            return False
        expected = json.loads(self.record.read_text())
        if expected.get("owner") != self.owner:
            raise OwnershipError("wrong_experiment_owner")
        pid = expected["pid"]
        if type(pid) is not int or pid <= 1 or pid == os.getpid():
            raise OwnershipError("invalid_experiment_pid")
        if expected.get("pgid") != pid or pid == os.getpgrp():
            raise OwnershipError("invalid_experiment_group")
        try:
            current = identity(pid)
        except (OSError, ProcessLookupError):
            self.record.unlink()
            return False
        if any(current.get(key) != expected.get(key) for key in current):
            raise OwnershipError("experiment_identity_changed")
        os.killpg(pid, signal.SIGTERM)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.process is not None:
                self.process.poll()
            try:
                current = identity(pid)
            except (OSError, ProcessLookupError):
                break
            if any(
                current.get(key) != expected.get(key)
                for key in ("pid", "pgid", "start_ticks")
            ):
                raise OwnershipError("experiment_identity_changed_during_shutdown")
            # No new signal is sent while waiting. A terminating process can
            # clear/change cmdline or cwd; a possible SIGKILL below still requires
            # the full original identity, including command and directory.
            time.sleep(0.05)
        else:
            # Verify identity again before escalation; never kill a reused PID.
            current = identity(pid)
            if any(current.get(key) != expected.get(key) for key in current):
                raise OwnershipError("experiment_identity_changed_before_kill")
            os.killpg(pid, signal.SIGKILL)
        if self.process is not None:
            self.process.wait(timeout=5)
        self.record.unlink()
        return True
