"""Helpers for consistent autonomy permission enforcement across mutating paths."""

import os
from typing import Any

from venom_core.core.permission_guard import permission_guard
from venom_core.core.policy_autonomy_contract import (
    EnforcementBlockPayload,
    EnforcementDecision,
    build_autonomy_block_payload,
    to_audit_details,
)
from venom_core.services.audit_stream import get_audit_stream
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


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
    mode = os.getenv("AUTONOMY_ENFORCEMENT_MODE", "hard").strip().lower()
    normalized_mode = "soft" if mode == "soft" else "hard"
    is_hard = normalized_mode == "hard"
    payload = build_autonomy_block_payload(
        user_message=message,
        operation=operation,
        decision=(
            EnforcementDecision.BLOCK if is_hard else EnforcementDecision.DEGRADED_ALLOW
        ),
        required_level=required_level,
        required_level_name=required_level_name,
        skill_name=skill_name,
        task_id=task_id,
        session_id=session_id,
        enforcement_mode=normalized_mode,
        terminal=is_hard,
        retryable=False,
    )
    details = to_audit_details(payload)
    get_audit_stream().publish(
        source="core.autonomy",
        action="autonomy.blocked" if is_hard else "autonomy.degraded_allow",
        actor="system",
        status="blocked" if is_hard else "degraded",
        details=details,
    )
    if not is_hard:
        logger.warning(
            "Autonomy soft-gate: allow with warning (operation=%s, level=%s)",
            operation,
            permission_guard.get_current_level_name(),
        )
        return
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


def require_desktop_input_permission() -> None:
    """Require desktop input control capability (mouse/keyboard automation)."""
    if not permission_guard.can_control_desktop_input():
        _deny(
            "AutonomyViolation: Brak uprawnień do automatyzacji desktop "
            f"(Poziom: {permission_guard.get_current_level_name()})",
            operation="desktop_input",
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
