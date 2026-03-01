"""Runtime/job orchestration helpers for GPUHabitat."""

from __future__ import annotations

import os
import signal
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, Optional


def run_training_job(
    *,
    manager: Any,
    dataset_path: str,
    base_model: str,
    output_dir: str,
    lora_rank: int,
    learning_rate: float,
    num_epochs: int,
    max_seq_length: int,
    batch_size: int,
    job_name: Optional[str],
    settings: Any,
    logger: Any,
    docker_module: Any,
    image_not_found_error: type[BaseException],
) -> Dict[str, str]:
    training_base_dir = Path(settings.ACADEMY_TRAINING_DIR).resolve()
    dataset_path_obj = (training_base_dir / Path(dataset_path).name).resolve()
    if not dataset_path_obj.exists():
        raise ValueError("Dataset nie istnieje")

    if not manager._is_path_within_base(dataset_path_obj, training_base_dir):
        raise ValueError("Dataset path jest poza katalogiem Academy training")

    models_base_dir = Path(settings.ACADEMY_MODELS_DIR).resolve()
    output_dir_obj = (models_base_dir / Path(output_dir).name).resolve()
    if not manager._is_path_within_base(output_dir_obj, models_base_dir):
        raise ValueError("Output path jest poza katalogiem Academy models")
    output_dir_obj.mkdir(parents=True, exist_ok=True)

    resolved_job_name = job_name or f"training_{dataset_path_obj.stem}"

    logger.info(
        f"Uruchamianie treningu ({'LOCAL' if manager.use_local_runtime else 'DOCKER'}): "
        f"job={resolved_job_name}, model={base_model}, dataset={dataset_path_obj.name}"
    )

    try:
        use_unsloth = manager.enable_gpu and getattr(manager, "_has_unsloth", True)

        training_script = manager._generate_training_script(
            dataset_path=str(dataset_path_obj)
            if manager.use_local_runtime
            else "/workspace/dataset.jsonl",
            base_model=base_model,
            output_dir=str(output_dir_obj)
            if manager.use_local_runtime
            else "/workspace/output",
            lora_rank=lora_rank,
            learning_rate=learning_rate,
            num_epochs=num_epochs,
            max_seq_length=max_seq_length,
            batch_size=batch_size,
            use_unsloth=use_unsloth,
        )

        script_path = output_dir_obj / "train_script.py"
        with open(script_path, "w", encoding="utf-8") as script_handle:
            script_handle.write(training_script)

        if manager.use_local_runtime:
            return manager._run_local_training_job(
                resolved_job_name,
                script_path,
                output_dir_obj,
                dataset_path_obj,
            )

        try:
            manager.client.images.get(manager.training_image)
            logger.info(f"Obraz {manager.training_image} już istnieje")
        except image_not_found_error:
            logger.info(f"Pobieranie obrazu {manager.training_image}...")
            manager.client.images.pull(manager.training_image)

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

        device_requests = None
        if manager.enable_gpu:
            device_requests = [
                docker_module.types.DeviceRequest(count=-1, capabilities=[["gpu"]])
            ]

        safe_job_name = "".join(
            c if c.isalnum() or c in ("-", "_") else "_" for c in resolved_job_name
        )
        container = manager.client.containers.run(
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

        manager.training_containers[resolved_job_name] = {
            "container_id": container.id,
            "container": container,
            "dataset_path": str(dataset_path_obj),
            "output_dir": str(output_dir_obj),
            "status": "running",
        }

        logger.info(
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
        logger.error(error_msg)
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
    logger: Any,
) -> Dict[str, str]:
    check_local_dependencies_fn()
    log_file = output_dir / "training.log"

    env = os.environ.copy()
    if enable_gpu:
        env["CUDA_VISIBLE_DEVICES"] = "0"

    with open(log_file, "w") as stdout_handle:
        process = subprocess.Popen(
            ["python3", str(script_path)],
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
