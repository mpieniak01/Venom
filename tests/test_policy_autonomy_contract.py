"""Tests for canonical policy/autonomy enforcement contract helpers."""

from venom_core.core.permission_guard import permission_guard
from venom_core.core.policy_autonomy_contract import (
    EnforcementDecision,
    build_autonomy_block_payload,
    build_policy_block_payload,
    to_audit_details,
)


def test_build_policy_block_payload_sets_canonical_fields() -> None:
    previous_level = permission_guard.get_current_level()
    permission_guard.set_level(10)
    try:
        payload = build_policy_block_payload(
            reason_code="POLICY_PROVIDER_RESTRICTED",
            user_message="Provider blocked",
            phase="before_provider",
            operation="provider_selection",
            task_id="task-1",
            intent="RESEARCH",
            planned_provider="openai",
            forced_provider="openai",
            forced_tool=None,
            session_id="session-1",
        )
    finally:
        permission_guard.set_level(previous_level)

    assert payload.decision == EnforcementDecision.BLOCK
    assert payload.reason_code == "POLICY_PROVIDER_RESTRICTED"
    assert payload.technical_context.phase == "before_provider"
    assert payload.technical_context.operation == "provider_selection"
    assert payload.technical_context.task_id == "task-1"
    assert payload.technical_context.session_id == "session-1"
    assert payload.technical_context.provider == "openai"
    assert "policy" in payload.tags
    assert "blocked" in payload.tags
    assert "before_provider" in payload.tags


def test_build_autonomy_block_payload_sets_reason_code_and_required_levels() -> None:
    previous_level = permission_guard.get_current_level()
    permission_guard.set_level(0)
    try:
        payload = build_autonomy_block_payload(
            user_message="AutonomyViolation",
            operation="core_patch",
            required_level=40,
            required_level_name="ROOT",
            skill_name="core_skill",
            task_id="task-2",
            session_id="session-2",
        )
    finally:
        permission_guard.set_level(previous_level)

    assert payload.reason_code == "AUTONOMY_PERMISSION_DENIED"
    assert payload.technical_context.operation == "core_patch"
    assert payload.technical_context.required_level == 40
    assert payload.technical_context.required_level_name == "ROOT"
    assert payload.technical_context.task_id == "task-2"
    assert payload.technical_context.session_id == "session-2"
    assert "autonomy" in payload.tags
    assert "blocked" in payload.tags
    assert "core_patch" in payload.tags
    assert "skill:core_skill" in payload.tags


def test_to_audit_details_flattens_technical_context() -> None:
    payload = build_policy_block_payload(
        reason_code="POLICY_TOOL_RESTRICTED",
        user_message="Tool blocked",
        phase="before_tool",
        operation="tool_execution",
        task_id="task-3",
        intent="EXECUTION",
        planned_provider="vllm",
        forced_provider=None,
        forced_tool="shell",
        session_id="session-3",
    )
    details = to_audit_details(payload)

    assert details["decision"] == "block"
    assert details["reason_code"] == "POLICY_TOOL_RESTRICTED"
    assert details["user_message"] == "Tool blocked"
    assert details["phase"] == "before_tool"
    assert details["operation"] == "tool_execution"
    assert details["task_id"] == "task-3"
    assert details["session_id"] == "session-3"
    assert isinstance(details["technical_context"], dict)
