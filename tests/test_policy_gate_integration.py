"""Testy integracyjne dla orchestratora z policy gate."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from venom_core.contracts.routing import ReasonCode, RoutingDecision, RuntimeTarget
from venom_core.core.models import TaskRequest, TaskStatus
from venom_core.core.orchestrator.orchestrator_submit import submit_task
from venom_core.core.policy_gate import (
    PolicyDecision,
    PolicyEvaluationContext,
    PolicyEvaluationResult,
    PolicyReasonCode,
)
from venom_core.core.tracer import TraceStatus
from venom_core.services.audit_stream import get_audit_stream


@pytest.fixture(autouse=True)
def _clear_audit_stream():
    get_audit_stream().clear()
    yield
    get_audit_stream().clear()


@pytest.fixture
def mock_orchestrator():
    """Mock orchestratora dla testów."""
    from uuid import uuid4

    orch = MagicMock()
    orch._refresh_kernel_if_needed = MagicMock()
    orch.last_activity = None
    orch.state_manager = MagicMock()
    orch.request_tracer = MagicMock()
    orch.task_manager = MagicMock()
    orch._broadcast_event = AsyncMock()

    # Mock create_task
    task = MagicMock()
    task.id = uuid4()
    task.status = TaskStatus.PENDING
    orch.state_manager.create_task.return_value = task
    orch.state_manager.get_task.return_value = task
    orch.state_manager.add_log = MagicMock()
    orch.state_manager.update_status = AsyncMock()
    orch.state_manager.update_context = MagicMock()

    # Mock request tracer
    orch.request_tracer.create_trace = MagicMock()
    orch.request_tracer.add_step = MagicMock()
    orch.request_tracer.set_llm_metadata = MagicMock()
    orch.request_tracer.update_status = MagicMock()

    # Mock task manager
    orch.task_manager.is_paused = False
    orch.task_manager.check_capacity = AsyncMock(return_value=(True, 0))

    return orch


@pytest.mark.asyncio
async def test_policy_gate_disabled_allows_all(mock_orchestrator):
    """Test: gdy gate wyłączony, wszystkie zadania są akceptowane."""
    with patch.dict(os.environ, {"ENABLE_POLICY_GATE": "false"}):
        # Reset policy gate singleton
        from venom_core.core.policy_gate import policy_gate

        policy_gate._initialized = False
        policy_gate.__init__()

        request = TaskRequest(content="test request")

        with patch(
            "venom_core.core.orchestrator.orchestrator_submit.get_active_llm_runtime"
        ) as mock_runtime:
            mock_runtime.return_value = MagicMock(
                provider="local",
                model_name="test-model",
                endpoint="http://localhost",
                to_payload=MagicMock(return_value={}),
            )

            response = await submit_task(mock_orchestrator, request)

            assert (
                response.task_id
                == mock_orchestrator.state_manager.create_task.return_value.id
            )
            assert not response.policy_blocked
            assert response.reason_code is None


@pytest.mark.asyncio
async def test_policy_gate_enabled_allow_path(mock_orchestrator):
    """Test: gdy gate włączony i decyzja ALLOW, zadanie wykonywane normalnie."""
    with patch.dict(os.environ, {"ENABLE_POLICY_GATE": "true"}):
        # Reset policy gate singleton
        from venom_core.core.policy_gate import policy_gate

        policy_gate._initialized = False
        policy_gate.__init__()

        request = TaskRequest(content="test request")

        with patch(
            "venom_core.core.orchestrator.orchestrator_submit.get_active_llm_runtime"
        ) as mock_runtime:
            mock_runtime.return_value = MagicMock(
                provider="local",
                model_name="test-model",
                endpoint="http://localhost",
                to_payload=MagicMock(return_value={}),
            )

            response = await submit_task(mock_orchestrator, request)

            assert (
                response.task_id
                == mock_orchestrator.state_manager.create_task.return_value.id
            )
            assert not response.policy_blocked


@pytest.mark.asyncio
async def test_policy_gate_enabled_block_before_tool_emits_audit(mock_orchestrator):
    """Test: blokada global pre-execution emituje wpis audytowy."""
    with patch.dict(os.environ, {"ENABLE_POLICY_GATE": "true"}):
        from venom_core.core.policy_gate import policy_gate

        policy_gate._initialized = False
        policy_gate.__init__()

        with patch.object(
            policy_gate,
            "evaluate_global_pre_execution",
            return_value=PolicyEvaluationResult(
                decision=PolicyDecision.BLOCK,
                reason_code=PolicyReasonCode.POLICY_TOOL_RESTRICTED,
                message="Tool blocked by policy",
            ),
        ):
            task_id = mock_orchestrator.state_manager.create_task.return_value.id
            request = TaskRequest(
                content="test tool request",
                forced_tool="browser",
                session_id="session-1",
            )
            context = PolicyEvaluationContext(
                content=request.content,
                intent="RESEARCH",
                planned_provider="openai",
                planned_tools=["browser"],
                session_id=request.session_id,
                forced_tool=request.forced_tool,
                forced_provider=request.forced_provider,
            )
            handler = __import__(
                "venom_core.core.orchestrator.orchestrator_dispatch",
                fromlist=["_handle_policy_block_global_pre_execution"],
            )._handle_policy_block_global_pre_execution

            blocked = await handler(mock_orchestrator, task_id, request, context)

            assert blocked is True
            entry = get_audit_stream().get_entries(
                action="policy.blocked.global_pre_execution", limit=1
            )[0]
            assert entry.source == "core.policy"
            assert entry.status == "blocked"
            assert entry.details["decision"] == "block"
            assert entry.details["reason_code"] == "POLICY_TOOL_RESTRICTED"
            assert entry.details["intent"] == "RESEARCH"
            assert entry.details["provider"] == "openai"
            assert entry.details["forced_tool"] == "browser"
            assert entry.details["operation"] == "orchestrator_execution"
            assert entry.details["phase"] == "global_pre_execution"
            assert entry.details["session_id"] == "session-1"
            assert entry.details["task_id"] == str(task_id)
            assert isinstance(entry.details["current_autonomy_level"], int)
            assert entry.details["current_autonomy_level_name"]
            assert isinstance(entry.details["technical_context"], dict)


@pytest.mark.asyncio
async def test_policy_gate_logs_block_reason(mock_orchestrator):
    """Test: blokada policy na checkpointcie runtime powinna być zalogowana."""
    with patch.dict(os.environ, {"ENABLE_POLICY_GATE": "true"}):
        from venom_core.core.orchestrator import (
            orchestrator_dispatch as dispatch_module,
        )
        from venom_core.core.policy_gate import policy_gate

        policy_gate._initialized = False
        policy_gate.__init__()

        with patch.object(
            policy_gate,
            "evaluate_global_pre_execution",
            return_value=PolicyEvaluationResult(
                decision=PolicyDecision.BLOCK,
                reason_code=PolicyReasonCode.POLICY_TOOL_RESTRICTED,
                message="Tool not allowed",
            ),
        ):
            task_id = mock_orchestrator.state_manager.create_task.return_value.id
            request = TaskRequest(content="test", forced_tool="dangerous_tool")
            context = PolicyEvaluationContext(
                content=request.content,
                intent="SYSTEM_DIAGNOSTICS",
                planned_tools=[request.forced_tool],
                forced_tool=request.forced_tool,
            )

            await dispatch_module._handle_policy_block_global_pre_execution(
                mock_orchestrator,
                task_id,
                request,
                context,
            )

            assert any(
                "Policy gate blocked" in str(call)
                for call in mock_orchestrator.state_manager.add_log.call_args_list
            )


@pytest.mark.asyncio
async def test_policy_gate_tracer_step_on_block(mock_orchestrator):
    """Test: blokada policy na checkpointcie runtime powinna dodać krok do tracera."""
    with patch.dict(os.environ, {"ENABLE_POLICY_GATE": "true"}):
        from venom_core.core.orchestrator import (
            orchestrator_dispatch as dispatch_module,
        )
        from venom_core.core.policy_gate import policy_gate

        policy_gate._initialized = False
        policy_gate.__init__()

        with patch.object(
            policy_gate,
            "evaluate_global_pre_execution",
            return_value=PolicyEvaluationResult(
                decision=PolicyDecision.BLOCK,
                reason_code=PolicyReasonCode.POLICY_PROVIDER_RESTRICTED,
                message="Provider not allowed",
            ),
        ):
            task_id = mock_orchestrator.state_manager.create_task.return_value.id
            request = TaskRequest(content="test", forced_provider="restricted")
            context = PolicyEvaluationContext(
                content=request.content,
                intent="RESEARCH",
                planned_provider="restricted",
                forced_provider=request.forced_provider,
            )

            await dispatch_module._handle_policy_block_global_pre_execution(
                mock_orchestrator,
                task_id,
                request,
                context,
            )

            mock_orchestrator.request_tracer.add_step.assert_called()
            mock_orchestrator.request_tracer.update_status.assert_called_with(
                task_id,
                TraceStatus.FAILED,
            )


@pytest.mark.asyncio
async def test_submit_task_stores_routing_decision_in_task_context(mock_orchestrator):
    """RoutingDecision powinien trafić do context payload w submit flow."""
    with patch.dict(os.environ, {"ENABLE_POLICY_GATE": "false"}):
        from venom_core.core.policy_gate import policy_gate

        policy_gate._initialized = False
        policy_gate.__init__()

        request = TaskRequest(content="test request")
        decision = RoutingDecision(
            target_runtime=RuntimeTarget.LOCAL_OLLAMA,
            provider="ollama",
            model="gemma3:4b",
            reason_code=ReasonCode.DEFAULT_ECO_MODE,
            fallback_applied=False,
        )

        with (
            patch(
                "venom_core.core.orchestrator.orchestrator_submit.get_active_llm_runtime"
            ) as mock_runtime,
            patch(
                "venom_core.core.orchestrator.orchestrator_submit.routing_integration.build_routing_decision",
                return_value=decision,
            ),
        ):
            mock_runtime.return_value = MagicMock(
                provider="ollama",
                model_name="test-model",
                endpoint="http://localhost",
                to_payload=MagicMock(return_value={}),
            )

            await submit_task(mock_orchestrator, request)

            update_calls = mock_orchestrator.state_manager.update_context.call_args_list
            assert update_calls
            payload = update_calls[0].args[1]
            assert "routing_decision" in payload
            assert payload["routing_decision"]["provider"] == "ollama"
            assert payload["routing_decision"]["reason_code"] == "default_eco_mode"


@pytest.mark.asyncio
async def test_submit_task_does_not_block_on_legacy_provider_stage(
    mock_orchestrator,
):
    """Submit flow nie wykonuje już legacy provider-stage policy checks."""
    with patch.dict(os.environ, {"ENABLE_POLICY_GATE": "true"}):
        from venom_core.core.policy_gate import policy_gate

        policy_gate._initialized = False
        policy_gate.__init__()

        request = TaskRequest(content="test request")
        decision = RoutingDecision(
            target_runtime=RuntimeTarget.CLOUD_OPENAI,
            provider="openai",
            model="gpt-4o-mini",
            reason_code=ReasonCode.TASK_COMPLEXITY_HIGH,
            fallback_applied=False,
        )

        with (
            patch(
                "venom_core.core.orchestrator.orchestrator_submit.get_active_llm_runtime"
            ) as mock_runtime,
            patch(
                "venom_core.core.orchestrator.orchestrator_submit.routing_integration.build_routing_decision",
                return_value=decision,
            ),
        ):
            mock_runtime.return_value = MagicMock(
                provider="ollama",
                model_name="test-model",
                endpoint="http://localhost",
                to_payload=MagicMock(return_value={}),
            )

            response = await submit_task(mock_orchestrator, request)

            assert response.policy_blocked is False
            assert (
                response.task_id
                == mock_orchestrator.state_manager.create_task.return_value.id
            )


@pytest.mark.asyncio
async def test_submit_task_persists_fallback_flag_from_routing_decision(
    mock_orchestrator,
):
    """Fallback metadata z RoutingDecision ma być zapisywane do contextu."""
    with patch.dict(os.environ, {"ENABLE_POLICY_GATE": "false"}):
        from venom_core.core.policy_gate import policy_gate

        policy_gate._initialized = False
        policy_gate.__init__()

        request = TaskRequest(content="test request")
        decision = RoutingDecision(
            target_runtime=RuntimeTarget.LOCAL_VLLM,
            provider="vllm",
            model="model-x",
            reason_code=ReasonCode.FALLBACK_AUTH_ERROR,
            fallback_applied=True,
            fallback_chain=["openai", "vllm"],
        )

        with (
            patch(
                "venom_core.core.orchestrator.orchestrator_submit.get_active_llm_runtime"
            ) as mock_runtime,
            patch(
                "venom_core.core.orchestrator.orchestrator_submit.routing_integration.build_routing_decision",
                return_value=decision,
            ),
        ):
            mock_runtime.return_value = MagicMock(
                provider="ollama",
                model_name="test-model",
                endpoint="http://localhost",
                to_payload=MagicMock(return_value={}),
            )

            await submit_task(mock_orchestrator, request)
            payload = mock_orchestrator.state_manager.update_context.call_args_list[
                0
            ].args[1]
            assert payload["routing_decision"]["fallback_applied"] is True
            assert payload["routing_decision"]["fallback_chain"] == ["openai", "vllm"]
