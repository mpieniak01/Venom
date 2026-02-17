"""Tests for workflow operations service and state machine."""

from uuid import uuid4

import pytest

from venom_core.api.model_schemas.workflow_control import (
    ReasonCode,
    WorkflowOperation,
    WorkflowStatus,
)
from venom_core.services.workflow_operations import (
    WorkflowOperationService,
    WorkflowStateMachine,
    get_workflow_operation_service,
)


class TestWorkflowStateMachine:
    """Test workflow state machine logic."""

    def test_idle_to_running_is_valid(self):
        """Test that IDLE can transition to RUNNING."""
        assert WorkflowStateMachine.is_valid_transition(
            WorkflowStatus.IDLE, WorkflowStatus.RUNNING
        )

    def test_running_to_paused_is_valid(self):
        """Test that RUNNING can transition to PAUSED."""
        assert WorkflowStateMachine.is_valid_transition(
            WorkflowStatus.RUNNING, WorkflowStatus.PAUSED
        )

    def test_paused_to_running_is_valid(self):
        """Test that PAUSED can transition to RUNNING (resume)."""
        assert WorkflowStateMachine.is_valid_transition(
            WorkflowStatus.PAUSED, WorkflowStatus.RUNNING
        )

    def test_running_to_cancelled_is_valid(self):
        """Test that RUNNING can transition to CANCELLED."""
        assert WorkflowStateMachine.is_valid_transition(
            WorkflowStatus.RUNNING, WorkflowStatus.CANCELLED
        )

    def test_failed_to_running_is_valid(self):
        """Test that FAILED can transition to RUNNING (retry)."""
        assert WorkflowStateMachine.is_valid_transition(
            WorkflowStatus.FAILED, WorkflowStatus.RUNNING
        )

    def test_idle_to_paused_is_invalid(self):
        """Test that IDLE cannot directly transition to PAUSED."""
        assert not WorkflowStateMachine.is_valid_transition(
            WorkflowStatus.IDLE, WorkflowStatus.PAUSED
        )

    def test_completed_to_running_is_invalid(self):
        """Test that COMPLETED cannot directly transition to RUNNING."""
        assert not WorkflowStateMachine.is_valid_transition(
            WorkflowStatus.COMPLETED, WorkflowStatus.RUNNING
        )

    def test_get_allowed_transitions_from_running(self):
        """Test getting allowed transitions from RUNNING state."""
        allowed = WorkflowStateMachine.get_allowed_transitions(WorkflowStatus.RUNNING)
        assert WorkflowStatus.PAUSED in allowed
        assert WorkflowStatus.COMPLETED in allowed
        assert WorkflowStatus.FAILED in allowed
        assert WorkflowStatus.CANCELLED in allowed

    def test_get_allowed_transitions_from_paused(self):
        """Test getting allowed transitions from PAUSED state."""
        allowed = WorkflowStateMachine.get_allowed_transitions(WorkflowStatus.PAUSED)
        assert WorkflowStatus.RUNNING in allowed
        assert WorkflowStatus.CANCELLED in allowed

    def test_get_allowed_transitions_from_idle(self):
        """Test getting allowed transitions from IDLE state."""
        allowed = WorkflowStateMachine.get_allowed_transitions(WorkflowStatus.IDLE)
        assert WorkflowStatus.RUNNING in allowed
        assert len(allowed) == 1


class TestWorkflowOperationService:
    """Test workflow operation service."""

    @pytest.fixture
    def service(self):
        """Create a fresh workflow operation service."""
        return WorkflowOperationService()

    @pytest.fixture
    def workflow_id(self):
        """Generate a workflow ID."""
        return str(uuid4())

    def test_pause_running_workflow(self, service, workflow_id):
        """Test pausing a running workflow."""
        # Set workflow to RUNNING state
        workflow = service._get_or_create_workflow(workflow_id)
        workflow["status"] = WorkflowStatus.RUNNING.value

        # Pause the workflow
        response = service.pause_workflow(workflow_id, "test_user")

        from uuid import UUID

        assert response.workflow_id == UUID(workflow_id)
        assert response.operation == WorkflowOperation.PAUSE
        assert response.status == WorkflowStatus.PAUSED
        assert response.reason_code == ReasonCode.OPERATION_COMPLETED
        assert "successfully" in response.message.lower()

    def test_pause_idle_workflow_fails(self, service, workflow_id):
        """Test that pausing an IDLE workflow fails."""
        # Workflow starts in IDLE state
        response = service.pause_workflow(workflow_id, "test_user")

        assert response.status == WorkflowStatus.IDLE
        assert response.reason_code == ReasonCode.FORBIDDEN_TRANSITION
        assert "cannot pause" in response.message.lower()

    def test_resume_paused_workflow(self, service, workflow_id):
        """Test resuming a paused workflow."""
        # Set workflow to PAUSED state
        workflow = service._get_or_create_workflow(workflow_id)
        workflow["status"] = WorkflowStatus.PAUSED.value

        # Resume the workflow
        response = service.resume_workflow(workflow_id, "test_user")

        assert response.operation == WorkflowOperation.RESUME
        assert response.status == WorkflowStatus.RUNNING
        assert response.reason_code == ReasonCode.OPERATION_COMPLETED

    def test_resume_running_workflow_fails(self, service, workflow_id):
        """Test that resuming a RUNNING workflow fails."""
        # Set workflow to RUNNING state
        workflow = service._get_or_create_workflow(workflow_id)
        workflow["status"] = WorkflowStatus.RUNNING.value

        # Try to resume
        response = service.resume_workflow(workflow_id, "test_user")

        assert response.status == WorkflowStatus.RUNNING
        assert response.reason_code == ReasonCode.FORBIDDEN_TRANSITION

    def test_cancel_running_workflow(self, service, workflow_id):
        """Test cancelling a running workflow."""
        # Set workflow to RUNNING state
        workflow = service._get_or_create_workflow(workflow_id)
        workflow["status"] = WorkflowStatus.RUNNING.value

        # Cancel the workflow
        response = service.cancel_workflow(workflow_id, "test_user")

        assert response.operation == WorkflowOperation.CANCEL
        assert response.status == WorkflowStatus.CANCELLED
        assert response.reason_code == ReasonCode.OPERATION_CANCELLED

    def test_cancel_paused_workflow(self, service, workflow_id):
        """Test cancelling a paused workflow."""
        # Set workflow to PAUSED state
        workflow = service._get_or_create_workflow(workflow_id)
        workflow["status"] = WorkflowStatus.PAUSED.value

        # Cancel the workflow
        response = service.cancel_workflow(workflow_id, "test_user")

        assert response.status == WorkflowStatus.CANCELLED
        assert response.reason_code == ReasonCode.OPERATION_CANCELLED

    def test_cancel_idle_workflow_fails(self, service, workflow_id):
        """Test that cancelling an IDLE workflow fails."""
        response = service.cancel_workflow(workflow_id, "test_user")

        assert response.status == WorkflowStatus.IDLE
        assert response.reason_code == ReasonCode.FORBIDDEN_TRANSITION

    def test_retry_failed_workflow(self, service, workflow_id):
        """Test retrying a failed workflow."""
        # Set workflow to FAILED state
        workflow = service._get_or_create_workflow(workflow_id)
        workflow["status"] = WorkflowStatus.FAILED.value

        # Retry the workflow
        response = service.retry_workflow(workflow_id, "test_user")

        assert response.operation == WorkflowOperation.RETRY
        assert response.status == WorkflowStatus.RUNNING
        assert response.reason_code == ReasonCode.OPERATION_COMPLETED

    def test_retry_cancelled_workflow(self, service, workflow_id):
        """Test retrying a cancelled workflow."""
        # Set workflow to CANCELLED state
        workflow = service._get_or_create_workflow(workflow_id)
        workflow["status"] = WorkflowStatus.CANCELLED.value

        # Retry the workflow
        response = service.retry_workflow(workflow_id, "test_user")

        assert response.status == WorkflowStatus.RUNNING
        assert response.reason_code == ReasonCode.OPERATION_COMPLETED

    def test_retry_with_step_id(self, service, workflow_id):
        """Test retrying from a specific step."""
        # Set workflow to FAILED state
        workflow = service._get_or_create_workflow(workflow_id)
        workflow["status"] = WorkflowStatus.FAILED.value

        # Retry from specific step
        response = service.retry_workflow(workflow_id, "test_user", step_id="step_123")

        assert response.status == WorkflowStatus.RUNNING
        assert response.metadata.get("step_id") == "step_123"
        assert "step_123" in response.message

    def test_retry_running_workflow_fails(self, service, workflow_id):
        """Test that retrying a RUNNING workflow fails."""
        # Set workflow to RUNNING state
        workflow = service._get_or_create_workflow(workflow_id)
        workflow["status"] = WorkflowStatus.RUNNING.value

        # Try to retry
        response = service.retry_workflow(workflow_id, "test_user")

        assert response.status == WorkflowStatus.RUNNING
        assert response.reason_code == ReasonCode.FORBIDDEN_TRANSITION

    def test_dry_run_execution(self, service, workflow_id):
        """Test dry-run execution."""
        response = service.dry_run(workflow_id, "test_user")

        assert response.operation == WorkflowOperation.DRY_RUN
        assert response.reason_code == ReasonCode.OPERATION_COMPLETED
        assert response.metadata.get("dry_run") is True
        assert "no changes" in response.message.lower()

    def test_dry_run_does_not_change_state(self, service, workflow_id):
        """Test that dry-run doesn't change workflow state."""
        # Set workflow to RUNNING state
        workflow = service._get_or_create_workflow(workflow_id)
        workflow["status"] = WorkflowStatus.RUNNING.value

        # Perform dry-run
        response = service.dry_run(workflow_id, "test_user")

        # State should remain RUNNING
        assert response.status == WorkflowStatus.RUNNING
        assert service.get_workflow_status(workflow_id) == WorkflowStatus.RUNNING

    def test_get_workflow_status(self, service, workflow_id):
        """Test getting workflow status."""
        # Initially IDLE
        assert service.get_workflow_status(workflow_id) == WorkflowStatus.IDLE

        # Change to RUNNING
        workflow = service._get_or_create_workflow(workflow_id)
        workflow["status"] = WorkflowStatus.RUNNING.value

        assert service.get_workflow_status(workflow_id) == WorkflowStatus.RUNNING

    def test_workflow_metadata_tracking(self, service, workflow_id):
        """Test that workflow operations track metadata."""
        # Set workflow to RUNNING
        workflow = service._get_or_create_workflow(workflow_id)
        workflow["status"] = WorkflowStatus.RUNNING.value

        # Pause with metadata
        response = service.pause_workflow(
            workflow_id, "test_user", metadata={"reason": "maintenance"}
        )

        assert response.metadata.get("reason") == "maintenance"

    def test_singleton_service(self):
        """Test that get_workflow_operation_service returns singleton."""
        service1 = get_workflow_operation_service()
        service2 = get_workflow_operation_service()
        assert service1 is service2


class TestWorkflowLifecycle:
    """Test complete workflow lifecycles."""

    @pytest.fixture
    def service(self):
        """Create a fresh workflow operation service."""
        return WorkflowOperationService()

    @pytest.fixture
    def workflow_id(self):
        """Generate a workflow ID."""
        return str(uuid4())

    def test_normal_workflow_lifecycle(self, service, workflow_id):
        """Test normal workflow: IDLE -> RUNNING -> COMPLETED."""
        # Start in IDLE
        assert service.get_workflow_status(workflow_id) == WorkflowStatus.IDLE

        # Start workflow (manually set to RUNNING for this test)
        workflow = service._get_or_create_workflow(workflow_id)
        workflow["status"] = WorkflowStatus.RUNNING.value

        # Complete workflow
        workflow["status"] = WorkflowStatus.COMPLETED.value
        assert service.get_workflow_status(workflow_id) == WorkflowStatus.COMPLETED

    def test_pause_resume_lifecycle(self, service, workflow_id):
        """Test pause/resume: IDLE -> RUNNING -> PAUSED -> RUNNING."""
        # Start workflow
        workflow = service._get_or_create_workflow(workflow_id)
        workflow["status"] = WorkflowStatus.RUNNING.value

        # Pause
        response = service.pause_workflow(workflow_id, "test_user")
        assert response.status == WorkflowStatus.PAUSED

        # Resume
        response = service.resume_workflow(workflow_id, "test_user")
        assert response.status == WorkflowStatus.RUNNING

    def test_failure_retry_lifecycle(self, service, workflow_id):
        """Test failure/retry: RUNNING -> FAILED -> RUNNING."""
        # Start and fail workflow
        workflow = service._get_or_create_workflow(workflow_id)
        workflow["status"] = WorkflowStatus.FAILED.value

        # Retry
        response = service.retry_workflow(workflow_id, "test_user")
        assert response.status == WorkflowStatus.RUNNING

    def test_cancel_lifecycle(self, service, workflow_id):
        """Test cancel: RUNNING -> CANCELLED."""
        # Start workflow
        workflow = service._get_or_create_workflow(workflow_id)
        workflow["status"] = WorkflowStatus.RUNNING.value

        # Cancel
        response = service.cancel_workflow(workflow_id, "test_user")
        assert response.status == WorkflowStatus.CANCELLED
