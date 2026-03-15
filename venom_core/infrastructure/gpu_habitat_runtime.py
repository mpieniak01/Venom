"""Runtime/job orchestration helpers for GPUHabitat."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, Optional


@dataclass(frozen=True)
class TrainingJobRequest:
    dataset_path: str
    base_model: str
    output_dir: str
    lora_rank: int
    learning_rate: float
    num_epochs: int
    max_seq_length: int
    batch_size: int
    job_name: Optional[str]


@dataclass(frozen=True)
class TrainingJobDeps:
    settings: Any
    logger: Any
    docker_module: Any
    image_not_found_error: type[BaseException]


def _resolve_dataset_path_for_request(
    *,
    dataset_path: str,
    training_base_dir: Path,
) -> Path:
    requested = Path(dataset_path).expanduser()
    if requested.is_absolute():
        return requested.resolve()
    requested_resolved = requested.resolve()
    if requested_resolved.exists():
        return requested_resolved
    return (training_base_dir / requested.name).resolve()


def _allowed_dataset_roots(settings: Any, training_base_dir: Path) -> list[Path]:
    roots = [training_base_dir.resolve()]
    repo_root = Path(getattr(settings, "REPO_ROOT", ".")).expanduser().resolve()
    roots.append(repo_root / "data" / "academy" / "self_learning")
    storage_prefix = str(getattr(settings, "STORAGE_PREFIX", "") or "").strip()
    if storage_prefix:
        roots.append(
            (Path(storage_prefix).resolve() / "data" / "academy" / "self_learning")
        )
    unique_roots: list[Path] = []
    for root in roots:
        if root not in unique_roots:
            unique_roots.append(root)
    return unique_roots


def _resolve_use_unsloth_for_training(*, manager: Any) -> bool:
    # Local runtime must detect optional Unsloth support before script selection.
    # Without this preflight, first-run fallback can incorrectly pick Unsloth path
    # and crash with `ModuleNotFoundError: unsloth`.
    use_unsloth = manager.enable_gpu and getattr(manager, "_has_unsloth", True)
    if not manager.use_local_runtime:
        return bool(use_unsloth)
    check_local_dependencies = getattr(manager, "_check_local_dependencies", None)
    if callable(check_local_dependencies):
        check_local_dependencies()
    return bool(manager.enable_gpu and getattr(manager, "_has_unsloth", False))


def _write_training_script(
    *,
    manager: Any,
    request: TrainingJobRequest,
    dataset_path_obj: Path,
    output_dir_obj: Path,
    use_unsloth: bool,
) -> Path:
    training_script = manager._generate_training_script(
        dataset_path=str(dataset_path_obj)
        if manager.use_local_runtime
        else "/workspace/dataset.jsonl",
        base_model=request.base_model,
        output_dir=str(output_dir_obj)
        if manager.use_local_runtime
        else "/workspace/output",
        lora_rank=request.lora_rank,
        learning_rate=request.learning_rate,
        num_epochs=request.num_epochs,
        max_seq_length=request.max_seq_length,
        batch_size=request.batch_size,
        use_unsloth=use_unsloth,
    )
    script_path = output_dir_obj / "train_script.py"
    with open(script_path, "w", encoding="utf-8") as script_handle:
        script_handle.write(training_script)
    return script_path


def _ensure_training_image_available(
    *,
    manager: Any,
    logger: Any,
    image_not_found_error: type[BaseException],
) -> None:
    try:
        manager.client.images.get(manager.training_image)
        logger.info(f"Obraz {manager.training_image} już istnieje")
    except image_not_found_error:
        logger.info(f"Pobieranie obrazu {manager.training_image}...")
        manager.client.images.pull(manager.training_image)


def _build_docker_device_requests(*, manager: Any, docker_module: Any) -> Any:
    if not manager.enable_gpu:
        return None
    return [docker_module.types.DeviceRequest(count=-1, capabilities=[["gpu"]])]


def _launch_docker_training_container(
    *,
    manager: Any,
    deps: TrainingJobDeps,
    resolved_job_name: str,
    dataset_path_obj: Path,
    output_dir_obj: Path,
) -> Any:
    _ensure_training_image_available(
        manager=manager,
        logger=deps.logger,
        image_not_found_error=deps.image_not_found_error,
    )
    volumes = {
        str(dataset_path_obj): {
            "bind": "/workspace/dataset.jsonl",
            "mode": "ro",
        },
        str(output_dir_obj): {
            "bind": "/workspace/output",
            "mode": "rw",
        },
    }
    device_requests = _build_docker_device_requests(
        manager=manager,
        docker_module=deps.docker_module,
    )
    safe_job_name = "".join(
        c if c.isalnum() or c in ("-", "_") else "_" for c in resolved_job_name
    )
    return manager.client.containers.run(
        image=manager.training_image,
        command="python /workspace/output/train_script.py",
        volumes=volumes,
        device_requests=device_requests,
        detach=True,
        remove=False,
        name=f"venom-training-{safe_job_name}",
        environment={
            "CUDA_VISIBLE_DEVICES": "0" if manager.enable_gpu else "",
        },
    )


def _register_training_container(
    *,
    manager: Any,
    resolved_job_name: str,
    container: Any,
    dataset_path_obj: Path,
    output_dir_obj: Path,
) -> None:
    manager.training_containers[resolved_job_name] = {
        "container_id": container.id,
        "container": container,
        "dataset_path": str(dataset_path_obj),
        "output_dir": str(output_dir_obj),
        "status": "running",
    }


def run_training_job(
    *,
    manager: Any,
    request: TrainingJobRequest,
    deps: TrainingJobDeps,
) -> Dict[str, str]:
    training_base_dir = Path(deps.settings.ACADEMY_TRAINING_DIR).resolve()
    dataset_path_obj = _resolve_dataset_path_for_request(
        dataset_path=request.dataset_path,
        training_base_dir=training_base_dir,
    )
    if not dataset_path_obj.exists():
        raise ValueError("Dataset nie istnieje")

    allowed_roots = _allowed_dataset_roots(deps.settings, training_base_dir)
    if not any(
        manager._is_path_within_base(dataset_path_obj, allowed_root)
        for allowed_root in allowed_roots
    ):
        raise ValueError("Dataset path jest poza dozwolonymi katalogami Academy")

    models_base_dir = Path(deps.settings.ACADEMY_MODELS_DIR).resolve()
    output_dir_obj = (models_base_dir / Path(request.output_dir).name).resolve()
    if not manager._is_path_within_base(output_dir_obj, models_base_dir):
        raise ValueError("Output path jest poza katalogiem Academy models")
    output_dir_obj.mkdir(parents=True, exist_ok=True)

    resolved_job_name = request.job_name or f"training_{dataset_path_obj.stem}"

    deps.logger.info(
        f"Uruchamianie treningu ({'LOCAL' if manager.use_local_runtime else 'DOCKER'}): "
        f"job={resolved_job_name}, model={request.base_model}, dataset={dataset_path_obj.name}"
    )

    try:
        use_unsloth = _resolve_use_unsloth_for_training(manager=manager)
        script_path = _write_training_script(
            manager=manager,
            request=request,
            dataset_path_obj=dataset_path_obj,
            output_dir_obj=output_dir_obj,
            use_unsloth=use_unsloth,
        )

        if manager.use_local_runtime:
            return manager._run_local_training_job(
                resolved_job_name,
                script_path,
                output_dir_obj,
                dataset_path_obj,
            )

        container = _launch_docker_training_container(
            manager=manager,
            deps=deps,
            resolved_job_name=resolved_job_name,
            dataset_path_obj=dataset_path_obj,
            output_dir_obj=output_dir_obj,
        )
        _register_training_container(
            manager=manager,
            resolved_job_name=resolved_job_name,
            container=container,
            dataset_path_obj=dataset_path_obj,
            output_dir_obj=output_dir_obj,
        )

        deps.logger.info(
            f"Kontener treningowy uruchomiony: {container.id[:12]} (job={resolved_job_name})"
        )

        return {
            "container_id": container.id,
            "job_name": resolved_job_name,
            "status": "running",
            "adapter_path": str(output_dir_obj / "adapter"),
        }
    except Exception as exc:
        error_msg = f"Błąd podczas uruchamiania treningu: {exc}"
        deps.logger.error(error_msg)
        raise RuntimeError(error_msg) from exc


def run_local_training_job(
    *,
    job_name: str,
    script_path: Path,
    output_dir: Path,
    dataset_path: Path,
    enable_gpu: bool,
    training_containers: dict[str, Any],
    check_local_dependencies_fn: Callable[[], None],
    python_bin: str | None,
    logger: Any,
) -> Dict[str, str]:
    check_local_dependencies_fn()
    log_file = output_dir / "training.log"

    env = os.environ.copy()
    if enable_gpu:
        env["CUDA_VISIBLE_DEVICES"] = "0"
    # Local Academy training must run without external experiment tracking setup.
    env.setdefault("WANDB_DISABLED", "true")
    env.setdefault("WANDB_MODE", "disabled")
    # Force writable HuggingFace cache in local runtime to avoid inheriting
    # non-writable defaults (for example /root/.cache in service environments).
    hf_cache_root = output_dir / ".hf-cache"
    hf_datasets_cache = hf_cache_root / "datasets"
    hf_hub_cache = hf_cache_root / "hub"
    hf_assets_cache = hf_cache_root / "assets"
    for cache_dir in (hf_cache_root, hf_datasets_cache, hf_hub_cache, hf_assets_cache):
        cache_dir.mkdir(parents=True, exist_ok=True)
    env.setdefault("HF_HOME", str(hf_cache_root))
    env.setdefault("HF_DATASETS_CACHE", str(hf_datasets_cache))
    env.setdefault("HUGGINGFACE_HUB_CACHE", str(hf_hub_cache))
    env.setdefault("HF_ASSETS_CACHE", str(hf_assets_cache))

    executable = (python_bin or "").strip() or sys.executable or "python3"

    with open(log_file, "w") as stdout_handle:
        process = subprocess.Popen(
            [executable, str(script_path)],
            stdout=stdout_handle,
            stderr=subprocess.STDOUT,
            env=env,
            cwd=str(output_dir),
            start_new_session=True,
        )

    training_containers[job_name] = {
        "pid": process.pid,
        "process": process,
        "script_path": str(script_path),
        "log_file": str(log_file),
        "dataset_path": str(dataset_path),
        "output_dir": str(output_dir),
        "status": "running",
        "type": "local",
    }

    logger.info(
        f"Proces treningowy uruchomiony lokalnie: PID={process.pid} (job={job_name})"
    )
    return {
        "container_id": f"local-{process.pid}",
        "job_name": job_name,
        "status": "running",
        "adapter_path": str(output_dir / "adapter"),
    }


def get_training_status(
    *,
    training_containers: dict[str, Any],
    job_name: str,
    get_job_container_fn: Callable[[str], Any],
    get_local_job_status_fn: Callable[[str], Dict[str, Optional[str]]],
    logger: Any,
) -> Dict[str, str | None]:
    job_info = training_containers[job_name]
    if job_info.get("type") == "local":
        return get_local_job_status_fn(job_name)

    container = get_job_container_fn(job_name)
    try:
        container.reload()
        status = container.status
        if status == "running":
            job_status = "running"
        elif status in {"created", "restarting"}:
            job_status = "preparing"
        elif status == "exited":
            exit_code = container.attrs["State"]["ExitCode"]
            job_status = "finished" if exit_code == 0 else "failed"
        elif status in {"dead", "removing"}:
            job_status = "failed"
        else:
            job_status = "failed"

        logs = container.logs(tail=50).decode("utf-8")
        job_info["status"] = job_status
        return {
            "status": job_status,
            "logs": logs,
            "container_id": container.id,
        }
    except Exception as exc:
        logger.error(f"Błąd podczas pobierania statusu: {exc}")
        return {
            "status": "failed",
            "error": str(exc),
            "container_id": container.id if hasattr(container, "id") else None,
        }


def get_local_job_status(
    *,
    training_containers: dict[str, Any],
    job_name: str,
    validate_local_job_pid_fn: Callable[[Dict[str, Any]], Optional[int]],
) -> Dict[str, Optional[str]]:
    job_info = training_containers[job_name]
    pid = job_info.get("pid")
    process = job_info.get("process")
    log_file = Path(job_info.get("log_file", ""))

    status = "unknown"
    if process:
        retcode = process.poll()
        if retcode is None:
            status = "running"
        elif retcode == 0:
            status = "finished"
        else:
            status = "failed"
    else:
        status = (
            "running" if validate_local_job_pid_fn(job_info) is not None else "finished"
        )

    job_info["status"] = status
    logs = ""
    if log_file.exists():
        try:
            file_size = log_file.stat().st_size
            with open(log_file, "r") as logs_handle:
                if file_size > 4000:
                    logs_handle.seek(file_size - 4000)
                logs = logs_handle.read()
        except Exception as exc:
            logs = f"Error reading logs: {exc}"

    return {
        "status": status,
        "logs": logs,
        "container_id": f"local-{pid}",
    }


def terminate_local_process(*, process: Any, pid: int, logger: Any) -> None:
    if process.poll() is None:
        logger.info(f"Terminating local process {pid}")
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


def cleanup_local_job(
    *,
    job_info: Dict[str, Any],
    resolve_positive_pid_fn: Callable[[Any], Optional[int]],
    terminate_local_process_fn: Callable[[Any, int], None],
    signal_validated_local_job_fn: Callable[[Dict[str, Any], signal.Signals], bool],
    logger: Any,
) -> None:
    process = job_info.get("process")
    pid = job_info.get("pid")

    if process:
        process_pid = resolve_positive_pid_fn(pid)
        if process_pid is None:
            process_pid = resolve_positive_pid_fn(getattr(process, "pid", None))
        if process_pid is None:
            logger.warning(
                "Cannot determine valid PID for local process during cleanup"
            )
            return
        terminate_local_process_fn(process, process_pid)
        return

    if pid:
        signal_validated_local_job_fn(job_info, signal.SIGTERM)


def cleanup_docker_job(
    *,
    job_name: str,
    get_job_container_fn: Callable[[str], Any],
) -> None:
    container = get_job_container_fn(job_name)
    try:
        container.stop(timeout=10)
    except TypeError:
        container.stop()

    try:
        container.remove(force=True)
    except TypeError:
        container.remove()


def cleanup_job(
    *,
    job_name: str,
    training_containers: dict[str, Any],
    cleanup_local_job_fn: Callable[[Dict[str, Any]], None],
    cleanup_docker_job_fn: Callable[[str], None],
    logger: Any,
) -> None:
    if job_name not in training_containers:
        logger.warning("Job cleanup pominięty: wskazany job nie istnieje")
        return

    try:
        job_info = training_containers[job_name]
        if job_info.get("type") == "local":
            cleanup_local_job_fn(job_info)
        else:
            cleanup_docker_job_fn(job_name)

        del training_containers[job_name]
        logger.info(f"Usunięto job: {job_name}")
    except Exception as exc:
        logger.error(f"Błąd podczas czyszczenia joba: {exc}")
    finally:
        training_containers.pop(job_name, None)


def stream_job_logs(
    *,
    job_name: str,
    since_timestamp: Optional[int],
    get_job_container_fn: Callable[[str], Any],
    logger: Any,
) -> Iterator[str]:
    container = get_job_container_fn(job_name)
    try:
        log_stream = container.logs(
            stream=True,
            follow=True,
            timestamps=True,
            since=since_timestamp,
        )
        for log_line in log_stream:
            try:
                line = log_line.decode("utf-8").strip()
                if line:
                    yield line
            except UnicodeDecodeError:
                continue
    except Exception as exc:
        logger.error(f"Błąd podczas streamowania logów: {exc}")
        yield f"Error streaming logs: {str(exc)}"
