"""Testy integracyjne dla orchestratora z policy gate."""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from venom_core.core.models import TaskRequest, TaskStatus
from venom_core.core.orchestrator.orchestrator_submit import submit_task
from venom_core.core.policy_gate import (
    PolicyDecision,
    PolicyEvaluationResult,
    PolicyReasonCode,
)


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

            assert response.task_id == mock_orchestrator.state_manager.create_task.return_value.id
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

            assert response.task_id == mock_orchestrator.state_manager.create_task.return_value.id
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

                assert response.task_id == mock_orchestrator.state_manager.create_task.return_value.id
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
                    mock_orchestrator.state_manager.create_task.return_value.id, "failed"
                )
