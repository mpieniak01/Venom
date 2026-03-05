from __future__ import annotations

import signal
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

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


def test_run_training_job_local_runtime_and_validation(tmp_path: Path) -> None:
    training_dir = tmp_path / "training"
    models_dir = tmp_path / "models"
    training_dir.mkdir()
    models_dir.mkdir()
    dataset = training_dir / "dataset.jsonl"
    dataset.write_text("{}", encoding="utf-8")
    settings = SimpleNamespace(
        ACADEMY_TRAINING_DIR=str(training_dir),
        ACADEMY_MODELS_DIR=str(models_dir),
    )
    logger = _Logger()

    manager = SimpleNamespace(
        use_local_runtime=True,
        enable_gpu=False,
        _has_unsloth=True,
        _is_path_within_base=lambda path, base: path.is_relative_to(base),
        _generate_training_script=lambda **_kwargs: "print('ok')",
        _run_local_training_job=lambda *_args: {
            "container_id": "local-1",
            "job_name": "job-1",
            "status": "running",
            "adapter_path": "x/adapter",
        },
    )

    result = runtime.run_training_job(
        manager=manager,
        request=runtime.TrainingJobRequest(
            dataset_path=str(dataset),
            base_model="phi",
            output_dir="out",
            lora_rank=8,
            learning_rate=0.0002,
            num_epochs=1,
            max_seq_length=512,
            batch_size=1,
            job_name="job-1",
        ),
        deps=runtime.TrainingJobDeps(
            settings=settings,
            logger=logger,
            docker_module=SimpleNamespace(types=SimpleNamespace(DeviceRequest=object)),
            image_not_found_error=RuntimeError,
        ),
    )
    assert result["job_name"] == "job-1"
    assert (models_dir / "out" / "train_script.py").exists()

    with pytest.raises(ValueError, match="Dataset nie istnieje"):
        runtime.run_training_job(
            manager=manager,
            request=runtime.TrainingJobRequest(
                dataset_path=str(training_dir / "missing.jsonl"),
                base_model="phi",
                output_dir="out",
                lora_rank=8,
                learning_rate=0.0002,
                num_epochs=1,
                max_seq_length=512,
                batch_size=1,
                job_name="job-1",
            ),
            deps=runtime.TrainingJobDeps(
                settings=settings,
                logger=logger,
                docker_module=SimpleNamespace(
                    types=SimpleNamespace(DeviceRequest=object)
                ),
                image_not_found_error=RuntimeError,
            ),
        )


def test_run_training_job_accepts_self_learning_storage_dataset(tmp_path: Path) -> None:
    storage_prefix = tmp_path / "storage"
    training_dir = storage_prefix / "data" / "training"
    models_dir = storage_prefix / "data" / "models"
    self_learning_dir = storage_prefix / "data" / "academy" / "self_learning" / "run-1"
    training_dir.mkdir(parents=True)
    models_dir.mkdir(parents=True)
    self_learning_dir.mkdir(parents=True)
    dataset = self_learning_dir / "dataset.jsonl"
    dataset.write_text("{}", encoding="utf-8")
    settings = SimpleNamespace(
        STORAGE_PREFIX=str(storage_prefix),
        ACADEMY_TRAINING_DIR=str(training_dir),
        ACADEMY_MODELS_DIR=str(models_dir),
    )
    logger = _Logger()

    manager = SimpleNamespace(
        use_local_runtime=True,
        enable_gpu=False,
        _has_unsloth=True,
        _is_path_within_base=lambda path, base: path.is_relative_to(base),
        _generate_training_script=lambda **_kwargs: "print('ok')",
        _run_local_training_job=lambda *_args: {
            "container_id": "local-2",
            "job_name": "job-self-learning",
            "status": "running",
            "adapter_path": "x/adapter",
        },
    )

    result = runtime.run_training_job(
        manager=manager,
        request=runtime.TrainingJobRequest(
            dataset_path=str(dataset),
            base_model="phi",
            output_dir="out-self-learning",
            lora_rank=8,
            learning_rate=0.0002,
            num_epochs=1,
            max_seq_length=512,
            batch_size=1,
            job_name="job-self-learning",
        ),
        deps=runtime.TrainingJobDeps(
            settings=settings,
            logger=logger,
            docker_module=SimpleNamespace(types=SimpleNamespace(DeviceRequest=object)),
            image_not_found_error=RuntimeError,
        ),
    )

    assert result["job_name"] == "job-self-learning"


def test_run_training_job_docker_runtime_paths(tmp_path: Path) -> None:
    training_dir = tmp_path / "training"
    models_dir = tmp_path / "models"
    training_dir.mkdir()
    models_dir.mkdir()
    dataset = training_dir / "dataset.jsonl"
    dataset.write_text("{}", encoding="utf-8")
    settings = SimpleNamespace(
        ACADEMY_TRAINING_DIR=str(training_dir),
        ACADEMY_MODELS_DIR=str(models_dir),
    )
    logger = _Logger()

    class _ImageNotFound(Exception):
        pass

    class _Images:
        def get(self, _name: str) -> None:
            raise _ImageNotFound("missing")

        def pull(self, _name: str) -> None:
            return None

    container = SimpleNamespace(id="abc123456789")
    manager = SimpleNamespace(
        use_local_runtime=False,
        enable_gpu=True,
        _has_unsloth=True,
        training_image="venom/train",
        client=SimpleNamespace(
            images=_Images(),
            containers=SimpleNamespace(run=lambda **_kwargs: container),
        ),
        training_containers={},
        _is_path_within_base=lambda path, base: path.is_relative_to(base),
        _generate_training_script=lambda **_kwargs: "print('ok')",
    )
    device_calls: list[dict[str, object]] = []
    docker_module = SimpleNamespace(
        types=SimpleNamespace(
            DeviceRequest=lambda **kwargs: device_calls.append(kwargs) or kwargs
        )
    )

    result = runtime.run_training_job(
        manager=manager,
        request=runtime.TrainingJobRequest(
            dataset_path=str(dataset),
            base_model="phi",
            output_dir="out2",
            lora_rank=8,
            learning_rate=0.0002,
            num_epochs=1,
            max_seq_length=512,
            batch_size=1,
            job_name="job-2",
        ),
        deps=runtime.TrainingJobDeps(
            settings=settings,
            logger=logger,
            docker_module=docker_module,
            image_not_found_error=_ImageNotFound,
        ),
    )
    assert result["status"] == "running"
    assert result["container_id"] == "abc123456789"
    assert "job-2" in manager.training_containers
    assert device_calls and device_calls[0]["count"] == -1
