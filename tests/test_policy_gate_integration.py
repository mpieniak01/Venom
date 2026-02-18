"""Testy integracyjne dla orchestratora z policy gate."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from venom_core.contracts.routing import ReasonCode, RoutingDecision, RuntimeTarget
from venom_core.core.models import TaskRequest, TaskStatus
from venom_core.core.orchestrator.orchestrator_submit import submit_task
from venom_core.core.policy_gate import (
    PolicyDecision,
    PolicyEvaluationResult,
    PolicyReasonCode,
)
from venom_core.core.tracer import TraceStatus


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
async def test_policy_gate_enabled_block_before_provider(mock_orchestrator):
    """Test: gdy gate blokuje przed wyborem providera, zadanie nie jest wykonywane."""
    with patch.dict(os.environ, {"ENABLE_POLICY_GATE": "true"}):
        # Reset policy gate singleton
        from venom_core.core.policy_gate import policy_gate

        policy_gate._initialized = False
        policy_gate.__init__()

        # Mock evaluate to return BLOCK
        with patch.object(
            policy_gate,
            "evaluate_before_provider_selection",
            return_value=PolicyEvaluationResult(
                decision=PolicyDecision.BLOCK,
                reason_code=PolicyReasonCode.POLICY_UNSAFE_CONTENT,
                message="Unsafe content detected",
            ),
        ):
            request = TaskRequest(content="dangerous request")

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
                assert response.policy_blocked is True
                assert response.reason_code == "POLICY_UNSAFE_CONTENT"
                assert response.user_message == "Unsafe content detected"
                assert response.status == TaskStatus.FAILED

                # Verify task was marked as failed
                mock_orchestrator.state_manager.update_status.assert_called_once()


@pytest.mark.asyncio
async def test_policy_gate_logs_block_reason(mock_orchestrator):
    """Test: blokada policy powinna być zalogowana."""
    with patch.dict(os.environ, {"ENABLE_POLICY_GATE": "true"}):
        from venom_core.core.policy_gate import policy_gate

        policy_gate._initialized = False
        policy_gate.__init__()

        with patch.object(
            policy_gate,
            "evaluate_before_provider_selection",
            return_value=PolicyEvaluationResult(
                decision=PolicyDecision.BLOCK,
                reason_code=PolicyReasonCode.POLICY_TOOL_RESTRICTED,
                message="Tool not allowed",
            ),
        ):
            request = TaskRequest(content="test", forced_tool="dangerous_tool")

            with patch(
                "venom_core.core.orchestrator.orchestrator_submit.get_active_llm_runtime"
            ) as mock_runtime:
                mock_runtime.return_value = MagicMock(
                    provider="local",
                    model_name="test-model",
                    endpoint="http://localhost",
                    to_payload=MagicMock(return_value={}),
                )

                await submit_task(mock_orchestrator, request)

                # Verify log was added
                assert any(
                    "Policy gate blocked" in str(call)
                    for call in mock_orchestrator.state_manager.add_log.call_args_list
                )


@pytest.mark.asyncio
async def test_policy_gate_tracer_step_on_block(mock_orchestrator):
    """Test: blokada policy powinna dodać krok do tracera."""
    with patch.dict(os.environ, {"ENABLE_POLICY_GATE": "true"}):
        from venom_core.core.policy_gate import policy_gate

        policy_gate._initialized = False
        policy_gate.__init__()

        with patch.object(
            policy_gate,
            "evaluate_before_provider_selection",
            return_value=PolicyEvaluationResult(
                decision=PolicyDecision.BLOCK,
                reason_code=PolicyReasonCode.POLICY_PROVIDER_RESTRICTED,
                message="Provider not allowed",
            ),
        ):
            request = TaskRequest(content="test", forced_provider="restricted")

            with patch(
                "venom_core.core.orchestrator.orchestrator_submit.get_active_llm_runtime"
            ) as mock_runtime:
                mock_runtime.return_value = MagicMock(
                    provider="local",
                    model_name="test-model",
                    endpoint="http://localhost",
                    to_payload=MagicMock(return_value={}),
                )

                await submit_task(mock_orchestrator, request)

                # Verify tracer was called
                mock_orchestrator.request_tracer.add_step.assert_called()
                mock_orchestrator.request_tracer.update_status.assert_called_with(
                    mock_orchestrator.state_manager.create_task.return_value.id,
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
async def test_submit_task_uses_routing_decision_provider_for_policy_context(
    mock_orchestrator,
):
    """planned_provider w PolicyEvaluationContext ma pochodzić z RoutingDecision."""
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

        seen_context = {}

        def _capture_context(context):
            seen_context["planned_provider"] = context.planned_provider
            return PolicyEvaluationResult(
                decision=PolicyDecision.ALLOW,
                message="ok",
            )

        with (
            patch(
                "venom_core.core.orchestrator.orchestrator_submit.get_active_llm_runtime"
            ) as mock_runtime,
            patch(
                "venom_core.core.orchestrator.orchestrator_submit.routing_integration.build_routing_decision",
                return_value=decision,
            ),
            patch.object(
                policy_gate,
                "evaluate_before_provider_selection",
                side_effect=_capture_context,
            ),
        ):
            mock_runtime.return_value = MagicMock(
                provider="ollama",
                model_name="test-model",
                endpoint="http://localhost",
                to_payload=MagicMock(return_value={}),
            )

            await submit_task(mock_orchestrator, request)

            assert seen_context["planned_provider"] == "openai"


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
