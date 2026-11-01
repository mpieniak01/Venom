"""Real harmless subprocesses exercise lifecycle; no SSH, models or provider calls."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import pytest

from venom_core.services.remote_training.lifecycle import (
    LOG_LIMIT,
    JobStore,
    atomic_json,
    group_alive,
    identity_alive,
    process_identity,
    signal_group,
)


def manifest(run_id="run-1", timeout=10):
    return {
        "run_id": run_id,
        "files": {},
        "identity": {"model": "fixture", "limits": {"max_seconds": timeout}},
    }


def prepared(store, value):
    state = store.prepare(value)
    upload = store.directory(value["run_id"]) / "input"
    upload.mkdir(exist_ok=True)
    atomic_json(upload / ".bundle-manifest.json", value)
    return state


def wait_state(
    store, run_id="run-1", statuses=("succeeded", "failed", "stopped", "timed_out")
):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        state = store.status(run_id)
        if state["status"] in statuses:
            return state
        time.sleep(0.02)
    raise AssertionError(store.status(run_id))


def launcher(store, code, *, detached=False):
    """Inject only a trusted local fixture command, never manifest argv."""
    processes = []

    def spawn(directory, attempt):
        request = directory / "attempts" / f"{attempt:04d}" / "request.json"
        command = [sys.executable, "-c", code, str(request)]
        if not detached:
            from venom_core.services.remote_training.supervisor import supervise

            thread = threading.Thread(
                target=supervise,
                args=(store.root, directory.name, attempt),
                kwargs={"worker_command": command},
                daemon=True,
            )

            class Owner:
                pid = os.getpid()

                def wait(self, timeout):
                    thread.join(timeout)
                    if thread.is_alive():
                        raise TimeoutError("fixture supervisor did not exit")

            process = Owner()
            processes.append(process)
            thread.start()
            return process
        script = (
            "import json,sys;from pathlib import Path;"
            "from venom_core.services.remote_training.supervisor import supervise;"
            "supervise(Path(sys.argv[1]),sys.argv[2],int(sys.argv[3]),worker_command=json.loads(sys.argv[4]))"
        )
        process = subprocess.Popen(
            [
                sys.executable,
                "-c",
                script,
                str(store.root),
                directory.name,
                str(attempt),
                json.dumps(command),
            ],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])},
        )
        processes.append(process)
        return process

    return spawn, processes


@pytest.fixture
def store(tmp_path):
    result = JobStore(tmp_path / "host")
    yield result
    for path in (result.root / "runs").glob("*/state.json"):
        data = json.loads(path.read_text())
        worker = data.get("worker")
        if worker and group_alive(worker["process_group"]):
            signal_group(worker, signal.SIGKILL)
        owner = data.get("supervisor")
        if owner and owner["pid"] != os.getpid() and identity_alive(owner):
            os.kill(owner["pid"], signal.SIGTERM)


def test_prepare_is_idempotent_but_rejects_changed_identity(store):
    first = prepared(store, manifest())
    assert prepared(store, manifest()) == first
    with pytest.raises(ValueError, match="identity_changed"):
        prepared(store, manifest(timeout=11))
    assert (
        json.loads((store.directory("run-1") / "manifest.json").read_text())
        == manifest()
    )


@pytest.mark.parametrize(
    "run_id", ["../elsewhere", "a/b", "", ".private", "x;touch", 123]
)
def test_run_ids_never_escape_root(store, run_id):
    with pytest.raises(ValueError, match="invalid_run_id"):
        prepared(store, manifest(run_id))


def test_symlink_run_is_rejected(store, tmp_path):
    (store.root / "runs" / "run-1").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink_run"):
        prepared(store, manifest())


def test_concurrent_start_is_once_and_completion_survives_new_client(store):
    prepared(store, manifest())
    spawn, processes = launcher(
        store,
        "import time;print('started',flush=True);time.sleep(0.3);print('done')",
        detached=True,
    )
    with patch.object(store, "_spawn", side_effect=spawn):
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(lambda _: store.start("run-1"), range(4)))
    assert len(processes) == 1
    assert {result["attempt"] for result in results} == {1}
    state = wait_state(JobStore(store.root))
    assert state["status"] == "succeeded"
    assert state["exit_code"] == 0
    assert state["attempt_root"] == "runs/run-1/attempts/0001"
    assert "done" in store.logs("run-1")
    assert store.start("run-1") == state
    processes[0].wait(timeout=5)


def test_failure_keeps_exit_code_and_logs_and_requires_explicit_resume(store):
    prepared(store, manifest())
    spawn, processes = launcher(
        store, "import sys;print('fixture-failure',flush=True);sys.exit(23)"
    )
    with patch.object(store, "_spawn", side_effect=spawn):
        store.start("run-1")
    state = wait_state(store)
    assert state["status"] == "failed"
    assert state["exit_code"] == 23
    assert "fixture-failure" in store.logs("run-1")
    with pytest.raises(ValueError, match="explicit_resume"):
        store.start("run-1")
    processes[0].wait(timeout=5)


def test_stop_and_resume_preserve_previous_output(store):
    prepared(store, manifest())
    code = (
        "import json,sys,time;from pathlib import Path;"
        "r=json.loads(Path(sys.argv[1]).read_text());"
        "p=Path(r['attempt_root'])/'result'/'checkpoint';p.mkdir(parents=True);"
        "(p/'state.json').write_text('checkpoint');print('started',flush=True);"
        "time.sleep(20 if not r['checkpoint'] else 0.1)"
    )
    spawn, processes = launcher(store, code)
    with patch.object(store, "_spawn", side_effect=spawn):
        store.start("run-1")
        wait_state(store, statuses=("running",))
        deadline = time.monotonic() + 5
        checkpoint = "attempts/0001/result/checkpoint"
        while not (store.directory("run-1") / checkpoint / "state.json").exists():
            assert time.monotonic() < deadline
            time.sleep(0.02)
        store.stop("run-1")
        assert wait_state(store)["status"] == "stopped"
        with pytest.raises(ValueError, match="checkpoint_path"):
            store.resume("run-1", "../outside")
        state = store.resume("run-1", checkpoint)
        assert state["attempt"] == 2
        assert wait_state(store)["status"] == "succeeded"
    assert (
        store.directory("run-1") / checkpoint / "state.json"
    ).read_text() == "checkpoint"
    assert store.stop("run-1")["status"] == "succeeded"
    for process in processes:
        process.wait(timeout=5)


def test_manifest_timeout_is_upper_bound(store):
    prepared(store, manifest(timeout=0.15))
    spawn, processes = launcher(store, "import time;time.sleep(20)")
    with patch.object(store, "_spawn", side_effect=spawn):
        store.start("run-1", timeout_seconds=100)
    state = wait_state(store)
    assert state["status"] == "timed_out"
    request = json.loads(
        (store.root / state["attempt_root"] / "request.json").read_text()
    )
    assert request["timeout_seconds"] == 0.15
    assert state["error"] == "wall_time_limit"
    assert not group_alive(state["worker"]["process_group"])
    processes[0].wait(timeout=5)


@pytest.mark.parametrize("value", [0, -1, float("inf"), float("nan")])
def test_invalid_operator_timeout_is_rejected(store, value):
    prepared(store, manifest())
    with pytest.raises(ValueError, match="timeout_invalid"):
        store.start("run-1", timeout_seconds=value)


def test_gpu_lock_survives_supervisor_death_and_orphan_can_be_stopped(store):
    prepared(store, manifest())
    prepared(store, manifest("run-2"))
    spawn, processes = launcher(store, "import time;time.sleep(20)", detached=True)
    with patch.object(store, "_spawn", side_effect=spawn):
        store.start("run-1")
        first = wait_state(store, statuses=("running",))
        processes[0].kill()
        processes[0].wait(timeout=5)
        assert store.status("run-1")["status"] == "orphaned"
        store.start("run-2")
        second = wait_state(store, "run-2")
        assert second["status"] == "failed"
        assert second["error"] == "host_gpu_busy"
        assert store.stop("run-1")["status"] == "stopped"
        assert not group_alive(first["worker"]["process_group"])
        processes[1].wait(timeout=5)


def test_log_retention_is_bounded(store):
    prepared(store, manifest())
    spawn, processes = launcher(
        store, "import sys;sys.stdout.write('x'*2200000);print('TAIL')"
    )
    with patch.object(store, "_spawn", side_effect=spawn):
        store.start("run-1")
    state = wait_state(store)
    log = store.root / state["attempt_root"] / "worker.log"
    assert state["status"] == "succeeded"
    assert log.stat().st_size <= LOG_LIMIT
    assert store.logs("run-1", 16).endswith("TAIL\n")
    with pytest.raises(ValueError, match="log_limit"):
        store.logs("run-1", LOG_LIMIT + 1)
    processes[0].wait(timeout=5)


def test_pid_reuse_does_not_authorize_signalling():
    child = subprocess.Popen(
        [sys.executable, "-c", "import time;time.sleep(20)"], start_new_session=True
    )
    try:
        current = process_identity(child.pid)
        assert current
        forged = {**current, "start_ticks": current["start_ticks"] + 1}
        with pytest.raises(RuntimeError, match="identity_changed"):
            signal_group(forged, signal.SIGTERM)
        assert child.poll() is None
    finally:
        child.terminate()
        child.wait(timeout=5)


def test_worker_leftover_children_are_terminated(store):
    prepared(store, manifest())
    code = "import subprocess,sys;subprocess.Popen([sys.executable,'-c','import time;time.sleep(20)'])"
    spawn, processes = launcher(store, code)
    with patch.object(store, "_spawn", side_effect=spawn):
        store.start("run-1")
    state = wait_state(store)
    assert state["status"] == "failed"
    assert state["error"] == "worker_left_running_children"
    assert not group_alive(state["worker"]["process_group"])
    processes[0].wait(timeout=5)


def test_stop_requested_before_supervisor_starts_does_not_run_worker(store):
    prepared(store, manifest())
    directory = store.directory("run-1")
    state = store._read(directory)
    state.update(
        status="stopping",
        stop_requested=True,
        attempt=1,
        supervisor=process_identity(os.getpid()),
    )
    atomic_json(directory / "state.json", state)
    from venom_core.services.remote_training.supervisor import supervise

    supervise(store.root, "run-1", 1, worker_command=["must-not-execute"])
    assert store.status("run-1")["status"] == "stopped"


def test_unuploaded_input_cannot_start(store):
    store.prepare(manifest())
    with pytest.raises(ValueError, match="destination_invalid"):
        store.start("run-1")


def test_modified_input_cannot_start(store):
    prepared(store, manifest())
    (store.directory("run-1") / "input" / "surprise.txt").write_text("not in manifest")
    with pytest.raises(ValueError, match="files_mismatch"):
        store.start("run-1")


def test_run_id_length_is_shared_with_bundle_contract(store):
    prepared(store, manifest("a" * 64))
    with pytest.raises(ValueError, match="invalid_run_id"):
        store.prepare(manifest("a" * 65))


def test_resume_cannot_replenish_run_time_budget(store):
    prepared(store, manifest(timeout=0.1))
    directory = store.directory("run-1")
    checkpoint = directory / "attempts/0001/result/checkpoint"
    checkpoint.mkdir(parents=True)
    state = store._read(directory)
    state.update(status="stopped", attempt=1, elapsed_seconds=0.1)
    atomic_json(directory / "state.json", state)
    with pytest.raises(ValueError, match="budget_exhausted"):
        store.resume("run-1", "attempts/0001/result/checkpoint")


def test_smoke_then_train_share_the_same_run_wall_budget(store):
    from types import SimpleNamespace

    prepared(store, manifest(timeout=10))
    # Budget carry-over is a persisted-state contract, independent of how long
    # Python/coverage takes to start a subprocess on a loaded test host.
    with patch.object(store, "_spawn", return_value=SimpleNamespace(pid=os.getpid())):
        first = store.start("run-1")
        first.update(status="succeeded", elapsed_seconds=3.25, exit_code=0)
        atomic_json(store.directory("run-1") / "state.json", first)
        second = store.start("run-1", stage="train")
    request = json.loads(
        (store.root / second["attempt_root"] / "request.json").read_text()
    )
    assert request["timeout_seconds"] == 6.75
    assert request["elapsed_before"] == 3.25
    assert second["elapsed_seconds"] == 3.25
    assert second["attempt"] == 2


def test_production_worker_uses_qualified_host_interpreter(store):
    from venom_core.services.remote_training.supervisor import worker_launch

    host = {
        "schema_version": 1,
        "host_id": "configured",
        "worker_python": "/qualified/model-python",
        "code_root": "/reviewed/code",
    }
    atomic_json(store.root / "host.json", host)
    argv, environment = worker_launch(store.root, store.root / "request.json", 77)
    assert argv[:6] == [
        "setpriv",
        "--pdeathsig",
        "TERM",
        "--",
        "/qualified/model-python",
        "-m",
    ]
    assert argv[6] == "venom_core.services.remote_training.worker"
    assert environment["PYTHONPATH"] == "/reviewed/code"
    assert environment["REMOTE_TRAINING_GPU_LOCK_FD"] == "77"


def test_unknown_existing_owner_cannot_authorize_second_start(store):
    from venom_core.services.remote_training import lifecycle

    prepared(store, manifest())
    directory = store.directory("run-1")
    state = store._read(directory)
    state.update(status="running", stage="smoke", supervisor={"pid": os.getpid()})
    atomic_json(directory / "state.json", state)
    with (
        patch.object(lifecycle, "process_identity", return_value=None),
        patch.object(store, "_spawn") as spawn,
    ):
        assert store.status("run-1")["status"] == "orphaned"
        store.start("run-1")
        spawn.assert_not_called()


def test_busy_host_fails_without_starting_a_worker(store):
    from venom_core.services.remote_training.lifecycle import file_lock

    prepared(store, manifest())
    spawn, processes = launcher(store, "raise AssertionError('must not execute')")
    with (
        file_lock(store.root / "gpu.lock"),
        patch.object(store, "_spawn", side_effect=spawn),
    ):
        store.start("run-1")
        state = wait_state(store)
    assert state["status"] == "failed"
    assert state["error"] == "host_gpu_busy"
    assert state["worker"] is None
    processes[0].wait(timeout=5)


def test_worker_spawn_failure_preserves_failure_state(store, monkeypatch):
    from venom_core.services.remote_training import supervisor

    prepared(store, manifest())
    spawn, processes = launcher(store, "print('never')")

    def cannot_spawn(*args, **kwargs):
        raise FileNotFoundError("missing fixture interpreter")

    monkeypatch.setattr(supervisor.subprocess, "Popen", cannot_spawn)
    with patch.object(store, "_spawn", side_effect=spawn):
        store.start("run-1")
        state = wait_state(store)
    assert state["status"] == "failed"
    assert state["error"] == "FileNotFoundError"
    assert state["exit_code"] is None
    processes[0].wait(timeout=5)


def test_stop_escalates_worker_ignoring_term_and_retains_lock_until_exit(store):
    prepared(store, manifest())
    code = "import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);print('ignoring',flush=True);time.sleep(20)"
    spawn, processes = launcher(store, code)
    with patch.object(store, "_spawn", side_effect=spawn):
        store.start("run-1")
        deadline = time.monotonic() + 5
        while "ignoring" not in store.logs("run-1"):
            assert time.monotonic() < deadline
            time.sleep(0.02)
        store.stop("run-1")
        state = wait_state(store)
    assert state["status"] == "stopped"
    assert state["exit_code"] == -signal.SIGKILL
    assert not group_alive(state["worker"]["process_group"])
    processes[0].wait(timeout=5)


def test_successful_resume_retry_does_not_spawn_or_spend_budget(store):
    prepared(store, manifest())
    checkpoint = "attempts/0001/result/checkpoint"
    (store.directory("run-1") / checkpoint).mkdir(parents=True)
    state_path = store.directory("run-1") / "state.json"
    state = json.loads(state_path.read_text())
    state.update(
        status="succeeded",
        stage="train",
        checkpoint=checkpoint,
        attempt=2,
        elapsed_seconds=10,
        exit_code=0,
    )
    atomic_json(state_path, state)
    with patch.object(store, "_spawn", side_effect=AssertionError("GPU retry")):
        assert store.resume("run-1", checkpoint) == state
