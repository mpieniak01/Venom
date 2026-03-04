"""Routes for Academy self-learning orchestration."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query

from venom_core.api.schemas.academy_self_learning import (
    SelfLearningCapabilitiesResponse,
    SelfLearningDeleteResponse,
    SelfLearningListResponse,
    SelfLearningRunStatusResponse,
    SelfLearningStartRequest,
    SelfLearningStartResponse,
)
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/academy/self-learning", tags=["academy"])

_self_learning_service: Any | None = None

SERVICE_UNAVAILABLE_DETAIL = "SelfLearningService is unavailable"
INTERNAL_ERROR_DETAIL = "Failed to process self-learning request"


def set_dependencies(*, self_learning_service: Any | None = None) -> None:
    """Set runtime dependencies for self-learning routes."""

    global _self_learning_service
    _self_learning_service = self_learning_service


@router.post(
    "/start",
    responses={
        400: {"description": "Invalid request payload."},
        500: {"description": INTERNAL_ERROR_DETAIL},
        503: {"description": SERVICE_UNAVAILABLE_DETAIL},
    },
)
async def start_self_learning(
    request: SelfLearningStartRequest,
) -> SelfLearningStartResponse:
    if _self_learning_service is None:
        raise HTTPException(status_code=503, detail=SERVICE_UNAVAILABLE_DETAIL)
    try:
        run_id = _self_learning_service.start_run(
            mode=request.mode,
            sources=request.sources,
            limits=request.limits.model_dump(),
            llm_config=request.llm_config.model_dump() if request.llm_config else None,
            rag_config=request.rag_config.model_dump() if request.rag_config else None,
            dry_run=request.dry_run,
        )
        return SelfLearningStartResponse(
            run_id=run_id,
            message="Self-learning run started",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to start self-learning run")
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR_DETAIL) from exc


@router.get(
    "/capabilities",
    responses={
        500: {"description": INTERNAL_ERROR_DETAIL},
        503: {"description": SERVICE_UNAVAILABLE_DETAIL},
    },
)
async def get_self_learning_capabilities() -> SelfLearningCapabilitiesResponse:
    if _self_learning_service is None:
        raise HTTPException(status_code=503, detail=SERVICE_UNAVAILABLE_DETAIL)
    try:
        payload = await _self_learning_service.get_capabilities()
        return SelfLearningCapabilitiesResponse(**payload)
    except Exception as exc:
        logger.exception("Failed to load self-learning capabilities")
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR_DETAIL) from exc


@router.get(
    "/{run_id}/status",
    responses={
        404: {"description": "Self-learning run not found."},
        500: {"description": INTERNAL_ERROR_DETAIL},
        503: {"description": SERVICE_UNAVAILABLE_DETAIL},
    },
)
def get_self_learning_status(run_id: str) -> SelfLearningRunStatusResponse:
    if _self_learning_service is None:
        raise HTTPException(status_code=503, detail=SERVICE_UNAVAILABLE_DETAIL)
    try:
        payload = _self_learning_service.get_status(run_id)
        if payload is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
        return SelfLearningRunStatusResponse(**payload)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to get self-learning status for run %s", run_id)
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR_DETAIL) from exc


@router.get(
    "/list",
    responses={
        500: {"description": INTERNAL_ERROR_DETAIL},
        503: {"description": SERVICE_UNAVAILABLE_DETAIL},
    },
)
def list_self_learning_runs(
    limit: Annotated[int, Query(ge=1, le=200)] = 20,
) -> SelfLearningListResponse:
    if _self_learning_service is None:
        raise HTTPException(status_code=503, detail=SERVICE_UNAVAILABLE_DETAIL)
    try:
        runs_payload = _self_learning_service.list_runs(limit=limit)
        runs = [SelfLearningRunStatusResponse(**run) for run in runs_payload]
        return SelfLearningListResponse(runs=runs, count=len(runs))
    except Exception as exc:
        logger.exception("Failed to list self-learning runs")
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR_DETAIL) from exc


@router.delete(
    "/all",
    responses={
        500: {"description": INTERNAL_ERROR_DETAIL},
        503: {"description": SERVICE_UNAVAILABLE_DETAIL},
    },
)
def clear_all_self_learning_runs() -> SelfLearningDeleteResponse:
    if _self_learning_service is None:
        raise HTTPException(status_code=503, detail=SERVICE_UNAVAILABLE_DETAIL)
    try:
        removed = _self_learning_service.clear_all_runs()
        return SelfLearningDeleteResponse(
            message=f"Removed {removed} self-learning runs",
            count=removed,
        )
    except Exception as exc:
        logger.exception("Failed to clear self-learning runs")
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR_DETAIL) from exc


@router.delete(
    "/{run_id}",
    responses={
        404: {"description": "Self-learning run not found."},
        500: {"description": INTERNAL_ERROR_DETAIL},
        503: {"description": SERVICE_UNAVAILABLE_DETAIL},
    },
)
def delete_self_learning_run(run_id: str) -> SelfLearningDeleteResponse:
    if _self_learning_service is None:
        raise HTTPException(status_code=503, detail=SERVICE_UNAVAILABLE_DETAIL)
    try:
        removed = _self_learning_service.delete_run(run_id)
        if not removed:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
        return SelfLearningDeleteResponse(message=f"Removed run {run_id}")
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to delete self-learning run %s", run_id)
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR_DETAIL) from exc
