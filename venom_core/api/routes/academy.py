"""Moduł: routes/academy - Endpointy API dla The Academy (trenowanie modeli)."""

import json
import mimetypes
import os
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Callable, Dict, List, Optional, TextIO, cast
from unittest.mock import Mock

import anyio
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse

from venom_core.api.routes import (
    academy_conversion,
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
EXT_JSON = ".json"
EXT_JSONL = ".jsonl"
EXT_MD = ".md"
EXT_TXT = ".txt"
EXT_CSV = ".csv"
EXT_DOC = ".doc"
EXT_DOCX = ".docx"
EXT_PDF = ".pdf"

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
    jobs_file = JOBS_HISTORY_FILE
    if not jobs_file.exists():
        return []

    jobs = []
    try:
        with open(jobs_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    jobs.append(json.loads(line))
    except Exception as e:
        logger.warning(f"Failed to load jobs history: {e}")
    return jobs


def _save_job_to_history(job: Dict[str, Any]):
    """Zapisuje job do historii (append do JSONL)."""
    jobs_file = JOBS_HISTORY_FILE
    jobs_file.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(jobs_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(job, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error(f"Failed to save job to history: {e}")


def _update_job_in_history(job_id: str, updates: Dict[str, Any]):
    """Aktualizuje job w historii."""
    jobs_file = JOBS_HISTORY_FILE
    if not jobs_file.exists():
        return

    try:
        # Wczytaj wszystkie joby
        jobs = _load_jobs_history()

        # Znajdź i zaktualizuj
        for job in jobs:
            if job.get("job_id") == job_id:
                job.update(updates)
                break

        # Zapisz z powrotem
        with open(jobs_file, "w", encoding="utf-8") as f:
            for job in jobs:
                f.write(json.dumps(job, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error(f"Failed to update job in history: {e}")


def _save_adapter_metadata(job: Dict[str, Any], adapter_path: Path) -> None:
    """Zapisuje deterministyczne metadata adaptera po udanym treningu."""
    metadata_file = adapter_path.parent / "metadata.json"
    metadata = {
        "job_id": job.get("job_id"),
        "base_model": job.get("base_model"),
        "dataset_path": job.get("dataset_path"),
        "parameters": job.get("parameters", {}),
        "created_at": job.get("finished_at") or datetime.now().isoformat(),
        "started_at": job.get("started_at"),
        "finished_at": job.get("finished_at"),
        "source": "academy",
    }
    with open(metadata_file, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)


def _is_path_within_base(path: Path, base: Path) -> bool:
    """Sprawdza czy `path` znajduje się w `base` (po resolve)."""
    return academy_storage.is_path_within_base(path=path, base=base)


# ==================== Upload Utilities ====================


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


def _is_safe_file_id(filename: str) -> bool:
    """Dodatkowa walidacja identyfikatora pliku używanego do ścieżek."""
    return academy_storage.is_safe_file_id(filename)


@contextmanager
def _file_lock(file_path: Path, mode: str = "r"):
    """
    Context manager dla atomicznego dostępu do pliku z lockowaniem.

    Używa fcntl na Unix/Linux lub msvcrt na Windows.
    Fallback: brak lockowania jeśli nie ma dostępnych bibliotek.
    """
    with academy_storage.file_lock(file_path=file_path, mode=mode) as handle:
        yield handle


def _load_uploads_metadata() -> List[Dict[str, Any]]:
    """Ładuje metadane uploadów z pliku JSONL."""
    return academy_storage.load_uploads_metadata()


def _get_uploads_metadata_lock_file() -> Path:
    """Zwraca ścieżkę lock-file dla operacji na metadata uploads."""
    return academy_storage.get_uploads_metadata_lock_file()


@contextmanager
def _uploads_metadata_lock():
    """
    Globalny lock dla operacji read/write/delete na metadata uploads.

    Chroni pełny cykl read-modify-write, nie tylko pojedynczy odczyt.
    """
    with academy_storage.uploads_metadata_lock():
        yield


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
    """
    Sprawdza czy model jest trenowalny (wspiera LoRA/QLoRA).

    Returns:
        True jeśli model jest trenowalny
    """
    return academy_models.is_model_trainable(model_id=model_id)


def _get_model_non_trainable_reason(
    model_id: str, provider: Optional[str] = None
) -> Optional[str]:
    """
    Zwraca powód braku trenowalności modelu dla Academy, albo None jeśli trenowalny.

    Academy trenuje adaptery LoRA/QLoRA na modelach HuggingFace/Unsloth.
    Lokalne modele Ollama (GGUF) pozostają inferencyjne.
    """
    return academy_models.get_model_non_trainable_reason(
        model_id=model_id,
        provider=provider,
    )


def _build_model_label(
    model_id: str, provider: str, source: Optional[str] = None
) -> str:
    """Buduje czytelną etykietę modelu dla UI Academy."""
    return academy_models.build_model_label(
        model_id=model_id,
        provider=provider,
        source=source,
    )


def _get_default_trainable_models_catalog() -> List[TrainableModelInfo]:
    """
    Zwraca domyślny katalog modeli trenowalnych.

    To fallback na wypadek braku lokalnych metadanych modeli.
    """
    return academy_models.get_default_trainable_models_catalog()


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
    uploads_count = 0
    uploads_dir = _get_uploads_dir()
    for upload_idx, file_id in enumerate(upload_ids, start=1):
        if not _check_path_traversal(file_id):
            logger.warning(
                "Skipped upload entry due to invalid identifier (idx=%s)",
                upload_idx,
            )
            continue

        file_path = uploads_dir / file_id
        if not file_path.exists():
            logger.warning(
                "Skipped upload entry because file was not found (idx=%s)",
                upload_idx,
            )
            continue

        try:
            uploads_count += _ingest_upload_file(curator, file_path)
        except Exception as e:
            logger.warning(
                "Failed to ingest upload entry (idx=%s, error=%s)",
                upload_idx,
                type(e).__name__,
            )
    return uploads_count


def _ingest_converted_files_for_curate(
    curator: Any,
    req: Request,
    conversion_file_ids: List[str],
) -> int:
    converted_count = 0
    for file_idx, file_id in enumerate(conversion_file_ids, start=1):
        if not _check_path_traversal(file_id):
            logger.warning(
                "Skipped converted file due to invalid identifier (idx=%s)",
                file_idx,
            )
            continue
        try:
            item, file_path = _resolve_existing_user_file(req, file_id=file_id)
            if str(item.get("category") or "") != "converted":
                logger.warning(
                    "Skipped conversion file because category is not converted (idx=%s)",
                    file_idx,
                )
                continue
            converted_count += _ingest_upload_file(curator, file_path)
        except Exception as e:
            logger.warning(
                "Failed to ingest converted file (idx=%s, error=%s)",
                file_idx,
                type(e).__name__,
            )
    return converted_count


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
    """
    Kuracja datasetu ze statystykami (v2: wspiera user-defined scope).

    Zbiera dane z:
    - LessonsStore (successful experiences) - jeśli include_lessons=True
    - Git history (commits) - jeśli include_git=True
    - Task history (opcjonalnie) - jeśli include_task_history=True
    - User uploads - jeśli upload_ids podane

    Returns:
        DatasetResponse ze ścieżką i statystykami
    """
    try:
        _ensure_academy_enabled()
    except AcademyRouteError as e:
        raise _to_http_exception(e) from e

    try:
        conversion_file_ids = _resolve_conversion_file_ids_for_dataset(
            req=req,
            requested_ids=request.conversion_file_ids,
        )
        logger.info(
            "Curating dataset: lessons=%s git=%s task_history=%s uploads=%s converted=%s",
            request.include_lessons,
            request.include_git,
            request.include_task_history,
            len(request.upload_ids or []),
            len(conversion_file_ids),
        )
        curator = _get_dataset_curator()

        # Wyczyść poprzednie przykłady
        curator.clear()
        scope_counts = _collect_scope_counts(curator, request)
        uploads_count = 0
        if request.upload_ids:
            uploads_count = _ingest_uploads_for_curate(curator, request.upload_ids)
        converted_count = 0
        if conversion_file_ids:
            converted_count = _ingest_converted_files_for_curate(
                curator=curator,
                req=req,
                conversion_file_ids=conversion_file_ids,
            )

        # Filtruj niską jakość
        removed = curator.filter_low_quality()

        # Zapisz dataset
        dataset_path = curator.save_dataset(format=request.format)

        # Statystyki
        stats = curator.get_statistics()

        return DatasetResponse(
            success=True,
            dataset_path=str(dataset_path),
            statistics={
                **stats,
                "lessons_collected": scope_counts["lessons"],
                "git_commits_collected": scope_counts["git"],
                "task_history_collected": scope_counts["task_history"],
                "uploads_collected": uploads_count,
                "converted_collected": converted_count,
                "removed_low_quality": removed,
                "quality_profile": request.quality_profile,
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
    """
    Start zadania treningowego.

    Uruchamia trening LoRA/QLoRA w kontenerze Docker z GPU.

    Returns:
        TrainingResponse z job_id i parametrami
    """
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
    """
    Pobiera status i logi zadania treningowego.

    Returns:
        JobStatusResponse ze statusem, logami i ścieżką adaptera
    """
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


def _sse_event(payload: Dict[str, Any]) -> str:
    return academy_training.sse_event(payload)


def _parse_stream_log_line(log_line: str) -> tuple[Optional[str], str]:
    return academy_training.parse_stream_log_line(log_line)


def _extract_metrics_data(
    parser: Any, all_metrics: List[Any], message: str
) -> Optional[Dict[str, Any]]:
    return academy_training.extract_metrics_data(
        parser=parser,
        all_metrics=all_metrics,
        message=message,
    )


def _build_log_event(
    line_no: int,
    message: str,
    timestamp: Optional[str],
    metrics_data: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    return academy_training.build_log_event(
        line_no=line_no,
        message=message,
        timestamp=timestamp,
        metrics_data=metrics_data,
    )


def _periodic_stream_events(
    line_no: int, habitat: Any, job_name: str, parser: Any, all_metrics: List[Any]
) -> tuple[List[Dict[str, Any]], bool]:
    return academy_training.periodic_stream_events(
        line_no=line_no,
        habitat=habitat,
        job_name=job_name,
        parser=parser,
        all_metrics=all_metrics,
        normalize_status_fn=_normalize_job_status,
        terminal_statuses=TERMINAL_JOB_STATUSES,
    )


@router.get(
    "/train/{job_id}/logs/stream",
    responses={
        404: RESP_404_JOB_NOT_FOUND,
        503: RESP_503_ACADEMY_UNAVAILABLE,
    },
)
async def stream_training_logs(job_id: str):
    """
    Stream logów z treningu (SSE - Server-Sent Events).

    Args:
        job_id: ID joba treningowego

    Returns:
        StreamingResponse z logami w formacie SSE
    """
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
    """
    Lista wszystkich jobów treningowych.

    Args:
        limit: Maksymalna liczba jobów do zwrócenia
        status: Filtruj po statusie (queued, running, finished, failed)

    Returns:
        Lista jobów
    """
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
    """
    Lista dostępnych adapterów.

    Skanuje katalog z modelami i zwraca listę dostępnych adapterów LoRA.

    Returns:
        Lista adapterów
    """
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
    """
    Aktywacja adaptera LoRA.

    Hot-swap adaptera bez restartu backendu.

    Returns:
        Status aktywacji
    """
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


async def _persist_uploaded_file(
    file: Any, file_path: Path, max_size_bytes: int
) -> tuple[int, bytes]:
    return await academy_uploads.persist_uploaded_file(
        file=file,
        file_path=file_path,
        max_size_bytes=max_size_bytes,
    )


def _cleanup_uploaded_file(file_path: Path) -> None:
    academy_uploads.cleanup_uploaded_file(file_path, logger=logger)


def _upload_error(filename: str, message: str) -> tuple[None, Dict[str, str]]:
    return academy_uploads.upload_error(filename, message)


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
        cleanup_uploaded_file_fn=_cleanup_uploaded_file,
    )


def _build_upload_info(
    file_id: str,
    filename: str,
    size_bytes: int,
    content_bytes: bytes,
    tag: str,
    description: str,
) -> Dict[str, Any]:
    return academy_uploads.build_upload_info(
        file_id=file_id,
        filename=filename,
        size_bytes=size_bytes,
        content_bytes=content_bytes,
        tag=tag,
        description=description,
        compute_bytes_hash_fn=_compute_bytes_hash,
        estimate_records_from_content_fn=_estimate_records_from_content,
        logger=logger,
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
        cleanup_uploaded_file_fn=_cleanup_uploaded_file,
        logger=logger,
    )


def _build_upload_response(
    uploaded_files: List[Dict[str, Any]], failed_files: List[Dict[str, str]]
) -> Dict[str, Any]:
    return academy_uploads.build_upload_response(uploaded_files, failed_files)


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

    return _build_upload_response(uploaded_files, failed_files)


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


def _sanitize_user_id(user_id: str) -> str:
    return academy_conversion.sanitize_user_id(user_id)


def _resolve_user_id(req: Request) -> str:
    actor = req.headers.get("X-Actor") or req.headers.get("X-User-Id") or "local-user"
    return _sanitize_user_id(actor.strip())


def _get_user_conversion_workspace(user_id: str) -> Dict[str, Path]:
    return academy_conversion.get_user_conversion_workspace(user_id)


def _get_conversion_output_dir() -> Path:
    return academy_conversion.get_conversion_output_dir()


def _get_user_conversion_lock_file(base_dir: Path) -> Path:
    return academy_conversion.get_user_conversion_lock_file(base_dir)


@contextmanager
def _user_conversion_metadata_lock(base_dir: Path):
    with academy_conversion.user_conversion_metadata_lock(base_dir):
        yield


def _load_user_conversion_metadata(metadata_file: Path) -> List[Dict[str, Any]]:
    return academy_conversion.load_user_conversion_metadata(metadata_file)


def _save_user_conversion_metadata(
    metadata_file: Path, items: List[Dict[str, Any]]
) -> None:
    academy_conversion.save_user_conversion_metadata(metadata_file, items)


def _normalize_conversion_item(raw: Dict[str, Any]) -> DatasetConversionFileInfo:
    return academy_conversion.normalize_conversion_item(raw)


def _find_conversion_item(
    items: List[Dict[str, Any]], file_id: str
) -> Dict[str, Any] | None:
    return academy_conversion.find_conversion_item(items, file_id)


def _resolve_workspace_file_path(
    workspace: Dict[str, Path],
    *,
    file_id: str,
    category: str,
) -> Path:
    if category == "source":
        base_dir = workspace["source_dir"]
        base_dir_resolved = base_dir.resolve()
        candidate = (base_dir / file_id).resolve()
        if not candidate.is_relative_to(base_dir_resolved):
            raise AcademyRouteError(status_code=400, detail="Invalid file path")
        return candidate
    elif category == "converted":
        converted_output_dir = _get_conversion_output_dir()
        converted_output_dir_resolved = converted_output_dir.resolve()
        global_candidate = (converted_output_dir / file_id).resolve()
        if global_candidate.is_relative_to(converted_output_dir_resolved):
            if global_candidate.exists():
                return global_candidate
        # Backward-compat fallback for historical files created per-user.
        legacy_dir = workspace["converted_dir"]
        legacy_dir_resolved = legacy_dir.resolve()
        legacy_candidate = (legacy_dir / file_id).resolve()
        if not legacy_candidate.is_relative_to(legacy_dir_resolved):
            raise AcademyRouteError(status_code=400, detail="Invalid file path")
        return legacy_candidate
    else:
        raise AcademyRouteError(status_code=400, detail="Invalid file category")


def _load_conversion_item_from_workspace(
    workspace: Dict[str, Path],
    *,
    file_id: str,
) -> Dict[str, Any]:
    with _user_conversion_metadata_lock(workspace["base_dir"]):
        items = _load_user_conversion_metadata(workspace["metadata_file"])
        item = _find_conversion_item(items, file_id)
    if not item:
        raise AcademyRouteError(status_code=404, detail="File not found")
    return item


def _resolve_existing_user_file(
    req: Request,
    *,
    file_id: str,
) -> tuple[Dict[str, Any], Path]:
    user_id = _resolve_user_id(req)
    workspace = _get_user_conversion_workspace(user_id)
    item = _load_conversion_item_from_workspace(workspace, file_id=file_id)
    file_path = _resolve_workspace_file_path(
        workspace,
        file_id=file_id,
        category=str(item.get("category") or "source"),
    )
    if not file_path.exists():
        raise AcademyRouteError(status_code=404, detail="File not found on disk")
    return item, file_path


def _build_conversion_file_id(*, extension: str | None = None) -> str:
    return academy_conversion.build_conversion_file_id(extension=extension)


def _serialize_records_to_markdown(records: List[Dict[str, str]]) -> str:
    return academy_conversion.serialize_records_to_markdown(records)


def _records_from_text(content: str) -> List[Dict[str, str]]:
    return academy_conversion.records_from_text(content)


def _records_from_json_file(source_path: Path) -> List[Dict[str, str]]:
    return academy_conversion.records_from_json_file(source_path)


def _records_from_jsonl_file(source_path: Path) -> List[Dict[str, str]]:
    return academy_conversion.records_from_jsonl_file(source_path)


def _records_from_csv_file(source_path: Path) -> List[Dict[str, str]]:
    return academy_conversion.records_from_csv_file(source_path)


def _extract_text_from_pdf(source_path: Path) -> str:
    return academy_conversion.extract_text_from_pdf(source_path)


def _extract_text_from_docx(source_path: Path) -> str:
    return academy_conversion.extract_text_from_docx(source_path)


def _convert_with_pandoc(source_path: Path, output_path: Path) -> bool:
    return academy_conversion.convert_with_pandoc(source_path, output_path)


def _markdown_from_json(source_path: Path) -> str:
    return academy_conversion.markdown_from_json(source_path)


def _markdown_from_jsonl(source_path: Path) -> str:
    return academy_conversion.markdown_from_jsonl(source_path)


def _markdown_from_csv(source_path: Path) -> str:
    return academy_conversion.markdown_from_csv(source_path)


def _markdown_from_binary_document(source_path: Path, ext: str) -> str:
    temp_md_path = source_path.with_suffix(source_path.suffix + ".pandoc.md")
    if _convert_with_pandoc(source_path, temp_md_path):
        content = temp_md_path.read_text(encoding="utf-8", errors="ignore")
        temp_md_path.unlink(missing_ok=True)
        return content
    temp_md_path.unlink(missing_ok=True)
    if ext == academy_conversion.EXT_PDF:
        return _extract_text_from_pdf(source_path)
    if ext == academy_conversion.EXT_DOCX:
        return _extract_text_from_docx(source_path)
    raise ValueError(
        "DOC conversion requires Pandoc with system support for legacy .doc files"
    )


def _source_to_markdown(source_path: Path) -> str:
    ext = source_path.suffix.lower()
    if ext in {academy_conversion.EXT_MD, academy_conversion.EXT_TXT}:
        return source_path.read_text(encoding="utf-8", errors="ignore")

    markdown_builders: dict[str, Callable[[Path], str]] = {
        academy_conversion.EXT_JSON: _markdown_from_json,
        academy_conversion.EXT_JSONL: _markdown_from_jsonl,
        academy_conversion.EXT_CSV: _markdown_from_csv,
    }
    builder = markdown_builders.get(ext)
    if builder:
        return builder(source_path)

    if ext in {
        academy_conversion.EXT_DOC,
        academy_conversion.EXT_DOCX,
        academy_conversion.EXT_PDF,
    }:
        return _markdown_from_binary_document(source_path, ext)

    raise ValueError(f"Unsupported source extension: {ext}")


def _source_to_records(source_path: Path) -> List[Dict[str, str]]:
    ext = source_path.suffix.lower()
    record_builders: dict[str, Callable[[Path], List[Dict[str, str]]]] = {
        academy_conversion.EXT_JSON: _records_from_json_file,
        academy_conversion.EXT_JSONL: _records_from_jsonl_file,
        academy_conversion.EXT_CSV: _records_from_csv_file,
    }
    builder = record_builders.get(ext)
    if builder:
        return builder(source_path)
    text = _source_to_markdown(source_path)
    return _records_from_text(text)


def _write_target_markdown(out_file: TextIO, records: List[Dict[str, str]]) -> None:
    academy_conversion.write_target_markdown(out_file, records)


def _write_target_text(out_file: TextIO, records: List[Dict[str, str]]) -> None:
    academy_conversion.write_target_text(out_file, records)


def _write_target_json(out_file: TextIO, records: List[Dict[str, str]]) -> None:
    academy_conversion.write_target_json(out_file, records)


def _write_target_jsonl(out_file: TextIO, records: List[Dict[str, str]]) -> None:
    academy_conversion.write_target_jsonl(out_file, records)


def _write_target_csv(out_file: TextIO, records: List[Dict[str, str]]) -> None:
    academy_conversion.write_target_csv(out_file, records)


def _write_records_as_target(
    records: List[Dict[str, str]],
    target_format: str,
) -> Path:
    return academy_conversion.write_records_as_target(records, target_format)


def _build_conversion_item(
    *,
    file_id: str,
    filename: str,
    path: Path,
    category: str,
    source_file_id: str | None = None,
    target_format: str | None = None,
) -> Dict[str, Any]:
    return academy_conversion.build_conversion_item(
        file_id=file_id,
        filename=filename,
        path=path,
        category=category,
        source_file_id=source_file_id,
        target_format=target_format,
    )


def _get_selected_converted_file_ids(req: Request) -> List[str]:
    user_id = _resolve_user_id(req)
    workspace = _get_user_conversion_workspace(user_id)
    with _user_conversion_metadata_lock(workspace["base_dir"]):
        items = _load_user_conversion_metadata(workspace["metadata_file"])
    selected_ids: List[str] = []
    for item in items:
        if str(item.get("category") or "") != "converted":
            continue
        if not bool(item.get("selected_for_training", False)):
            continue
        file_id = str(item.get("file_id") or "")
        if file_id and _check_path_traversal(file_id):
            selected_ids.append(file_id)
    return selected_ids


def _resolve_conversion_file_ids_for_dataset(
    req: Request,
    requested_ids: List[str] | None = None,
) -> List[str]:
    if requested_ids is not None:
        return requested_ids
    return _get_selected_converted_file_ids(req)


@router.get("/dataset/conversion/files")
async def list_dataset_conversion_files(req: Request) -> DatasetConversionListResponse:
    try:
        _ensure_academy_enabled()
    except AcademyRouteError as e:
        raise _to_http_exception(e) from e

    user_id = _resolve_user_id(req)
    workspace = _get_user_conversion_workspace(user_id)
    with _user_conversion_metadata_lock(workspace["base_dir"]):
        items = _load_user_conversion_metadata(workspace["metadata_file"])

    source_files = [
        _normalize_conversion_item(item)
        for item in items
        if str(item.get("category")) == "source"
    ]
    converted_files = [
        _normalize_conversion_item(item)
        for item in items
        if str(item.get("category")) == "converted"
    ]

    return DatasetConversionListResponse(
        user_id=user_id,
        workspace_dir=str(workspace["base_dir"]),
        source_files=source_files,
        converted_files=converted_files,
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

    uploaded: List[Dict[str, Any]] = []
    failed: List[Dict[str, str]] = []
    with _user_conversion_metadata_lock(workspace["base_dir"]):
        items = _load_user_conversion_metadata(workspace["metadata_file"])
        for file in files:
            filename, filename_error = _validate_upload_filename(
                file,
                SETTINGS,
                allowed_extensions=getattr(
                    SETTINGS,
                    "ACADEMY_ALLOWED_CONVERSION_EXTENSIONS",
                    SETTINGS.ACADEMY_ALLOWED_EXTENSIONS,
                ),
            )
            if filename_error:
                failed.append(filename_error)
                continue
            if not filename:
                continue

            file_id = _build_conversion_file_id(extension=Path(filename).suffix.lower())
            file_path = workspace["source_dir"] / file_id
            persisted, persist_error = await _persist_with_limits(
                file=file,
                file_path=file_path,
                filename=filename,
                settings=SETTINGS,
            )
            if persist_error or not persisted:
                failed.append(
                    persist_error
                    or {"name": filename, "error": "Failed to persist uploaded file"}
                )
                continue

            item = _build_conversion_item(
                file_id=file_id,
                filename=filename,
                path=file_path,
                category="source",
            )
            items.append(item)
            uploaded.append(item)

        _save_user_conversion_metadata(workspace["metadata_file"], items)
    return {
        "success": len(uploaded) > 0,
        "uploaded": len(uploaded),
        "failed": len(failed),
        "files": [_normalize_conversion_item(item).model_dump() for item in uploaded],
        "errors": failed,
        "message": f"Uploaded {len(uploaded)} file(s), failed {len(failed)}",
    }


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

    if not _check_path_traversal(file_id):
        raise HTTPException(status_code=400, detail=f"Invalid file_id: {file_id}")

    user_id = _resolve_user_id(req)
    workspace = _get_user_conversion_workspace(user_id)
    with _user_conversion_metadata_lock(workspace["base_dir"]):
        items = _load_user_conversion_metadata(workspace["metadata_file"])
        source_item = _find_conversion_item(items, file_id)
        if not source_item:
            raise HTTPException(status_code=404, detail="Source file not found")
        if str(source_item.get("category")) != "source":
            raise HTTPException(
                status_code=400, detail="Conversion requires source file"
            )

        try:
            source_path = _resolve_workspace_file_path(
                workspace,
                file_id=file_id,
                category="source",
            )
        except AcademyRouteError as e:
            raise _to_http_exception(e) from e
        if not source_path.exists():
            raise HTTPException(status_code=404, detail="Source file not found on disk")

        target_format = payload.target_format.lower()
        source_stem = Path(str(source_item.get("name") or "dataset")).name
        source_stem = Path(source_stem).stem
        converted_name = f"{source_stem}.{target_format}"

        try:
            records = _source_to_records(source_path)
            if not records:
                raise ValueError("No valid records produced from source file")
            converted_path = _write_records_as_target(
                records,
                target_format,
            )
            converted_file_id = converted_path.name
        except (ValueError, OSError) as exc:
            raise HTTPException(
                status_code=400, detail=f"Conversion failed: {str(exc)}"
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

        converted_item = _build_conversion_item(
            file_id=converted_file_id,
            filename=converted_name,
            path=converted_path,
            category="converted",
            source_file_id=file_id,
            target_format=target_format,
        )
        items.append(converted_item)
        _save_user_conversion_metadata(workspace["metadata_file"], items)

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

    if not _check_path_traversal(file_id):
        raise HTTPException(status_code=400, detail=f"Invalid file_id: {file_id}")

    user_id = _resolve_user_id(req)
    workspace = _get_user_conversion_workspace(user_id)
    with _user_conversion_metadata_lock(workspace["base_dir"]):
        items = _load_user_conversion_metadata(workspace["metadata_file"])
        item = _find_conversion_item(items, file_id)
        if not item:
            raise HTTPException(status_code=404, detail="File not found")
        if str(item.get("category") or "") != "converted":
            raise HTTPException(
                status_code=400,
                detail="Only converted files can be marked for training",
            )
        item["selected_for_training"] = bool(payload.selected_for_training)
        _save_user_conversion_metadata(workspace["metadata_file"], items)
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

    max_chars = 20_000
    async with await anyio.open_file(
        file_path, "r", encoding="utf-8", errors="ignore"
    ) as file_obj:
        preview_plus_one = await file_obj.read(max_chars + 1)
    truncated = len(preview_plus_one) > max_chars
    preview_text = preview_plus_one[:max_chars]

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

    media_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
    return FileResponse(
        path=str(file_path),
        filename=str(item.get("name") or file_path.name),
        media_type=media_type,
    )


def _ingest_uploads_for_preview(
    curator: Any, upload_ids: List[str], warnings: List[str]
) -> int:
    uploads_count = 0
    uploads_dir = _get_uploads_dir()
    for upload_idx, file_id in enumerate(upload_ids, start=1):
        if not _check_path_traversal(file_id):
            warnings.append(f"Invalid file_id (path traversal): {file_id}")
            continue
        file_path = uploads_dir / file_id
        if not file_path.exists():
            warnings.append(f"Upload not found: {file_id}")
            continue
        try:
            uploads_count += _ingest_upload_file(curator, file_path)
        except Exception as e:
            logger.warning(
                "Failed to ingest upload entry during preview (idx=%s, error=%s)",
                upload_idx,
                type(e).__name__,
            )
            warnings.append(f"Failed to ingest {file_id}: {str(e)}")
    return uploads_count


def _ingest_converted_files_for_preview(
    curator: Any,
    req: Request,
    conversion_file_ids: List[str],
    warnings: List[str],
) -> int:
    converted_count = 0
    for file_idx, file_id in enumerate(conversion_file_ids, start=1):
        if not _check_path_traversal(file_id):
            warnings.append(f"Invalid converted file_id (path traversal): {file_id}")
            continue
        try:
            item, file_path = _resolve_existing_user_file(req, file_id=file_id)
            if str(item.get("category") or "") != "converted":
                warnings.append(f"File is not converted: {file_id}")
                continue
            converted_count += _ingest_upload_file(curator, file_path)
        except AcademyRouteError as e:
            warnings.append(f"Converted file unavailable ({file_id}): {e.detail}")
        except HTTPException as e:
            warnings.append(f"Converted file unavailable ({file_id}): {e.detail}")
        except Exception as e:
            logger.warning(
                "Failed to ingest converted file during preview (idx=%s, error=%s)",
                file_idx,
                type(e).__name__,
            )
            warnings.append(f"Failed to ingest converted file {file_id}: {str(e)}")
    return converted_count


def _add_low_examples_warning(
    warnings: List[str], total_examples: int, quality_profile: str
) -> None:
    recommended_min_examples = {
        "strict": 150,
        "balanced": 100,
        "lenient": 50,
    }.get(quality_profile, 100)
    if total_examples >= recommended_min_examples:
        return
    warnings.append(
        f"Low number of examples ({total_examples}). Recommended for profile "
        f"'{quality_profile}': >= {recommended_min_examples}"
    )


def _build_preview_samples(curator: Any) -> List[Dict[str, str]]:
    samples: List[Dict[str, str]] = []
    if not hasattr(curator, "examples") or not curator.examples:
        return samples
    for example in curator.examples[:5]:
        output = example.get("output", "")
        samples.append(
            {
                "instruction": example.get("instruction", ""),
                "input": example.get("input", ""),
                "output": output[:200] + ("..." if len(output) > 200 else ""),
            }
        )
    return samples


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
    """
    Preview datasetu przed curate z wybranym scope.

    Zwraca statystyki i sample bez zapisywania datasetu.

    Args:
        request: DatasetScopeRequest z wybranym scope

    Returns:
        DatasetPreviewResponse ze statystykami i samples
    """
    try:
        _ensure_academy_enabled()
    except AcademyRouteError as e:
        raise _to_http_exception(e) from e

    try:
        conversion_file_ids = _resolve_conversion_file_ids_for_dataset(
            req=req,
            requested_ids=request.conversion_file_ids,
        )
        logger.info(
            "Previewing dataset: lessons=%s git=%s task_history=%s uploads=%s converted=%s",
            request.include_lessons,
            request.include_git,
            request.include_task_history,
            len(request.upload_ids or []),
            len(conversion_file_ids),
        )
        curator = _get_dataset_curator()

        # Wyczyść poprzednie przykłady
        curator.clear()

        by_source = _collect_scope_counts(curator, request)
        warnings: List[str] = []

        # Zbierz z uploadów
        if request.upload_ids:
            by_source["uploads"] = _ingest_uploads_for_preview(
                curator=curator,
                upload_ids=request.upload_ids,
                warnings=warnings,
            )
        if conversion_file_ids:
            by_source["converted"] = _ingest_converted_files_for_preview(
                curator=curator,
                req=req,
                conversion_file_ids=conversion_file_ids,
                warnings=warnings,
            )

        # Filtruj niską jakość. quality_profile steruje progiem ostrzeżeń.
        removed = curator.filter_low_quality()

        # Statystyki
        stats = curator.get_statistics()
        total_examples = stats.get("total_examples", 0)

        _add_low_examples_warning(
            warnings=warnings,
            total_examples=total_examples,
            quality_profile=request.quality_profile,
        )
        samples = _build_preview_samples(curator)

        return DatasetPreviewResponse(
            total_examples=total_examples,
            by_source=by_source,
            removed_low_quality=removed,
            warnings=warnings,
            samples=samples,
        )

    except Exception as e:
        logger.error(f"Failed to preview dataset: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to preview dataset: {str(e)}"
        )


def _append_training_record_if_valid(curator: Any, record: Dict[str, Any]) -> int:
    if not _validate_training_record(record):
        return 0
    curator.examples.append(record)
    return 1


def _ingest_jsonl_upload(curator: Any, file_path: Path) -> int:
    count = 0
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                count += _append_training_record_if_valid(curator, record)
            except Exception as e:
                logger.warning(f"Failed to parse JSONL line: {e}")
    return count


def _ingest_json_upload(curator: Any, file_path: Path) -> int:
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return sum(_append_training_record_if_valid(curator, record) for record in data)
    if isinstance(data, dict):
        return _append_training_record_if_valid(curator, data)
    return 0


def _ingest_text_upload(curator: Any, file_path: Path) -> int:
    count = 0
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    sections = content.split("\n\n")
    for i in range(0, len(sections) - 1, 2):
        instruction = sections[i].strip()
        output = sections[i + 1].strip() if i + 1 < len(sections) else ""
        if not instruction or not output:
            continue
        count += _append_training_record_if_valid(
            curator,
            {"instruction": instruction, "input": "", "output": output},
        )
    return count


def _ingest_csv_upload(curator: Any, file_path: Path) -> int:
    import csv

    count = 0
    with open(file_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            record = {
                "instruction": row.get("instruction", row.get("prompt", "")),
                "input": row.get("input", ""),
                "output": row.get("output", row.get("response", "")),
            }
            count += _append_training_record_if_valid(curator, record)
    return count


def _ingest_upload_file(curator, file_path: Path) -> int:
    """
    Ingestuje plik uploadowany do curator.

    Returns:
        Liczba dodanych rekordów
    """
    ext = file_path.suffix.lower()
    ingest_by_extension = {
        ".jsonl": _ingest_jsonl_upload,
        ".json": _ingest_json_upload,
        ".md": _ingest_text_upload,
        ".txt": _ingest_text_upload,
        ".csv": _ingest_csv_upload,
    }

    try:
        handler = ingest_by_extension.get(ext)
        if not handler:
            return 0
        return handler(curator, file_path)

    except Exception as e:
        logger.error(f"Failed to ingest file {file_path}: {e}")
        raise


def _validate_training_record(record: Dict[str, Any]) -> bool:
    """Waliduje czy rekord treningowy jest poprawny."""
    if not isinstance(record, dict):
        return False

    # Required fields
    instruction = record.get("instruction", "")
    output = record.get("output", "")

    # Min length check
    if len(instruction) < 10 or len(output) < 10:
        return False

    return True


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
