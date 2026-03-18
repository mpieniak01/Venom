"""API routes for Workflow Control Plane.

This module provides endpoints for:
- Planning configuration changes
- Applying changes with validation
- Querying system state
- Audit trail access
"""

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from venom_core.api.dependencies import (
    get_control_plane_audit_trail,
    get_control_plane_service,
)
from venom_core.api.schemas.workflow_control import AuditEntry as AuditEntryModel
from venom_core.api.schemas.workflow_control import (
    ControlApplyRequest,
    ControlApplyResponse,
    ControlAuditResponse,
    ControlOptionsResponse,
    ControlPlanRequest,
    ControlPlanResponse,
    ControlStateResponse,
    ResourceType,
    WorkflowOperation,
)
from venom_core.services.control_plane import ControlPlaneService
from venom_core.services.control_plane_audit import ControlPlaneAuditTrail
from venom_core.services.runtime_controller import ServiceType, runtime_controller
from venom_core.services.workflow_operations import get_workflow_operation_service
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/workflow/control", tags=["workflow-control"])


def _extract_user_from_request(request: Request) -> str:
    """Extract user identifier from request for audit logging.

    Args:
        request: FastAPI request object

    Returns:
        User identifier string
    """
    try:
        # Try user set by authentication middleware
        if hasattr(request, "state") and hasattr(request.state, "user"):
            user = request.state.user
            if user:
                return str(user)

        # Fallback to common identity headers
        if hasattr(request, "headers"):
            for header_name in [
                "x-authenticated-user",
                "x-user",
                "x-admin-user",
            ]:
                user = request.headers.get(header_name)
                if user:
                    return user

        # Final fallback
        return "unknown"
    except Exception as e:
        logger.warning(f"Could not extract user from request: {e}")
        return "unknown"


@router.post(
    "/plan",
    response_model=ControlPlanResponse,
    responses={
        400: {"description": "Invalid request"},
        500: {"description": "Internal server error"},
    },
)
async def plan_changes(
    request: Request,
    plan_request: ControlPlanRequest,
    service: Annotated[ControlPlaneService, Depends(get_control_plane_service)],
):
    """Plan configuration changes and validate compatibility.

    This endpoint analyzes requested changes and returns:
    - Validation results
    - Compatibility report
    - Required restarts
    - Execution ticket for applying changes

    Args:
        request: FastAPI request
        plan_request: Plan request with desired changes
        service: Control plane service injected via Depends

    Returns:
        Plan response with validation results
    """
    try:
        user = _extract_user_from_request(request)
        return service.plan_changes(plan_request, triggered_by=user)
    except Exception as e:
        logger.exception("Failed to plan changes")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post(
    "/apply",
    response_model=ControlApplyResponse,
    responses={
        400: {"description": "Invalid request or execution ticket"},
        500: {"description": "Internal server error"},
    },
)
async def apply_changes(
    request: Request,
    apply_request: ControlApplyRequest,
    service: Annotated[ControlPlaneService, Depends(get_control_plane_service)],
):
    """Apply previously planned changes.

    This endpoint executes changes that were previously validated
    via the /plan endpoint.

    Args:
        request: FastAPI request
        apply_request: Apply request with execution ticket
        service: Control plane service injected via Depends

    Returns:
        Apply response with results
    """
    try:
        user = _extract_user_from_request(request)
        return service.apply_changes(apply_request, triggered_by=user)
    except Exception as e:
        logger.exception("Failed to apply changes")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get(
    "/state",
    response_model=ControlStateResponse,
    responses={
        500: {"description": "Internal server error"},
    },
)
async def get_control_state(
    service: Annotated[ControlPlaneService, Depends(get_control_plane_service)],
    request_id: Optional[str] = Query(default=None),
):
    """Get canonical operator state for workflow-control.

    Args:
        service: Control plane service injected via Depends
        request_id: Optional explicit request selector

    Returns:
        Current canonical operator state
    """
    try:
        return service.get_control_state(request_id=request_id)
    except Exception as e:
        logger.exception("Failed to get system state")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get(
    "/options",
    response_model=ControlOptionsResponse,
    responses={
        500: {"description": "Internal server error"},
    },
)
async def get_control_options(
    service: Annotated[ControlPlaneService, Depends(get_control_plane_service)],
):
    """Get local/cloud option catalogs for provider and embedding selectors.

    Args:
        service: Control plane service injected via Depends
    """
    try:
        options = service.get_control_options()
        return ControlOptionsResponse(**options)
    except Exception as e:
        logger.exception("Failed to get control options")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post(
    "/runtime/{service_id}/{action}",
    responses={
        400: {"description": "Invalid service or runtime action"},
        500: {"description": "Internal server error"},
    },
)
async def runtime_service_action(
    service_id: str,
    action: str,
):
    """Execute runtime service action via workflow-control gateway."""
    try:
        try:
            service_type = ServiceType(service_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown service_id '{service_id}'",
            ) from exc

        if action not in {"start", "stop", "restart"}:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown runtime action '{action}'",
            )

        if action == "start":
            return runtime_controller.start_service(service_type)
        if action == "stop":
            return runtime_controller.stop_service(service_type)
        return runtime_controller.restart_service(service_type)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            "Failed runtime action for service_id=%s action=%s", service_id, action
        )
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post(
    "/workflow/{request_id}/{operation}",
    responses={
        400: {"description": "Invalid workflow operation"},
        500: {"description": "Internal server error"},
    },
)
async def workflow_operation_gateway(
    request: Request,
    request_id: str,
    operation: WorkflowOperation,
):
    """Execute workflow operation via workflow-control gateway."""
    try:
        user = _extract_user_from_request(request)
        service = get_workflow_operation_service()

        if operation == WorkflowOperation.PAUSE:
            return service.pause_workflow(
                workflow_id=request_id, triggered_by=user, metadata={}
            )
        if operation == WorkflowOperation.RESUME:
            return service.resume_workflow(
                workflow_id=request_id, triggered_by=user, metadata={}
            )
        if operation == WorkflowOperation.CANCEL:
            return service.cancel_workflow(
                workflow_id=request_id, triggered_by=user, metadata={}
            )
        if operation == WorkflowOperation.RETRY:
            return service.retry_workflow(
                workflow_id=request_id,
                triggered_by=user,
                step_id=None,
                metadata={},
            )
        return service.dry_run(workflow_id=request_id, triggered_by=user, metadata={})
    except Exception as e:
        logger.exception(
            "Failed workflow gateway operation=%s request_id=%s",
            operation,
            request_id,
        )
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get(
    "/audit",
    response_model=ControlAuditResponse,
    responses={
        500: {"description": "Internal server error"},
    },
)
async def get_audit_trail(
    audit_trail: Annotated[
        ControlPlaneAuditTrail, Depends(get_control_plane_audit_trail)
    ],
    operation_type: Optional[str] = None,
    resource_type: Optional[ResourceType] = None,
    triggered_by: Optional[str] = None,
    result: Optional[str] = None,
    page: Annotated[int, Query(ge=1, description="Page number (minimum 1)")] = 1,
    page_size: Annotated[
        int, Query(ge=1, le=100, description="Items per page (1-100)")
    ] = 50,
):
    """Get audit trail of control plane operations.

    Supports filtering by:
    - operation_type (plan, apply, etc.)
    - resource_type (config, workflow, etc.)
    - triggered_by (user identifier)
    - result (success, failure, cancelled)

    Args:
        operation_type: Filter by operation type
        resource_type: Filter by resource type
        triggered_by: Filter by user
        result: Filter by result
        page: Page number (1-based)
        page_size: Number of entries per page
        audit_trail: Audit trail service injected via Depends

    Returns:
        Audit trail entries
    """
    try:
        # Calculate offset
        offset = (page - 1) * page_size
        limit = page_size

        # Get entries with filters
        entries = audit_trail.get_entries(
            operation_type=operation_type,
            resource_type=resource_type,
            triggered_by=triggered_by,
            result=result,
            limit=None,  # Get all matching entries first
        )

        total_count = len(entries)

        # Apply pagination
        paginated_entries = entries[offset : offset + limit]

        # Convert to response models
        entry_models = [
            AuditEntryModel(
                operation_id=e.operation_id,
                timestamp=e.timestamp,
                triggered_by=e.triggered_by,
                operation_type=e.operation_type,
                resource_type=e.resource_type,
                resource_id=e.resource_id,
                params=e.params,
                result=e.result,
                reason_code=e.reason_code,
                duration_ms=e.duration_ms,
                error_message=e.error_message,
            )
            for e in paginated_entries
        ]

        return ControlAuditResponse(
            entries=entry_models,
            total_count=total_count,
            page=page,
            page_size=page_size,
        )
    except Exception as e:
        logger.exception("Failed to get audit trail")
        raise HTTPException(status_code=500, detail=str(e)) from e
