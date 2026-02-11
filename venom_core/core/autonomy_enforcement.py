"""Helpers for consistent autonomy permission enforcement across mutating paths."""

from venom_core.core.permission_guard import permission_guard


def _deny(message: str) -> None:
    raise PermissionError(message)


def require_file_write_permission() -> None:
    """Require file-write capability for mutating filesystem operations."""
    if not permission_guard.can_write_files():
        _deny(
            "AutonomyViolation: Brak uprawnień do zapisu plików "
            f"(Poziom: {permission_guard.get_current_level_name()})"
        )


def require_shell_permission() -> None:
    """Require shell execution capability."""
    if not permission_guard.can_execute_shell():
        _deny(
            "AutonomyViolation: Brak uprawnień do shella "
            f"(Poziom: {permission_guard.get_current_level_name()})"
        )


def require_core_patch_permission() -> None:
    """Require highest autonomy level for core patching operations."""
    current_level = permission_guard.get_current_level()
    if current_level < 40:
        _deny(
            "AutonomyViolation: Brak uprawnień do modyfikacji rdzenia systemu "
            f"(Poziom: {permission_guard.get_current_level_name()}, wymagany: ROOT)"
        )
