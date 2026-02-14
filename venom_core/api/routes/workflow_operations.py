"""API routes for Workflow Operations.

This module provides endpoints for workflow control operations:
- pause/resume workflows
- cancel workflows
- retry failed workflows
- dry-run execution
"""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request

from venom_core.api.model_schemas.workflow_control import (
    WorkflowOperationRequest,
    WorkflowOperationResponse,
)
from venom_core.services.workflow_operations import (
    StateTransitionError,
    get_workflow_operation_service,
)
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/workflow/operations", tags=["workflow-operations"])


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
    "/pause",
    response_model=WorkflowOperationResponse,
    responses={
        400: {"description": "Invalid request or transition"},
        500: {"description": "Internal server error"},
    },
)
async def pause_workflow(request: Request, operation_request: WorkflowOperationRequest):
    """Pause a running workflow.

    This endpoint pauses a workflow that is currently running.
    The workflow can be resumed later from the same state.

    Args:
        request: FastAPI request
        operation_request: Workflow operation request

    Returns:
        Workflow operation response with result
    """
    try:
        user = _extract_user_from_request(request)
        service = get_workflow_operation_service()

        return service.pause_workflow(
            workflow_id=str(operation_request.workflow_id),
            triggered_by=user,
            metadata=operation_request.metadata,
        )
    except StateTransitionError as e:
        logger.warning(f"Invalid state transition for pause: {e}")
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception("Failed to pause workflow")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post(
    "/resume",
    response_model=WorkflowOperationResponse,
    responses={
        400: {"description": "Invalid request or transition"},
        500: {"description": "Internal server error"},
    },
)
async def resume_workflow(request: Request, operation_request: WorkflowOperationRequest):
    """Resume a paused workflow.

    This endpoint resumes a workflow that was previously paused.
    The workflow will continue from where it was paused.

    Args:
        request: FastAPI request
        operation_request: Workflow operation request

    Returns:
        Workflow operation response with result
    """
    try:
        user = _extract_user_from_request(request)
        service = get_workflow_operation_service()

        return service.resume_workflow(
            workflow_id=str(operation_request.workflow_id),
            triggered_by=user,
            metadata=operation_request.metadata,
        )
    except StateTransitionError as e:
        logger.warning(f"Invalid state transition for resume: {e}")
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception("Failed to resume workflow")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post(
    "/cancel",
    response_model=WorkflowOperationResponse,
    responses={
        400: {"description": "Invalid request or transition"},
        500: {"description": "Internal server error"},
    },
)
async def cancel_workflow(request: Request, operation_request: WorkflowOperationRequest):
    """Cancel a workflow.

    This endpoint cancels a running or paused workflow.
    The workflow will be terminated and cannot be resumed.

    Args:
        request: FastAPI request
        operation_request: Workflow operation request

    Returns:
        Workflow operation response with result
    """
    try:
        user = _extract_user_from_request(request)
        service = get_workflow_operation_service()

        return service.cancel_workflow(
            workflow_id=str(operation_request.workflow_id),
            triggered_by=user,
            metadata=operation_request.metadata,
        )
    except StateTransitionError as e:
        logger.warning(f"Invalid state transition for cancel: {e}")
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception("Failed to cancel workflow")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post(
    "/retry",
    response_model=WorkflowOperationResponse,
    responses={
        400: {"description": "Invalid request or transition"},
        500: {"description": "Internal server error"},
    },
)
async def retry_workflow(request: Request, operation_request: WorkflowOperationRequest):
    """Retry a failed or cancelled workflow.

    This endpoint retries a workflow that failed or was cancelled.
    Optionally, can retry from a specific step.

    Args:
        request: FastAPI request
        operation_request: Workflow operation request (with optional step_id)

    Returns:
        Workflow operation response with result
    """
    try:
        user = _extract_user_from_request(request)
        service = get_workflow_operation_service()

        return service.retry_workflow(
            workflow_id=str(operation_request.workflow_id),
            triggered_by=user,
            step_id=operation_request.step_id,
            metadata=operation_request.metadata,
        )
    except StateTransitionError as e:
        logger.warning(f"Invalid state transition for retry: {e}")
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception("Failed to retry workflow")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post(
    "/dry-run",
    response_model=WorkflowOperationResponse,
    responses={
        500: {"description": "Internal server error"},
    },
)
async def dry_run_workflow(request: Request, operation_request: WorkflowOperationRequest):
    """Perform a dry-run of workflow execution.

    This endpoint simulates workflow execution without actually
    performing any actions. Useful for testing decision paths.

    Args:
        request: FastAPI request
        operation_request: Workflow operation request

    Returns:
        Workflow operation response with simulated result
    """
    try:
        user = _extract_user_from_request(request)
        service = get_workflow_operation_service()

        return service.dry_run(
            workflow_id=str(operation_request.workflow_id),
            triggered_by=user,
            metadata=operation_request.metadata,
        )
    except Exception as e:
        logger.exception("Failed to perform dry-run")
        raise HTTPException(status_code=500, detail=str(e)) from e
