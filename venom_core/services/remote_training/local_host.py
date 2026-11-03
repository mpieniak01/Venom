"""Read-only local admission checks; never stop an API or reserve another ledger."""

from __future__ import annotations

import fcntl
import shutil
from pathlib import Path

from dotenv import dotenv_values

from .host import load_host
from .paths import operator_path


def canonical_ledger(code_root: Path) -> Path:
    """Read only the host memory setting from its selected development env file."""
    settings = dotenv_values(code_root / ".env.dev", interpolate=False)
    memory = settings.get("MEMORY_ROOT") or "data/memory"
    path = Path(memory)
    return operator_path(
        (path if path.is_absolute() else code_root / path) / "runtime-admission.sqlite3"
    )


def readiness(root: Path) -> dict:
    root = operator_path(root)
    host = load_host(root)
    code_root = operator_path(host["code_root"])
    expected = canonical_ledger(code_root)
    selected = operator_path(host["admission_db"])
    blockers = []
    if selected != expected:
        blockers.append("local_admission_ledger_mismatch")
    lock = expected.with_suffix(".host.lock")
    if lock.exists():
        if lock.is_symlink():
            raise ValueError("remote_training_local_lock_symlink")
        with lock.open("rb") as stream:
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                blockers.append("local_host_owned_by_running_process")
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    # Do not create the DB or recover a stale/quarantined lease.
    if expected.exists():
        import sqlite3

        with sqlite3.connect("file:" + str(expected) + "?mode=ro", uri=True) as db:
            if db.execute("SELECT count(*) FROM lease").fetchone()[0]:
                blockers.append("local_runtime_lease_present")
            if db.execute("SELECT count(*) FROM operation").fetchone()[0]:
                blockers.append("local_runtime_operation_present")
    if not Path(host["worker_python"]).is_file():
        blockers.append("local_worker_python_missing")
    if not Path(host["snapshot"]).is_dir():
        blockers.append("local_snapshot_missing")
    if shutil.disk_usage(root).free < 10 * 1024**3:
        blockers.append("local_free_disk_insufficient")
    return {
        "ready": not blockers,
        "blockers": blockers,
        "execution": "local",
        "admission_db": str(expected),
        "host_id": host["host_id"],
        "gpu_qualified": False,
        "model_loaded": False,
        "training_started": False,
        "remediation": "Use an explicit exclusive GPU window; no automatic service shutdown.",
    }
