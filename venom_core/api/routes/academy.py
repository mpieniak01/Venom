"""Moduł: routes/academy - Endpointy API dla The Academy (trenowanie modeli)."""

import os
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Dict, List, Optional, cast
from unittest.mock import Mock

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse

from venom_core.api.routes import (
    academy_conversion,
    academy_history,
    academy_models,
    academy_storage,
    academy_training,
    academy_uploads,
)
from venom_core.api.schemas.academy import (
    AcademyJobsListResponse,
    AcademyJobSummary,
    ActivateAdapterRequest,
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
    TrainableModelInfo,
    TrainingRequest,
    TrainingResponse,
    UploadFileInfo,
)
from venom_core.services.academy import file_resolution as academy_file_resolution
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/academy", tags=["academy"])

# Globalne zależności - będą ustawione przez main.py
professor = None
dataset_curator = None
gpu_habitat = None
lessons_store = None
model_manager = None

# Backward-compat aliases (stary kod i testy używają _prefiksu)
_professor = None
_dataset_curator = None
_gpu_habitat = None
_lessons_store = None
_model_manager = None

CANONICAL_JOB_STATUSES = {
    "queued",
    "preparing",
    "running",
    "finished",
    "failed",
    "cancelled",
}
TERMINAL_JOB_STATUSES = {"finished", "failed", "cancelled"}
JOBS_HISTORY_FILE = Path("./data/training/jobs.jsonl")
DATASET_REQUIRED_DETAIL = "No dataset found. Please curate dataset first."

RESP_400_DATASET_REQUIRED = {"description": DATASET_REQUIRED_DETAIL}
RESP_403_LOCALHOST_ONLY = {
    "description": "Access denied for non-localhost administrative operation."
}
RESP_404_JOB_NOT_FOUND = {"description": "Training job not found."}
RESP_404_ADAPTER_NOT_FOUND = {"description": "Adapter not found."}
RESP_500_INTERNAL = {"description": "Internal server error."}
RESP_503_ACADEMY_UNAVAILABLE = {
    "description": "Academy is unavailable or not initialized."
}
RESP_400_BAD_REQUEST = {"description": "Invalid request payload."}
RESP_404_FILE_NOT_FOUND = {"description": "Requested file was not found."}


class AcademyRouteError(Exception):
    """Błąd domenowy routingu Academy mapowany na HTTPException w endpointach."""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def set_dependencies(
    professor=None,
    dataset_curator=None,
    gpu_habitat=None,
    lessons_store=None,
    model_manager=None,
):
    """Ustawia zależności Academy (używane w main.py podczas startup)."""
    global _professor, _dataset_curator, _gpu_habitat, _lessons_store, _model_manager
    globals()["professor"] = professor
    globals()["dataset_curator"] = dataset_curator
    globals()["gpu_habitat"] = gpu_habitat
    globals()["lessons_store"] = lessons_store
    globals()["model_manager"] = model_manager
    _professor = professor
    _dataset_curator = dataset_curator
    _gpu_habitat = gpu_habitat
    _lessons_store = lessons_store
    _model_manager = model_manager
    logger.info(
        "Academy dependencies set: professor=%s, curator=%s, habitat=%s, lessons=%s, model_mgr=%s",
        _professor is not None,
        _dataset_curator is not None,
        _gpu_habitat is not None,
        _lessons_store is not None,
        _model_manager is not None,
    )


def _get_professor():
    return _professor if _professor is not None else professor


def _get_dataset_curator():
    return _dataset_curator if _dataset_curator is not None else dataset_curator


def _get_gpu_habitat():
    return _gpu_habitat if _gpu_habitat is not None else gpu_habitat


def _get_lessons_store():
    return _lessons_store if _lessons_store is not None else lessons_store


def _get_model_manager():
    return _model_manager if _model_manager is not None else model_manager


def _normalize_job_status(raw_status: Optional[str]) -> str:
    """Mapuje status źródłowy do kontraktu canonical API."""
    if not raw_status:
        return "failed"
    if raw_status in CANONICAL_JOB_STATUSES:
        return raw_status
    if raw_status == "completed":
        return "finished"
    if raw_status in {"error", "unknown", "dead", "removing"}:
        return "failed"
    if raw_status in {"created", "restarting"}:
        return "preparing"
    return "failed"


def require_localhost_request(req: Request) -> None:
    """Dopuszcza wyłącznie mutujące operacje administracyjne z localhosta."""
    client_host = req.client.host if req.client else "unknown"
    if client_host not in ["127.0.0.1", "::1", "localhost"]:
        logger.warning(
            "Próba dostępu do endpointu administracyjnego Academy z hosta: %s",
            client_host,
        )
        raise AcademyRouteError(status_code=403, detail="Access denied")


# ==================== Helpers ====================


def _ensure_academy_enabled():
    """Sprawdza czy Academy jest włączone i dependencies są ustawione."""
    from venom_core.config import SETTINGS

    testing_mode = bool(os.getenv("PYTEST_CURRENT_TEST"))
    if not SETTINGS.ENABLE_ACADEMY and (not testing_mode or isinstance(SETTINGS, Mock)):
        raise AcademyRouteError(status_code=503, detail="Academy is disabled in config")

    if not _get_professor() or not _get_dataset_curator() or not _get_gpu_habitat():
        raise AcademyRouteError(
            status_code=503,
            detail="Academy components not initialized. Check server logs.",
        )


def _to_http_exception(exc: AcademyRouteError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


def _to_job_summary(job: Dict[str, Any]) -> AcademyJobSummary:
    """Normalizuje rekord historii do stabilnego kontraktu API."""
    job_id = str(job.get("job_id") or job.get("job_name") or "unknown")
    return AcademyJobSummary(
        job_id=job_id,
        job_name=job.get("job_name"),
        status=_normalize_job_status(cast(Optional[str], job.get("status"))),
        started_at=cast(Optional[str], job.get("started_at")),
        finished_at=cast(Optional[str], job.get("finished_at")),
        adapter_path=cast(Optional[str], job.get("adapter_path")),
        base_model=cast(Optional[str], job.get("base_model")),
        output_dir=cast(Optional[str], job.get("output_dir")),
        dataset_path=cast(Optional[str], job.get("dataset_path")),
        parameters=cast(Dict[str, Any], job.get("parameters") or {}),
        error=cast(Optional[str], job.get("error")),
    )


def _load_jobs_history() -> List[Dict[str, Any]]:
    """Ładuje historię jobów z pliku JSONL."""
    return academy_history.load_jobs_history(JOBS_HISTORY_FILE, logger=logger)


def _save_job_to_history(job: Dict[str, Any]):
    """Zapisuje job do historii (append do JSONL)."""
    academy_history.save_job_to_history(job, JOBS_HISTORY_FILE, logger=logger)


def _update_job_in_history(job_id: str, updates: Dict[str, Any]):
    """Aktualizuje job w historii."""
    academy_history.update_job_in_history(
        job_id,
        updates,
        JOBS_HISTORY_FILE,
        logger=logger,
    )


def _save_adapter_metadata(job: Dict[str, Any], adapter_path: Path) -> None:
    """Zapisuje deterministyczne metadata adaptera po udanym treningu."""
    academy_history.save_adapter_metadata(job, adapter_path)


# ==================== Upload Utilities ====================


def _is_path_within_base(path: Path, base: Path) -> bool:
    """Sprawdza czy `path` znajduje się w `base` (po resolve)."""
    return academy_storage.is_path_within_base(path=path, base=base)


def _get_uploads_dir() -> Path:
    """Zwraca katalog uploads pod ACADEMY_TRAINING_DIR."""
    return academy_storage.get_uploads_dir()


def _get_uploads_metadata_file() -> Path:
    """Zwraca plik z metadanymi uploadów."""
    return academy_storage.get_uploads_metadata_file()


def _validate_file_extension(
    filename: str, *, allowed_extensions: list[str] | None = None
) -> bool:
    """Waliduje rozszerzenie pliku."""
    return academy_storage.validate_file_extension(
        filename,
        allowed_extensions=allowed_extensions,
    )


def _validate_file_size(size_bytes: int) -> bool:
    """Waliduje rozmiar pliku."""
    return academy_storage.validate_file_size(size_bytes)


def _check_path_traversal(filename: str) -> bool:
    """Sprawdza czy filename nie zawiera path traversal."""
    return academy_storage.check_path_traversal(filename)


def _load_uploads_metadata() -> List[Dict[str, Any]]:
    """Ładuje metadane uploadów z pliku JSONL."""
    return academy_storage.load_uploads_metadata()


def _save_upload_metadata(upload_info: Dict[str, Any]):
    """Zapisuje metadata uploadu (append do JSONL) z lockowaniem."""
    academy_storage.save_upload_metadata(upload_info)


def _delete_upload_metadata(file_id: str):
    """Usuwa metadata uploadu z pliku z atomową operacją read-modify-write."""
    academy_storage.delete_upload_metadata(file_id)


def _compute_file_hash(file_path: Path) -> str:
    """Oblicza SHA256 hash pliku."""
    return academy_storage.compute_file_hash(file_path)


def _compute_bytes_hash(content: bytes) -> str:
    """Oblicza SHA256 hash dla bajtów w pamięci."""
    return academy_storage.compute_bytes_hash(content)


def _estimate_records_from_content(filename: str, content: bytes) -> int:
    """Szacuje liczbę rekordów na podstawie zawartości pliku w pamięci."""
    return academy_storage.estimate_records_from_content(
        filename=filename,
        content=content,
    )


def _is_model_trainable(model_id: str) -> bool:
    return academy_models.is_model_trainable(model_id=model_id)


# ==================== Endpointy ====================


def _collect_scope_counts(curator: Any, request: DatasetScopeRequest) -> Dict[str, int]:
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


def _ingest_uploads_for_curate(curator: Any, upload_ids: List[str]) -> int:
    return academy_uploads.ingest_uploads_for_ids(
        curator=curator,
        upload_ids=upload_ids,
        uploads_dir=_get_uploads_dir(),
        check_path_traversal_fn=_check_path_traversal,
        ingest_upload_file_fn=_ingest_upload_file,
        logger=logger,
    )


def _ingest_converted_files_for_curate(
    curator: Any,
    req: Request,
    conversion_file_ids: List[str],
) -> int:
    return academy_uploads.ingest_converted_files_for_ids(
        curator=curator,
        conversion_file_ids=conversion_file_ids,
        check_path_traversal_fn=_check_path_traversal,
        resolve_existing_user_file_fn=(
            lambda file_id: _resolve_existing_user_file(req, file_id=file_id)
        ),
        ingest_upload_file_fn=_ingest_upload_file,
        logger=logger,
    )


@router.post(
    "/dataset",
    responses={
        503: RESP_503_ACADEMY_UNAVAILABLE,
    },
)
async def curate_dataset(
    request: DatasetScopeRequest,
    req: Request,
) -> DatasetResponse:
    try:
        _ensure_academy_enabled()
    except AcademyRouteError as e:
        raise _to_http_exception(e) from e

    try:
        result = academy_training.curate_dataset_scope(
            request=request,
            req=req,
            resolve_conversion_file_ids_for_dataset_fn=_resolve_conversion_file_ids_for_dataset,
            get_dataset_curator_fn=_get_dataset_curator,
            collect_scope_counts_fn=_collect_scope_counts,
            ingest_uploads_for_curate_fn=_ingest_uploads_for_curate,
            ingest_converted_files_for_curate_fn=_ingest_converted_files_for_curate,
            logger=logger,
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
        logger.error(f"Failed to curate dataset: {e}", exc_info=True)
        return DatasetResponse(
            success=False, message=f"Failed to curate dataset: {str(e)}"
        )


@router.post(
    "/train",
    responses={
        400: RESP_400_DATASET_REQUIRED,
        403: RESP_403_LOCALHOST_ONLY,
        503: RESP_503_ACADEMY_UNAVAILABLE,
    },
)
async def start_training(request: TrainingRequest, req: Request) -> TrainingResponse:
    try:
        _ensure_academy_enabled()
        require_localhost_request(req)
        from venom_core.config import SETTINGS

        logger.info(
            "Starting training: base_model_set=%s lora_rank=%s num_epochs=%s learning_rate=%s batch_size=%s",
            bool(request.base_model),
            request.lora_rank,
            request.num_epochs,
            request.learning_rate,
            request.batch_size,
        )
        habitat = _get_gpu_habitat()

        dataset_path = academy_training.resolve_dataset_path(
            request.dataset_path,
            academy_training_dir=SETTINGS.ACADEMY_TRAINING_DIR,
            dataset_required_detail=DATASET_REQUIRED_DETAIL,
        )
        base_model = academy_training.ensure_trainable_base_model(
            request_base_model=request.base_model,
            default_base_model=SETTINGS.ACADEMY_DEFAULT_BASE_MODEL,
            is_model_trainable_fn=_is_model_trainable,
        )

        # Przygotuj output directory
        job_id = f"training_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        output_dir = Path(SETTINGS.ACADEMY_MODELS_DIR) / job_id
        output_dir.mkdir(parents=True, exist_ok=True)

        job_record = academy_training.build_job_record(
            dataset_path=dataset_path,
            base_model=base_model,
            output_dir=output_dir,
            request=request,
        )
        job_id = str(job_record["job_id"])
        _save_job_to_history(job_record)
        _update_job_in_history(job_id, {"status": "preparing"})

        # Uruchom trening
        try:
            job_info = habitat.run_training_job(
                dataset_path=dataset_path,
                base_model=base_model,
                output_dir=str(output_dir),
                lora_rank=request.lora_rank,
                learning_rate=request.learning_rate,
                num_epochs=request.num_epochs,
                max_seq_length=request.max_seq_length,
                batch_size=request.batch_size,
                job_name=job_id,
            )
        except Exception as e:
            _update_job_in_history(
                job_id,
                {
                    "status": "failed",
                    "finished_at": datetime.now().isoformat(),
                    "error": str(e),
                    "error_code": "TRAINING_START_FAILED",
                },
            )
            raise

        _update_job_in_history(
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

    except AcademyRouteError as e:
        raise _to_http_exception(e) from e
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start training: {e}", exc_info=True)
        return TrainingResponse(
            success=False, message=f"Failed to start training: {str(e)}"
        )


def _find_job_or_404(job_id: str) -> Dict[str, Any]:
    try:
        return academy_training.find_job_or_404(job_id, jobs=_load_jobs_history())
    except HTTPException as exc:
        raise AcademyRouteError(status_code=exc.status_code, detail=str(exc.detail))


def _sync_job_status_with_habitat(
    habitat: Any, job_id: str, job: Dict[str, Any], job_name: str
) -> tuple[Dict[str, Any], str]:
    return academy_training.sync_job_status_with_habitat(
        habitat=habitat,
        job_id=job_id,
        job=job,
        job_name=job_name,
        normalize_status_fn=_normalize_job_status,
        terminal_statuses=TERMINAL_JOB_STATUSES,
        update_job_fn=_update_job_in_history,
    )


def _log_internal_operation_failure(message: str) -> None:
    """Loguje błędy operacyjne bez danych kontrolowanych przez użytkownika."""
    logger.warning(message, exc_info=True)


def _save_finished_job_metadata(job: Dict[str, Any], current_status: str) -> None:
    academy_training.save_finished_job_metadata(
        job=job,
        current_status=current_status,
        save_adapter_metadata_fn=_save_adapter_metadata,
        log_internal_operation_failure_fn=_log_internal_operation_failure,
    )


def _cleanup_terminal_job_container(
    habitat: Any, job_id: str, job: Dict[str, Any], job_name: str, current_status: str
) -> None:
    academy_training.cleanup_terminal_job_container(
        habitat=habitat,
        job_id=job_id,
        job=job,
        job_name=job_name,
        current_status=current_status,
        terminal_statuses=TERMINAL_JOB_STATUSES,
        update_job_fn=_update_job_in_history,
        log_internal_operation_failure_fn=_log_internal_operation_failure,
    )


@router.get(
    "/train/{job_id}/status",
    responses={
        404: RESP_404_JOB_NOT_FOUND,
        500: RESP_500_INTERNAL,
        503: RESP_503_ACADEMY_UNAVAILABLE,
    },
)
async def get_training_status(job_id: str) -> JobStatusResponse:
    try:
        _ensure_academy_enabled()
        habitat = _get_gpu_habitat()
        job = _find_job_or_404(job_id)
        job_name = job.get("job_name", job_id)
        status_info, current_status = _sync_job_status_with_habitat(
            habitat, job_id, job, job_name
        )
        _save_finished_job_metadata(job, current_status)
        _cleanup_terminal_job_container(habitat, job_id, job, job_name, current_status)

        return JobStatusResponse(
            job_id=job_id,
            status=current_status,
            logs=status_info.get("logs", "")[-5000:],  # Last 5000 chars
            started_at=job.get("started_at"),
            finished_at=job.get("finished_at"),
            adapter_path=job.get("adapter_path"),
            error=status_info.get("error"),
        )

    except AcademyRouteError as e:
        raise _to_http_exception(e) from e
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get training status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get status: {str(e)}")


@router.get(
    "/train/{job_id}/logs/stream",
    responses={
        404: RESP_404_JOB_NOT_FOUND,
        503: RESP_503_ACADEMY_UNAVAILABLE,
    },
)
async def stream_training_logs(job_id: str):
    try:
        _ensure_academy_enabled()
        job = _find_job_or_404(job_id)
    except AcademyRouteError as e:
        raise _to_http_exception(e) from e

    job_name = job.get("job_name", job_id)

    return StreamingResponse(
        _stream_training_logs_events(job_id=job_id, job_name=job_name),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


async def _stream_training_logs_events(job_id: str, job_name: str):
    """Generator eventów SSE dla streamingu logów treningu."""
    from venom_core.learning.training_metrics_parser import TrainingMetricsParser

    async for event in academy_training.stream_training_logs_events(
        job_id=job_id,
        job_name=job_name,
        habitat=_get_gpu_habitat(),
        parser_factory=TrainingMetricsParser,
        normalize_status_fn=_normalize_job_status,
        terminal_statuses=TERMINAL_JOB_STATUSES,
        logger=logger,
    ):
        yield event


@router.get(
    "/jobs",
    responses={
        500: RESP_500_INTERNAL,
        503: RESP_503_ACADEMY_UNAVAILABLE,
    },
)
async def list_jobs(
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    status: Annotated[Optional[str], Query()] = None,
) -> AcademyJobsListResponse:
    try:
        _ensure_academy_enabled()
        jobs = academy_training.list_jobs_response(
            jobs=_load_jobs_history(),
            to_job_summary_fn=_to_job_summary,
            limit=limit,
            status=status,
        )
        return AcademyJobsListResponse(count=len(jobs), jobs=jobs)

    except AcademyRouteError as e:
        raise _to_http_exception(e) from e
    except Exception as e:
        logger.error(f"Failed to list jobs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list jobs: {str(e)}")


@router.get(
    "/adapters",
    responses={
        500: RESP_500_INTERNAL,
        503: RESP_503_ACADEMY_UNAVAILABLE,
    },
)
async def list_adapters() -> List[AdapterInfo]:
    try:
        _ensure_academy_enabled()
        return await academy_models.list_adapters(mgr=_get_model_manager())

    except AcademyRouteError as e:
        raise _to_http_exception(e) from e
    except Exception as e:
        logger.error(f"Failed to list adapters: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to list adapters: {str(e)}"
        )


@router.post(
    "/adapters/activate",
    responses={
        403: RESP_403_LOCALHOST_ONLY,
        404: RESP_404_ADAPTER_NOT_FOUND,
        500: RESP_500_INTERNAL,
        503: RESP_503_ACADEMY_UNAVAILABLE,
    },
)
async def activate_adapter(
    request: ActivateAdapterRequest, req: Request
) -> Dict[str, Any]:
    try:
        _ensure_academy_enabled()
        require_localhost_request(req)
        manager = _get_model_manager()
        if not manager:
            raise AcademyRouteError(
                status_code=503,
                detail="ModelManager not available for adapter activation",
            )
        return academy_models.activate_adapter(
            mgr=manager,
            adapter_id=request.adapter_id,
        )

    except AcademyRouteError as e:
        raise _to_http_exception(e) from e
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Adapter not found") from None
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to activate adapter: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to activate adapter: {str(e)}"
        )


@router.post(
    "/adapters/deactivate",
    responses={
        403: RESP_403_LOCALHOST_ONLY,
        500: RESP_500_INTERNAL,
        503: RESP_503_ACADEMY_UNAVAILABLE,
    },
)
async def deactivate_adapter(req: Request) -> Dict[str, Any]:
    """
    Dezaktywacja aktywnego adaptera (rollback do modelu bazowego).

    Returns:
        Status dezaktywacji
    """
    try:
        _ensure_academy_enabled()
        require_localhost_request(req)
        manager = _get_model_manager()
        if not manager:
            raise AcademyRouteError(
                status_code=503,
                detail="ModelManager not available for adapter deactivation",
            )
        return academy_models.deactivate_adapter(mgr=manager)

    except AcademyRouteError as e:
        raise _to_http_exception(e) from e
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to deactivate adapter: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to deactivate adapter: {str(e)}"
        )


@router.delete(
    "/train/{job_id}",
    responses={
        403: RESP_403_LOCALHOST_ONLY,
        404: RESP_404_JOB_NOT_FOUND,
        500: RESP_500_INTERNAL,
        503: RESP_503_ACADEMY_UNAVAILABLE,
    },
)
async def cancel_training(job_id: str, req: Request) -> Dict[str, Any]:
    """
    Anuluj trening (zatrzymaj kontener).

    Returns:
        Status anulowania
    """
    try:
        _ensure_academy_enabled()
        require_localhost_request(req)
        return academy_training.cancel_training_job(
            job_id=job_id,
            habitat=_get_gpu_habitat(),
            jobs=_load_jobs_history(),
            update_job_fn=_update_job_in_history,
            logger=logger,
        )

    except AcademyRouteError as e:
        raise _to_http_exception(e) from e
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel training: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to cancel training: {str(e)}"
        )


@router.get(
    "/status",
    responses={
        500: RESP_500_INTERNAL,
    },
)
async def academy_status() -> Dict[str, Any]:
    """
    Ogólny status Academy.

    Returns:
        Status komponentów i statystyki
    """
    try:
        from venom_core.config import SETTINGS

        # Statystyki LessonsStore
        lessons_stats = {}
        lessons_store_dep = _get_lessons_store()
        if lessons_store_dep:
            lessons_stats = lessons_store_dep.get_statistics()

        # Status GPU
        gpu_available = False
        gpu_info = {}
        habitat = _get_gpu_habitat()
        if habitat:
            gpu_available = habitat.is_gpu_available()
            # Pobierz szczegółowe info o GPU
            try:
                gpu_info = habitat.get_gpu_info()
            except Exception as e:
                logger.warning(f"Failed to get GPU info: {e}")
                gpu_info = {"available": gpu_available}

        # Statystyki jobów
        jobs = _load_jobs_history()
        jobs_stats = {
            "total": len(jobs),
            "running": len([j for j in jobs if j.get("status") == "running"]),
            "finished": len([j for j in jobs if j.get("status") == "finished"]),
            "failed": len([j for j in jobs if j.get("status") == "failed"]),
        }

        return {
            "enabled": SETTINGS.ENABLE_ACADEMY,
            "components": {
                "professor": _get_professor() is not None,
                "dataset_curator": _get_dataset_curator() is not None,
                "gpu_habitat": _get_gpu_habitat() is not None,
                "lessons_store": _get_lessons_store() is not None,
                "model_manager": _get_model_manager() is not None,
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
                "default_base_model": SETTINGS.ACADEMY_DEFAULT_BASE_MODEL,
            },
        }

    except Exception as e:
        logger.error(f"Failed to get academy status: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to get academy status: {str(e)}"
        )


# ==================== Upload Endpoints ====================


def _validate_upload_filename(
    file: Any,
    settings: Any,
    *,
    allowed_extensions: list[str] | None = None,
) -> tuple[Optional[str], Optional[Dict[str, str]]]:
    return academy_uploads.validate_upload_filename(
        file=file,
        settings=settings,
        check_path_traversal_fn=_check_path_traversal,
        validate_file_extension_fn=_validate_file_extension,
        allowed_extensions=allowed_extensions,
    )


async def _persist_with_limits(
    file: Any,
    file_path: Path,
    filename: str,
    settings: Any,
) -> tuple[Optional[tuple[int, bytes]], Optional[Dict[str, str]]]:
    return await academy_uploads.persist_with_limits(
        file=file,
        file_path=file_path,
        filename=filename,
        settings=settings,
        logger=logger,
        cleanup_uploaded_file_fn=lambda path: academy_uploads.cleanup_uploaded_file(
            path, logger=logger
        ),
    )


async def _process_uploaded_file(
    file: Any, uploads_dir: Path, tag: str, description: str
) -> tuple[Optional[Dict[str, Any]], Optional[Dict[str, str]]]:
    from venom_core.config import SETTINGS

    return await academy_uploads.process_uploaded_file(
        file=file,
        uploads_dir=uploads_dir,
        tag=tag,
        description=description,
        settings=SETTINGS,
        check_path_traversal_fn=_check_path_traversal,
        validate_file_extension_fn=_validate_file_extension,
        compute_bytes_hash_fn=_compute_bytes_hash,
        estimate_records_from_content_fn=_estimate_records_from_content,
        save_upload_metadata_fn=_save_upload_metadata,
        cleanup_uploaded_file_fn=lambda path: academy_uploads.cleanup_uploaded_file(
            path, logger=logger
        ),
        logger=logger,
    )


@router.post(
    "/dataset/upload",
    responses={
        400: {
            "description": "Invalid request payload (e.g., no files, too many files)."
        },
        403: RESP_403_LOCALHOST_ONLY,
        503: RESP_503_ACADEMY_UNAVAILABLE,
    },
)
async def upload_dataset_files(req: Request) -> Dict[str, Any]:
    """
    Upload plików użytkownika do Academy (localhost-only).

    Akceptuje multipart/form-data z plikami.
    Waliduje rozszerzenie, rozmiar, path traversal.

    Returns:
        Lista uploadowanych plików z metadata
    """
    try:
        _ensure_academy_enabled()
        require_localhost_request(req)
    except AcademyRouteError as e:
        raise _to_http_exception(e) from e

    from venom_core.config import SETTINGS

    # Parse multipart form data manually
    form = await req.form()
    files, tag, description = academy_uploads.parse_upload_form(form)

    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    if len(files) > SETTINGS.ACADEMY_MAX_UPLOADS_PER_REQUEST:
        raise HTTPException(
            status_code=400,
            detail=f"Too many files (max {SETTINGS.ACADEMY_MAX_UPLOADS_PER_REQUEST})",
        )

    uploaded_files = []
    failed_files = []
    uploads_dir = _get_uploads_dir()

    for file in files:
        upload_info, error_info = await _process_uploaded_file(
            file=file,
            uploads_dir=uploads_dir,
            tag=tag,
            description=description,
        )
        if upload_info:
            uploaded_files.append(upload_info)
        if error_info:
            failed_files.append(error_info)

    logger.info(
        f"Uploaded {len(uploaded_files)} files to Academy ({len(failed_files)} failed)"
    )

    return academy_uploads.build_upload_response(uploaded_files, failed_files)


@router.get("/dataset/uploads")
async def list_dataset_uploads() -> List[UploadFileInfo]:
    """
    Lista uploadowanych plików użytkownika.

    Returns:
        Lista UploadFileInfo
    """
    try:
        _ensure_academy_enabled()
    except AcademyRouteError as e:
        raise _to_http_exception(e) from e

    uploads = _load_uploads_metadata()
    return [UploadFileInfo(**u) for u in uploads]


@router.delete(
    "/dataset/uploads/{file_id}",
    responses={
        400: {"description": "Invalid upload identifier."},
        403: RESP_403_LOCALHOST_ONLY,
        404: {"description": "Upload not found"},
        500: RESP_500_INTERNAL,
        503: RESP_503_ACADEMY_UNAVAILABLE,
    },
)
async def delete_dataset_upload(file_id: str, req: Request) -> Dict[str, Any]:
    """
    Usuwa uploadowany plik (localhost-only).

    Args:
        file_id: ID pliku do usunięcia

    Returns:
        Status usunięcia
    """
    try:
        _ensure_academy_enabled()
        require_localhost_request(req)
    except AcademyRouteError as e:
        raise _to_http_exception(e) from e

    try:
        return academy_uploads.delete_upload_file(
            file_id=file_id,
            uploads_dir=_get_uploads_dir(),
            check_path_traversal_fn=_check_path_traversal,
            delete_upload_metadata_fn=_delete_upload_metadata,
            logger=logger,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except FileNotFoundError:
        raise HTTPException(
            status_code=404, detail=f"Upload not found: {file_id}"
        ) from None
    except Exception as e:
        logger.error(f"Failed to delete upload {file_id}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to delete upload: {str(e)}"
        )


_sanitize_user_id = academy_conversion.sanitize_user_id


def _resolve_user_id(req: Request) -> str:
    actor = req.headers.get("X-Actor") or req.headers.get("X-User-Id") or "local-user"
    return _sanitize_user_id(actor.strip())


_get_user_conversion_workspace = academy_conversion.get_user_conversion_workspace


_get_conversion_output_dir = academy_conversion.get_conversion_output_dir


_get_user_conversion_lock_file = academy_conversion.get_user_conversion_lock_file


_user_conversion_metadata_lock = academy_conversion.user_conversion_metadata_lock


_load_user_conversion_metadata = academy_conversion.load_user_conversion_metadata


_save_user_conversion_metadata = academy_conversion.save_user_conversion_metadata


_normalize_conversion_item = academy_conversion.normalize_conversion_item


_find_conversion_item = academy_conversion.find_conversion_item


def _resolve_workspace_file_path(
    workspace: Dict[str, Path],
    *,
    file_id: str,
    category: str,
) -> Path:
    try:
        return academy_file_resolution.resolve_workspace_file_path(
            workspace,
            file_id=file_id,
            category=category,
            get_conversion_output_dir_fn=_get_conversion_output_dir,
            resolve_workspace_file_path_impl=academy_conversion.resolve_workspace_file_path,
        )
    except ValueError as exc:
        detail = str(exc)
        if detail == "Invalid file category":
            raise AcademyRouteError(status_code=400, detail=detail) from exc
        raise AcademyRouteError(status_code=400, detail="Invalid file path") from exc


def _load_conversion_item_from_workspace(
    workspace: Dict[str, Path],
    *,
    file_id: str,
) -> Dict[str, Any]:
    try:
        return academy_file_resolution.load_conversion_item_from_workspace(
            workspace,
            file_id=file_id,
            user_conversion_metadata_lock_fn=_user_conversion_metadata_lock,
            load_user_conversion_metadata_fn=_load_user_conversion_metadata,
            find_conversion_item_fn=_find_conversion_item,
            load_conversion_item_impl=academy_conversion.load_conversion_item_from_workspace,
        )
    except FileNotFoundError as exc:
        raise AcademyRouteError(status_code=404, detail="File not found") from exc


def _resolve_existing_user_file(
    req: Request,
    *,
    file_id: str,
) -> tuple[Dict[str, Any], Path]:
    user_id = _resolve_user_id(req)
    try:
        return academy_file_resolution.resolve_existing_user_file(
            user_id=user_id,
            file_id=file_id,
            get_user_conversion_workspace_fn=_get_user_conversion_workspace,
            load_conversion_item_fn=lambda workspace, fid: (
                _load_conversion_item_from_workspace(workspace, file_id=fid)
            ),
            resolve_workspace_file_path_fn=lambda workspace, fid, category: (
                _resolve_workspace_file_path(
                    workspace,
                    file_id=fid,
                    category=category,
                )
            ),
        )
    except FileNotFoundError as exc:
        raise AcademyRouteError(
            status_code=404, detail="File not found on disk"
        ) from exc


_build_conversion_file_id = academy_conversion.build_conversion_file_id


_serialize_records_to_markdown = academy_conversion.serialize_records_to_markdown


_records_from_text = academy_conversion.records_from_text


_records_from_json_file = academy_conversion.records_from_json_file


_records_from_jsonl_file = academy_conversion.records_from_jsonl_file


_records_from_csv_file = academy_conversion.records_from_csv_file


_extract_text_from_pdf = academy_conversion.extract_text_from_pdf


_extract_text_from_docx = academy_conversion.extract_text_from_docx


_convert_with_pandoc = academy_conversion.convert_with_pandoc


_markdown_from_json = academy_conversion.markdown_from_json


_markdown_from_jsonl = academy_conversion.markdown_from_jsonl


_markdown_from_csv = academy_conversion.markdown_from_csv


def _markdown_from_binary_document(source_path: Path, ext: str) -> str:
    return academy_file_resolution.markdown_from_binary_document_with_impls(
        source_path=source_path,
        ext=ext,
        ext_pdf=academy_conversion.EXT_PDF,
        ext_docx=academy_conversion.EXT_DOCX,
        convert_with_pandoc_fn=_convert_with_pandoc,
        extract_text_from_pdf_fn=_extract_text_from_pdf,
        extract_text_from_docx_fn=_extract_text_from_docx,
    )


def _source_to_markdown(source_path: Path) -> str:
    return academy_file_resolution.source_to_markdown_with_impls(
        source_path,
        ext_md=academy_conversion.EXT_MD,
        ext_txt=academy_conversion.EXT_TXT,
        ext_json=academy_conversion.EXT_JSON,
        ext_jsonl=academy_conversion.EXT_JSONL,
        ext_csv=academy_conversion.EXT_CSV,
        ext_doc=academy_conversion.EXT_DOC,
        ext_docx=academy_conversion.EXT_DOCX,
        ext_pdf=academy_conversion.EXT_PDF,
        markdown_from_json_fn=_markdown_from_json,
        markdown_from_jsonl_fn=_markdown_from_jsonl,
        markdown_from_csv_fn=_markdown_from_csv,
        markdown_from_binary_document_fn=_markdown_from_binary_document,
    )


def _source_to_records(source_path: Path) -> List[Dict[str, str]]:
    return academy_file_resolution.source_to_records_with_impls(
        source_path,
        ext_json=academy_conversion.EXT_JSON,
        ext_jsonl=academy_conversion.EXT_JSONL,
        ext_csv=academy_conversion.EXT_CSV,
        records_from_json_file_fn=_records_from_json_file,
        records_from_jsonl_file_fn=_records_from_jsonl_file,
        records_from_csv_file_fn=_records_from_csv_file,
        source_to_markdown_fn=_source_to_markdown,
        records_from_text_fn=_records_from_text,
    )


_write_target_markdown = academy_conversion.write_target_markdown


_write_target_text = academy_conversion.write_target_text


_write_target_json = academy_conversion.write_target_json


_write_target_jsonl = academy_conversion.write_target_jsonl


_write_target_csv = academy_conversion.write_target_csv


_write_records_as_target = academy_conversion.write_records_as_target


_build_conversion_item = academy_conversion.build_conversion_item


def _get_selected_converted_file_ids(req: Request) -> List[str]:
    user_id = _resolve_user_id(req)
    workspace = _get_user_conversion_workspace(user_id)
    return academy_conversion.get_selected_converted_file_ids(
        workspace=workspace,
        user_conversion_metadata_lock_fn=_user_conversion_metadata_lock,
        load_user_conversion_metadata_fn=_load_user_conversion_metadata,
        check_path_traversal_fn=_check_path_traversal,
    )


def _resolve_conversion_file_ids_for_dataset(
    req: Request,
    requested_ids: List[str] | None = None,
) -> List[str]:
    return academy_conversion.resolve_conversion_file_ids_for_dataset(
        requested_ids=requested_ids,
        selected_ids_fn=lambda: _get_selected_converted_file_ids(req),
    )


@router.get("/dataset/conversion/files")
async def list_dataset_conversion_files(req: Request) -> DatasetConversionListResponse:
    try:
        _ensure_academy_enabled()
    except AcademyRouteError as e:
        raise _to_http_exception(e) from e

    user_id = _resolve_user_id(req)
    workspace = _get_user_conversion_workspace(user_id)
    payload = academy_conversion.list_conversion_files_for_user(
        user_id=user_id,
        workspace=workspace,
        user_conversion_metadata_lock_fn=_user_conversion_metadata_lock,
        load_user_conversion_metadata_fn=_load_user_conversion_metadata,
        normalize_conversion_item_fn=_normalize_conversion_item,
    )
    return DatasetConversionListResponse(
        user_id=payload["user_id"],
        workspace_dir=payload["workspace_dir"],
        source_files=payload["source_files"],
        converted_files=payload["converted_files"],
    )


@router.post(
    "/dataset/conversion/upload",
    responses={
        400: RESP_400_BAD_REQUEST,
    },
)
async def upload_dataset_conversion_files(req: Request) -> Dict[str, Any]:
    try:
        _ensure_academy_enabled()
        require_localhost_request(req)
    except AcademyRouteError as e:
        raise _to_http_exception(e) from e

    from venom_core.config import SETTINGS

    user_id = _resolve_user_id(req)
    workspace = _get_user_conversion_workspace(user_id)

    form = await req.form()
    files = form.getlist("files")
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")
    if len(files) > SETTINGS.ACADEMY_MAX_UPLOADS_PER_REQUEST:
        raise HTTPException(
            status_code=400,
            detail=f"Too many files (max {SETTINGS.ACADEMY_MAX_UPLOADS_PER_REQUEST})",
        )
    return await academy_conversion.upload_conversion_files_for_user(
        files=files,
        workspace=workspace,
        settings=SETTINGS,
        user_conversion_metadata_lock_fn=_user_conversion_metadata_lock,
        load_user_conversion_metadata_fn=_load_user_conversion_metadata,
        save_user_conversion_metadata_fn=_save_user_conversion_metadata,
        validate_upload_filename_fn=_validate_upload_filename,
        persist_with_limits_fn=_persist_with_limits,
        build_conversion_file_id_fn=_build_conversion_file_id,
        build_conversion_item_fn=_build_conversion_item,
        normalize_conversion_item_fn=_normalize_conversion_item,
    )


@router.post(
    "/dataset/conversion/files/{file_id}/convert",
    responses={
        400: RESP_400_BAD_REQUEST,
        404: RESP_404_FILE_NOT_FOUND,
        500: RESP_500_INTERNAL,
    },
)
async def convert_dataset_file(
    file_id: str,
    payload: DatasetConversionRequest,
    req: Request,
) -> DatasetConversionResult:
    try:
        _ensure_academy_enabled()
        require_localhost_request(req)
    except AcademyRouteError as e:
        raise _to_http_exception(e) from e

    user_id = _resolve_user_id(req)
    workspace = _get_user_conversion_workspace(user_id)
    target_format = payload.target_format.lower()
    try:
        source_item, converted_item = academy_conversion.convert_dataset_source_file(
            file_id=file_id,
            workspace=workspace,
            target_format=target_format,
            check_path_traversal_fn=_check_path_traversal,
            user_conversion_metadata_lock_fn=_user_conversion_metadata_lock,
            load_user_conversion_metadata_fn=_load_user_conversion_metadata,
            save_user_conversion_metadata_fn=_save_user_conversion_metadata,
            find_conversion_item_fn=_find_conversion_item,
            resolve_workspace_file_path_fn=_resolve_workspace_file_path,
            source_to_records_fn=_source_to_records,
            write_records_as_target_fn=_write_records_as_target,
            build_conversion_item_fn=_build_conversion_item,
        )
    except AcademyRouteError as e:
        raise _to_http_exception(e) from e
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
        logger.exception(
            "Unexpected conversion error for user=%s file_id=%s target=%s",
            user_id,
            file_id,
            target_format,
        )
        raise HTTPException(
            status_code=500,
            detail="Conversion failed due to internal error",
        ) from exc

    return DatasetConversionResult(
        success=True,
        message=f"Converted to {target_format}",
        source_file=_normalize_conversion_item(source_item),
        converted_file=_normalize_conversion_item(converted_item),
    )


@router.post(
    "/dataset/conversion/files/{file_id}/training-selection",
    responses={
        400: RESP_400_BAD_REQUEST,
        404: RESP_404_FILE_NOT_FOUND,
    },
)
async def set_dataset_conversion_training_selection(
    file_id: str,
    payload: DatasetConversionTrainingSelectionRequest,
    req: Request,
) -> DatasetConversionFileInfo:
    try:
        _ensure_academy_enabled()
        require_localhost_request(req)
    except AcademyRouteError as e:
        raise _to_http_exception(e) from e

    user_id = _resolve_user_id(req)
    workspace = _get_user_conversion_workspace(user_id)
    try:
        item = academy_conversion.set_conversion_training_selection(
            file_id=file_id,
            selected_for_training=bool(payload.selected_for_training),
            workspace=workspace,
            check_path_traversal_fn=_check_path_traversal,
            user_conversion_metadata_lock_fn=_user_conversion_metadata_lock,
            load_user_conversion_metadata_fn=_load_user_conversion_metadata,
            save_user_conversion_metadata_fn=_save_user_conversion_metadata,
            find_conversion_item_fn=_find_conversion_item,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _normalize_conversion_item(item)


@router.get(
    "/dataset/conversion/files/{file_id}/preview",
    responses={
        400: RESP_400_BAD_REQUEST,
        404: RESP_404_FILE_NOT_FOUND,
    },
)
async def preview_dataset_conversion_file(
    file_id: str,
    req: Request,
) -> DatasetFilePreviewResponse:
    try:
        _ensure_academy_enabled()
        require_localhost_request(req)
    except AcademyRouteError as e:
        raise _to_http_exception(e) from e

    if not _check_path_traversal(file_id):
        raise HTTPException(status_code=400, detail=f"Invalid file_id: {file_id}")

    try:
        item, file_path = _resolve_existing_user_file(req, file_id=file_id)
    except AcademyRouteError as e:
        raise _to_http_exception(e) from e

    ext = file_path.suffix.lower()
    if ext not in {".txt", ".md"}:
        raise HTTPException(
            status_code=400,
            detail="Preview supported only for .txt and .md files",
        )

    preview_text, truncated = await academy_conversion.read_text_preview(
        file_path=file_path
    )

    return DatasetFilePreviewResponse(
        file_id=file_id,
        name=str(item.get("name") or file_id),
        extension=ext,
        preview=preview_text,
        truncated=truncated,
    )


@router.get(
    "/dataset/conversion/files/{file_id}/download",
    responses={
        400: RESP_400_BAD_REQUEST,
        404: RESP_404_FILE_NOT_FOUND,
    },
)
async def download_dataset_conversion_file(
    file_id: str,
    req: Request,
) -> FileResponse:
    try:
        _ensure_academy_enabled()
        require_localhost_request(req)
    except AcademyRouteError as e:
        raise _to_http_exception(e) from e

    if not _check_path_traversal(file_id):
        raise HTTPException(status_code=400, detail=f"Invalid file_id: {file_id}")

    try:
        item, file_path = _resolve_existing_user_file(req, file_id=file_id)
    except AcademyRouteError as e:
        raise _to_http_exception(e) from e

    media_type = academy_conversion.guess_media_type(file_path)
    return FileResponse(
        path=str(file_path),
        filename=str(item.get("name") or file_path.name),
        media_type=media_type,
    )


@router.post(
    "/dataset/preview",
    responses={
        500: RESP_500_INTERNAL,
        503: RESP_503_ACADEMY_UNAVAILABLE,
    },
)
async def preview_dataset(
    request: DatasetScopeRequest,
    req: Request,
) -> DatasetPreviewResponse:
    try:
        _ensure_academy_enabled()
    except AcademyRouteError as e:
        raise _to_http_exception(e) from e

    try:
        result = academy_training.preview_dataset_scope(
            request=request,
            req=req,
            resolve_conversion_file_ids_for_dataset_fn=_resolve_conversion_file_ids_for_dataset,
            get_dataset_curator_fn=_get_dataset_curator,
            collect_scope_counts_fn=_collect_scope_counts,
            ingest_uploads_for_preview_fn=lambda curator,
            upload_ids,
            warnings: academy_uploads.ingest_uploads_for_preview(
                curator=curator,
                upload_ids=upload_ids,
                warnings=warnings,
                uploads_dir=_get_uploads_dir(),
                check_path_traversal_fn=_check_path_traversal,
                ingest_upload_file_fn=_ingest_upload_file,
            ),
            ingest_converted_files_for_preview_fn=lambda curator,
            req_obj,
            conversion_file_ids,
            warnings: academy_uploads.ingest_converted_files_for_preview(
                curator=curator,
                conversion_file_ids=conversion_file_ids,
                warnings=warnings,
                check_path_traversal_fn=_check_path_traversal,
                resolve_existing_user_file_fn=lambda *,
                file_id: _resolve_existing_user_file(req_obj, file_id=file_id),
                ingest_upload_file_fn=_ingest_upload_file,
            ),
            add_low_examples_warning_fn=lambda warnings,
            total_examples,
            quality_profile: academy_uploads.add_low_examples_warning(
                warnings=warnings,
                total_examples=total_examples,
                quality_profile=quality_profile,
            ),
            build_preview_samples_fn=academy_uploads.build_preview_samples,
            logger=logger,
        )
        return DatasetPreviewResponse(
            total_examples=result["total_examples"],
            by_source=result["by_source"],
            removed_low_quality=result["removed_low_quality"],
            warnings=result["warnings"],
            samples=result["samples"],
        )

    except Exception as e:
        logger.error(f"Failed to preview dataset: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to preview dataset: {str(e)}"
        )


def _ingest_jsonl_upload(curator: Any, file_path: Path) -> int:
    return academy_uploads.ingest_jsonl_upload(curator, file_path, logger=logger)


def _ingest_upload_file(curator, file_path: Path) -> int:
    """
    Ingestuje plik uploadowany do curator.

    Returns:
        Liczba dodanych rekordów
    """
    return academy_uploads.ingest_upload_file(curator, file_path, logger=logger)


def _validate_training_record(record: Dict[str, Any]) -> bool:
    """Waliduje czy rekord treningowy jest poprawny."""
    return academy_uploads.validate_training_record(record)


def _add_trainable_model_from_catalog(
    result: List[TrainableModelInfo],
    seen: set[str],
    model_id: str,
    provider: str,
    label: str,
    default_model: str,
    reason: Optional[str] = None,
    installed_local: bool = False,
) -> None:
    academy_models.add_trainable_model_from_catalog(
        result=result,
        seen=seen,
        model_id=model_id,
        provider=provider,
        label=label,
        default_model=default_model,
        reason=reason,
        installed_local=installed_local,
    )


async def _collect_local_trainable_models(
    mgr: Any, default_model: str, result: List[TrainableModelInfo], seen: set[str]
) -> None:
    await academy_models.collect_local_trainable_models(
        mgr=mgr,
        default_model=default_model,
        result=result,
        seen=seen,
    )


def _collect_default_trainable_models(
    default_model: str, result: List[TrainableModelInfo], seen: set[str]
) -> None:
    academy_models.collect_default_trainable_models(
        default_model=default_model,
        result=result,
        seen=seen,
    )


def _ensure_default_model_visible(
    default_model: str, result: List[TrainableModelInfo], seen: set[str]
) -> None:
    academy_models.ensure_default_model_visible(
        default_model=default_model,
        result=result,
        seen=seen,
    )


@router.get("/models/trainable")
async def get_trainable_models() -> List[TrainableModelInfo]:
    """
    Lista modeli trenowalnych dla Academy.

    Returns:
        Lista TrainableModelInfo z modelami zgodnymi z LoRA/QLoRA
    """
    try:
        _ensure_academy_enabled()
    except AcademyRouteError as e:
        raise _to_http_exception(e) from e

    return await academy_models.list_trainable_models(mgr=_get_model_manager())
