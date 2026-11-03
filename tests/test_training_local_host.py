"""Local preflight never bypasses the active host namespace."""

import fcntl
import sqlite3
from types import SimpleNamespace as NS

from venom_core.services.remote_training import local_host


def setup_host(tmp_path, monkeypatch):
    code = tmp_path / "code"
    code.mkdir()
    memory = tmp_path / "canonical-memory"
    memory.mkdir()
    (code / ".env.dev").write_text("MEMORY_ROOT=" + str(memory) + "\n")
    worker = tmp_path / "python"
    worker.write_text("")
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    ledger = memory / "runtime-admission.sqlite3"
    host = {
        "host_id": "test",
        "code_root": str(code),
        "worker_python": str(worker),
        "snapshot": str(snapshot),
        "admission_db": str(ledger),
    }
    monkeypatch.setattr(local_host, "load_host", lambda root: host)
    monkeypatch.setattr(
        local_host.shutil, "disk_usage", lambda root: NS(free=20 * 1024**3)
    )
    return host, ledger


def test_ready_has_no_side_effects(tmp_path, monkeypatch):
    host, ledger = setup_host(tmp_path, monkeypatch)
    assert local_host.readiness(tmp_path)["ready"]
    assert not ledger.exists()


def test_wrong_database_is_blocked(tmp_path, monkeypatch):
    host, ledger = setup_host(tmp_path, monkeypatch)
    host["admission_db"] = str(tmp_path / "empty.sqlite")
    assert (
        "local_admission_ledger_mismatch" in local_host.readiness(tmp_path)["blockers"]
    )


def test_live_lock_is_blocked_without_recovery(tmp_path, monkeypatch):
    host, ledger = setup_host(tmp_path, monkeypatch)
    lock = ledger.with_suffix(".host.lock")
    lock.touch()
    with lock.open("rb") as held:
        fcntl.flock(held.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert (
            "local_host_owned_by_running_process"
            in local_host.readiness(tmp_path)["blockers"]
        )
    assert local_host.readiness(tmp_path)["ready"]


def test_present_lease_and_resources(tmp_path, monkeypatch):
    host, ledger = setup_host(tmp_path, monkeypatch)
    with sqlite3.connect(ledger) as db:
        db.execute("CREATE TABLE lease(id INTEGER)")
        db.execute("INSERT INTO lease VALUES(1)")
        db.execute("CREATE TABLE operation(id INTEGER)")
        db.execute("INSERT INTO operation VALUES(1)")
    host["worker_python"] = str(tmp_path / "missing")
    host["snapshot"] = str(tmp_path / "absent")
    monkeypatch.setattr(local_host.shutil, "disk_usage", lambda root: NS(free=1))
    blocked = local_host.readiness(tmp_path)["blockers"]
    assert set(blocked) == {
        "local_runtime_lease_present",
        "local_runtime_operation_present",
        "local_worker_python_missing",
        "local_snapshot_missing",
        "local_free_disk_insufficient",
    }
