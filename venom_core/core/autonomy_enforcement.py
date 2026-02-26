"""Helpers for consistent autonomy permission enforcement across mutating paths."""

from venom_core.core.permission_guard import permission_guard
from venom_core.services.audit_stream import get_audit_stream


def _deny(
    message: str,
    *,
    operation: str,
    required_level: int | None = None,
    required_level_name: str | None = None,
    skill_name: str | None = None,
    task_id: str | None = None,
    session_id: str | None = None,
) -> None:
    current_level = permission_guard.get_current_level()
    details = {
        "operation": operation,
        "current_level": current_level,
        "current_level_name": permission_guard.get_current_level_name(),
    }
    if required_level is not None:
        details["required_level"] = required_level
    if required_level_name:
        details["required_level_name"] = required_level_name
    if skill_name:
        details["skill_name"] = skill_name
    if task_id:
        details["task_id"] = task_id
    if session_id:
        details["session_id"] = session_id
    get_audit_stream().publish(
        source="core.autonomy",
        action="autonomy.blocked",
        actor="system",
        status="blocked",
        details=details,
    )
    raise PermissionError(message)


def require_file_write_permission() -> None:
    """Require file-write capability for mutating filesystem operations."""
    if not permission_guard.can_write_files():
        _deny(
            "AutonomyViolation: Brak uprawnień do zapisu plików "
            f"(Poziom: {permission_guard.get_current_level_name()})",
            operation="file_write",
        )


def require_shell_permission() -> None:
    """Require shell execution capability."""
    if not permission_guard.can_execute_shell():
        _deny(
            "AutonomyViolation: Brak uprawnień do shella "
            f"(Poziom: {permission_guard.get_current_level_name()})",
            operation="shell_execution",
        )


def require_core_patch_permission() -> None:
    """Require highest autonomy level for core patching operations."""
    current_level = permission_guard.get_current_level()
    if current_level < 40:
        _deny(
            "AutonomyViolation: Brak uprawnień do modyfikacji rdzenia systemu "
            f"(Poziom: {permission_guard.get_current_level_name()}, wymagany: ROOT)",
            operation="core_patch",
            required_level=40,
            required_level_name="ROOT",
        )
