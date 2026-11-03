"""Detached, fixed-entrypoint supervisor with inherited host GPU ownership."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import time
from pathlib import Path

from .host import load_host
from .lifecycle import (
    LOG_LIMIT,
    TERMINAL,
    JobStore,
    account_elapsed,
    atomic_json,
    file_lock,
    group_alive,
    log_base,
    process_identity,
    signal_group,
)


def _append(path: Path, chunk: bytes) -> None:
    with file_lock(path.with_suffix(".log.lock")):
        if path.is_symlink():
            raise ValueError("remote_training_log_symlink")
        previous = path.read_bytes() if path.exists() else b""
        base, _ = log_base(path) if path.exists() else (0, False)
        retained = (previous + chunk)[-LOG_LIMIT:]
        base += len(previous) + len(chunk) - len(retained)
        temporary = path.with_suffix(".tmp")
        descriptor = os.open(
            temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600
        )
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(retained)
        temporary.replace(path)
        stat = path.stat()
        atomic_json(
            path.with_suffix(".offset.json"),
            {"base_offset": base, "inode": stat.st_ino, "device": stat.st_dev},
        )


def _drain(child: subprocess.Popen, path: Path) -> None:
    if child.stdout is None:
        return
    for _ in range(16):
        try:
            chunk = os.read(child.stdout.fileno(), 65536)
        except BlockingIOError:
            return
        if not chunk:
            return
        _append(path, chunk)


def _finish(store: JobStore, run_id: str, attempt: int, **values) -> None:
    directory = store.directory(run_id)
    with file_lock(directory / ".state.lock"):
        state = store._read(directory)
        if state["attempt"] != attempt:
            raise RuntimeError("remote_training_attempt_changed")
        if values.get("status") in TERMINAL and state["status"] not in TERMINAL:
            account_elapsed(state)
        state.update(**values, updated_at=time.time())
        from .milestones import seal_attempt

        seal_attempt(directory, state)
        atomic_json(directory / "state.json", state)


def _terminate(child: subprocess.Popen, identity: dict, log: Path) -> None:
    signal_group(identity, signal.SIGTERM)
    deadline = time.monotonic() + 3
    while group_alive(identity["process_group"]) and time.monotonic() < deadline:
        _drain(child, log)
        child.poll()
        time.sleep(0.05)
    if group_alive(identity["process_group"]):
        signal_group(identity, signal.SIGKILL)
    child.wait(timeout=5)
    deadline = time.monotonic() + 5
    while group_alive(identity["process_group"]):
        if time.monotonic() > deadline:
            raise RuntimeError("remote_training_group_not_quiescent")
        time.sleep(0.05)


def worker_launch(
    root: Path, request_path: Path, gpu_lock: int
) -> tuple[list[str], dict[str, str]]:
    """Control Python may differ from the separately qualified model interpreter."""
    host = load_host(root)
    environment = os.environ.copy()
    environment["PYTHONPATH"] = host["code_root"]
    environment["HF_HUB_OFFLINE"] = "1"
    environment["TRANSFORMERS_OFFLINE"] = "1"
    environment["TOKENIZERS_PARALLELISM"] = "false"
    environment["REMOTE_TRAINING_GPU_LOCK_FD"] = str(gpu_lock)
    argv = [
        "setpriv",
        "--pdeathsig",
        "TERM",
        "--",
        host["worker_python"],
        "-m",
        "venom_core.services.remote_training.worker",
        str(request_path),
    ]
    return argv, environment


def supervise(
    root: Path, run_id: str, attempt: int, *, worker_command: list[str] | None = None
) -> None:
    """worker_command is an in-process test seam, never deserialized or exposed by CLI."""
    store = JobStore(root)
    directory = store.directory(run_id)
    with file_lock(directory / ".state.lock"):
        state = store._read(directory)
        if state["attempt"] != attempt or state["status"] not in {
            "starting",
            "stopping",
        }:
            return
        if state["supervisor"] != process_identity(os.getpid()):
            raise RuntimeError("remote_training_supervisor_identity_mismatch")
        if state.get("stop_requested"):
            account_elapsed(state)
            state.update(status="stopped", finished_at=time.time())
            atomic_json(directory / "state.json", state)
            return
        attempt_root = store.root / state["attempt_root"]
        request_path = attempt_root / "request.json"
        request = json.loads(request_path.read_text())
    child = None
    identity = None
    log = attempt_root / "worker.log"
    result = "failed"
    error = None
    exit_code = None
    try:
        with file_lock(store.root / "gpu.lock", blocking=False) as gpu_lock:
            if worker_command is None:
                argv, environment = worker_launch(store.root, request_path, gpu_lock)
            else:
                environment = os.environ.copy()
                environment["REMOTE_TRAINING_GPU_LOCK_FD"] = str(gpu_lock)
                argv = worker_command
            child = subprocess.Popen(
                argv,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                pass_fds=(gpu_lock,),
                env=environment,
            )
            identity = process_identity(child.pid)
            if identity is None:
                raise RuntimeError("remote_training_worker_start_unconfirmed")
            if child.stdout is None:
                raise RuntimeError("remote_training_worker_pipe_missing")
            os.set_blocking(child.stdout.fileno(), False)
            _finish(
                store,
                run_id,
                attempt,
                status="running",
                worker=identity,
                heartbeat_at=time.time(),
            )
            startup_elapsed = max(
                0, time.time() - state.get("attempt_started_at", time.time())
            )
            deadline = time.monotonic() + max(
                0, request["timeout_seconds"] - startup_elapsed
            )
            last_heartbeat = 0.0
            while True:
                _drain(child, log)
                with file_lock(directory / ".state.lock"):
                    state = store._read(directory)
                if state.get("stop_requested"):
                    result = "stopped"
                    _terminate(child, identity, log)
                    break
                if time.monotonic() >= deadline:
                    result, error = "timed_out", "wall_time_limit"
                    _terminate(child, identity, log)
                    break
                code = child.poll()
                if code is not None:
                    if group_alive(identity["process_group"]):
                        _terminate(child, identity, log)
                        error = "worker_left_running_children"
                        break
                    result = "succeeded" if code == 0 else "failed"
                    error = None if code == 0 else "worker_nonzero_exit"
                    break
                if time.monotonic() - last_heartbeat >= 1:
                    _finish(store, run_id, attempt, heartbeat_at=time.time())
                    last_heartbeat = time.monotonic()
                time.sleep(0.05)
            exit_code = child.wait(timeout=5)
            _drain(child, log)
    except BlockingIOError:
        error = "host_gpu_busy"
    except Exception as exc:
        error = type(exc).__name__
        if child is not None and identity is not None:
            _terminate(child, identity, log)
            exit_code = child.returncode
    finally:
        if child is not None and child.stdout is not None:
            child.stdout.close()
    _finish(
        store,
        run_id,
        attempt,
        status=result,
        error=error,
        exit_code=exit_code,
        finished_at=time.time(),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("run_id")
    parser.add_argument("attempt", type=int)
    args = parser.parse_args()
    supervise(args.root, args.run_id, args.attempt)


if __name__ == "__main__":
    main()
