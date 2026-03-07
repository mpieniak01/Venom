"""Moduł: routes/academy - Endpointy API dla The Academy (trenowanie modeli)."""

import os
import sys
from pathlib import Path
from typing import Annotated, Any, Dict, List, Optional, cast
from unittest.mock import Mock

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse

import venom_core.services.academy.route_handlers as academy_route_handlers
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
    client_host = req.client.host if req.client else "unknown"
    if client_host not in ["127.0.0.1", "::1", "localhost"]:
        logger.warning(
            "Próba dostępu do endpointu administracyjnego Academy z hosta: %s",
            client_host,
        )
        raise AcademyRouteError(status_code=403, detail="Access denied")


def _academy_module() -> Any:
    return sys.modules[__name__]


def _ensure_academy_enabled():
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
    return academy_history.load_jobs_history(JOBS_HISTORY_FILE, logger=logger)


def _save_job_to_history(job: Dict[str, Any]):
    academy_history.save_job_to_history(job, JOBS_HISTORY_FILE, logger=logger)


def _update_job_in_history(job_id: str, updates: Dict[str, Any]):
    academy_history.update_job_in_history(
        job_id,
        updates,
        JOBS_HISTORY_FILE,
        logger=logger,
    )


def _save_adapter_metadata(job: Dict[str, Any], adapter_path: Path) -> None:
    academy_history.save_adapter_metadata(job, adapter_path)


def _is_path_within_base(path: Path, base: Path) -> bool:
    return academy_storage.is_path_within_base(path=path, base=base)


def _get_uploads_dir() -> Path:
    return academy_storage.get_uploads_dir()


def _get_uploads_metadata_file() -> Path:
    return academy_storage.get_uploads_metadata_file()


def _validate_file_extension(
    filename: str, *, allowed_extensions: list[str] | None = None
) -> bool:
    return academy_storage.validate_file_extension(
        filename,
        allowed_extensions=allowed_extensions,
    )


def _validate_file_size(size_bytes: int) -> bool:
    return academy_storage.validate_file_size(size_bytes)


def _check_path_traversal(filename: str) -> bool:
    return academy_storage.check_path_traversal(filename)


def _load_uploads_metadata() -> List[Dict[str, Any]]:
    return academy_storage.load_uploads_metadata()


def _save_upload_metadata(upload_info: Dict[str, Any]):
    academy_storage.save_upload_metadata(upload_info)


def _delete_upload_metadata(file_id: str):
    academy_storage.delete_upload_metadata(file_id)


def _compute_file_hash(file_path: Path) -> str:
    return academy_storage.compute_file_hash(file_path)


def _compute_bytes_hash(content: bytes) -> str:
    return academy_storage.compute_bytes_hash(content)


def _estimate_records_from_content(filename: str, content: bytes) -> int:
    return academy_storage.estimate_records_from_content(
        filename=filename,
        content=content,
    )


def _is_model_trainable(model_id: str) -> bool:
    return academy_models.is_model_trainable(model_id=model_id)


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
    return academy_route_handlers.curate_dataset_handler(
        request=request,
        req=req,
        academy=_academy_module(),
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
    return await academy_route_handlers.start_training_handler(
        request=request,
        req=req,
        academy=_academy_module(),
    )


def _log_internal_operation_failure(message: str) -> None:
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
    return academy_route_handlers.get_training_status_handler(
        job_id=job_id,
        academy=_academy_module(),
    )


@router.get(
    "/train/{job_id}/logs/stream",
    responses={
        404: RESP_404_JOB_NOT_FOUND,
        503: RESP_503_ACADEMY_UNAVAILABLE,
    },
)
async def stream_training_logs(job_id: str):
    return academy_route_handlers.stream_training_logs_handler(
        job_id=job_id,
        academy=_academy_module(),
    )


async def _stream_training_logs_events(job_id: str, job_name: str):
    async for event in academy_route_handlers.stream_training_logs_events_handler(
        job_id=job_id,
        job_name=job_name,
        academy=_academy_module(),
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
    return academy_route_handlers.list_jobs_handler(
        limit=limit,
        status=status,
        academy=_academy_module(),
    )


@router.get(
    "/adapters",
    responses={
        500: RESP_500_INTERNAL,
        503: RESP_503_ACADEMY_UNAVAILABLE,
    },
)
async def list_adapters() -> List[AdapterInfo]:
    return await academy_route_handlers.list_adapters_handler(academy=_academy_module())


@router.get(
    "/adapters/audit",
    responses={
        500: RESP_500_INTERNAL,
        503: RESP_503_ACADEMY_UNAVAILABLE,
    },
)
async def audit_adapters(
    runtime_id: Annotated[Optional[str], Query()] = None,
    model_id: Annotated[Optional[str], Query()] = None,
) -> Dict[str, Any]:
    return academy_route_handlers.audit_adapters_handler(
        academy=_academy_module(),
        runtime_id=runtime_id,
        model_id=model_id,
    )


@router.post(
    "/adapters/activate",
    responses={
        400: RESP_400_BAD_REQUEST,
        403: RESP_403_LOCALHOST_ONLY,
        404: RESP_404_ADAPTER_NOT_FOUND,
        500: RESP_500_INTERNAL,
        503: RESP_503_ACADEMY_UNAVAILABLE,
    },
)
async def activate_adapter(
    request: ActivateAdapterRequest, req: Request
) -> Dict[str, Any]:
    return await academy_route_handlers.activate_adapter_handler(
        request=request,
        req=req,
        academy=_academy_module(),
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
    return academy_route_handlers.deactivate_adapter_handler(
        req=req,
        academy=_academy_module(),
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
    return academy_route_handlers.cancel_training_handler(
        job_id=job_id,
        req=req,
        academy=_academy_module(),
    )


@router.get(
    "/status",
    responses={
        500: RESP_500_INTERNAL,
    },
)
async def academy_status() -> Dict[str, Any]:
    return academy_route_handlers.academy_status_handler(academy=_academy_module())


# ==================== Upload Endpoints ====================


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
    return await academy_route_handlers.upload_dataset_files_handler(
        req=req,
        academy=_academy_module(),
    )


@router.get("/dataset/uploads")
async def list_dataset_uploads() -> List[UploadFileInfo]:
    return academy_route_handlers.list_dataset_uploads_handler(
        academy=_academy_module()
    )


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
    return academy_route_handlers.delete_dataset_upload_handler(
        file_id=file_id,
        req=req,
        academy=_academy_module(),
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
_extract_text_from_pdf = academy_conversion.extract_text_from_pdf
_extract_text_from_docx = academy_conversion.extract_text_from_docx
_convert_with_pandoc = academy_conversion.convert_with_pandoc


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
        markdown_from_json_fn=academy_conversion.markdown_from_json,
        markdown_from_jsonl_fn=academy_conversion.markdown_from_jsonl,
        markdown_from_csv_fn=academy_conversion.markdown_from_csv,
        markdown_from_binary_document_fn=_markdown_from_binary_document,
    )


def _source_to_records(source_path: Path) -> List[Dict[str, str]]:
    return academy_file_resolution.source_to_records_with_impls(
        source_path,
        ext_json=academy_conversion.EXT_JSON,
        ext_jsonl=academy_conversion.EXT_JSONL,
        ext_csv=academy_conversion.EXT_CSV,
        records_from_json_file_fn=academy_conversion.records_from_json_file,
        records_from_jsonl_file_fn=academy_conversion.records_from_jsonl_file,
        records_from_csv_file_fn=academy_conversion.records_from_csv_file,
        source_to_markdown_fn=_source_to_markdown,
        records_from_text_fn=academy_conversion.records_from_text,
    )


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
    return academy_route_handlers.list_dataset_conversion_files_handler(
        req=req,
        academy=_academy_module(),
    )


@router.post(
    "/dataset/conversion/upload",
    responses={
        400: RESP_400_BAD_REQUEST,
    },
)
async def upload_dataset_conversion_files(req: Request) -> Dict[str, Any]:
    return await academy_route_handlers.upload_dataset_conversion_files_handler(
        req=req,
        academy=_academy_module(),
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
    return academy_route_handlers.convert_dataset_file_handler(
        file_id=file_id,
        payload=payload,
        req=req,
        academy=_academy_module(),
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
    return academy_route_handlers.set_dataset_conversion_training_selection_handler(
        file_id=file_id,
        payload=payload,
        req=req,
        academy=_academy_module(),
    )


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
    return await academy_route_handlers.preview_dataset_conversion_file_handler(
        file_id=file_id,
        req=req,
        academy=_academy_module(),
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
    return academy_route_handlers.download_dataset_conversion_file_handler(
        file_id=file_id,
        req=req,
        academy=_academy_module(),
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
    return academy_route_handlers.preview_dataset_handler(
        request=request,
        req=req,
        academy=_academy_module(),
    )


def _ingest_upload_file(curator, file_path: Path) -> int:
    return academy_uploads.ingest_upload_file(curator, file_path, logger=logger)


def _validate_training_record(record: Dict[str, Any]) -> bool:
    return academy_uploads.validate_training_record(record)
