"""Contract tests for Workflow Control Plane API schemas.

These tests validate the contract definitions, ensuring schema stability
and backward compatibility for the Control Plane API.
"""

from datetime import datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from venom_core.api.model_schemas.workflow_control import (
    AppliedChange,
    ApplyMode,
    AuditEntry,
    CompatibilityReport,
    ControlApplyRequest,
    ControlApplyResponse,
    ControlAuditResponse,
    ControlPlanRequest,
    ControlPlanResponse,
    ControlStateResponse,
    ReasonCode,
    ResourceChange,
    ResourceType,
    SystemState,
    WorkflowOperation,
    WorkflowOperationRequest,
    WorkflowOperationResponse,
    WorkflowStatus,
)


class TestEnumContracts:
    """Test enum contracts for stability."""

    def test_apply_mode_values(self):
        """Test ApplyMode enum has expected values."""
        assert ApplyMode.HOT_SWAP.value == "hot_swap"
        assert ApplyMode.RESTART_REQUIRED.value == "restart_required"
        assert ApplyMode.REJECTED.value == "rejected"

    def test_reason_code_values(self):
        """Test ReasonCode enum has core values."""
        # Success codes
        assert ReasonCode.SUCCESS_HOT_SWAP.value == "success_hot_swap"
        assert ReasonCode.SUCCESS_RESTART_PENDING.value == "success_restart_pending"

        # Rejection codes
        assert ReasonCode.INVALID_CONFIGURATION.value == "invalid_configuration"
        assert ReasonCode.INCOMPATIBLE_COMBINATION.value == "incompatible_combination"

        # Operation codes
        assert ReasonCode.OPERATION_COMPLETED.value == "operation_completed"
        assert ReasonCode.OPERATION_FAILED.value == "operation_failed"

    def test_resource_type_values(self):
        """Test ResourceType enum has expected values."""
        assert ResourceType.DECISION_STRATEGY.value == "decision_strategy"
        assert ResourceType.INTENT_MODE.value == "intent_mode"
        assert ResourceType.KERNEL.value == "kernel"
        assert ResourceType.RUNTIME.value == "runtime"
        assert ResourceType.PROVIDER.value == "provider"
        assert ResourceType.EMBEDDING_MODEL.value == "embedding_model"
        assert ResourceType.WORKFLOW.value == "workflow"
        assert ResourceType.CONFIG.value == "config"

    def test_workflow_operation_values(self):
        """Test WorkflowOperation enum has expected values."""
        assert WorkflowOperation.PAUSE.value == "pause"
        assert WorkflowOperation.RESUME.value == "resume"
        assert WorkflowOperation.CANCEL.value == "cancel"
        assert WorkflowOperation.RETRY.value == "retry"
        assert WorkflowOperation.DRY_RUN.value == "dry_run"

    def test_workflow_status_values(self):
        """Test WorkflowStatus enum has expected values."""
        assert WorkflowStatus.IDLE.value == "idle"
        assert WorkflowStatus.RUNNING.value == "running"
        assert WorkflowStatus.PAUSED.value == "paused"
        assert WorkflowStatus.COMPLETED.value == "completed"
        assert WorkflowStatus.FAILED.value == "failed"
        assert WorkflowStatus.CANCELLED.value == "cancelled"


class TestRequestModels:
    """Test request model contracts."""

    def test_resource_change_minimal(self):
        """Test ResourceChange with minimal required fields."""
        change = ResourceChange(
            resource_type=ResourceType.KERNEL,
            resource_id="standard",
            action="update",
        )
        assert change.resource_type == ResourceType.KERNEL
        assert change.resource_id == "standard"
        assert change.action == "update"
        assert change.current_value is None
        assert change.new_value is None
        assert change.metadata == {}

    def test_resource_change_full(self):
        """Test ResourceChange with all fields."""
        change = ResourceChange(
            resource_type=ResourceType.PROVIDER,
            resource_id="ollama",
            action="update",
            current_value="llama2",
            new_value="llama3",
            metadata={"reason": "upgrade"},
        )
        assert change.resource_type == ResourceType.PROVIDER
        assert change.current_value == "llama2"
        assert change.new_value == "llama3"
        assert change.metadata["reason"] == "upgrade"

    def test_control_plan_request_minimal(self):
        """Test ControlPlanRequest with minimal fields."""
        change = ResourceChange(
            resource_type=ResourceType.KERNEL,
            resource_id="standard",
            action="update",
        )
        request = ControlPlanRequest(changes=[change])

        assert len(request.changes) == 1
        assert request.dry_run is False
        assert request.force is False
        assert request.metadata == {}

    def test_control_plan_request_full(self):
        """Test ControlPlanRequest with all fields."""
        change = ResourceChange(
            resource_type=ResourceType.KERNEL,
            resource_id="standard",
            action="update",
        )
        request = ControlPlanRequest(
            changes=[change],
            dry_run=True,
            force=True,
            metadata={"user": "admin"},
        )

        assert request.dry_run is True
        assert request.force is True
        assert request.metadata["user"] == "admin"

    def test_control_apply_request(self):
        """Test ControlApplyRequest contract."""
        ticket = str(uuid4())
        request = ControlApplyRequest(
            execution_ticket=ticket,
            confirm_restart=True,
            metadata={"note": "maintenance window"},
        )

        assert request.execution_ticket == ticket
        assert request.confirm_restart is True
        assert request.metadata["note"] == "maintenance window"

    def test_workflow_operation_request(self):
        """Test WorkflowOperationRequest contract."""
        workflow_id = uuid4()
        request = WorkflowOperationRequest(
            workflow_id=workflow_id,
            operation=WorkflowOperation.PAUSE,
            step_id="step_123",
            metadata={"reason": "investigation"},
        )

        assert request.workflow_id == workflow_id
        assert request.operation == WorkflowOperation.PAUSE
        assert request.step_id == "step_123"


class TestResponseModels:
    """Test response model contracts."""

    def test_compatibility_report(self):
        """Test CompatibilityReport contract."""
        report = CompatibilityReport(
            compatible=False,
            issues=["Kernel not compatible with runtime"],
            warnings=["High memory usage expected"],
            affected_services=["backend", "ui"],
        )

        assert report.compatible is False
        assert len(report.issues) == 1
        assert len(report.warnings) == 1
        assert "backend" in report.affected_services

    def test_applied_change(self):
        """Test AppliedChange contract."""
        change = AppliedChange(
            resource_type=ResourceType.KERNEL,
            resource_id="standard",
            action="update",
            apply_mode=ApplyMode.RESTART_REQUIRED,
            reason_code=ReasonCode.SUCCESS_RESTART_PENDING,
            message="Kernel updated, restart required",
            timestamp=datetime.utcnow(),
        )

        assert change.resource_type == ResourceType.KERNEL
        assert change.apply_mode == ApplyMode.RESTART_REQUIRED
        assert change.reason_code == ReasonCode.SUCCESS_RESTART_PENDING

    def test_control_plan_response(self):
        """Test ControlPlanResponse contract."""
        ticket = str(uuid4())
        compatibility = CompatibilityReport(
            compatible=True, issues=[], warnings=[], affected_services=[]
        )
        change = AppliedChange(
            resource_type=ResourceType.KERNEL,
            resource_id="standard",
            action="update",
            apply_mode=ApplyMode.HOT_SWAP,
            reason_code=ReasonCode.SUCCESS_HOT_SWAP,
            message="Change validated",
            timestamp=datetime.utcnow(),
        )

        response = ControlPlanResponse(
            execution_ticket=ticket,
            valid=True,
            reason_code=ReasonCode.SUCCESS_HOT_SWAP,
            compatibility_report=compatibility,
            planned_changes=[change],
            hot_swap_changes=["standard"],
            restart_required_services=[],
            rejected_changes=[],
            estimated_duration_seconds=1.0,
        )

        assert response.execution_ticket == ticket
        assert response.valid is True
        assert len(response.planned_changes) == 1
        assert len(response.hot_swap_changes) == 1

    def test_control_apply_response(self):
        """Test ControlApplyResponse contract."""
        ticket = str(uuid4())
        change = AppliedChange(
            resource_type=ResourceType.KERNEL,
            resource_id="standard",
            action="update",
            apply_mode=ApplyMode.HOT_SWAP,
            reason_code=ReasonCode.SUCCESS_HOT_SWAP,
            message="Applied successfully",
            timestamp=datetime.utcnow(),
        )

        response = ControlApplyResponse(
            execution_ticket=ticket,
            apply_mode=ApplyMode.HOT_SWAP,
            reason_code=ReasonCode.SUCCESS_HOT_SWAP,
            message="All changes applied",
            applied_changes=[change],
            pending_restart=[],
            failed_changes=[],
            rollback_available=True,
        )

        assert response.execution_ticket == ticket
        assert response.apply_mode == ApplyMode.HOT_SWAP
        assert len(response.applied_changes) == 1
        assert response.rollback_available is True

    def test_system_state(self):
        """Test SystemState contract."""
        state = SystemState(
            timestamp=datetime.utcnow(),
            decision_strategy="standard",
            intent_mode="simple",
            kernel="standard",
            runtime={"services": []},
            provider={"active": "ollama", "available": ["ollama", "openai"]},
            embedding_model="sentence-transformers",
            workflow_status=WorkflowStatus.IDLE,
            active_operations=[],
            health={"overall": "healthy"},
        )

        assert state.decision_strategy == "standard"
        assert state.intent_mode == "simple"
        assert state.kernel == "standard"
        assert state.workflow_status == WorkflowStatus.IDLE
        assert state.provider["active"] == "ollama"

    def test_control_state_response(self):
        """Test ControlStateResponse contract."""
        state = SystemState(
            timestamp=datetime.utcnow(),
            decision_strategy="standard",
            intent_mode="simple",
            kernel="standard",
            runtime={},
            provider={"active": "ollama"},
            embedding_model="sentence-transformers",
            workflow_status=WorkflowStatus.IDLE,
            active_operations=[],
            health={},
        )

        response = ControlStateResponse(
            system_state=state,
            last_operation="plan_123",
            pending_changes=["change_1"],
        )

        assert response.system_state.kernel == "standard"
        assert response.last_operation == "plan_123"
        assert len(response.pending_changes) == 1

    def test_workflow_operation_response(self):
        """Test WorkflowOperationResponse contract."""
        workflow_id = uuid4()
        response = WorkflowOperationResponse(
            workflow_id=workflow_id,
            operation=WorkflowOperation.PAUSE,
            status=WorkflowStatus.PAUSED,
            reason_code=ReasonCode.OPERATION_COMPLETED,
            message="Workflow paused successfully",
            timestamp=datetime.utcnow(),
            metadata={"duration_ms": 100},
        )

        assert response.workflow_id == workflow_id
        assert response.operation == WorkflowOperation.PAUSE
        assert response.status == WorkflowStatus.PAUSED

    def test_audit_entry(self):
        """Test AuditEntry contract."""
        entry = AuditEntry(
            operation_id=str(uuid4()),
            timestamp=datetime.utcnow(),
            triggered_by="admin",
            operation_type="plan",
            resource_type=ResourceType.CONFIG,
            resource_id="system",
            params={"changes": 1},
            result="success",
            reason_code=ReasonCode.SUCCESS_HOT_SWAP,
            duration_ms=50.0,
            error_message=None,
        )

        assert entry.triggered_by == "admin"
        assert entry.operation_type == "plan"
        assert entry.result == "success"
        assert entry.duration_ms == 50.0

    def test_control_audit_response(self):
        """Test ControlAuditResponse contract."""
        entry = AuditEntry(
            operation_id=str(uuid4()),
            timestamp=datetime.utcnow(),
            triggered_by="admin",
            operation_type="plan",
            resource_type=ResourceType.CONFIG,
            resource_id="system",
            params={},
            result="success",
            reason_code=ReasonCode.SUCCESS_HOT_SWAP,
        )

        response = ControlAuditResponse(
            entries=[entry],
            total_count=1,
            page=1,
            page_size=50,
        )

        assert len(response.entries) == 1
        assert response.total_count == 1
        assert response.page == 1


class TestValidation:
    """Test validation rules."""

    def test_resource_change_requires_type(self):
        """Test ResourceChange requires resource_type."""
        with pytest.raises(ValidationError):
            ResourceChange(resource_id="test", action="update")

    def test_resource_change_requires_id(self):
        """Test ResourceChange requires resource_id."""
        with pytest.raises(ValidationError):
            ResourceChange(resource_type=ResourceType.KERNEL, action="update")

    def test_resource_change_requires_action(self):
        """Test ResourceChange requires action."""
        with pytest.raises(ValidationError):
            ResourceChange(resource_type=ResourceType.KERNEL, resource_id="test")

    def test_control_plan_request_requires_changes(self):
        """Test ControlPlanRequest requires changes list."""
        with pytest.raises(ValidationError):
            ControlPlanRequest()

    def test_control_apply_request_requires_ticket(self):
        """Test ControlApplyRequest requires execution_ticket."""
        with pytest.raises(ValidationError):
            ControlApplyRequest()


class TestBackwardCompatibility:
    """Test backward compatibility of contracts."""

    def test_resource_change_accepts_extra_metadata(self):
        """Test ResourceChange metadata accepts arbitrary keys."""
        change = ResourceChange(
            resource_type=ResourceType.KERNEL,
            resource_id="standard",
            action="update",
            metadata={
                "custom_field_1": "value1",
                "custom_field_2": 123,
                "nested": {"key": "value"},
            },
        )
        assert change.metadata["custom_field_1"] == "value1"
        assert change.metadata["nested"]["key"] == "value"

    def test_optional_fields_have_defaults(self):
        """Test that optional fields have sensible defaults."""
        change = ResourceChange(
            resource_type=ResourceType.KERNEL,
            resource_id="test",
            action="update",
        )
        assert change.metadata == {}
        assert change.current_value is None
        assert change.new_value is None

        request = ControlPlanRequest(changes=[change])
        assert request.dry_run is False
        assert request.force is False
        assert request.metadata == {}
