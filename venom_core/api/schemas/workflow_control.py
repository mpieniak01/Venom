"""Schema definitions for Workflow Control Plane API.

This module defines the contract for the Workflow Control Plane,
including request/response models, enums, and validation rules.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ApplyMode(str, Enum):
    """Mode of applying configuration changes."""

    HOT_SWAP = "hot_swap"  # Applied immediately without restart
    RESTART_REQUIRED = "restart_required"  # Requires service restart
    REJECTED = "rejected"  # Change was rejected


class ReasonCode(str, Enum):
    """Reason codes for operation results."""

    # Success codes
    SUCCESS_HOT_SWAP = "success_hot_swap"
    SUCCESS_RESTART_PENDING = "success_restart_pending"

    # Rejection codes
    INVALID_CONFIGURATION = "invalid_configuration"
    INCOMPATIBLE_COMBINATION = "incompatible_combination"
    DEPENDENCY_MISSING = "dependency_missing"
    SERVICE_UNAVAILABLE = "service_unavailable"
    FORBIDDEN_TRANSITION = "forbidden_transition"
    INVALID_STATE = "invalid_state"

    # Validation codes
    KERNEL_RUNTIME_MISMATCH = "kernel_runtime_mismatch"
    PROVIDER_MODEL_MISMATCH = "provider_model_mismatch"
    EMBEDDING_INCOMPATIBLE = "embedding_incompatible"
    INTENT_MODE_CONFLICT = "intent_mode_conflict"

    # Operation codes
    OPERATION_IN_PROGRESS = "operation_in_progress"
    OPERATION_COMPLETED = "operation_completed"
    OPERATION_FAILED = "operation_failed"
    OPERATION_CANCELLED = "operation_cancelled"


class ResourceType(str, Enum):
    """Types of resources managed by control plane."""

    DECISION_STRATEGY = "decision_strategy"
    INTENT_MODE = "intent_mode"
    KERNEL = "kernel"
    RUNTIME = "runtime"
    PROVIDER = "provider"
    EMBEDDING_MODEL = "embedding_model"
    WORKFLOW = "workflow"
    CONFIG = "config"


class WorkflowOperation(str, Enum):
    """Operations that can be performed on workflows."""

    PAUSE = "pause"
    RESUME = "resume"
    CANCEL = "cancel"
    RETRY = "retry"
    DRY_RUN = "dry_run"


class WorkflowStatus(str, Enum):
    """Status of a workflow execution."""

    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# Request Models


class ResourceChange(BaseModel):
    """Single resource change in a plan."""

    resource_type: ResourceType
    resource_id: str
    action: str  # update, create, delete, restart
    current_value: Optional[Any] = None
    new_value: Optional[Any] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ControlPlanRequest(BaseModel):
    """Request to plan configuration changes."""

    changes: list[ResourceChange]
    dry_run: bool = False
    force: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class ControlApplyRequest(BaseModel):
    """Request to apply planned changes."""

    execution_ticket: str
    confirm_restart: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkflowOperationRequest(BaseModel):
    """Request to perform workflow operation."""

    workflow_id: UUID
    operation: WorkflowOperation
    step_id: Optional[str] = None  # For retry from specific step
    metadata: dict[str, Any] = Field(default_factory=dict)


# Response Models


class CompatibilityReport(BaseModel):
    """Compatibility analysis for planned changes."""

    compatible: bool
    issues: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    affected_services: list[str] = Field(default_factory=list)


class AppliedChange(BaseModel):
    """Record of an applied change."""

    resource_type: ResourceType
    resource_id: str
    action: str
    apply_mode: ApplyMode
    reason_code: ReasonCode
    message: str
    timestamp: datetime


class ControlPlanResponse(BaseModel):
    """Response from plan endpoint."""

    execution_ticket: str
    valid: bool
    reason_code: ReasonCode
    compatibility_report: CompatibilityReport
    planned_changes: list[AppliedChange]
    hot_swap_changes: list[str] = Field(default_factory=list)
    restart_required_services: list[str] = Field(default_factory=list)
    rejected_changes: list[str] = Field(default_factory=list)
    estimated_duration_seconds: Optional[float] = None


class ControlApplyResponse(BaseModel):
    """Response from apply endpoint."""

    execution_ticket: str
    apply_mode: ApplyMode
    reason_code: ReasonCode
    message: str
    applied_changes: list[AppliedChange]
    pending_restart: list[str] = Field(default_factory=list)
    failed_changes: list[str] = Field(default_factory=list)
    rollback_available: bool = False


class SystemState(BaseModel):
    """Current state of the entire system."""

    timestamp: datetime
    decision_strategy: str
    intent_mode: str
    kernel: str
    runtime: dict[str, Any]
    provider: dict[str, Any]
    embedding_model: str
    provider_source: Optional[str] = None
    embedding_source: Optional[str] = None
    workflow_status: WorkflowStatus
    active_operations: list[str] = Field(default_factory=list)
    health: dict[str, Any] = Field(default_factory=dict)


class ControlStateResponse(BaseModel):
    """Response from state endpoint."""

    system_state: SystemState
    last_operation: Optional[str] = None
    pending_changes: list[str] = Field(default_factory=list)


class ControlOptionsCatalog(BaseModel):
    """Catalog of available options grouped by source type."""

    local: list[str] = Field(default_factory=list)
    cloud: list[str] = Field(default_factory=list)


class ControlOptionsActive(BaseModel):
    """Active source types inferred from current state."""

    provider_source: str = "local"
    embedding_source: str = "local"


class ControlOptionsResponse(BaseModel):
    """Response with workflow control option catalogs."""

    provider_sources: list[str] = Field(default_factory=lambda: ["local", "cloud"])
    embedding_sources: list[str] = Field(default_factory=lambda: ["local", "cloud"])
    providers: ControlOptionsCatalog
    embeddings: ControlOptionsCatalog
    active: ControlOptionsActive


class WorkflowOperationResponse(BaseModel):
    """Response from workflow operation."""

    workflow_id: UUID
    operation: WorkflowOperation
    status: WorkflowStatus
    reason_code: ReasonCode
    message: str
    timestamp: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class AuditEntry(BaseModel):
    """Audit trail entry for control plane operations."""

    operation_id: str
    timestamp: datetime
    triggered_by: str
    operation_type: str
    resource_type: ResourceType
    resource_id: str
    params: dict[str, Any]
    result: str  # success, failure, cancelled
    reason_code: ReasonCode
    duration_ms: Optional[float] = None
    error_message: Optional[str] = None


class ControlAuditResponse(BaseModel):
    """Response from audit trail query."""

    entries: list[AuditEntry]
    total_count: int
    page: int = 1
    page_size: int = 50
