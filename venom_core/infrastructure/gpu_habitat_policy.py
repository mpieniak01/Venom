"""Policy/safety helpers for GPUHabitat local runtime."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional


def resolve_positive_pid(pid_raw: Any) -> Optional[int]:
    try:
        pid = int(pid_raw)
    except (TypeError, ValueError):
        return None
    if pid <= 1:
        return None
    return pid


def validate_local_job_pid(
    *,
    job_info: dict[str, Any],
    path_factory: Callable[[str], Any] = Path,
) -> Optional[int]:
    raw_pid = job_info.get("pid")
    if raw_pid is None:
        return None

    pid = resolve_positive_pid(raw_pid)
    if pid is None:
        return None

    proc_dir = path_factory(f"/proc/{pid}")
    if not proc_dir.exists():
        return None

    output_dir = job_info.get("output_dir")
    if output_dir:
        try:
            expected_cwd = path_factory(str(output_dir)).resolve()
            actual_cwd = (proc_dir / "cwd").resolve()
            if actual_cwd != expected_cwd:
                return None
        except OSError:
            return None

    expected_script = job_info.get("script_path")
    if expected_script:
        try:
            cmdline_raw = (proc_dir / "cmdline").read_text(encoding="utf-8")
            args = [part for part in cmdline_raw.split("\x00") if part]
            expected_script_path = path_factory(str(expected_script)).resolve()
            has_expected_script = any(
                path_factory(arg).resolve() == expected_script_path for arg in args
            )
            if not has_expected_script:
                return None
        except (OSError, ValueError):
            return None

    return pid


def is_allowed_local_job_signal(
    *,
    sig: Any,
    allowed_local_job_signals: set[Any],
    signal_module: Any,
) -> bool:
    try:
        normalized_signal = signal_module.Signals(sig)
    except (TypeError, ValueError):
        return False
    return normalized_signal in allowed_local_job_signals


def is_pid_owned_by_current_user(
    *,
    pid: int,
    path_factory: Callable[[str], Any] = Path,
    get_uid_fn: Callable[[], int] | None = None,
) -> bool:
    if pid <= 1:
        return False
    if get_uid_fn is None:
        import os

        get_uid_fn = os.getuid

    try:
        status_content = path_factory(f"/proc/{pid}/status").read_text(encoding="utf-8")
        uid_line = next(
            (line for line in status_content.splitlines() if line.startswith("Uid:")),
            None,
        )
        if uid_line is None:
            return False
        parts = uid_line.split()
        if len(parts) < 2:
            return False
        process_real_uid = int(parts[1])
        return process_real_uid == get_uid_fn()
    except (OSError, ValueError, StopIteration):
        return False


def send_signal_to_validated_pid(
    *,
    pid: int,
    sig: Any,
    signal_module: Any,
    os_module: Any,
    subprocess_module: Any,
) -> bool:
    try:
        normalized_signal = signal_module.Signals(sig)
    except (TypeError, ValueError):
        return False

    if hasattr(os_module, "pidfd_open") and hasattr(signal_module, "pidfd_send_signal"):
        pidfd = None
        try:
            pidfd = os_module.pidfd_open(pid, 0)
            signal_module.pidfd_send_signal(pidfd, normalized_signal, None, 0)
            return True
        except OSError:
            return False
        finally:
            if pidfd is not None:
                try:
                    os_module.close(pidfd)
                except OSError:
                    pass

    try:
        subprocess_module.run(
            ["kill", "-s", normalized_signal.name, str(pid)],
            check=True,
            capture_output=True,
            text=True,
        )
        return True
    except (OSError, subprocess_module.SubprocessError):
        return False


def signal_validated_local_job(
    *,
    job_info: dict[str, Any],
    sig: Any,
    validate_local_job_pid_fn: Callable[[dict[str, Any]], Optional[int]],
    is_allowed_local_job_signal_fn: Callable[[Any], bool],
    is_pid_owned_by_current_user_fn: Callable[[int], bool],
    send_signal_to_validated_pid_fn: Callable[[int, Any], bool],
    logger: Any,
) -> bool:
    pid = validate_local_job_pid_fn(job_info)
    if pid is None:
        logger.warning(
            "Pomijam wysłanie sygnału %s: PID niezweryfikowany",
            sig,
        )
        return False

    if not is_allowed_local_job_signal_fn(sig):
        logger.warning(
            "Pomijam wysłanie sygnału %s: sygnał poza allowlist",
            sig,
        )
        return False

    if not is_pid_owned_by_current_user_fn(pid):
        logger.warning(
            "Pomijam wysłanie sygnału %s: PID nie należy do aktualnego użytkownika",
            sig,
        )
        return False

    return send_signal_to_validated_pid_fn(pid, sig)
