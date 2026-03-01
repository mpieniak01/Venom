"""Health/probe helpers for RuntimeController."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

import psutil


def apply_process_metrics(
    *,
    info: Any,
    pid: int,
    get_process_info_fn: Callable[[int], Optional[dict[str, float | int]]],
) -> None:
    process_info = get_process_info_fn(pid)
    if not process_info:
        return
    info.pid = pid
    info.cpu_percent = process_info["cpu_percent"]
    info.memory_mb = process_info["memory_mb"]
    uptime_seconds = process_info.get("uptime_seconds")
    if uptime_seconds is not None:
        info.uptime_seconds = int(uptime_seconds)


def read_pid_file(*, pid_files: dict[Any, Path], service_type: Any) -> Optional[int]:
    pid_file = pid_files.get(service_type)
    if not pid_file or not pid_file.exists():
        return None
    with open(pid_file, "r") as pid_handle:
        return int(pid_handle.read().strip())


def update_pid_file_service_status(
    *,
    info: Any,
    service_type: Any,
    read_pid_file_fn: Callable[[Any], Optional[int]],
    get_process_info_fn: Callable[[int], Optional[dict[str, float | int]]],
    apply_process_metrics_fn: Callable[[Any, int], None],
    service_type_enum: Any,
    service_status_enum: Any,
) -> None:
    try:
        pid = read_pid_file_fn(service_type)
        if pid is None:
            info.status = service_status_enum.STOPPED
            return

        process_info = get_process_info_fn(pid)
        if not process_info:
            info.status = service_status_enum.STOPPED
            return

        info.status = service_status_enum.RUNNING
        apply_process_metrics_fn(info, pid)
        if service_type == service_type_enum.BACKEND:
            info.port = 8000
        elif service_type == service_type_enum.UI:
            info.port = 3000
    except Exception as exc:
        info.status = service_status_enum.ERROR
        info.error_message = str(exc)


def update_llm_status(
    *,
    info: Any,
    port: int,
    process_match: str,
    service_type: Any,
    check_port_listening_fn: Callable[[int], bool],
    apply_process_metrics_fn: Callable[[Any, int], None],
    get_service_runtime_version_fn: Callable[[Any], Optional[str]],
    refresh_ollama_runtime_version_fn: Callable[..., Optional[str]],
    service_type_enum: Any,
    service_status_enum: Any,
) -> None:
    info.port = port
    info.runtime_version = get_service_runtime_version_fn(service_type)
    if not check_port_listening_fn(port):
        info.status = service_status_enum.STOPPED
        return

    info.status = service_status_enum.RUNNING
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            proc_name = (proc.info.get("name") or "").lower()
            cmdline = " ".join(proc.info.get("cmdline") or []).lower()
            if process_match in proc_name or process_match in cmdline:
                pid = proc.info["pid"]
                apply_process_metrics_fn(info, pid)
                break
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    if service_type == service_type_enum.LLM_OLLAMA:
        info.runtime_version = refresh_ollama_runtime_version_fn(force=False)


def check_port_listening(*, process_monitor: Any, port: int) -> bool:
    return process_monitor.check_port_listening(port)
