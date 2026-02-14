"""Workflow operation service for Control Plane.

This module provides operations for managing workflow execution:
- pause/resume workflow flows
- cancel running workflows
- retry from specific steps
- dry-run execution paths

Supported state transitions:
- IDLE → RUNNING
- RUNNING → PAUSED | COMPLETED | FAILED | CANCELLED
- PAUSED → RUNNING | CANCELLED
- COMPLETED → IDLE (restart)
- FAILED → RUNNING (retry) | IDLE (reset)
- CANCELLED → IDLE (reset) | RUNNING (retry)
"""

import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from venom_core.api.model_schemas.workflow_control import (
    ReasonCode,
    ResourceType,
    WorkflowOperation,
    WorkflowOperationResponse,
    WorkflowStatus,
)
from venom_core.services.control_plane_audit import get_control_plane_audit_trail
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class StateTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""

    pass


class WorkflowStateMachine:
    """Defines valid workflow states and transitions."""

    # Valid state transitions: from_state -> [allowed_to_states]
    TRANSITIONS = {
        WorkflowStatus.IDLE: [WorkflowStatus.RUNNING],
        WorkflowStatus.RUNNING: [
            WorkflowStatus.PAUSED,
            WorkflowStatus.COMPLETED,
            WorkflowStatus.FAILED,
            WorkflowStatus.CANCELLED,
        ],
        WorkflowStatus.PAUSED: [
            WorkflowStatus.RUNNING,  # resume
            WorkflowStatus.CANCELLED,
        ],
        WorkflowStatus.COMPLETED: [WorkflowStatus.IDLE],  # restart
        WorkflowStatus.FAILED: [
            WorkflowStatus.RUNNING,  # retry
            WorkflowStatus.IDLE,
        ],
        WorkflowStatus.CANCELLED: [
            WorkflowStatus.IDLE,  # restart
            WorkflowStatus.RUNNING,  # retry
        ],
    }

    @classmethod
    def is_valid_transition(
        cls, from_state: WorkflowStatus, to_state: WorkflowStatus
    ) -> bool:
        """Check if a state transition is valid.

        Args:
            from_state: Current workflow state
            to_state: Desired workflow state

        Returns:
            True if transition is valid, False otherwise
        """
        allowed_states = cls.TRANSITIONS.get(from_state, [])
        return to_state in allowed_states

    @classmethod
    def get_allowed_transitions(
        cls, from_state: WorkflowStatus
    ) -> list[WorkflowStatus]:
        """Get list of allowed transitions from a given state.

        Args:
            from_state: Current workflow state

        Returns:
            List of allowed target states
        """
        return cls.TRANSITIONS.get(from_state, [])


class WorkflowOperationService:
    """Service for managing workflow operations."""

    def __init__(self):
        """Initialize workflow operation service."""
        self._workflows: dict[str, dict[str, Any]] = {}
        self._audit_trail = get_control_plane_audit_trail()
        self._lock = threading.Lock()  # Thread-safe access to workflows

    def _validate_and_parse_uuid(self, workflow_id: str) -> uuid.UUID:
        """Validate and parse workflow ID as UUID.

        Args:
            workflow_id: String to validate as UUID

        Returns:
            Parsed UUID object

        Raises:
            ValueError: If workflow_id is not a valid UUID
        """
        try:
            return uuid.UUID(workflow_id)
        except (ValueError, AttributeError) as e:
            raise ValueError(
                f"Invalid workflow_id format: {workflow_id}. Must be a valid UUID."
            ) from e

    def _invalid_uuid_response(
        self,
        workflow_id: str,
        operation: WorkflowOperation,
        metadata: Optional[dict[str, Any]] = None,
    ) -> WorkflowOperationResponse:
        """Return a structured response for invalid UUID inputs."""
        return WorkflowOperationResponse(
            workflow_id=uuid.uuid4(),  # Synthetic ID for validation error responses
            operation=operation,
            status=WorkflowStatus.IDLE,
            reason_code=ReasonCode.INVALID_CONFIGURATION,
            message=f"Invalid workflow_id format: {workflow_id}. Must be a valid UUID.",
            timestamp=datetime.now(timezone.utc),
            metadata=metadata or {},
        )

    def pause_workflow(
        self,
        workflow_id: str,
        triggered_by: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> WorkflowOperationResponse:
        """Pause a running workflow.

        Args:
            workflow_id: UUID of the workflow
            triggered_by: User or system triggering the pause
            metadata: Optional metadata for the operation

        Returns:
            WorkflowOperationResponse with result

        Raises:
            ValueError: If workflow_id is not a valid UUID
        """
        # Validate UUID first
        try:
            workflow_uuid = self._validate_and_parse_uuid(workflow_id)
        except ValueError as e:
            return WorkflowOperationResponse(
                workflow_id=uuid.uuid4(),  # Dummy UUID for error response
                operation=WorkflowOperation.PAUSE,
                status=WorkflowStatus.IDLE,
                reason_code=ReasonCode.INVALID_CONFIGURATION,
                message=str(e),
                timestamp=datetime.now(timezone.utc),
                metadata=metadata or {},
            )

        with self._lock:
            workflow = self._get_or_create_workflow(workflow_id)
            current_state = WorkflowStatus(workflow["status"])

            # Validate transition
            if not WorkflowStateMachine.is_valid_transition(
                current_state, WorkflowStatus.PAUSED
            ):
                reason_code = ReasonCode.FORBIDDEN_TRANSITION
                message = (
                    f"Cannot pause workflow in state {current_state.value}. "
                    f"Allowed states: {[s.value for s in WorkflowStateMachine.get_allowed_transitions(current_state)]}"
                )

                # Log to audit trail
                self._audit_trail.log_operation(
                    triggered_by=triggered_by,
                    operation_type="pause",
                    resource_type=ResourceType.WORKFLOW,
                    resource_id=workflow_id,
                    params=metadata or {},
                    result="failure",
                    reason_code=reason_code,
                )

                return WorkflowOperationResponse(
                    workflow_id=workflow_uuid,
                    operation=WorkflowOperation.PAUSE,
                    status=current_state,
                    reason_code=reason_code,
                    message=message,
                    timestamp=datetime.now(timezone.utc),
                    metadata=metadata or {},
                )

            # Perform pause
            workflow["status"] = WorkflowStatus.PAUSED.value
            workflow["paused_at"] = datetime.now(timezone.utc).isoformat()
            workflow["paused_by"] = triggered_by

            # Log to audit trail
            self._audit_trail.log_operation(
                triggered_by=triggered_by,
                operation_type="pause",
                resource_type=ResourceType.WORKFLOW,
                resource_id=workflow_id,
                params=metadata or {},
                result="success",
                reason_code=ReasonCode.OPERATION_COMPLETED,
            )

            logger.info(f"Workflow {workflow_id} paused by {triggered_by}")

            return WorkflowOperationResponse(
                workflow_id=workflow_uuid,
                operation=WorkflowOperation.PAUSE,
                status=WorkflowStatus.PAUSED,
                reason_code=ReasonCode.OPERATION_COMPLETED,
                message="Workflow paused successfully",
                timestamp=datetime.now(timezone.utc),
                metadata=metadata or {},
            )

    def resume_workflow(
        self,
        workflow_id: str,
        triggered_by: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> WorkflowOperationResponse:
        """Resume a paused workflow.

        Args:
            workflow_id: UUID of the workflow
            triggered_by: User or system triggering the resume
            metadata: Optional metadata for the operation

        Returns:
            WorkflowOperationResponse with result
        """
        try:
            workflow_uuid = self._validate_and_parse_uuid(workflow_id)
        except ValueError:
            return self._invalid_uuid_response(
                workflow_id, WorkflowOperation.RESUME, metadata
            )

        with self._lock:
            workflow = self._get_or_create_workflow(workflow_id)
            current_state = WorkflowStatus(workflow["status"])

            if not WorkflowStateMachine.is_valid_transition(
                current_state, WorkflowStatus.RUNNING
            ):
                reason_code = ReasonCode.FORBIDDEN_TRANSITION
                message = (
                    f"Cannot resume workflow in state {current_state.value}. "
                    f"Allowed states: {[s.value for s in WorkflowStateMachine.get_allowed_transitions(current_state)]}"
                )

                self._audit_trail.log_operation(
                    triggered_by=triggered_by,
                    operation_type="resume",
                    resource_type=ResourceType.WORKFLOW,
                    resource_id=workflow_id,
                    params=metadata or {},
                    result="failure",
                    reason_code=reason_code,
                )

                return WorkflowOperationResponse(
                    workflow_id=workflow_uuid,
                    operation=WorkflowOperation.RESUME,
                    status=current_state,
                    reason_code=reason_code,
                    message=message,
                    timestamp=datetime.now(timezone.utc),
                    metadata=metadata or {},
                )

            workflow["status"] = WorkflowStatus.RUNNING.value
            workflow["resumed_at"] = datetime.now(timezone.utc).isoformat()
            workflow["resumed_by"] = triggered_by
            workflow["updated_at"] = datetime.now(timezone.utc).isoformat()

            self._audit_trail.log_operation(
                triggered_by=triggered_by,
                operation_type="resume",
                resource_type=ResourceType.WORKFLOW,
                resource_id=workflow_id,
                params=metadata or {},
                result="success",
                reason_code=ReasonCode.OPERATION_COMPLETED,
            )

            logger.info(f"Workflow {workflow_id} resumed by {triggered_by}")

            return WorkflowOperationResponse(
                workflow_id=workflow_uuid,
                operation=WorkflowOperation.RESUME,
                status=WorkflowStatus.RUNNING,
                reason_code=ReasonCode.OPERATION_COMPLETED,
                message="Workflow resumed successfully",
                timestamp=datetime.now(timezone.utc),
                metadata=metadata or {},
            )

    def cancel_workflow(
        self,
        workflow_id: str,
        triggered_by: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> WorkflowOperationResponse:
        """Cancel a workflow.

        Args:
            workflow_id: UUID of the workflow
            triggered_by: User or system triggering the cancel
            metadata: Optional metadata for the operation

        Returns:
            WorkflowOperationResponse with result
        """
        try:
            workflow_uuid = self._validate_and_parse_uuid(workflow_id)
        except ValueError:
            return self._invalid_uuid_response(
                workflow_id, WorkflowOperation.CANCEL, metadata
            )

        with self._lock:
            workflow = self._get_or_create_workflow(workflow_id)
            current_state = WorkflowStatus(workflow["status"])

            if not WorkflowStateMachine.is_valid_transition(
                current_state, WorkflowStatus.CANCELLED
            ):
                reason_code = ReasonCode.FORBIDDEN_TRANSITION
                message = (
                    f"Cannot cancel workflow in state {current_state.value}. "
                    f"Allowed states: {[s.value for s in WorkflowStateMachine.get_allowed_transitions(current_state)]}"
                )

                self._audit_trail.log_operation(
                    triggered_by=triggered_by,
                    operation_type="cancel",
                    resource_type=ResourceType.WORKFLOW,
                    resource_id=workflow_id,
                    params=metadata or {},
                    result="failure",
                    reason_code=reason_code,
                )

                return WorkflowOperationResponse(
                    workflow_id=workflow_uuid,
                    operation=WorkflowOperation.CANCEL,
                    status=current_state,
                    reason_code=reason_code,
                    message=message,
                    timestamp=datetime.now(timezone.utc),
                    metadata=metadata or {},
                )

            workflow["status"] = WorkflowStatus.CANCELLED.value
            workflow["cancelled_at"] = datetime.now(timezone.utc).isoformat()
            workflow["cancelled_by"] = triggered_by
            workflow["updated_at"] = datetime.now(timezone.utc).isoformat()

            self._audit_trail.log_operation(
                triggered_by=triggered_by,
                operation_type="cancel",
                resource_type=ResourceType.WORKFLOW,
                resource_id=workflow_id,
                params=metadata or {},
                result="success",
                reason_code=ReasonCode.OPERATION_CANCELLED,
            )

            logger.info(f"Workflow {workflow_id} cancelled by {triggered_by}")

            return WorkflowOperationResponse(
                workflow_id=workflow_uuid,
                operation=WorkflowOperation.CANCEL,
                status=WorkflowStatus.CANCELLED,
                reason_code=ReasonCode.OPERATION_CANCELLED,
                message="Workflow cancelled successfully",
                timestamp=datetime.now(timezone.utc),
                metadata=metadata or {},
            )

    def retry_workflow(
        self,
        workflow_id: str,
        triggered_by: str,
        step_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> WorkflowOperationResponse:
        """Retry a failed or cancelled workflow.

        Args:
            workflow_id: UUID of the workflow
            triggered_by: User or system triggering the retry
            step_id: Optional step ID to retry from
            metadata: Optional metadata for the operation

        Returns:
            WorkflowOperationResponse with result
        """
        try:
            workflow_uuid = self._validate_and_parse_uuid(workflow_id)
        except ValueError:
            return self._invalid_uuid_response(
                workflow_id,
                WorkflowOperation.RETRY,
                {"step_id": step_id, **(metadata or {})},
            )

        with self._lock:
            workflow = self._get_or_create_workflow(workflow_id)
            current_state = WorkflowStatus(workflow["status"])

            if not WorkflowStateMachine.is_valid_transition(
                current_state, WorkflowStatus.RUNNING
            ):
                reason_code = ReasonCode.FORBIDDEN_TRANSITION
                message = (
                    f"Cannot retry workflow in state {current_state.value}. "
                    f"Allowed states: {[s.value for s in WorkflowStateMachine.get_allowed_transitions(current_state)]}"
                )

                self._audit_trail.log_operation(
                    triggered_by=triggered_by,
                    operation_type="retry",
                    resource_type=ResourceType.WORKFLOW,
                    resource_id=workflow_id,
                    params={"step_id": step_id, **(metadata or {})},
                    result="failure",
                    reason_code=reason_code,
                )

                return WorkflowOperationResponse(
                    workflow_id=workflow_uuid,
                    operation=WorkflowOperation.RETRY,
                    status=current_state,
                    reason_code=reason_code,
                    message=message,
                    timestamp=datetime.now(timezone.utc),
                    metadata={"step_id": step_id, **(metadata or {})},
                )

            workflow["status"] = WorkflowStatus.RUNNING.value
            workflow["retried_at"] = datetime.now(timezone.utc).isoformat()
            workflow["retried_by"] = triggered_by
            if step_id:
                workflow["retry_from_step"] = step_id
            workflow["updated_at"] = datetime.now(timezone.utc).isoformat()

            self._audit_trail.log_operation(
                triggered_by=triggered_by,
                operation_type="retry",
                resource_type=ResourceType.WORKFLOW,
                resource_id=workflow_id,
                params={"step_id": step_id, **(metadata or {})},
                result="success",
                reason_code=ReasonCode.OPERATION_COMPLETED,
            )

            logger.info(
                f"Workflow {workflow_id} retried by {triggered_by}"
                + (f" from step {step_id}" if step_id else "")
            )

            return WorkflowOperationResponse(
                workflow_id=workflow_uuid,
                operation=WorkflowOperation.RETRY,
                status=WorkflowStatus.RUNNING,
                reason_code=ReasonCode.OPERATION_COMPLETED,
                message=f"Workflow retried successfully{' from step ' + step_id if step_id else ''}",
                timestamp=datetime.now(timezone.utc),
                metadata={"step_id": step_id, **(metadata or {})},
            )

    def dry_run(
        self,
        workflow_id: str,
        triggered_by: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> WorkflowOperationResponse:
        """Perform a dry-run of workflow without executing actions.

        Args:
            workflow_id: UUID of the workflow
            triggered_by: User or system triggering the dry-run
            metadata: Optional metadata for the operation

        Returns:
            WorkflowOperationResponse with simulated result
        """
        try:
            workflow_uuid = self._validate_and_parse_uuid(workflow_id)
        except ValueError:
            return self._invalid_uuid_response(
                workflow_id, WorkflowOperation.DRY_RUN, metadata
            )

        with self._lock:
            workflow = self._get_or_create_workflow(workflow_id)
            current_state = WorkflowStatus(workflow["status"])

            self._audit_trail.log_operation(
                triggered_by=triggered_by,
                operation_type="dry_run",
                resource_type=ResourceType.WORKFLOW,
                resource_id=workflow_id,
                params=metadata or {},
                result="success",
                reason_code=ReasonCode.OPERATION_COMPLETED,
            )

            logger.info(
                f"Dry-run executed for workflow {workflow_id} by {triggered_by}"
            )

            return WorkflowOperationResponse(
                workflow_id=workflow_uuid,
                operation=WorkflowOperation.DRY_RUN,
                status=current_state,
                reason_code=ReasonCode.OPERATION_COMPLETED,
                message=f"Dry-run completed. Current state: {current_state.value}. No changes made.",
                timestamp=datetime.now(timezone.utc),
                metadata={
                    "dry_run": True,
                    "simulated_actions": [],
                    **(metadata or {}),
                },
            )

    def get_workflow_status(self, workflow_id: str) -> WorkflowStatus:
        """Get current status of a workflow.

        Args:
            workflow_id: UUID of the workflow

        Returns:
            Current WorkflowStatus
        """
        with self._lock:
            workflow = self._get_or_create_workflow(workflow_id)
            return WorkflowStatus(workflow["status"])

    def get_latest_workflow_status(self) -> WorkflowStatus:
        """Get status of most recently updated workflow, or IDLE if none exist."""
        with self._lock:
            if not self._workflows:
                return WorkflowStatus.IDLE

            latest_workflow = max(
                self._workflows.values(),
                key=lambda wf: wf.get("updated_at", wf.get("created_at", "")),
            )
            try:
                return WorkflowStatus(str(latest_workflow["status"]))
            except (KeyError, ValueError):
                return WorkflowStatus.IDLE

    def _get_or_create_workflow(self, workflow_id: str) -> dict[str, Any]:
        """Get or create workflow record.

        Args:
            workflow_id: UUID of the workflow

        Returns:
            Workflow record dictionary
        """
        if workflow_id not in self._workflows:
            self._workflows[workflow_id] = {
                "id": workflow_id,
                "status": WorkflowStatus.IDLE.value,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        return self._workflows[workflow_id]


# Singleton instance
_workflow_operation_service: WorkflowOperationService | None = None


def get_workflow_operation_service() -> WorkflowOperationService:
    """Get singleton workflow operation service instance.

    Returns:
        WorkflowOperationService instance
    """
    global _workflow_operation_service
    if _workflow_operation_service is None:
        _workflow_operation_service = WorkflowOperationService()
    return _workflow_operation_service


def get_workflow_service() -> WorkflowOperationService:
    """Backward-compatible alias used by older control-plane callers."""
    return get_workflow_operation_service()
