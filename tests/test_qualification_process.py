"""Real harmless child processes verify isolated start/stop and identity refusal."""

import json
import os
import sys
from unittest.mock import Mock

import pytest

from scripts.dev import qualification_process as module
from scripts.dev.qualification_process import OwnershipError, QualificationProcess


def test_own_process_stops_without_affecting_the_parent(tmp_path):
    process = QualificationProcess(tmp_path, "native-probe")
    pid = process.start(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        cwd=tmp_path,
        environment={"PATH": os.defpath},
    )
    recorded = json.loads(process.record.read_text())
    assert recorded["pid"] == recorded["pgid"] == pid
    assert recorded["cwd"] == str(tmp_path)
    assert "argv" not in recorded
    assert process.stop()
    assert process.process.poll() is not None
    assert not process.record.exists()
    assert process.stop() is False


def test_changed_identity_is_refused_before_any_signal(monkeypatch, tmp_path):
    process = QualificationProcess(tmp_path, "native-probe")
    expected = {
        "owner": "native-probe",
        "pid": 12345,
        "pgid": 12345,
        "cwd": str(tmp_path),
        "start_ticks": "1",
        "command_sha256": "old",
    }
    process.record.write_text(json.dumps(expected))
    monkeypatch.setattr(
        module, "identity", lambda pid: {**expected, "start_ticks": "2"}
    )
    kill = Mock()
    monkeypatch.setattr(module.os, "killpg", kill)
    with pytest.raises(OwnershipError, match="identity_changed"):
        process.stop()
    kill.assert_not_called()
    assert process.record.exists()


@pytest.mark.parametrize("owner", ["../escape", "bad/name", "", "A"])
def test_invalid_owner_never_creates_process(tmp_path, owner):
    with pytest.raises(ValueError):
        QualificationProcess(tmp_path, owner)


@pytest.mark.parametrize(
    "field,value", [("pid", 1), ("pid", True), ("pgid", 2), ("owner", "other")]
)
def test_invalid_ownership_never_sends_signal(monkeypatch, tmp_path, field, value):
    process = QualificationProcess(tmp_path, "probe")
    data = {"owner": "probe", "pid": 12345, "pgid": 12345}
    data[field] = value
    process.record.write_text(json.dumps(data))
    kill = Mock()
    monkeypatch.setattr(module.os, "killpg", kill)
    with pytest.raises(OwnershipError):
        process.stop()
    kill.assert_not_called()


def test_symlink_record_is_refused(tmp_path):
    process = QualificationProcess(tmp_path, "probe")
    other = tmp_path / "other.json"
    other.write_text("{}")
    process.record.symlink_to(other)
    with pytest.raises(OwnershipError, match="symlink"):
        process.stop()
    assert other.read_text() == "{}"


def test_relative_executable_is_refused(tmp_path):
    process = QualificationProcess(tmp_path, "probe")
    with pytest.raises(ValueError, match="absolute_executable"):
        process.start(["python"], cwd=tmp_path, environment={})


def test_dead_process_removes_stale_receipt_without_signal(monkeypatch, tmp_path):
    process = QualificationProcess(tmp_path, "probe")
    process.record.write_text(
        json.dumps({"owner": "probe", "pid": 12345, "pgid": 12345})
    )

    def gone(pid):
        raise ProcessLookupError(pid)

    monkeypatch.setattr(module, "identity", gone)
    kill = Mock()
    monkeypatch.setattr(module.os, "killpg", kill)
    assert process.stop() is False
    kill.assert_not_called()
    assert not process.record.exists()


def test_exit_during_identity_read_is_not_a_new_process(monkeypatch):
    from pathlib import Path

    live = "123 (python) S " + " ".join(["0"] * 18 + ["123"])
    zombie = live.replace(") S ", ") Z ")
    reads = iter([live, zombie])
    monkeypatch.setattr(Path, "read_text", lambda self: next(reads))
    monkeypatch.setattr(Path, "read_bytes", lambda self: b"")
    monkeypatch.setattr(module.os, "getpgid", lambda pid: pid)
    monkeypatch.setattr(module.os, "readlink", lambda path: "/tmp/probe")
    with pytest.raises(ProcessLookupError):
        module.identity(123)


def test_live_empty_command_cannot_be_stamped_as_owned(monkeypatch):
    from pathlib import Path

    live = "123 (ollama) S " + " ".join(["0"] * 18 + ["123"])
    monkeypatch.setattr(Path, "read_text", lambda self: live)
    monkeypatch.setattr(Path, "read_bytes", lambda self: b"")
    monkeypatch.setattr(module.os, "getpgid", lambda pid: pid)
    monkeypatch.setattr(module.os, "readlink", lambda path: "/tmp/probe")
    with pytest.raises(OwnershipError, match="process_command_not_ready"):
        module.identity(123)


def test_start_waits_for_real_child_command_before_recording(monkeypatch, tmp_path):
    real_identity = module.identity
    calls = []

    def during_exec(pid):
        calls.append(pid)
        if len(calls) == 1:
            raise OwnershipError("process_command_not_ready")
        return real_identity(pid)

    monkeypatch.setattr(module, "identity", during_exec)
    process = QualificationProcess(tmp_path, "exec-race")
    try:
        process.start(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            cwd=tmp_path,
            environment={"PATH": os.defpath},
        )
        assert len(calls) >= 2
        data = json.loads(process.record.read_text())
        assert data["command_sha256"] != module.hashlib.sha256(b"").hexdigest()
    finally:
        process.stop()


def test_persistently_empty_command_fails_closed_and_reaps_child(monkeypatch, tmp_path):
    fake = Mock(pid=12345)
    fake.poll.return_value = None
    monkeypatch.setattr(module.subprocess, "Popen", Mock(return_value=fake))
    monkeypatch.setattr(
        module,
        "identity",
        Mock(side_effect=OwnershipError("process_command_not_ready")),
    )
    monkeypatch.setattr(module.time, "monotonic", Mock(side_effect=[0, 3]))
    process = QualificationProcess(tmp_path, "empty-command")
    with pytest.raises(OwnershipError, match="process_command_not_ready"):
        process.start([sys.executable], cwd=tmp_path, environment={})
    fake.terminate.assert_called_once()
    fake.wait.assert_called_once_with(timeout=5)
    assert not process.record.exists()
