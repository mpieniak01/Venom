"""Routes for Academy self-learning orchestration."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query

from venom_core.api.schemas.academy_self_learning import (
    SelfLearningCapabilitiesResponse,
    SelfLearningDeleteResponse,
    SelfLearningEvaluationBaselineResponse,
    SelfLearningEvaluationBaselineUpdateRequest,
    SelfLearningListResponse,
    SelfLearningRunStatusResponse,
    SelfLearningStartRequest,
    SelfLearningStartResponse,
)
from venom_core.services.academy.self_learning_service import (
    SelfLearningValidationError,
)
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/academy/self-learning", tags=["academy"])

_self_learning_service: Any | None = None

SERVICE_UNAVAILABLE_DETAIL = "SelfLearningService is unavailable"
INTERNAL_ERROR_DETAIL = "Failed to process self-learning request"


def _error_detail_with_reason_code(
    *,
    reason_code: str,
    message: str,
    **context: str | None,
) -> dict[str, str]:
    detail: dict[str, str] = {
        "error": reason_code,
        "message": message,
        "reason_code": reason_code,
    }
    for key, value in context.items():
        normalized_value = str(value or "").strip()
        if normalized_value:
            detail[key] = normalized_value
    return detail


def _value_error_detail_with_reason_code(
    exc: ValueError,
    **context: str | None,
) -> str | dict[str, str]:
    raw_detail = str(exc).strip()
    if ":" not in raw_detail:
        return raw_detail
    reason_code, message = raw_detail.split(":", 1)
    normalized_reason = reason_code.strip()
    normalized_message = message.strip()
    if not normalized_reason or not normalized_message:
        return raw_detail
    if not normalized_reason.replace("_", "").isalnum():
        return raw_detail
    return _error_detail_with_reason_code(
        reason_code=normalized_reason,
        message=normalized_message,
        **context,
    )


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
    requested_runtime_id = (
        str(getattr(request.llm_config, "runtime_id", "") or "").strip()
        if request.llm_config
        else ""
    )
    requested_base_model = (
        str(getattr(request.llm_config, "base_model", "") or "").strip()
        if request.llm_config
        else ""
    )
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
    except SelfLearningValidationError as exc:
        raise HTTPException(status_code=400, detail=exc.detail) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=_value_error_detail_with_reason_code(
                exc,
                requested_runtime_id=requested_runtime_id or None,
                requested_base_model=requested_base_model or None,
            ),
        ) from exc
    except Exception as exc:
        logger.exception("Failed to start self-learning run")
        raise HTTPException(
            status_code=500,
            detail=_error_detail_with_reason_code(
                reason_code="SELF_LEARNING_START_FAILED",
                message=f"Failed to process self-learning request: {str(exc)}",
                requested_runtime_id=requested_runtime_id or None,
                requested_base_model=requested_base_model or None,
            ),
        ) from exc


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
        raise HTTPException(
            status_code=500,
            detail=_error_detail_with_reason_code(
                reason_code="SELF_LEARNING_CAPABILITIES_FAILED",
                message=f"Failed to load self-learning capabilities: {str(exc)}",
            ),
        ) from exc


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
        raise HTTPException(
            status_code=500,
            detail=_error_detail_with_reason_code(
                reason_code="SELF_LEARNING_STATUS_FAILED",
                message=f"Failed to get self-learning status: {str(exc)}",
                run_id=run_id,
            ),
        ) from exc


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
        raise HTTPException(
            status_code=500,
            detail=_error_detail_with_reason_code(
                reason_code="SELF_LEARNING_LIST_FAILED",
                message=f"Failed to list self-learning runs: {str(exc)}",
            ),
        ) from exc


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
        raise HTTPException(
            status_code=500,
            detail=_error_detail_with_reason_code(
                reason_code="SELF_LEARNING_CLEAR_FAILED",
                message=f"Failed to clear self-learning runs: {str(exc)}",
            ),
        ) from exc


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
        raise HTTPException(
            status_code=500,
            detail=_error_detail_with_reason_code(
                reason_code="SELF_LEARNING_DELETE_FAILED",
                message=f"Failed to delete self-learning run: {str(exc)}",
                run_id=run_id,
            ),
        ) from exc


@router.get(
    "/evaluation/baseline",
    responses={
        500: {"description": INTERNAL_ERROR_DETAIL},
        503: {"description": SERVICE_UNAVAILABLE_DETAIL},
    },
)
def get_self_learning_evaluation_baseline() -> SelfLearningEvaluationBaselineResponse:
    if _self_learning_service is None:
        raise HTTPException(status_code=503, detail=SERVICE_UNAVAILABLE_DETAIL)
    try:
        payload = _self_learning_service.get_evaluation_baselines()
        return SelfLearningEvaluationBaselineResponse(**payload)
    except Exception as exc:
        logger.exception("Failed to get self-learning evaluation baseline")
        raise HTTPException(
            status_code=500,
            detail=_error_detail_with_reason_code(
                reason_code="SELF_LEARNING_EVAL_BASELINE_GET_FAILED",
                message=f"Failed to get self-learning evaluation baseline: {str(exc)}",
            ),
        ) from exc


@router.put(
    "/evaluation/baseline",
    responses={
        400: {"description": "Invalid request payload."},
        500: {"description": INTERNAL_ERROR_DETAIL},
        503: {"description": SERVICE_UNAVAILABLE_DETAIL},
    },
)
def update_self_learning_evaluation_baseline(
    request: SelfLearningEvaluationBaselineUpdateRequest,
) -> SelfLearningEvaluationBaselineResponse:
    if _self_learning_service is None:
        raise HTTPException(status_code=503, detail=SERVICE_UNAVAILABLE_DETAIL)
    try:
        payload = _self_learning_service.update_evaluation_baselines(
            request.model_dump()
        )
        return SelfLearningEvaluationBaselineResponse(**payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=_value_error_detail_with_reason_code(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Failed to update self-learning evaluation baseline")
        raise HTTPException(
            status_code=500,
            detail=_error_detail_with_reason_code(
                reason_code="SELF_LEARNING_EVAL_BASELINE_UPDATE_FAILED",
                message=(
                    f"Failed to update self-learning evaluation baseline: {str(exc)}"
                ),
            ),
        ) from exc
