from __future__ import annotations

import signal
import subprocess
import types
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from venom_core.infrastructure import gpu_habitat_runtime as runtime
from venom_core.services import onnx_runtime_cleanup


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


def test_dataset_path_resolution_and_allowed_roots_helpers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    training_dir = tmp_path / "training"
    training_dir.mkdir()
    existing_rel = tmp_path / "nested" / "dataset.jsonl"
    existing_rel.parent.mkdir(parents=True, exist_ok=True)
    existing_rel.write_text("{}", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    resolved_existing = runtime._resolve_dataset_path_for_request(
        dataset_path="nested/dataset.jsonl",
        training_base_dir=training_dir,
    )
    assert resolved_existing == existing_rel.resolve()

    resolved_missing = runtime._resolve_dataset_path_for_request(
        dataset_path="missing/sub/path.jsonl",
        training_base_dir=training_dir,
    )
    assert resolved_missing == (training_dir / "path.jsonl").resolve()

    settings = SimpleNamespace(
        REPO_ROOT=str(tmp_path), STORAGE_PREFIX=str(tmp_path / "storage")
    )
    roots = runtime._allowed_dataset_roots(settings, training_dir)
    assert roots[0] == training_dir
    assert roots[1] == (tmp_path.resolve() / "data" / "academy" / "self_learning")
    assert roots[2] == (
        (tmp_path / "storage").resolve() / "data" / "academy" / "self_learning"
    )


def test_run_training_job_rejects_dataset_outside_allowed_roots(tmp_path: Path) -> None:
    training_dir = tmp_path / "training"
    models_dir = tmp_path / "models"
    training_dir.mkdir()
    models_dir.mkdir()
    outside_dataset = tmp_path / "outside.jsonl"
    outside_dataset.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="poza dozwolonymi katalogami"):
        runtime.run_training_job(
            manager=SimpleNamespace(
                _is_path_within_base=lambda _path, _base: False,
            ),
            request=runtime.TrainingJobRequest(
                dataset_path=str(outside_dataset),
                base_model="phi",
                output_dir="out",
                lora_rank=8,
                learning_rate=0.0002,
                num_epochs=1,
                max_seq_length=512,
                batch_size=1,
                job_name="job-outside",
            ),
            deps=runtime.TrainingJobDeps(
                settings=SimpleNamespace(
                    ACADEMY_TRAINING_DIR=str(training_dir),
                    ACADEMY_MODELS_DIR=str(models_dir),
                    STORAGE_PREFIX="",
                ),
                logger=_Logger(),
                docker_module=SimpleNamespace(
                    types=SimpleNamespace(DeviceRequest=object)
                ),
                image_not_found_error=RuntimeError,
            ),
        )


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


def test_release_onnx_runtime_best_effort_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str, dict[str, object]]] = []

    def _safe_call(module_name: str, function_name: str, **kwargs: object) -> bool:
        calls.append((module_name, function_name, kwargs))
        return function_name == "release_onnx_simple_client"

    monkeypatch.setattr(onnx_runtime_cleanup, "_safe_call", _safe_call)

    assert onnx_runtime_cleanup.release_onnx_runtime_best_effort(wait=True) is True
    assert calls == [
        (
            "venom_core.api.routes.tasks",
            "release_onnx_task_runtime",
            {"wait": True},
        ),
        (
            "venom_core.api.routes.llm_simple",
            "release_onnx_simple_client",
            {},
        ),
    ]

    monkeypatch.setattr(
        onnx_runtime_cleanup,
        "_safe_call",
        lambda *_args, **_kwargs: False,
    )
    assert onnx_runtime_cleanup.release_onnx_runtime_best_effort(wait=False) is False


def test_onnx_safe_call_covers_success_and_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_kwargs: list[dict[str, object]] = []
    module_ok = types.SimpleNamespace(
        release_onnx_task_runtime=lambda **kwargs: call_kwargs.append(kwargs)
    )

    monkeypatch.setattr(
        "venom_core.services.onnx_runtime_cleanup.importlib.import_module",
        lambda _name: module_ok,
    )
    assert (
        onnx_runtime_cleanup._safe_call(
            "venom_core.api.routes.tasks",
            "release_onnx_task_runtime",
            wait=True,
        )
        is True
    )
    assert call_kwargs == [{"wait": True}]

    module_missing = types.SimpleNamespace(release_onnx_task_runtime="x")
    monkeypatch.setattr(
        "venom_core.services.onnx_runtime_cleanup.importlib.import_module",
        lambda _name: module_missing,
    )
    assert (
        onnx_runtime_cleanup._safe_call(
            "venom_core.api.routes.tasks",
            "release_onnx_task_runtime",
            wait=False,
        )
        is False
    )

    def _raise(_name: str):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "venom_core.services.onnx_runtime_cleanup.importlib.import_module",
        _raise,
    )
    assert (
        onnx_runtime_cleanup._safe_call(
            "venom_core.api.routes.tasks",
            "release_onnx_task_runtime",
            wait=False,
        )
        is False
    )


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


def test_run_training_job_local_runtime_resolves_unsloth_after_dependency_check(
    tmp_path: Path,
) -> None:
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
    calls: dict[str, object] = {}

    manager = SimpleNamespace(
        use_local_runtime=True,
        enable_gpu=True,
        _is_path_within_base=lambda path, base: path.is_relative_to(base),
    )

    def _check_local_dependencies() -> None:
        calls["checked"] = True
        manager._has_unsloth = False

    def _generate_training_script(**kwargs: object) -> str:
        calls["use_unsloth"] = kwargs.get("use_unsloth")
        return "print('ok')"

    manager._check_local_dependencies = _check_local_dependencies
    manager._generate_training_script = _generate_training_script
    manager._run_local_training_job = lambda *_args: {
        "container_id": "local-4",
        "job_name": "job-deps",
        "status": "running",
        "adapter_path": "x/adapter",
    }

    result = runtime.run_training_job(
        manager=manager,
        request=runtime.TrainingJobRequest(
            dataset_path=str(dataset),
            base_model="phi",
            output_dir="out-deps",
            lora_rank=8,
            learning_rate=0.0002,
            num_epochs=1,
            max_seq_length=512,
            batch_size=1,
            job_name="job-deps",
        ),
        deps=runtime.TrainingJobDeps(
            settings=settings,
            logger=logger,
            docker_module=SimpleNamespace(types=SimpleNamespace(DeviceRequest=object)),
            image_not_found_error=RuntimeError,
        ),
    )

    assert result["job_name"] == "job-deps"
    assert calls["checked"] is True
    assert calls["use_unsloth"] is False


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
        REPO_ROOT=str(tmp_path),
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


def test_run_training_job_accepts_self_learning_dataset_without_storage_prefix(
    tmp_path: Path,
) -> None:
    training_dir = tmp_path / "data" / "training"
    models_dir = tmp_path / "data" / "models"
    self_learning_dir = tmp_path / "data" / "academy" / "self_learning" / "run-1"
    training_dir.mkdir(parents=True)
    models_dir.mkdir(parents=True)
    self_learning_dir.mkdir(parents=True)
    dataset = self_learning_dir / "dataset.jsonl"
    dataset.write_text("{}", encoding="utf-8")
    settings = SimpleNamespace(
        REPO_ROOT=str(tmp_path),
        STORAGE_PREFIX="",
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
            "container_id": "local-3",
            "job_name": "job-self-learning-no-prefix",
            "status": "running",
            "adapter_path": "x/adapter",
        },
    )

    result = runtime.run_training_job(
        manager=manager,
        request=runtime.TrainingJobRequest(
            dataset_path=str(dataset),
            base_model="phi",
            output_dir="out-self-learning-no-prefix",
            lora_rank=8,
            learning_rate=0.0002,
            num_epochs=1,
            max_seq_length=512,
            batch_size=1,
            job_name="job-self-learning-no-prefix",
        ),
        deps=runtime.TrainingJobDeps(
            settings=settings,
            logger=logger,
            docker_module=SimpleNamespace(types=SimpleNamespace(DeviceRequest=object)),
            image_not_found_error=RuntimeError,
        ),
    )

    assert result["job_name"] == "job-self-learning-no-prefix"


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
