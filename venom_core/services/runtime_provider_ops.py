"""Provider/runtime command helpers extracted from RuntimeController."""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any, Callable


def start_backend(
    *,
    project_root: Path,
    get_service_status_fn: Callable[[Any], Any],
    backend_service_type: Any,
    service_status_running: Any,
    subprocess_module: Any,
    time_module: Any,
) -> dict[str, Any]:
    """Start backend via Makefile and verify process status."""
    try:
        subprocess_module.Popen(
            ["make", "start-dev"],
            cwd=str(project_root),
            stdout=subprocess_module.DEVNULL,
            stderr=subprocess_module.DEVNULL,
            start_new_session=True,
        )

        time_module.sleep(3)
        status = get_service_status_fn(backend_service_type)
        if status.status == service_status_running:
            return {
                "success": True,
                "message": f"Backend uruchomiony (PID {status.pid})",
            }
        return {
            "success": False,
            "message": "Backend nie uruchomił się w oczekiwanym czasie",
        }
    except Exception as exc:
        return {"success": False, "message": f"Błąd uruchamiania backend: {exc}"}


def stop_backend(*, project_root: Path, subprocess_module: Any) -> dict[str, Any]:
    """Stop backend via Makefile."""
    try:
        result = subprocess_module.run(
            ["make", "stop"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0:
            return {"success": True, "message": "Backend zatrzymany"}
        return {
            "success": False,
            "message": f"Błąd zatrzymywania backend: {result.stderr}",
        }
    except Exception as exc:
        return {"success": False, "message": f"Błąd zatrzymywania backend: {exc}"}


def start_ui(
    *,
    get_service_status_fn: Callable[[Any], Any],
    ui_service_type: Any,
    service_status_running: Any,
) -> dict[str, Any]:
    """UI is started by make start-dev; only verify status."""
    status = get_service_status_fn(ui_service_type)
    if status.status == service_status_running:
        return {
            "success": True,
            "message": f"UI uruchomiony (PID {status.pid})",
        }
    return {
        "success": False,
        "message": "UI nie jest uruchomiony. Użyj 'make start-dev' aby uruchomić cały stos.",
    }


def stop_ui() -> dict[str, Any]:
    """UI stop path is managed by make stop."""
    return {
        "success": True,
        "message": "UI zatrzymywany przez 'make stop'",
    }


def _start_command_service(
    *,
    command: str | None,
    start_sleep_seconds: int,
    missing_command_message: str,
    start_error_prefix: str,
    started_message: str,
    not_started_message: str,
    get_service_status_fn: Callable[[Any], Any],
    service_type: Any,
    service_status_running: Any,
    subprocess_module: Any,
    time_module: Any,
    on_started: Callable[[], None] | None = None,
) -> dict[str, Any]:
    if not command:
        return {"success": False, "message": missing_command_message}

    try:
        command_args = shlex.split(command)
        if not command_args:
            return {"success": False, "message": missing_command_message}
        subprocess_module.Popen(
            command_args,
            stdout=subprocess_module.DEVNULL,
            stderr=subprocess_module.DEVNULL,
            start_new_session=True,
        )
        time_module.sleep(start_sleep_seconds)
        status = get_service_status_fn(service_type)
        if status.status == service_status_running:
            if on_started is not None:
                on_started()
            return {"success": True, "message": started_message}
        return {
            "success": False,
            "message": not_started_message,
        }
    except Exception as exc:
        return {
            "success": False,
            "message": f"{start_error_prefix}: {exc}",
        }


def _stop_command_service(
    *,
    command: str | None,
    missing_command_message: str,
    stop_error_prefix: str,
    stopped_message: str,
    subprocess_module: Any,
) -> dict[str, Any]:
    if not command:
        return {"success": False, "message": missing_command_message}

    try:
        command_args = shlex.split(command)
        if not command_args:
            return {"success": False, "message": missing_command_message}
        result = subprocess_module.run(
            command_args,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return {"success": True, "message": stopped_message}
        return {
            "success": False,
            "message": f"{stop_error_prefix}: {result.stderr}",
        }
    except Exception as exc:
        return {
            "success": False,
            "message": f"{stop_error_prefix}: {exc}",
        }


def start_ollama(
    *,
    command: str | None,
    get_service_status_fn: Callable[[Any], Any],
    ollama_service_type: Any,
    service_status_running: Any,
    subprocess_module: Any,
    time_module: Any,
    refresh_runtime_version_fn: Callable[[], None],
) -> dict[str, Any]:
    return _start_command_service(
        command=command,
        start_sleep_seconds=3,
        missing_command_message="Brak skonfigurowanego OLLAMA_START_COMMAND w aktywnym pliku env",
        start_error_prefix="Błąd uruchamiania Ollama",
        started_message="Ollama uruchomiony",
        not_started_message="Ollama nie uruchomił się w oczekiwanym czasie",
        get_service_status_fn=get_service_status_fn,
        service_type=ollama_service_type,
        service_status_running=service_status_running,
        subprocess_module=subprocess_module,
        time_module=time_module,
        on_started=refresh_runtime_version_fn,
    )


def stop_ollama(*, command: str | None, subprocess_module: Any) -> dict[str, Any]:
    return _stop_command_service(
        command=command,
        missing_command_message="Brak skonfigurowanego OLLAMA_STOP_COMMAND w aktywnym pliku env",
        stop_error_prefix="Błąd zatrzymywania Ollama",
        stopped_message="Ollama zatrzymany",
        subprocess_module=subprocess_module,
    )


def start_vllm(
    *,
    command: str | None,
    get_service_status_fn: Callable[[Any], Any],
    vllm_service_type: Any,
    service_status_running: Any,
    subprocess_module: Any,
    time_module: Any,
) -> dict[str, Any]:
    return _start_command_service(
        command=command,
        start_sleep_seconds=5,
        missing_command_message="Brak skonfigurowanego VLLM_START_COMMAND w aktywnym pliku env",
        start_error_prefix="Błąd uruchamiania vLLM",
        started_message="vLLM uruchomiony",
        not_started_message="vLLM nie uruchomił się w oczekiwanym czasie",
        get_service_status_fn=get_service_status_fn,
        service_type=vllm_service_type,
        service_status_running=service_status_running,
        subprocess_module=subprocess_module,
        time_module=time_module,
    )


def stop_vllm(*, command: str | None, subprocess_module: Any) -> dict[str, Any]:
    return _stop_command_service(
        command=command,
        missing_command_message="Brak skonfigurowanego VLLM_STOP_COMMAND w aktywnym pliku env",
        stop_error_prefix="Błąd zatrzymywania vLLM",
        stopped_message="vLLM zatrzymany",
        subprocess_module=subprocess_module,
    )
