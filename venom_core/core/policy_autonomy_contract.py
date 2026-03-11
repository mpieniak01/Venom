"""Canonical contract helpers for policy/autonomy enforcement decisions."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from venom_core.core.permission_guard import permission_guard


class EnforcementDecision(str, Enum):
    """Unified decision model across policy and autonomy checks."""

    ALLOW = "allow"
    BLOCK = "block"
    DEGRADED_ALLOW = "degraded_allow"


class EnforcementTechnicalContext(BaseModel):
    """Technical context exposed to audit and internal UI state."""

    current_autonomy_level: int
    current_autonomy_level_name: str
    required_level: int | None = None
    required_level_name: str | None = None
    skill_name: str | None = None
    operation: str | None = None
    phase: str | None = None
    provider: str | None = None
    tool: str | None = None
    forced_provider: str | None = None
    forced_tool: str | None = None
    intent: str | None = None
    session_id: str | None = None
    task_id: str | None = None
    enforcement_mode: str | None = None
    terminal: bool | None = None
    retryable: bool | None = None


class EnforcementBlockPayload(BaseModel):
    """Canonical payload for deny events."""

    decision: EnforcementDecision = EnforcementDecision.BLOCK
    reason_code: str | None = None
    user_message: str
    technical_context: EnforcementTechnicalContext
    tags: list[str] = Field(default_factory=list)


def _current_autonomy_context() -> tuple[int, str]:
    return (
        permission_guard.get_current_level(),
        permission_guard.get_current_level_name(),
    )


def build_policy_block_payload(
    *,
    reason_code: str | None,
    user_message: str,
    phase: str,
    operation: str,
    task_id: str | None,
    intent: str | None,
    planned_provider: str | None,
    forced_provider: str | None,
    forced_tool: str | None,
    session_id: str | None,
) -> EnforcementBlockPayload:
    """Build canonical payload for policy deny events."""
    current_level, current_level_name = _current_autonomy_context()
    technical_context = EnforcementTechnicalContext(
        current_autonomy_level=current_level,
        current_autonomy_level_name=current_level_name,
        operation=operation,
        phase=phase,
        provider=planned_provider,
        forced_provider=forced_provider,
        forced_tool=forced_tool,
        tool=forced_tool,
        intent=intent,
        session_id=session_id,
        task_id=task_id,
    )
    return EnforcementBlockPayload(
        reason_code=reason_code,
        user_message=user_message,
        technical_context=technical_context,
        tags=["policy", "blocked", phase],
    )


def build_autonomy_block_payload(
    *,
    user_message: str,
    operation: str,
    decision: EnforcementDecision = EnforcementDecision.BLOCK,
    required_level: int | None = None,
    required_level_name: str | None = None,
    skill_name: str | None = None,
    task_id: str | None = None,
    session_id: str | None = None,
    enforcement_mode: str | None = None,
    terminal: bool | None = None,
    retryable: bool | None = False,
) -> EnforcementBlockPayload:
    """Build canonical payload for autonomy deny events."""
    current_level, current_level_name = _current_autonomy_context()
    technical_context = EnforcementTechnicalContext(
        current_autonomy_level=current_level,
        current_autonomy_level_name=current_level_name,
        required_level=required_level,
        required_level_name=required_level_name,
        skill_name=skill_name,
        operation=operation,
        phase="autonomy_enforcement",
        session_id=session_id,
        task_id=task_id,
        enforcement_mode=enforcement_mode,
        terminal=terminal,
        retryable=retryable,
    )
    tags = ["autonomy", operation]
    if decision == EnforcementDecision.BLOCK:
        tags.append("blocked")
    elif decision == EnforcementDecision.DEGRADED_ALLOW:
        tags.append("degraded_allow")
    if skill_name:
        tags.append(f"skill:{skill_name}")
    return EnforcementBlockPayload(
        decision=decision,
        reason_code="AUTONOMY_PERMISSION_DENIED",
        user_message=user_message,
        technical_context=technical_context,
        tags=tags,
    )


def to_audit_details(payload: EnforcementBlockPayload) -> dict[str, Any]:
    """Convert canonical block payload to a flat audit details object."""
    technical = payload.technical_context.model_dump(exclude_none=True)
    details: dict[str, Any] = {
        "decision": payload.decision.value,
        "reason_code": payload.reason_code,
        "user_message": payload.user_message,
        "technical_context": technical,
        "tags": payload.tags,
    }
    details.update(technical)
    return details
