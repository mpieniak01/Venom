from __future__ import annotations

import signal
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from venom_core.infrastructure import gpu_habitat_runtime as runtime


class _Logger:
    def __init__(self) -> None:
        self.warnings: list[str] = []
        self.errors: list[str] = []

    def info(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def warning(self, msg: str, *args: Any, **_kwargs: Any) -> None:
        self.warnings.append(msg % args if args else msg)

    def error(self, msg: str, *args: Any, **_kwargs: Any) -> None:
        self.errors.append(msg % args if args else msg)


def test_get_local_job_status_process_and_pid_fallback(tmp_path: Path) -> None:
    log = tmp_path / "train.log"
    log.write_text("hello\n", encoding="utf-8")

    running = runtime.get_local_job_status(
        training_containers={
            "a": {
                "pid": 101,
                "process": SimpleNamespace(poll=lambda: None),
                "log_file": str(log),
            }
        },
        job_name="a",
        validate_local_job_pid_fn=lambda _info: None,
    )
    assert running["status"] == "running"

    finished = runtime.get_local_job_status(
        training_containers={
            "b": {
                "pid": 102,
                "process": SimpleNamespace(poll=lambda: 0),
                "log_file": str(log),
            }
        },
        job_name="b",
        validate_local_job_pid_fn=lambda _info: None,
    )
    assert finished["status"] == "finished"

    fallback = runtime.get_local_job_status(
        training_containers={
            "c": {
                "pid": 103,
                "process": None,
                "log_file": str(log),
            }
        },
        job_name="c",
        validate_local_job_pid_fn=lambda _info: 103,
    )
    assert fallback["status"] == "running"


def test_terminate_local_process_timeout_kills() -> None:
    events: list[str] = []

    class _Proc:
        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            events.append("terminate")

        def wait(self, timeout: int) -> None:
            raise subprocess.TimeoutExpired("cmd", timeout)

        def kill(self) -> None:
            events.append("kill")

    runtime.terminate_local_process(process=_Proc(), pid=777, logger=_Logger())
    assert events == ["terminate", "kill"]


def test_cleanup_helpers_cover_missing_and_fallback_paths() -> None:
    logger = _Logger()
    calls: list[str] = []

    runtime.cleanup_local_job(
        job_info={"pid": None, "process": SimpleNamespace(pid=None)},
        resolve_positive_pid_fn=lambda _value: None,
        terminate_local_process_fn=lambda _process, _pid: calls.append("terminate"),
        signal_validated_local_job_fn=lambda _job, _sig: calls.append("signal") is None,
        logger=logger,
    )
    assert any("Cannot determine valid PID" in msg for msg in logger.warnings)

    class _Container:
        def stop(self, timeout: int = 0) -> None:
            if timeout:
                raise TypeError("old sdk")

        def remove(self, force: bool = False) -> None:
            if force:
                raise TypeError("old sdk")

    runtime.cleanup_docker_job(
        job_name="x",
        get_job_container_fn=lambda _job: _Container(),
    )

    jobs = {"x": {"type": "local"}, "y": {"type": "docker"}}
    runtime.cleanup_job(
        job_name="x",
        training_containers=jobs,
        cleanup_local_job_fn=lambda _job: calls.append("local"),
        cleanup_docker_job_fn=lambda _job: calls.append("docker"),
        logger=logger,
    )
    runtime.cleanup_job(
        job_name="y",
        training_containers=jobs,
        cleanup_local_job_fn=lambda _job: calls.append("local"),
        cleanup_docker_job_fn=lambda _job: calls.append("docker"),
        logger=logger,
    )
    runtime.cleanup_job(
        job_name="missing",
        training_containers=jobs,
        cleanup_local_job_fn=lambda _job: calls.append("local"),
        cleanup_docker_job_fn=lambda _job: calls.append("docker"),
        logger=logger,
    )
    assert "local" in calls and "docker" in calls


def test_stream_job_logs_handles_decode_error() -> None:
    logger = _Logger()

    class _Container:
        def logs(self, **_kwargs: Any):
            return iter([b"ok", b"\xff\xfe", b"done"])

    lines = list(
        runtime.stream_job_logs(
            job_name="job-1",
            since_timestamp=None,
            get_job_container_fn=lambda _job: _Container(),
            logger=logger,
        )
    )
    assert lines == ["ok", "done"]


def test_cleanup_local_job_signals_pid_when_no_process() -> None:
    called: list[signal.Signals] = []
    runtime.cleanup_local_job(
        job_info={"pid": 333, "process": None},
        resolve_positive_pid_fn=lambda value: int(value) if value else None,
        terminate_local_process_fn=lambda _process, _pid: None,
        signal_validated_local_job_fn=lambda _job, sig: called.append(sig) is not None,
        logger=_Logger(),
    )
    assert called == [signal.SIGTERM]
