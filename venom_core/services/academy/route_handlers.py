"""Endpoint logic handlers extracted from academy routes module."""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, NoReturn, Optional, cast

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse

from venom_core.api.schemas.academy import (
    AcademyJobsListResponse,
    AdapterInfo,
    DatasetConversionFileInfo,
    DatasetConversionListResponse,
    DatasetConversionRequest,
    DatasetConversionResult,
    DatasetConversionTrainingSelectionRequest,
    DatasetFilePreviewResponse,
    DatasetPreviewResponse,
    DatasetResponse,
    DatasetScopeRequest,
    JobStatusResponse,
    TrainingRequest,
    TrainingResponse,
    UploadFileInfo,
)
from venom_core.services.academy.adapter_metadata_service import (
    ADAPTER_NOT_FOUND_DETAIL,
)
from venom_core.utils.llm_runtime import get_active_llm_runtime

_RUNTIME_UNAVAILABLE_REASON_CODES = {"ADAPTER_RUNTIME_SERVICE_UNAVAILABLE"}


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
    detail: dict[str, str] = {
        "error": normalized_reason,
        "message": normalized_message,
        "reason_code": normalized_reason,
    }
    for key, value in context.items():
        normalized_value = str(value or "").strip()
        if normalized_value:
            detail[key] = normalized_value
    return detail


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


def _runtime_error_detail_with_reason_code(
    exc: RuntimeError,
    **context: str | None,
) -> dict[str, str]:
    raw_detail = str(exc).strip()
    if ":" not in raw_detail:
        return _error_detail_with_reason_code(
            reason_code="ADAPTER_ACTIVATION_FAILED",
            message=raw_detail,
            **context,
        )
    reason_code, message = raw_detail.split(":", 1)
    normalized_reason = reason_code.strip()
    normalized_message = message.strip()
    if (
        not normalized_reason
        or not normalized_message
        or not normalized_reason.replace("_", "").isalnum()
    ):
        return _error_detail_with_reason_code(
            reason_code="ADAPTER_ACTIVATION_FAILED",
            message=raw_detail,
            **context,
        )
    return _error_detail_with_reason_code(
        reason_code=normalized_reason,
        message=normalized_message,
        **context,
    )


def _require_adapter_signing_manager(academy: Any) -> Any:
    manager = academy._get_model_manager()
    if manager:
        return manager
    raise academy.AcademyRouteError(
        status_code=503,
        detail="ModelManager not available for adapter signing",
    )


def _parse_adapter_signature_request(
    request: Any,
) -> tuple[str, str | None, str | None, str]:
    runtime_id = str(getattr(request, "runtime_id", "") or "").strip().lower()
    if not runtime_id:
        raise ValueError(
            "ADAPTER_SIGNATURE_RUNTIME_REQUIRED: Select target runtime for adapter signature."
        )
    model_id = str(getattr(request, "model_id", "") or "").strip() or None
    signer = str(getattr(request, "signer", "") or "").strip() or None
    conversion_mode = str(getattr(request, "conversion_mode", "none") or "none")
    return runtime_id, model_id, signer, conversion_mode.strip().lower()


def _map_adapter_signing_file_error(exc: FileNotFoundError) -> NoReturn:
    message = str(exc).strip() or ADAPTER_NOT_FOUND_DETAIL
    if message == ADAPTER_NOT_FOUND_DETAIL:
        raise HTTPException(status_code=404, detail=ADAPTER_NOT_FOUND_DETAIL) from None
    raise HTTPException(status_code=500, detail=message) from exc


def _collect_scope_counts(
    *,
    curator: Any,
    request: DatasetScopeRequest,
) -> Dict[str, int]:
    counts = {"lessons": 0, "git": 0, "task_history": 0}
    if request.include_lessons:
        counts["lessons"] = curator.collect_from_lessons(limit=request.lessons_limit)
    if request.include_git:
        counts["git"] = curator.collect_from_git_history(
            max_commits=request.git_commits_limit
        )
    if request.include_task_history:
        counts["task_history"] = curator.collect_from_task_history(max_tasks=100)
    return counts


async def _resolve_training_models_for_request(
    *,
    request: TrainingRequest,
    academy: Any,
) -> tuple[str, str]:
    base_model = academy.academy_training.ensure_trainable_base_model(
        request_base_model=request.base_model,
        is_model_trainable_fn=academy._is_model_trainable,
    )
    validate_runtime_pair = getattr(
        academy.academy_training,
        "validate_runtime_compatibility_for_base_model",
        None,
    )
    if callable(validate_runtime_pair):
        onnx_conversion_mode = (
            str(getattr(request, "onnx_conversion_mode", "none") or "none")
            .strip()
            .lower()
        )
        await validate_runtime_pair(
            base_model=base_model,
            runtime_id=request.runtime_id,
            allow_indirect_onnx_path=onnx_conversion_mode != "none",
            manager=academy._get_model_manager(),
        )
    resolve_training_base_model = getattr(
        academy.academy_training,
        "resolve_training_base_model",
        None,
    )
    training_base_model = base_model
    if callable(resolve_training_base_model):
        training_base_model = await resolve_training_base_model(
            base_model=base_model,
            manager=academy._get_model_manager(),
        )
    if not str(training_base_model or "").strip():
        raise ValueError(
            "MODEL_TRAINING_BASE_UNRESOLVED: Failed to resolve concrete training base model"
        )
    return base_model, str(training_base_model)


def _request_runtime_base_context(request: TrainingRequest) -> dict[str, str | None]:
    return {
        "requested_runtime_id": str(getattr(request, "runtime_id", "") or "").strip()
        or None,
        "requested_base_model": str(getattr(request, "base_model", "") or "").strip()
        or None,
    }


def _mark_training_start_failed(*, academy: Any, job_id: str, exc: Exception) -> None:
    academy._update_job_in_history(
        job_id,
        {
            "status": "failed",
            "finished_at": datetime.now().isoformat(),
            "error": str(exc),
            "error_code": "TRAINING_START_FAILED",
        },
    )


def curate_dataset_handler(
    *,
    request: DatasetScopeRequest,
    req: Request,
    academy: Any,
) -> DatasetResponse:
    try:
        academy._ensure_academy_enabled()
    except academy.AcademyRouteError as e:
        raise academy._to_http_exception(e) from e

    try:
        result = academy.academy_training.curate_dataset_scope(
            request=request,
            req=req,
            resolve_conversion_file_ids_for_dataset_fn=(
                academy._resolve_conversion_file_ids_for_dataset
            ),
            get_dataset_curator_fn=academy._get_dataset_curator,
            collect_scope_counts_fn=lambda curator, req_payload: _collect_scope_counts(
                curator=curator,
                request=req_payload,
            ),
            ingest_uploads_for_curate_fn=lambda curator,
            upload_ids: academy.academy_uploads.ingest_uploads_for_ids(
                curator=curator,
                upload_ids=upload_ids,
                uploads_dir=academy._get_uploads_dir(),
                check_path_traversal_fn=academy._check_path_traversal,
                ingest_upload_file_fn=academy._ingest_upload_file,
                logger=academy.logger,
            ),
            ingest_converted_files_for_curate_fn=lambda curator,
            req_obj,
            conversion_file_ids: academy.academy_uploads.ingest_converted_files_for_ids(
                curator=curator,
                conversion_file_ids=conversion_file_ids,
                check_path_traversal_fn=academy._check_path_traversal,
                resolve_existing_user_file_fn=(
                    lambda file_id: academy._resolve_existing_user_file(
                        req_obj,
                        file_id=file_id,
                    )
                ),
                ingest_upload_file_fn=academy._ingest_upload_file,
                logger=academy.logger,
            ),
            logger=academy.logger,
        )
        stats = result["stats"]
        scope_counts = result["scope_counts"]
        uploads_count = result["uploads_count"]
        converted_count = result["converted_count"]

        return DatasetResponse(
            success=True,
            dataset_path=str(result["dataset_path"]),
            statistics={
                **stats,
                "lessons_collected": scope_counts["lessons"],
                "git_commits_collected": scope_counts["git"],
                "task_history_collected": scope_counts["task_history"],
                "uploads_collected": uploads_count,
                "converted_collected": converted_count,
                "removed_low_quality": result["removed_low_quality"],
                "quality_profile": result["quality_profile"],
                "by_source": {
                    "lessons": scope_counts["lessons"],
                    "git": scope_counts["git"],
                    "task_history": scope_counts["task_history"],
                    "uploads": uploads_count,
                    "converted": converted_count,
                },
            },
            message=f"Dataset curated successfully: {stats['total_examples']} examples",
        )

    except Exception as e:
        academy.logger.error(f"Failed to curate dataset: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=_error_detail_with_reason_code(
                reason_code="DATASET_CURATE_FAILED",
                message=f"Failed to curate dataset: {str(e)}",
            ),
        ) from e


async def start_training_handler(
    *,
    request: TrainingRequest,
    req: Request,
    academy: Any,
) -> TrainingResponse:
    request_context = _request_runtime_base_context(request)
    try:
        academy._ensure_academy_enabled()
        academy.require_localhost_request(req)
        from venom_core.config import SETTINGS

        academy.logger.info(
            "Starting training: base_model_set=%s lora_rank=%s num_epochs=%s learning_rate=%s batch_size=%s",
            bool(request.base_model),
            request.lora_rank,
            request.num_epochs,
            request.learning_rate,
            request.batch_size,
        )
        habitat = academy._get_gpu_habitat()

        dataset_path = academy.academy_training.resolve_dataset_path(
            request.dataset_path,
            academy_training_dir=SETTINGS.ACADEMY_TRAINING_DIR,
            dataset_required_detail=academy.DATASET_REQUIRED_DETAIL,
        )
        base_model, training_base_model = await _resolve_training_models_for_request(
            request=request,
            academy=academy,
        )

        job_id = f"training_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        output_dir = Path(SETTINGS.ACADEMY_MODELS_DIR) / job_id
        output_dir.mkdir(parents=True, exist_ok=True)

        job_record = academy.academy_training.build_job_record(
            dataset_path=dataset_path,
            base_model=base_model,
            output_dir=output_dir,
            request=request,
            training_base_model=training_base_model,
        )
        job_id = str(job_record["job_id"])
        academy._save_job_to_history(job_record)
        academy._update_job_in_history(job_id, {"status": "preparing"})

        try:
            job_info = habitat.run_training_job(
                dataset_path=dataset_path,
                base_model=training_base_model,
                output_dir=str(output_dir),
                lora_rank=request.lora_rank,
                learning_rate=request.learning_rate,
                num_epochs=request.num_epochs,
                max_seq_length=request.max_seq_length,
                batch_size=request.batch_size,
                job_name=job_id,
            )
        except Exception as e:
            _mark_training_start_failed(academy=academy, job_id=job_id, exc=e)
            raise

        academy._update_job_in_history(
            job_id,
            {
                "status": "running",
                "container_id": job_info.get("container_id"),
                "job_name": job_info.get("job_name", job_id),
            },
        )

        return TrainingResponse(
            success=True,
            job_id=job_id,
            message=f"Training started successfully: {job_id}",
            parameters=cast(Dict[str, Any], job_record["parameters"]),
        )

    except academy.AcademyRouteError as e:
        raise academy._to_http_exception(e) from e
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=_value_error_detail_with_reason_code(
                e,
                **request_context,
            ),
        ) from e
    except HTTPException:
        raise
    except Exception as e:
        academy.logger.error(f"Failed to start training: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=_error_detail_with_reason_code(
                reason_code="TRAINING_START_FAILED",
                message=f"Failed to start training: {str(e)}",
                **request_context,
            ),
        ) from e


def get_training_status_handler(
    *,
    job_id: str,
    academy: Any,
) -> JobStatusResponse:
    try:
        academy._ensure_academy_enabled()
        habitat = academy._get_gpu_habitat()
        try:
            job = academy.academy_training.find_job_or_404(
                job_id,
                jobs=academy._load_jobs_history(),
            )
        except HTTPException as exc:
            raise academy.AcademyRouteError(
                status_code=exc.status_code,
                detail=str(exc.detail),
            ) from exc
        job_name = job.get("job_name", job_id)
        status_info, current_status = (
            academy.academy_training.sync_job_status_with_habitat(
                habitat=habitat,
                job_id=job_id,
                job=job,
                job_name=job_name,
                normalize_status_fn=academy._normalize_job_status,
                terminal_statuses=academy.TERMINAL_JOB_STATUSES,
                update_job_fn=academy._update_job_in_history,
            )
        )
        academy._save_finished_job_metadata(job, current_status)
        academy._cleanup_terminal_job_container(
            habitat,
            job_id,
            job,
            job_name,
            current_status,
        )

        return JobStatusResponse(
            job_id=job_id,
            status=current_status,
            logs=status_info.get("logs", "")[-5000:],
            started_at=job.get("started_at"),
            finished_at=job.get("finished_at"),
            adapter_path=job.get("adapter_path"),
            error=status_info.get("error"),
        )

    except academy.AcademyRouteError as e:
        raise academy._to_http_exception(e) from e
    except HTTPException:
        raise
    except Exception as e:
        academy.logger.error(f"Failed to get training status: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=_error_detail_with_reason_code(
                reason_code="TRAINING_STATUS_FAILED",
                message=f"Failed to get status: {str(e)}",
                job_id=job_id,
            ),
        )


def stream_training_logs_handler(*, job_id: str, academy: Any) -> StreamingResponse:
    try:
        academy._ensure_academy_enabled()
        try:
            job = academy.academy_training.find_job_or_404(
                job_id,
                jobs=academy._load_jobs_history(),
            )
        except HTTPException as exc:
            raise academy.AcademyRouteError(
                status_code=exc.status_code,
                detail=str(exc.detail),
            ) from exc
    except academy.AcademyRouteError as e:
        raise academy._to_http_exception(e) from e

    job_name = job.get("job_name", job_id)
    return StreamingResponse(
        academy._stream_training_logs_events(job_id=job_id, job_name=job_name),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def stream_training_logs_events_handler(
    *, job_id: str, job_name: str, academy: Any
):
    from venom_core.learning.training_metrics_parser import TrainingMetricsParser

    async for event in academy.academy_training.stream_training_logs_events(
        job_id=job_id,
        job_name=job_name,
        habitat=academy._get_gpu_habitat(),
        parser_factory=TrainingMetricsParser,
        normalize_status_fn=academy._normalize_job_status,
        terminal_statuses=academy.TERMINAL_JOB_STATUSES,
        logger=academy.logger,
    ):
        yield event


def list_jobs_handler(
    *,
    limit: int,
    status: Optional[str],
    academy: Any,
) -> AcademyJobsListResponse:
    try:
        academy._ensure_academy_enabled()
        jobs = academy.academy_training.list_jobs_response(
            jobs=academy._load_jobs_history(),
            to_job_summary_fn=academy._to_job_summary,
            limit=limit,
            status=status,
        )
        return AcademyJobsListResponse(count=len(jobs), jobs=jobs)

    except academy.AcademyRouteError as e:
        raise academy._to_http_exception(e) from e
    except Exception as e:
        academy.logger.error(f"Failed to list jobs: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=_error_detail_with_reason_code(
                reason_code="TRAINING_JOBS_LIST_FAILED",
                message=f"Failed to list jobs: {str(e)}",
                requested_status=status,
            ),
        )


def list_adapters_handler(*, academy: Any) -> List[AdapterInfo]:
    try:
        academy._ensure_academy_enabled()
        return academy.academy_models.list_adapters(mgr=academy._get_model_manager())

    except academy.AcademyRouteError as e:
        raise academy._to_http_exception(e) from e
    except Exception as e:
        academy.logger.error(f"Failed to list adapters: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=_error_detail_with_reason_code(
                reason_code="ADAPTERS_LIST_FAILED",
                message=f"Failed to list adapters: {str(e)}",
            ),
        )


def audit_adapters_handler(
    *,
    academy: Any,
    runtime_id: str | None,
    model_id: str | None,
) -> Dict[str, Any]:
    try:
        academy._ensure_academy_enabled()
        return academy.academy_models.audit_adapters(
            mgr=academy._get_model_manager(),
            runtime_id=runtime_id,
            model_id=model_id,
        )

    except academy.AcademyRouteError as e:
        raise academy._to_http_exception(e) from e
    except Exception as e:
        academy.logger.error(f"Failed to audit adapters: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=_error_detail_with_reason_code(
                reason_code="ADAPTERS_AUDIT_FAILED",
                message=f"Failed to audit adapters: {str(e)}",
                requested_runtime_id=runtime_id,
                requested_model_id=model_id,
            ),
        )


def _resolve_activation_runtime_id(*, request: Any) -> str:
    runtime_id = str(getattr(request, "runtime_id", "") or "").strip()
    if runtime_id:
        return runtime_id
    if bool(getattr(request, "deploy_to_chat_runtime", False)):
        return ""
    active_runtime = get_active_llm_runtime()
    return str(getattr(active_runtime, "provider", "") or "").strip()


def _validate_activation_request_contract(*, request: Any, runtime_id: str) -> None:
    if not bool(getattr(request, "deploy_to_chat_runtime", False)):
        return
    if not runtime_id:
        raise ValueError(
            "ADAPTER_RUNTIME_REQUIRED: Select target runtime before adapter activation."
        )
    model_id = str(getattr(request, "model_id", "") or "").strip()
    if not model_id:
        raise ValueError(
            "ADAPTER_RUNTIME_MODEL_REQUIRED: Select runtime model before adapter activation."
        )


async def _validate_adapter_compatibility_if_runtime_selected(
    *,
    academy: Any,
    manager: Any,
    request: Any,
    runtime_id: str,
) -> None:
    if not runtime_id:
        return
    await academy.academy_models.validate_adapter_runtime_compatibility(
        mgr=manager,
        adapter_id=request.adapter_id,
        runtime_id=runtime_id,
        model_id=str(getattr(request, "model_id", "") or "").strip() or None,
    )


async def activate_adapter_handler(
    *,
    request: Any,
    req: Request,
    academy: Any,
) -> Dict[str, Any]:
    requested_adapter_id = str(getattr(request, "adapter_id", "") or "").strip()
    requested_runtime_id = _resolve_activation_runtime_id(request=request)
    requested_model_id = str(getattr(request, "model_id", "") or "").strip()
    try:
        academy._ensure_academy_enabled()
        academy.require_localhost_request(req)
        manager = _require_adapter_activation_manager(academy)
        await _prepare_adapter_activation(
            academy=academy,
            manager=manager,
            request=request,
            requested_runtime_id=requested_runtime_id,
        )
        return await _activate_adapter(
            academy=academy,
            manager=manager,
            request=request,
            adapter_id=requested_adapter_id,
            runtime_id=requested_runtime_id,
            model_id=requested_model_id,
        )
    except Exception as exc:
        _raise_adapter_activation_http_exception(
            academy=academy,
            exc=exc,
            adapter_id=requested_adapter_id,
            requested_runtime_id=requested_runtime_id,
            requested_model_id=requested_model_id,
        )


def _require_adapter_activation_manager(academy: Any) -> Any:
    manager = academy._get_model_manager()
    if manager:
        return manager
    raise academy.AcademyRouteError(
        status_code=503,
        detail="ModelManager not available for adapter activation",
    )


async def _prepare_adapter_activation(
    *,
    academy: Any,
    manager: Any,
    request: Any,
    requested_runtime_id: str,
) -> None:
    _validate_activation_request_contract(
        request=request,
        runtime_id=requested_runtime_id,
    )
    await _validate_adapter_compatibility_if_runtime_selected(
        academy=academy,
        manager=manager,
        request=request,
        runtime_id=requested_runtime_id,
    )
    if bool(getattr(request, "deploy_to_chat_runtime", False)) and bool(
        getattr(request, "require_chat_signature", False)
    ):
        academy.academy_models.ensure_adapter_signed_for_chat(
            adapter_id=str(getattr(request, "adapter_id", "") or "").strip(),
            runtime_id=requested_runtime_id,
            model_id=str(getattr(request, "model_id", "") or "").strip() or None,
        )


async def _activate_adapter(
    *,
    academy: Any,
    manager: Any,
    request: Any,
    adapter_id: str,
    runtime_id: str,
    model_id: str,
) -> Dict[str, Any]:
    return await asyncio.to_thread(
        academy.academy_models.activate_adapter,
        mgr=manager,
        adapter_id=adapter_id,
        runtime_id=runtime_id or None,
        model_id=model_id or None,
        deploy_to_chat_runtime=bool(getattr(request, "deploy_to_chat_runtime", False)),
    )


def _raise_adapter_activation_http_exception(
    *,
    academy: Any,
    exc: Exception,
    adapter_id: str,
    requested_runtime_id: str,
    requested_model_id: str,
) -> NoReturn:
    context = {
        "adapter_id": adapter_id or None,
        "requested_runtime_id": requested_runtime_id or None,
        "requested_model_id": requested_model_id or None,
    }
    if isinstance(exc, academy.AcademyRouteError):
        raise academy._to_http_exception(exc) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(
            status_code=400,
            detail=_value_error_detail_with_reason_code(exc, **context),
        ) from exc
    if isinstance(exc, FileNotFoundError):
        message = str(exc).strip() or ADAPTER_NOT_FOUND_DETAIL
        if message == ADAPTER_NOT_FOUND_DETAIL:
            raise HTTPException(
                status_code=404, detail=ADAPTER_NOT_FOUND_DETAIL
            ) from None
        raise HTTPException(
            status_code=500,
            detail=_error_detail_with_reason_code(
                reason_code="ADAPTER_RUNTIME_DEPLOY_ARTIFACT_MISSING",
                message=message,
                **context,
            ),
        ) from exc
    if isinstance(exc, RuntimeError):
        runtime_detail = _runtime_error_detail_with_reason_code(exc, **context)
        reason_code = str(runtime_detail.get("reason_code") or "").strip()
        status_code = 503 if reason_code in _RUNTIME_UNAVAILABLE_REASON_CODES else 500
        raise HTTPException(
            status_code=status_code,
            detail=runtime_detail,
        ) from exc
    if isinstance(exc, HTTPException):
        raise exc
    academy.logger.error(f"Failed to activate adapter: {exc}", exc_info=True)
    raise HTTPException(
        status_code=500,
        detail=_error_detail_with_reason_code(
            reason_code="ADAPTER_ACTIVATION_FAILED",
            message=f"Failed to activate adapter: {str(exc)}",
            **context,
        ),
    ) from exc


def deactivate_adapter_handler(*, req: Request, academy: Any) -> Dict[str, Any]:
    try:
        academy._ensure_academy_enabled()
        academy.require_localhost_request(req)
        manager = academy._get_model_manager()
        if not manager:
            raise academy.AcademyRouteError(
                status_code=503,
                detail="ModelManager not available for adapter deactivation",
            )
        deploy_to_chat_runtime_raw = (
            str(req.query_params.get("deploy_to_chat_runtime", "true")).strip().lower()
        )
        deploy_to_chat_runtime = deploy_to_chat_runtime_raw not in {
            "0",
            "false",
            "no",
            "off",
        }
        return academy.academy_models.deactivate_adapter(
            mgr=manager,
            deploy_to_chat_runtime=deploy_to_chat_runtime,
        )

    except academy.AcademyRouteError as e:
        raise academy._to_http_exception(e) from e
    except HTTPException:
        raise
    except Exception as e:
        academy.logger.error(f"Failed to deactivate adapter: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=_error_detail_with_reason_code(
                reason_code="ADAPTER_DEACTIVATION_FAILED",
                message=f"Failed to deactivate adapter: {str(e)}",
            ),
        )


def sign_adapter_for_chat_handler(
    *,
    adapter_id: str,
    request: Any,
    req: Request,
    academy: Any,
) -> Dict[str, Any]:
    try:
        academy._ensure_academy_enabled()
        academy.require_localhost_request(req)
        manager = _require_adapter_signing_manager(academy)
        runtime_id, model_id, signer, conversion_mode = (
            _parse_adapter_signature_request(request)
        )
        return academy.academy_models.sign_adapter_for_chat(
            mgr=manager,
            adapter_id=adapter_id,
            runtime_id=runtime_id,
            model_id=model_id,
            signer=signer,
            conversion_mode=conversion_mode,
        )
    except academy.AcademyRouteError as e:
        raise academy._to_http_exception(e) from e
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=_value_error_detail_with_reason_code(
                e,
                adapter_id=adapter_id,
                requested_runtime_id=str(
                    getattr(request, "runtime_id", "") or ""
                ).strip()
                or None,
                requested_model_id=str(getattr(request, "model_id", "") or "").strip()
                or None,
            ),
        ) from e
    except FileNotFoundError as e:
        _map_adapter_signing_file_error(e)
    except Exception as e:
        academy.logger.error(f"Failed to sign adapter for chat: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=_error_detail_with_reason_code(
                reason_code="ADAPTER_SIGNATURE_FAILED",
                message=f"Failed to sign adapter for chat: {str(e)}",
                adapter_id=adapter_id,
            ),
        ) from e


def cancel_training_handler(
    *,
    job_id: str,
    req: Request,
    academy: Any,
) -> Dict[str, Any]:
    try:
        academy._ensure_academy_enabled()
        academy.require_localhost_request(req)
        return academy.academy_training.cancel_training_job(
            job_id=job_id,
            habitat=academy._get_gpu_habitat(),
            jobs=academy._load_jobs_history(),
            update_job_fn=academy._update_job_in_history,
            logger=academy.logger,
        )

    except academy.AcademyRouteError as e:
        raise academy._to_http_exception(e) from e
    except HTTPException:
        raise
    except Exception as e:
        academy.logger.error(f"Failed to cancel training: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=_error_detail_with_reason_code(
                reason_code="TRAINING_CANCEL_FAILED",
                message=f"Failed to cancel training: {str(e)}",
                job_id=job_id,
            ),
        )


def academy_status_handler(*, academy: Any) -> Dict[str, Any]:
    try:
        from venom_core.config import SETTINGS

        lessons_stats = {}
        lessons_store_dep = academy._get_lessons_store()
        if lessons_store_dep:
            lessons_stats = lessons_store_dep.get_statistics()

        gpu_available = False
        gpu_info: Dict[str, Any] = {}
        habitat = academy._get_gpu_habitat()
        if habitat:
            gpu_available = habitat.is_gpu_available()
            try:
                gpu_info = habitat.get_gpu_info()
            except Exception as e:
                academy.logger.warning(f"Failed to get GPU info: {e}")
                gpu_info = {"available": gpu_available}

        jobs = academy._load_jobs_history()
        jobs_stats = {
            "total": len(jobs),
            "running": len([j for j in jobs if j.get("status") == "running"]),
            "finished": len([j for j in jobs if j.get("status") == "finished"]),
            "failed": len([j for j in jobs if j.get("status") == "failed"]),
        }

        return {
            "enabled": SETTINGS.ENABLE_ACADEMY,
            "components": {
                "professor": academy._get_professor() is not None,
                "dataset_curator": academy._get_dataset_curator() is not None,
                "gpu_habitat": academy._get_gpu_habitat() is not None,
                "lessons_store": academy._get_lessons_store() is not None,
                "model_manager": academy._get_model_manager() is not None,
            },
            "gpu": {
                "available": gpu_available,
                "enabled": SETTINGS.ACADEMY_ENABLE_GPU,
                **gpu_info,
            },
            "lessons": lessons_stats,
            "jobs": jobs_stats,
            "config": {
                "min_lessons": SETTINGS.ACADEMY_MIN_LESSONS,
                "training_interval_hours": SETTINGS.ACADEMY_TRAINING_INTERVAL_HOURS,
            },
        }

    except Exception as e:
        academy.logger.error(f"Failed to get academy status: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=_error_detail_with_reason_code(
                reason_code="ACADEMY_STATUS_FAILED",
                message=f"Failed to get academy status: {str(e)}",
            ),
        )


async def upload_dataset_files_handler(*, req: Request, academy: Any) -> Dict[str, Any]:
    try:
        academy._ensure_academy_enabled()
        academy.require_localhost_request(req)
    except academy.AcademyRouteError as e:
        raise academy._to_http_exception(e) from e

    from venom_core.config import SETTINGS

    form = await req.form()
    files, tag, description = academy.academy_uploads.parse_upload_form(form)

    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    if len(files) > SETTINGS.ACADEMY_MAX_UPLOADS_PER_REQUEST:
        raise HTTPException(
            status_code=400,
            detail=f"Too many files (max {SETTINGS.ACADEMY_MAX_UPLOADS_PER_REQUEST})",
        )

    uploaded_files = []
    failed_files = []
    uploads_dir = academy._get_uploads_dir()

    for file in files:
        upload_info, error_info = await academy._process_uploaded_file(
            file=file,
            uploads_dir=uploads_dir,
            tag=tag,
            description=description,
        )
        if upload_info:
            uploaded_files.append(upload_info)
        if error_info:
            failed_files.append(error_info)

    academy.logger.info(
        f"Uploaded {len(uploaded_files)} files to Academy ({len(failed_files)} failed)"
    )

    return academy.academy_uploads.build_upload_response(uploaded_files, failed_files)


def list_dataset_uploads_handler(*, academy: Any) -> List[UploadFileInfo]:
    try:
        academy._ensure_academy_enabled()
    except academy.AcademyRouteError as e:
        raise academy._to_http_exception(e) from e
    try:
        uploads = academy._load_uploads_metadata()
        return [UploadFileInfo(**u) for u in uploads]
    except Exception as exc:
        academy.logger.error("Failed to list dataset uploads: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=_error_detail_with_reason_code(
                reason_code="DATASET_UPLOADS_LIST_FAILED",
                message=f"Failed to list dataset uploads: {str(exc)}",
            ),
        ) from exc


def delete_dataset_upload_handler(
    *,
    file_id: str,
    req: Request,
    academy: Any,
) -> Dict[str, Any]:
    try:
        academy._ensure_academy_enabled()
        academy.require_localhost_request(req)
    except academy.AcademyRouteError as e:
        raise academy._to_http_exception(e) from e

    try:
        return academy.academy_uploads.delete_upload_file(
            file_id=file_id,
            uploads_dir=academy._get_uploads_dir(),
            check_path_traversal_fn=academy._check_path_traversal,
            delete_upload_metadata_fn=academy._delete_upload_metadata,
            logger=academy.logger,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except FileNotFoundError:
        raise HTTPException(
            status_code=404, detail=f"Upload not found: {file_id}"
        ) from None
    except Exception as e:
        academy.logger.error(f"Failed to delete upload {file_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=_error_detail_with_reason_code(
                reason_code="DATASET_UPLOAD_DELETE_FAILED",
                message=f"Failed to delete upload: {str(e)}",
                file_id=file_id,
            ),
        )


def list_dataset_conversion_files_handler(
    *,
    req: Request,
    academy: Any,
) -> DatasetConversionListResponse:
    try:
        academy._ensure_academy_enabled()
    except academy.AcademyRouteError as e:
        raise academy._to_http_exception(e) from e

    try:
        user_id = academy._resolve_user_id(req)
        workspace = academy._get_user_conversion_workspace(user_id)
        payload = academy.academy_conversion.list_conversion_files_for_user(
            user_id=user_id,
            workspace=workspace,
            user_conversion_metadata_lock_fn=academy._user_conversion_metadata_lock,
            load_user_conversion_metadata_fn=academy._load_user_conversion_metadata,
            normalize_conversion_item_fn=academy._normalize_conversion_item,
        )
        return DatasetConversionListResponse(
            user_id=payload["user_id"],
            workspace_dir=payload["workspace_dir"],
            source_files=payload["source_files"],
            converted_files=payload["converted_files"],
        )
    except Exception as exc:
        academy.logger.error(
            "Failed to list conversion files: %s",
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=_error_detail_with_reason_code(
                reason_code="DATASET_CONVERSION_LIST_FAILED",
                message=f"Failed to list conversion files: {str(exc)}",
            ),
        ) from exc


async def upload_dataset_conversion_files_handler(
    *,
    req: Request,
    academy: Any,
) -> Dict[str, Any]:
    try:
        academy._ensure_academy_enabled()
        academy.require_localhost_request(req)
    except academy.AcademyRouteError as e:
        raise academy._to_http_exception(e) from e

    from venom_core.config import SETTINGS

    try:
        user_id = academy._resolve_user_id(req)
        workspace = academy._get_user_conversion_workspace(user_id)

        form = await req.form()
        files = form.getlist("files")
        if not files:
            raise HTTPException(status_code=400, detail="No files provided")
        if len(files) > SETTINGS.ACADEMY_MAX_UPLOADS_PER_REQUEST:
            raise HTTPException(
                status_code=400,
                detail=f"Too many files (max {SETTINGS.ACADEMY_MAX_UPLOADS_PER_REQUEST})",
            )
        return await academy.academy_conversion.upload_conversion_files_for_user(
            files=files,
            workspace=workspace,
            settings=SETTINGS,
            user_conversion_metadata_lock_fn=academy._user_conversion_metadata_lock,
            load_user_conversion_metadata_fn=academy._load_user_conversion_metadata,
            save_user_conversion_metadata_fn=academy._save_user_conversion_metadata,
            validate_upload_filename_fn=lambda file,
            settings,
            *,
            allowed_extensions=None: academy.academy_uploads.validate_upload_filename(
                file=file,
                settings=settings,
                check_path_traversal_fn=academy._check_path_traversal,
                validate_file_extension_fn=academy._validate_file_extension,
                allowed_extensions=allowed_extensions,
            ),
            persist_with_limits_fn=lambda **kwargs: academy.academy_uploads.persist_with_limits(
                **kwargs,
                logger=academy.logger,
                cleanup_uploaded_file_fn=lambda path: academy.academy_uploads.cleanup_uploaded_file(
                    path,
                    logger=academy.logger,
                ),
            ),
            build_conversion_file_id_fn=academy._build_conversion_file_id,
            build_conversion_item_fn=academy._build_conversion_item,
            normalize_conversion_item_fn=academy._normalize_conversion_item,
        )
    except HTTPException:
        raise
    except Exception as exc:
        academy.logger.error(
            "Failed to upload conversion files: %s",
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=_error_detail_with_reason_code(
                reason_code="DATASET_CONVERSION_UPLOAD_FAILED",
                message=f"Failed to upload conversion files: {str(exc)}",
            ),
        ) from exc


def convert_dataset_file_handler(
    *,
    file_id: str,
    payload: DatasetConversionRequest,
    req: Request,
    academy: Any,
) -> DatasetConversionResult:
    try:
        academy._ensure_academy_enabled()
        academy.require_localhost_request(req)
    except academy.AcademyRouteError as e:
        raise academy._to_http_exception(e) from e

    user_id = academy._resolve_user_id(req)
    workspace = academy._get_user_conversion_workspace(user_id)
    target_format = payload.target_format.lower()
    try:
        source_item, converted_item = (
            academy.academy_conversion.convert_dataset_source_file(
                file_id=file_id,
                workspace=workspace,
                target_format=target_format,
                check_path_traversal_fn=academy._check_path_traversal,
                user_conversion_metadata_lock_fn=academy._user_conversion_metadata_lock,
                load_user_conversion_metadata_fn=academy._load_user_conversion_metadata,
                save_user_conversion_metadata_fn=academy._save_user_conversion_metadata,
                find_conversion_item_fn=academy._find_conversion_item,
                resolve_workspace_file_path_fn=academy._resolve_workspace_file_path,
                source_to_records_fn=academy._source_to_records,
                write_records_as_target_fn=academy._write_records_as_target,
                build_conversion_item_fn=academy._build_conversion_item,
            )
        )
    except academy.AcademyRouteError as e:
        raise academy._to_http_exception(e) from e
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, OSError) as exc:
        detail = str(exc)
        if (
            detail.startswith("Invalid file_id:")
            or detail == "Conversion requires source file"
        ):
            raise HTTPException(status_code=400, detail=detail) from exc
        raise HTTPException(
            status_code=400, detail=f"Conversion failed: {detail}"
        ) from exc
    except Exception as exc:
        academy.logger.exception(
            "Unexpected conversion error for user=%s file_id=%s target=%s",
            user_id,
            file_id,
            target_format,
        )
        raise HTTPException(
            status_code=500,
            detail=_error_detail_with_reason_code(
                reason_code="DATASET_CONVERSION_INTERNAL_FAILED",
                message="Conversion failed due to internal error",
                file_id=file_id,
                target_format=target_format,
            ),
        ) from exc

    return DatasetConversionResult(
        success=True,
        message=f"Converted to {target_format}",
        source_file=academy._normalize_conversion_item(source_item),
        converted_file=academy._normalize_conversion_item(converted_item),
    )


def set_dataset_conversion_training_selection_handler(
    *,
    file_id: str,
    payload: DatasetConversionTrainingSelectionRequest,
    req: Request,
    academy: Any,
) -> DatasetConversionFileInfo:
    try:
        academy._ensure_academy_enabled()
        academy.require_localhost_request(req)
    except academy.AcademyRouteError as e:
        raise academy._to_http_exception(e) from e

    user_id = academy._resolve_user_id(req)
    workspace = academy._get_user_conversion_workspace(user_id)
    try:
        item = academy.academy_conversion.set_conversion_training_selection(
            file_id=file_id,
            selected_for_training=bool(payload.selected_for_training),
            workspace=workspace,
            check_path_traversal_fn=academy._check_path_traversal,
            user_conversion_metadata_lock_fn=academy._user_conversion_metadata_lock,
            load_user_conversion_metadata_fn=academy._load_user_conversion_metadata,
            save_user_conversion_metadata_fn=academy._save_user_conversion_metadata,
            find_conversion_item_fn=academy._find_conversion_item,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        academy.logger.error(
            "Failed to update conversion training selection for %s: %s",
            file_id,
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=_error_detail_with_reason_code(
                reason_code="DATASET_CONVERSION_SELECTION_FAILED",
                message=f"Failed to update conversion training selection: {str(exc)}",
                file_id=file_id,
            ),
        ) from exc
    return academy._normalize_conversion_item(item)


async def preview_dataset_conversion_file_handler(
    *,
    file_id: str,
    req: Request,
    academy: Any,
) -> DatasetFilePreviewResponse:
    try:
        academy._ensure_academy_enabled()
        academy.require_localhost_request(req)
    except academy.AcademyRouteError as e:
        raise academy._to_http_exception(e) from e

    if not academy._check_path_traversal(file_id):
        raise HTTPException(status_code=400, detail=f"Invalid file_id: {file_id}")

    try:
        item, file_path = academy._resolve_existing_user_file(req, file_id=file_id)
    except academy.AcademyRouteError as e:
        raise academy._to_http_exception(e) from e

    ext = file_path.suffix.lower()
    if ext not in {".txt", ".md"}:
        raise HTTPException(
            status_code=400,
            detail="Preview supported only for .txt and .md files",
        )

    try:
        preview_text, truncated = await academy.academy_conversion.read_text_preview(
            file_path=file_path
        )
    except Exception as exc:
        academy.logger.error(
            "Failed to preview conversion file %s: %s",
            file_id,
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=_error_detail_with_reason_code(
                reason_code="DATASET_FILE_PREVIEW_FAILED",
                message=f"Failed to preview conversion file: {str(exc)}",
                file_id=file_id,
            ),
        ) from exc

    return DatasetFilePreviewResponse(
        file_id=file_id,
        name=str(item.get("name") or file_id),
        extension=ext,
        preview=preview_text,
        truncated=truncated,
    )


def download_dataset_conversion_file_handler(
    *,
    file_id: str,
    req: Request,
    academy: Any,
) -> FileResponse:
    try:
        academy._ensure_academy_enabled()
        academy.require_localhost_request(req)
    except academy.AcademyRouteError as e:
        raise academy._to_http_exception(e) from e

    if not academy._check_path_traversal(file_id):
        raise HTTPException(status_code=400, detail=f"Invalid file_id: {file_id}")

    try:
        item, file_path = academy._resolve_existing_user_file(req, file_id=file_id)
    except academy.AcademyRouteError as e:
        raise academy._to_http_exception(e) from e

    try:
        media_type = academy.academy_conversion.guess_media_type(file_path)
        return FileResponse(
            path=str(file_path),
            filename=str(item.get("name") or file_path.name),
            media_type=media_type,
        )
    except Exception as exc:
        academy.logger.error(
            "Failed to download conversion file %s: %s",
            file_id,
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=_error_detail_with_reason_code(
                reason_code="DATASET_FILE_DOWNLOAD_FAILED",
                message=f"Failed to download conversion file: {str(exc)}",
                file_id=file_id,
            ),
        ) from exc


def preview_dataset_handler(
    *,
    request: DatasetScopeRequest,
    req: Request,
    academy: Any,
) -> DatasetPreviewResponse:
    try:
        academy._ensure_academy_enabled()
    except academy.AcademyRouteError as e:
        raise academy._to_http_exception(e) from e

    try:
        result = academy.academy_training.preview_dataset_scope(
            request=request,
            req=req,
            resolve_conversion_file_ids_for_dataset_fn=(
                academy._resolve_conversion_file_ids_for_dataset
            ),
            get_dataset_curator_fn=academy._get_dataset_curator,
            collect_scope_counts_fn=lambda curator, req_payload: _collect_scope_counts(
                curator=curator,
                request=req_payload,
            ),
            ingest_uploads_for_preview_fn=lambda curator,
            upload_ids,
            warnings: academy.academy_uploads.ingest_uploads_for_preview(
                curator=curator,
                upload_ids=upload_ids,
                warnings=warnings,
                uploads_dir=academy._get_uploads_dir(),
                check_path_traversal_fn=academy._check_path_traversal,
                ingest_upload_file_fn=academy._ingest_upload_file,
            ),
            ingest_converted_files_for_preview_fn=lambda curator,
            req_obj,
            conversion_file_ids,
            warnings: academy.academy_uploads.ingest_converted_files_for_preview(
                curator=curator,
                conversion_file_ids=conversion_file_ids,
                warnings=warnings,
                check_path_traversal_fn=academy._check_path_traversal,
                resolve_existing_user_file_fn=lambda *,
                file_id: academy._resolve_existing_user_file(req_obj, file_id=file_id),
                ingest_upload_file_fn=academy._ingest_upload_file,
            ),
            add_low_examples_warning_fn=lambda warnings,
            total_examples,
            quality_profile: academy.academy_uploads.add_low_examples_warning(
                warnings=warnings,
                total_examples=total_examples,
                quality_profile=quality_profile,
            ),
            build_preview_samples_fn=academy.academy_uploads.build_preview_samples,
            logger=academy.logger,
        )
        return DatasetPreviewResponse(
            total_examples=result["total_examples"],
            by_source=result["by_source"],
            removed_low_quality=result["removed_low_quality"],
            warnings=result["warnings"],
            samples=result["samples"],
        )

    except Exception as e:
        academy.logger.error(f"Failed to preview dataset: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=_error_detail_with_reason_code(
                reason_code="DATASET_PREVIEW_FAILED",
                message=f"Failed to preview dataset: {str(e)}",
            ),
        )
