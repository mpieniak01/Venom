"""Helpers for consistent autonomy permission enforcement across mutating paths."""

from typing import Any

from venom_core.core.permission_guard import permission_guard
from venom_core.core.policy_autonomy_contract import (
    EnforcementBlockPayload,
    build_autonomy_block_payload,
    to_audit_details,
)
from venom_core.services.audit_stream import get_audit_stream


class AutonomyPermissionDenied(PermissionError):
    """PermissionError carrying canonical autonomy deny payload for UI/API mapping."""

    def __init__(self, payload: EnforcementBlockPayload):
        super().__init__(payload.user_message)
        self.payload = payload
        self.decision = payload.decision.value
        self.reason_code = payload.reason_code or "AUTONOMY_PERMISSION_DENIED"
        self.user_message = payload.user_message
        self.technical_context: dict[str, Any] = payload.technical_context.model_dump(
            exclude_none=True
        )
        self.tags = list(payload.tags)


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
    payload = build_autonomy_block_payload(
        user_message=message,
        operation=operation,
        required_level=required_level,
        required_level_name=required_level_name,
        skill_name=skill_name,
        task_id=task_id,
        session_id=session_id,
    )
    details = to_audit_details(payload)
    if skill_name:
        details["skill_name"] = skill_name
    get_audit_stream().publish(
        source="core.autonomy",
        action="autonomy.blocked",
        actor="system",
        status="blocked",
        details=details,
    )
    raise AutonomyPermissionDenied(payload)


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
