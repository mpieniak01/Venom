"""Runtime policy-gate contract tests executed in fast PR lane."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from venom_core.core.models import TaskRequest, TaskStatus
from venom_core.core.orchestrator import orchestrator_dispatch as dispatch_module
from venom_core.core.policy_gate import (
    PolicyDecision,
    PolicyEvaluationContext,
    PolicyEvaluationResult,
    PolicyReasonCode,
)
from venom_core.services.audit_stream import get_audit_stream


@pytest.fixture(autouse=True)
def _clear_audit_stream() -> None:
    stream = get_audit_stream()
    stream.clear()
    yield
    stream.clear()


@pytest.mark.asyncio
async def test_global_pre_execution_block_emits_canonical_runtime_audit() -> None:
    orch = MagicMock()
    orch.state_manager = MagicMock()
    orch.state_manager.update_status = AsyncMock()
    orch.state_manager.add_log = MagicMock()
    orch.state_manager.update_context = MagicMock()
    orch.request_tracer = MagicMock()
    orch._append_session_history = MagicMock()

    task_id = uuid4()
    request = TaskRequest(
        content="research blocked",
        session_id="session-runtime-1",
        forced_tool="browser",
    )
    context = PolicyEvaluationContext(
        content=request.content,
        intent="RESEARCH",
        planned_provider="openai",
        planned_tools=["browser"],
        session_id=request.session_id,
        forced_tool=request.forced_tool,
    )

    with (
        patch.object(dispatch_module.policy_gate, "_enabled", True),
        patch.object(
            dispatch_module.policy_gate,
            "evaluate_global_pre_execution",
            return_value=PolicyEvaluationResult(
                decision=PolicyDecision.BLOCK,
                reason_code=PolicyReasonCode.POLICY_TOOL_RESTRICTED,
                message="Tool blocked",
            ),
        ),
    ):
        blocked = await dispatch_module._handle_policy_block_global_pre_execution(
            orch,
            task_id,
            request,
            context,
        )

    assert blocked is True
    entries = get_audit_stream().get_entries(
        action="policy.blocked.global_pre_execution",
        limit=1,
    )
    assert len(entries) == 1
    entry = entries[0]
    assert entry.details["phase"] == "global_pre_execution"
    assert entry.details["operation"] == "orchestrator_execution"
    assert entry.details["reason_code"] == "POLICY_TOOL_RESTRICTED"
    orch.state_manager.update_status.assert_awaited_once_with(
        task_id,
        TaskStatus.FAILED,
        result="Tool blocked",
    )


def test_runtime_policy_context_does_not_mix_intent_into_planned_tools() -> None:
    request = TaskRequest(content="analyze", forced_tool=None)
    risk_context = dispatch_module._build_risk_context(
        request=request,
        intent="RESEARCH",
        tool_required=True,
    )
    ctx = PolicyEvaluationContext(
        content=request.content,
        intent="RESEARCH",
        planned_provider="openai",
        planned_tools=[],
        risk_context=risk_context,
    )

    assert ctx.planned_tools == []
    assert ctx.intent == "RESEARCH"
    assert ctx.risk_context["tool_required"] is True
