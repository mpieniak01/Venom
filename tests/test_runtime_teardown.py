"""Exact engine ownership and complete stop, using fakes or harmless child processes."""

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.dev import runtime_teardown as rt
from scripts.dev import stack_profile as sp
from scripts.dev.qualification_process import QualificationProcess, identity


def test_unconfigured_stopped_engines_do_not_create_component_storage(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(rt, "validate_listeners", lambda *_: None)
    assert rt.engine_owners(tmp_path, {}) == []
    assert not (tmp_path / ".venom_runtime").exists()


@pytest.mark.parametrize("scope", ["user", "system"])
def test_systemd_owner_is_exact_and_explicit(tmp_path, monkeypatch, scope):
    observed = {"pid": 42, "command_sha256": "fixed"}
    monkeypatch.setattr(rt, "identity", lambda pid: observed)
    monkeypatch.setattr(
        rt.subprocess,
        "run",
        lambda command, **_: SimpleNamespace(returncode=0, stdout="42"),
    )
    stat = Path.stat
    read = Path.read_bytes
    monkeypatch.setattr(
        Path,
        "stat",
        lambda path, **kw: SimpleNamespace(st_uid=stat(tmp_path).st_uid)
        if str(path) == "/proc/42"
        else stat(path, **kw),
    )
    monkeypatch.setattr(
        Path,
        "read_bytes",
        lambda path: b"/opt/ollama\0serve"
        if str(path) == "/proc/42/cmdline"
        else read(path),
    )
    owner = rt._service(
        tmp_path,
        {"UNIT": "venom-ollama.service", "SCOPE": scope},
        "ollama",
        "UNIT",
        "SCOPE",
    )
    assert owner.pid == 42
    assert owner.observed == observed
    assert owner.service == (
        "systemctl",
        *(("--user",) if scope == "user" else ()),
        "stop",
        "--",
        "venom-ollama.service",
    )


@pytest.mark.parametrize(
    "values",
    [{"UNIT": "../../bad.service"}, {"UNIT": "venom.service", "SCOPE": "wrong"}],
)
def test_invalid_unit_or_scope_cannot_execute_systemctl(tmp_path, monkeypatch, values):
    monkeypatch.setattr(
        rt.subprocess, "run", lambda *_a, **_k: pytest.fail("must not execute")
    )
    with pytest.raises(ValueError):
        rt._service(tmp_path, values, "ollama", "UNIT", "SCOPE")


def test_unavailable_configured_unit_is_not_a_green_stop(tmp_path, monkeypatch):
    monkeypatch.setattr(
        rt.subprocess, "run", lambda *_a, **_k: SimpleNamespace(returncode=1, stdout="")
    )
    with pytest.raises(ValueError, match="Cannot verify"):
        rt._service(tmp_path, {"UNIT": "venom.service"}, "ollama", "UNIT", "SCOPE")


@pytest.mark.parametrize("owned", [False, True])
def test_listener_proof_never_adopts_a_process_by_port(monkeypatch, owned):
    monkeypatch.setattr(sp, "descendants", lambda _: [43])
    monkeypatch.setattr(
        rt.subprocess,
        "run",
        lambda *_a, **_k: SimpleNamespace(
            stdout='LISTEN 0 10 127.0.0.1:11434 0.0.0.0:* users:(("ollama",pid=43,fd=4))'
        ),
    )
    owners = [rt.EngineOwner("ollama", 42, {})] if owned else []
    if owned:
        rt.validate_listeners({}, owners)
    else:
        with pytest.raises(ValueError, match="no verified owner"):
            rt.validate_listeners({}, owners)


def test_missing_pid_visibility_is_not_green(monkeypatch):
    monkeypatch.setattr(
        rt.subprocess,
        "run",
        lambda *_a, **_k: SimpleNamespace(
            stdout="LISTEN 0 10 127.0.0.1:11434 0.0.0.0:*"
        ),
    )
    with pytest.raises(ValueError, match="no verified owner"):
        rt.validate_listeners({}, [])


def test_reused_pid_is_never_signalled(monkeypatch):
    monkeypatch.setattr(rt, "identity", lambda _: {"pid": 42, "start_ticks": "new"})
    monkeypatch.setattr(os, "kill", lambda *_: pytest.fail("must not signal"))
    with pytest.raises(ValueError, match="reused"):
        rt.stop_engines(
            [rt.EngineOwner("ollama", 42, {"pid": 42, "start_ticks": "old"})]
        )


def test_missing_engine_is_idempotent(monkeypatch):
    def absent(_):
        raise ProcessLookupError()

    monkeypatch.setattr(rt, "identity", absent)
    rt.stop_engines([rt.EngineOwner("ollama", 42, {})])


def test_manual_owned_engine_really_exits(tmp_path):
    process = QualificationProcess(tmp_path, "harmless")
    pid = process.start(
        [sys.executable, "-c", "import time; time.sleep(120)"],
        cwd=tmp_path,
        environment=dict(os.environ),
    )
    try:
        owner = rt.EngineOwner(
            "test", pid, identity(pid), receipts=rt._receipt_files(process.record)
        )
        rt.stop_engines([owner])
        assert not sp.running(pid)
        assert not process.record.exists()
    finally:
        process.stop(timeout=1)
        if process.process:
            process.process.wait(timeout=5)


def test_surviving_child_prevents_success(monkeypatch):
    monkeypatch.setattr(rt.time, "monotonic", iter([0, 0, 31]).__next__)
    monkeypatch.setattr(rt.select, "select", lambda *_: ([], [], []))
    with pytest.raises(ValueError, match="descendants"):
        rt.wait_engine_exit([42], timeout=30)


def test_pid_reuse_between_validation_and_snapshot_never_signals(monkeypatch):
    monkeypatch.setattr(rt, "_same", lambda _: True)
    monkeypatch.setattr(sp, "descendants", lambda _: [])
    monkeypatch.setattr(os, "pidfd_open", lambda _: 90)
    closed = []
    monkeypatch.setattr(os, "close", closed.append)
    monkeypatch.setattr(
        rt, "identity", lambda _: {"pid": 42, "start_ticks": "replacement"}
    )
    monkeypatch.setattr(
        rt.signal,
        "pidfd_send_signal",
        lambda *_: pytest.fail("foreign process must not be signalled"),
    )
    with pytest.raises(ValueError, match="reused"):
        rt.stop_engines(
            [rt.EngineOwner("test", 42, {"pid": 42, "start_ticks": "original"})]
        )
    assert closed == [90]


def test_symlink_pid_receipt_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(rt, "validate_listeners", lambda *_: None)
    target = tmp_path / "other"
    target.write_text("42")
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs/ollama.pid").symlink_to(target)
    with pytest.raises(ValueError, match="symlink"):
        rt.engine_owners(tmp_path, {})


def test_live_peer_blocks_variant_switch_and_shared_engine_stop(tmp_path, monkeypatch):
    (tmp_path / ".venom_runtime").mkdir()
    (tmp_path / ".venom_runtime/.host-api-owners.json").write_text(
        json.dumps([{"pid": 43, "stamp": "peer"}])
    )
    monkeypatch.setattr(sp, "owned_pid", lambda *_a, **_k: 42)
    monkeypatch.setattr(sp, "running", lambda _: True)
    monkeypatch.setattr(sp, "process_stamp", lambda _: ("peer", 0))
    with pytest.raises(ValueError, match="Another environment"):
        sp.check_variant_peers(tmp_path, {})


def test_retire_refuses_stale_stamp_without_killing_real_child(tmp_path):
    from scripts.dev.retire_process import retire

    process = QualificationProcess(tmp_path, "retire-proof")
    pid = process.start(
        [sys.executable, "-c", "import time; time.sleep(120)"],
        cwd=tmp_path,
        environment=dict(os.environ),
    )
    try:
        with pytest.raises(ValueError, match="identity differs"):
            retire(pid, "1", tmp_path)
        assert sp.running(pid)
        retire(pid, identity(pid)["start_ticks"], tmp_path)
        assert not sp.running(pid)
    finally:
        process.stop(timeout=1)
        if process.process:
            process.process.wait(timeout=5)


def test_api_rollback_forwards_original_spawn_identity_to_receipt_guard(
    tmp_path, monkeypatch
):
    from scripts.dev import startup_rollback as rollback

    calls = []
    monkeypatch.setattr(sp, "stop", lambda *a, **kw: calls.append((a, kw)))
    values = {"PID_FILE": str(tmp_path / "api.pid")}
    rollback.rollback_api(tmp_path, values, {"pid": 42, "stamp": "12345"})
    assert calls == [
        ((tmp_path, values, ("PID_FILE",)), {"expected": {"PID_FILE": (42, "12345")}})
    ]


@pytest.mark.parametrize(
    "receipt",
    [
        {"pid": True, "stamp": "1"},
        {"pid": 1, "stamp": "2"},
        {"pid": 42, "stamp": "bad"},
        {"pid": "42", "stamp": "1"},
    ],
)
def test_invalid_api_spawn_token_cannot_reach_retirement(
    tmp_path, monkeypatch, receipt
):
    from scripts.dev import startup_rollback as rollback

    monkeypatch.setattr(sp, "stop", lambda *_a, **_k: pytest.fail("must not stop"))
    with pytest.raises(ValueError, match="original API"):
        rollback.rollback_api(tmp_path, {}, receipt)


def test_api_spawn_returns_creation_stamp_and_rolls_back_if_recording_fails(
    tmp_path, monkeypatch
):
    from scripts.dev import startup_rollback as rollback
    from scripts.llm import with_gpu_libraries

    monkeypatch.setattr(with_gpu_libraries, "command_python", lambda *_: "/fake/python")
    monkeypatch.setattr(
        sp.subprocess, "Popen", lambda *_a, **_kw: SimpleNamespace(pid=42)
    )
    monkeypatch.setattr(sp, "process_stamp", lambda pid: ("12345", os.getuid()))
    values = {
        "PORT": "8820",
        "PID_FILE": str(tmp_path / "api.pid"),
        "BACKEND_LOG": str(tmp_path / "backend.log"),
    }
    monkeypatch.setattr(sp, "record_pid", lambda *_a: None)
    assert sp.spawn_api(tmp_path, values) == {"pid": 42, "stamp": "12345"}
    retired = []
    monkeypatch.setattr(rollback, "retire_unrecorded_api", lambda *a: retired.append(a))

    def failed_record(*args):
        raise OSError("disk failure")

    monkeypatch.setattr(sp, "record_pid", failed_record)
    with pytest.raises(OSError, match="disk failure"):
        sp.spawn_api(tmp_path, values)
    assert retired == [(tmp_path, {"pid": 42, "stamp": "12345"})]


def test_unrecorded_api_rollback_reuses_shared_pidfd_retirement(tmp_path, monkeypatch):
    from scripts.dev import retire_process
    from scripts.dev import startup_rollback as rollback

    called = []
    monkeypatch.setattr(retire_process, "retire", lambda *a: called.append(a))
    rollback.retire_unrecorded_api(tmp_path, {"pid": 42, "stamp": "12345"})
    assert called == [(42, "12345", tmp_path)]


def _engine(kind, pid, stamp, service=()):
    return rt.EngineOwner(
        kind, pid, {"pid": pid, "start_ticks": stamp}, service=service
    )


def test_failed_start_rolls_back_new_engines_and_preserves_reused_owners(
    tmp_path, monkeypatch
):
    import subprocess

    from scripts.dev import startup_rollback as rollback

    previous = [
        _engine("ollama", 42, "original"),
        _engine("vllm", 43, "old", ("systemctl", "--user", "stop", "vllm.service")),
    ]
    # Automatic restart of a preexisting explicit service is still preexisting.
    surviving = [previous[0], _engine("vllm", 44, "restart", previous[1].service)]
    created = _engine("multi_runtime", 45, "new")
    snapshots = iter([[*surviving, created], surviving])
    monkeypatch.setattr(rt, "engine_owners", lambda *_: next(snapshots))
    stopped = []
    monkeypatch.setattr(rt, "stop_engines", lambda owners: stopped.extend(owners))

    def fail(*args, **kwargs):
        assert kwargs["env"]["VENOM_STACK_RESOLVED"] == "1"
        raise subprocess.CalledProcessError(1, args[0])

    monkeypatch.setattr(rollback.subprocess, "run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        rollback.run_start_stack(tmp_path, {"VENOM_VARIANT": "studio"}, previous)
    assert stopped == [created]


def test_failed_start_does_not_adopt_changed_or_unverified_engine(
    tmp_path, monkeypatch
):
    from scripts.dev import startup_rollback as rollback

    def fail(*args, **kwargs):
        raise RuntimeError("UI failed")

    monkeypatch.setattr(rollback.subprocess, "run", fail)

    def unverifiable(*args):
        raise ValueError("unverified engine owner")

    monkeypatch.setattr(rt, "engine_owners", unverifiable)
    monkeypatch.setattr(rt, "stop_engines", lambda *_: pytest.fail("must not stop"))
    with pytest.raises(ValueError, match="unverified engine"):
        rollback.run_start_stack(tmp_path, {}, [])


def test_failed_start_reports_residual_replacement_engine_without_stopping_it(
    tmp_path, monkeypatch
):
    from scripts.dev import startup_rollback as rollback

    initial = _engine("ollama", 42, "initial")
    replacement = _engine("ollama", 43, "replacement")
    snapshots = iter([[initial], [replacement]])
    monkeypatch.setattr(rt, "engine_owners", lambda *_: next(snapshots))
    stopped = []
    monkeypatch.setattr(rt, "stop_engines", lambda owners: stopped.extend(owners))
    with pytest.raises(ValueError, match="rollback incomplete"):
        rollback.rollback_new_engines(tmp_path, {}, [])
    assert stopped == [initial]


def test_success_or_legacy_start_never_retires_preexisting_engines(
    tmp_path, monkeypatch
):
    from scripts.dev import startup_rollback as rollback

    monkeypatch.setattr(
        rt, "engine_owners", lambda *_: pytest.fail("must not inspect after success")
    )
    monkeypatch.setattr(rt, "stop_engines", lambda *_: pytest.fail("must not stop"))
    monkeypatch.setattr(
        rollback.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=0)
    )
    rollback.run_start_stack(tmp_path, {}, [_engine("ollama", 42, "old")])

    def fail(*args, **kwargs):
        raise RuntimeError("legacy launch failed")

    monkeypatch.setattr(rollback.subprocess, "run", fail)
    with pytest.raises(RuntimeError, match="legacy launch"):
        rollback.run_start_stack(tmp_path, {}, None)


@pytest.mark.parametrize("current_pid", [None, 43])
def test_component_failure_rolls_back_original_spawn_never_current_pid(
    tmp_path, monkeypatch, current_pid
):
    from scripts.dev import startup_rollback as rollback

    monkeypatch.setattr(sp, "preflight", lambda *_: None)
    owner_reads = iter([None, current_pid])
    monkeypatch.setattr(sp, "owned_pid", lambda *_a, **_kw: next(owner_reads))
    monkeypatch.setattr(sp, "running", lambda _: True)
    receipt = {"pid": 42, "stamp": "12345"}
    monkeypatch.setattr(sp, "spawn_api", lambda *_: receipt)
    calls = []
    monkeypatch.setattr(rollback, "rollback_api", lambda *a: calls.append(a))
    values = {"API_PROXY_TARGET": "http://127.0.0.1:8820"}
    with pytest.raises(ValueError, match="exited|owner changed"):
        sp.component(tmp_path, values, "api")
    assert calls == [(tmp_path, values, receipt)]


def test_startup_rollback_cli_binds_receipt_without_reading_mutable_pid_file(
    monkeypatch,
):
    from scripts.dev import startup_rollback as rollback

    receipt = {"pid": 42, "stamp": "12345"}
    monkeypatch.setattr(sys, "argv", ["startup_rollback", json.dumps(receipt)])
    calls = []
    monkeypatch.setattr(rollback, "rollback_api", lambda *a: calls.append(a))
    rollback.main()
    assert calls[0][0] == Path(rollback.__file__).resolve().parents[2]
    assert calls[0][2] == receipt
