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
        service.register_workflow(workflow_id, WorkflowStatus.RUNNING)

        # Pause the workflow
        response = service.pause_workflow(workflow_id, "test_user")

        from uuid import UUID

        assert response.workflow_id == UUID(workflow_id)
        assert response.operation == WorkflowOperation.PAUSE
        assert response.status == WorkflowStatus.PAUSED
        assert response.reason_code == ReasonCode.OPERATION_COMPLETED
        assert "successfully" in response.message.lower()

    def test_pause_idle_registered_workflow_fails(self, service, workflow_id):
        """Test that pausing a registered IDLE workflow returns FORBIDDEN_TRANSITION."""
        service.register_workflow(workflow_id, WorkflowStatus.IDLE)
        response = service.pause_workflow(workflow_id, "test_user")

        assert response.status == WorkflowStatus.IDLE
        assert response.reason_code == ReasonCode.FORBIDDEN_TRANSITION
        assert "cannot pause" in response.message.lower()

    def test_pause_unregistered_workflow_returns_not_found(self, service, workflow_id):
        """Test that pausing an unregistered workflow returns RESOURCE_NOT_FOUND (PR 204)."""
        response = service.pause_workflow(workflow_id, "test_user")

        assert response.status == WorkflowStatus.IDLE
        assert response.reason_code == ReasonCode.RESOURCE_NOT_FOUND

    def test_resume_paused_workflow(self, service, workflow_id):
        """Test resuming a paused workflow."""
        # Set workflow to PAUSED state
        service.register_workflow(workflow_id, WorkflowStatus.PAUSED)

        # Resume the workflow
        response = service.resume_workflow(workflow_id, "test_user")

        assert response.operation == WorkflowOperation.RESUME
        assert response.status == WorkflowStatus.RUNNING
        assert response.reason_code == ReasonCode.OPERATION_COMPLETED

    def test_resume_running_workflow_fails(self, service, workflow_id):
        """Test that resuming a RUNNING workflow fails."""
        # Set workflow to RUNNING state
        service.register_workflow(workflow_id, WorkflowStatus.RUNNING)

        # Try to resume
        response = service.resume_workflow(workflow_id, "test_user")

        assert response.status == WorkflowStatus.RUNNING
        assert response.reason_code == ReasonCode.FORBIDDEN_TRANSITION

    def test_cancel_running_workflow(self, service, workflow_id):
        """Test cancelling a running workflow."""
        # Set workflow to RUNNING state
        service.register_workflow(workflow_id, WorkflowStatus.RUNNING)

        # Cancel the workflow
        response = service.cancel_workflow(workflow_id, "test_user")

        assert response.operation == WorkflowOperation.CANCEL
        assert response.status == WorkflowStatus.CANCELLED
        assert response.reason_code == ReasonCode.OPERATION_CANCELLED

    def test_cancel_paused_workflow(self, service, workflow_id):
        """Test cancelling a paused workflow."""
        # Set workflow to PAUSED state
        service.register_workflow(workflow_id, WorkflowStatus.PAUSED)

        # Cancel the workflow
        response = service.cancel_workflow(workflow_id, "test_user")

        assert response.status == WorkflowStatus.CANCELLED
        assert response.reason_code == ReasonCode.OPERATION_CANCELLED

    def test_cancel_idle_registered_workflow_fails(self, service, workflow_id):
        """Test that cancelling a registered IDLE workflow returns FORBIDDEN_TRANSITION."""
        service.register_workflow(workflow_id, WorkflowStatus.IDLE)
        response = service.cancel_workflow(workflow_id, "test_user")

        assert response.status == WorkflowStatus.IDLE
        assert response.reason_code == ReasonCode.FORBIDDEN_TRANSITION

    def test_cancel_unregistered_workflow_returns_not_found(self, service, workflow_id):
        """Cancelling an unregistered workflow returns RESOURCE_NOT_FOUND (PR 204)."""
        response = service.cancel_workflow(workflow_id, "test_user")

        assert response.status == WorkflowStatus.IDLE
        assert response.reason_code == ReasonCode.RESOURCE_NOT_FOUND

    def test_retry_failed_workflow(self, service, workflow_id):
        """Test retrying a failed workflow."""
        # Set workflow to FAILED state
        service.register_workflow(workflow_id, WorkflowStatus.FAILED)

        # Retry the workflow
        response = service.retry_workflow(workflow_id, "test_user")

        assert response.operation == WorkflowOperation.RETRY
        assert response.status == WorkflowStatus.RUNNING
        assert response.reason_code == ReasonCode.OPERATION_COMPLETED

    def test_retry_cancelled_workflow(self, service, workflow_id):
        """Test retrying a cancelled workflow."""
        # Set workflow to CANCELLED state
        service.register_workflow(workflow_id, WorkflowStatus.CANCELLED)

        # Retry the workflow
        response = service.retry_workflow(workflow_id, "test_user")

        assert response.status == WorkflowStatus.RUNNING
        assert response.reason_code == ReasonCode.OPERATION_COMPLETED

    def test_retry_with_step_id(self, service, workflow_id):
        """Test retrying from a specific step."""
        # Set workflow to FAILED state
        service.register_workflow(workflow_id, WorkflowStatus.FAILED)

        # Retry from specific step
        response = service.retry_workflow(workflow_id, "test_user", step_id="step_123")

        assert response.status == WorkflowStatus.RUNNING
        assert response.metadata.get("step_id") == "step_123"
        assert "step_123" in response.message

    def test_retry_running_workflow_fails(self, service, workflow_id):
        """Test that retrying a RUNNING workflow fails."""
        # Set workflow to RUNNING state
        service.register_workflow(workflow_id, WorkflowStatus.RUNNING)

        # Try to retry
        response = service.retry_workflow(workflow_id, "test_user")

        assert response.status == WorkflowStatus.RUNNING
        assert response.reason_code == ReasonCode.FORBIDDEN_TRANSITION

    def test_dry_run_execution(self, service, workflow_id):
        """Test dry-run execution."""
        service.register_workflow(workflow_id, WorkflowStatus.RUNNING)
        response = service.dry_run(workflow_id, "test_user")

        assert response.operation == WorkflowOperation.DRY_RUN
        assert response.reason_code == ReasonCode.OPERATION_COMPLETED
        assert response.metadata.get("dry_run") is True
        assert "no changes" in response.message.lower()

    def test_dry_run_does_not_change_state(self, service, workflow_id):
        """Test that dry-run doesn't change workflow state."""
        # Set workflow to RUNNING state
        service.register_workflow(workflow_id, WorkflowStatus.RUNNING)

        # Perform dry-run
        response = service.dry_run(workflow_id, "test_user")

        # State should remain RUNNING
        assert response.status == WorkflowStatus.RUNNING
        assert service.get_workflow_status(workflow_id) == WorkflowStatus.RUNNING

    def test_get_workflow_status(self, service, workflow_id):
        """Test getting workflow status."""
        # Unregistered workflow => IDLE
        assert service.get_workflow_status(workflow_id) == WorkflowStatus.IDLE

        # Register as RUNNING
        service.register_workflow(workflow_id, WorkflowStatus.RUNNING)
        assert service.get_workflow_status(workflow_id) == WorkflowStatus.RUNNING

    def test_workflow_metadata_tracking(self, service, workflow_id):
        """Test that workflow operations track metadata."""
        # Set workflow to RUNNING
        service.register_workflow(workflow_id, WorkflowStatus.RUNNING)

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

    @pytest.mark.parametrize(
        "operation,method_name",
        [
            (WorkflowOperation.RESUME, "resume_workflow"),
            (WorkflowOperation.CANCEL, "cancel_workflow"),
            (WorkflowOperation.RETRY, "retry_workflow"),
            (WorkflowOperation.DRY_RUN, "dry_run"),
        ],
    )
    def test_invalid_uuid_paths_use_structured_response(
        self, service, operation, method_name
    ):
        """Operations return INVALID_CONFIGURATION for malformed UUID."""
        method = getattr(service, method_name)
        response = method("not-a-uuid", "test_user")
        assert response.operation == operation
        assert response.reason_code == ReasonCode.INVALID_CONFIGURATION
        assert response.status == WorkflowStatus.IDLE

    def test_get_latest_workflow_status_fallback_paths(self, service):
        """Latest status falls back to IDLE for empty/invalid workflow records."""
        assert service.get_latest_workflow_status() == WorkflowStatus.IDLE

        workflow_id = str(uuid4())
        service.register_workflow(workflow_id)
        service._workflows[workflow_id]["status"] = "NOT_A_STATUS"

        assert service.get_latest_workflow_status() == WorkflowStatus.IDLE

    def test_get_latest_workflow_status_handles_missing_status_key(self, service):
        """Missing status key in latest record should safely fall back to IDLE."""
        workflow_id = str(uuid4())
        service.register_workflow(workflow_id)
        service._workflows[workflow_id].pop("status", None)
        service._workflows[workflow_id]["updated_at"] = "9999-01-01T00:00:00+00:00"

        assert service.get_latest_workflow_status() == WorkflowStatus.IDLE

    def test_pause_invalid_uuid_returns_structured_error(self, service):
        """Pause path should also return INVALID_CONFIGURATION for malformed UUID."""
        response = service.pause_workflow("invalid-uuid", "test_user")

        assert response.operation == WorkflowOperation.PAUSE
        assert response.reason_code == ReasonCode.INVALID_CONFIGURATION
        assert response.status == WorkflowStatus.IDLE

    def test_get_workflow_service_alias_uses_singleton(self):
        """Backward-compatible alias should return singleton service instance."""
        from venom_core.services.workflow_operations import get_workflow_service

        assert get_workflow_service() is get_workflow_operation_service()


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
        # Unregistered => IDLE
        assert service.get_workflow_status(workflow_id) == WorkflowStatus.IDLE

        # Register and set to RUNNING
        service.register_workflow(workflow_id, WorkflowStatus.RUNNING)

        # Complete workflow
        service._workflows[workflow_id]["status"] = WorkflowStatus.COMPLETED.value
        assert service.get_workflow_status(workflow_id) == WorkflowStatus.COMPLETED

    def test_pause_resume_lifecycle(self, service, workflow_id):
        """Test pause/resume: RUNNING -> PAUSED -> RUNNING."""
        # Start workflow
        service.register_workflow(workflow_id, WorkflowStatus.RUNNING)

        # Pause
        response = service.pause_workflow(workflow_id, "test_user")
        assert response.status == WorkflowStatus.PAUSED

        # Resume
        response = service.resume_workflow(workflow_id, "test_user")
        assert response.status == WorkflowStatus.RUNNING

    def test_failure_retry_lifecycle(self, service, workflow_id):
        """Test failure/retry: RUNNING -> FAILED -> RUNNING."""
        # Start and fail workflow
        service.register_workflow(workflow_id, WorkflowStatus.FAILED)

        # Retry
        response = service.retry_workflow(workflow_id, "test_user")
        assert response.status == WorkflowStatus.RUNNING

    def test_cancel_lifecycle(self, service, workflow_id):
        """Test cancel: RUNNING -> CANCELLED."""
        # Start workflow
        service.register_workflow(workflow_id, WorkflowStatus.RUNNING)

        # Cancel
        response = service.cancel_workflow(workflow_id, "test_user")
        assert response.status == WorkflowStatus.CANCELLED


class TestPR204WorkflowOperationsContract:
    """PR 204: Operations require real/registered workflow IDs.

    Verifies that auto-create phantom workflow behaviour is eliminated.
    """

    @pytest.fixture
    def service(self):
        return WorkflowOperationService()

    @pytest.fixture
    def workflow_id(self):
        return str(uuid4())

    def test_resume_on_unregistered_id_returns_not_found(self, service, workflow_id):
        """Resume on an unregistered UUID must NOT create a phantom RUNNING workflow (PR 204)."""
        response = service.resume_workflow(workflow_id, "test_user")

        assert response.reason_code == ReasonCode.RESOURCE_NOT_FOUND
        assert response.status == WorkflowStatus.IDLE
        # Workflow must NOT have been created in internal state
        assert workflow_id not in service._workflows

    def test_completed_workflow_cannot_be_resumed(self, service, workflow_id):
        """A COMPLETED task must not transition to RUNNING via resume (PR 204)."""
        service.register_workflow(workflow_id, WorkflowStatus.COMPLETED)

        response = service.resume_workflow(workflow_id, "test_user")

        assert response.reason_code == ReasonCode.FORBIDDEN_TRANSITION
        assert response.status == WorkflowStatus.COMPLETED
        # Status must remain COMPLETED
        assert service.get_workflow_status(workflow_id) == WorkflowStatus.COMPLETED

    def test_pause_on_unregistered_id_returns_not_found(self, service, workflow_id):
        """Pause on unregistered UUID returns resource_not_found."""
        response = service.pause_workflow(workflow_id, "test_user")

        assert response.reason_code == ReasonCode.RESOURCE_NOT_FOUND
        assert workflow_id not in service._workflows

    def test_cancel_on_unregistered_id_returns_not_found(self, service, workflow_id):
        """Cancel on unregistered UUID returns resource_not_found."""
        response = service.cancel_workflow(workflow_id, "test_user")

        assert response.reason_code == ReasonCode.RESOURCE_NOT_FOUND
        assert workflow_id not in service._workflows

    def test_retry_on_unregistered_id_returns_not_found(self, service, workflow_id):
        """Retry on unregistered UUID returns resource_not_found."""
        response = service.retry_workflow(workflow_id, "test_user")

        assert response.reason_code == ReasonCode.RESOURCE_NOT_FOUND
        assert workflow_id not in service._workflows

    def test_dry_run_on_unregistered_id_returns_not_found(self, service, workflow_id):
        """Dry-run on unregistered UUID returns resource_not_found."""
        response = service.dry_run(workflow_id, "test_user")

        assert response.reason_code == ReasonCode.RESOURCE_NOT_FOUND
        assert workflow_id not in service._workflows

    def test_register_workflow_creates_entry(self, service, workflow_id):
        """register_workflow creates an entry that can be operated on."""
        service.register_workflow(workflow_id, WorkflowStatus.RUNNING)

        assert workflow_id in service._workflows
        assert service.get_workflow_status(workflow_id) == WorkflowStatus.RUNNING

    def test_register_workflow_is_idempotent(self, service, workflow_id):
        """Calling register_workflow twice does not overwrite existing state."""
        service.register_workflow(workflow_id, WorkflowStatus.RUNNING)
        # Pause to change state
        service.pause_workflow(workflow_id, "test_user")
        # Re-registering should not reset to RUNNING
        service.register_workflow(workflow_id, WorkflowStatus.RUNNING)

        # State must remain PAUSED
        assert service.get_workflow_status(workflow_id) == WorkflowStatus.PAUSED

    def test_allowed_operations_for_running_workflow(self, service, workflow_id):
        """RUNNING workflow allows pause and cancel; stop auto-create check."""
        service.register_workflow(workflow_id, WorkflowStatus.RUNNING)
        allowed = WorkflowStateMachine.get_allowed_transitions(WorkflowStatus.RUNNING)
        assert WorkflowStatus.PAUSED in allowed
        assert WorkflowStatus.CANCELLED in allowed
        assert (
            WorkflowStatus.RUNNING not in allowed
        )  # Cannot stay in RUNNING via a single transition

    def test_allowed_operations_for_completed_workflow(self, service, workflow_id):
        """COMPLETED workflow has no path to RUNNING (only IDLE restart)."""
        service.register_workflow(workflow_id, WorkflowStatus.COMPLETED)
        allowed = WorkflowStateMachine.get_allowed_transitions(WorkflowStatus.COMPLETED)
        assert WorkflowStatus.RUNNING not in allowed
        assert WorkflowStatus.IDLE in allowed
