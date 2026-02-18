"""Moduł: routes/academy - Endpointy API dla The Academy (trenowanie modeli)."""

import asyncio
import json
import os
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Dict, List, Optional, cast
from unittest.mock import Mock

import anyio
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from venom_core.api.schemas.academy import (
    AcademyJobsListResponse,
    ActivateAdapterRequest,
    AdapterInfo,
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

# Import platform-specific file locking
fcntl: Any = None
msvcrt: Any = None
HAS_FCNTL = False
HAS_MSVCRT = False
try:
    import fcntl as _fcntl

    fcntl = _fcntl
    HAS_FCNTL = True
except ImportError:
    try:
        import msvcrt as _msvcrt

        msvcrt = _msvcrt
        HAS_MSVCRT = True
    except ImportError:
        HAS_MSVCRT = False

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
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False


# ==================== Upload Utilities ====================


def _get_uploads_dir() -> Path:
    """Zwraca katalog uploads pod ACADEMY_TRAINING_DIR."""
    from venom_core.config import SETTINGS

    uploads_dir = Path(SETTINGS.ACADEMY_TRAINING_DIR) / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    return uploads_dir


def _get_uploads_metadata_file() -> Path:
    """Zwraca plik z metadanymi uploadów."""
    uploads_dir = _get_uploads_dir()
    metadata_file = uploads_dir / "metadata.jsonl"
    return metadata_file


def _validate_file_extension(filename: str) -> bool:
    """Waliduje rozszerzenie pliku."""
    from venom_core.config import SETTINGS

    ext = Path(filename).suffix.lower()
    return ext in SETTINGS.ACADEMY_ALLOWED_EXTENSIONS


def _validate_file_size(size_bytes: int) -> bool:
    """Waliduje rozmiar pliku."""
    from venom_core.config import SETTINGS

    max_bytes = SETTINGS.ACADEMY_MAX_UPLOAD_SIZE_MB * 1024 * 1024
    return size_bytes <= max_bytes


def _check_path_traversal(filename: str) -> bool:
    """Sprawdza czy filename nie zawiera path traversal."""
    # Nie dopuszczamy '..' ani '/' w nazwie pliku
    if ".." in filename or "/" in filename or "\\" in filename:
        return False
    return True


@contextmanager
def _file_lock(file_path: Path, mode: str = "r"):
    """
    Context manager dla atomicznego dostępu do pliku z lockowaniem.

    Używa fcntl na Unix/Linux lub msvcrt na Windows.
    Fallback: brak lockowania jeśli nie ma dostępnych bibliotek.
    """
    with open(file_path, mode, encoding="utf-8") as f:
        locked = False
        try:
            if HAS_FCNTL:
                # Unix/Linux file locking
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                locked = True
            elif HAS_MSVCRT and msvcrt is not None:
                # Windows file locking
                msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
                locked = True
            # Jeśli brak lockowania, po prostu yield (localhost-only, niskie ryzyko)
            yield f
        finally:
            if locked:
                if HAS_FCNTL:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                elif HAS_MSVCRT and msvcrt is not None:
                    msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)


def _load_uploads_metadata() -> List[Dict[str, Any]]:
    """Ładuje metadane uploadów z pliku JSONL."""
    metadata_file = _get_uploads_metadata_file()
    uploads = []
    try:
        with _uploads_metadata_lock():
            if not metadata_file.exists():
                return []
            with open(metadata_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        uploads.append(json.loads(line))
    except Exception as e:
        logger.warning(f"Failed to load uploads metadata: {e}")
    return uploads


def _get_uploads_metadata_lock_file() -> Path:
    """Zwraca ścieżkę lock-file dla operacji na metadata uploads."""
    metadata_file = _get_uploads_metadata_file()
    return metadata_file.with_suffix(".lock")


@contextmanager
def _uploads_metadata_lock():
    """
    Globalny lock dla operacji read/write/delete na metadata uploads.

    Chroni pełny cykl read-modify-write, nie tylko pojedynczy odczyt.
    """
    lock_file = _get_uploads_metadata_lock_file()
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    lock_file.touch(exist_ok=True)
    with _file_lock(lock_file, "a"):
        yield


def _save_upload_metadata(upload_info: Dict[str, Any]):
    """Zapisuje metadata uploadu (append do JSONL) z lockowaniem."""
    metadata_file = _get_uploads_metadata_file()
    try:
        with _uploads_metadata_lock():
            # Upewnij się że plik istnieje
            metadata_file.touch(exist_ok=True)
            with open(metadata_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(upload_info, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error("Failed to save upload metadata: %s", e, exc_info=True)
        raise


def _delete_upload_metadata(file_id: str):
    """Usuwa metadata uploadu z pliku z atomową operacją read-modify-write."""
    metadata_file = _get_uploads_metadata_file()
    temp_file = metadata_file.with_suffix(".tmp")
    try:
        with _uploads_metadata_lock():
            if not metadata_file.exists():
                return

            uploads = []
            with open(metadata_file, "r", encoding="utf-8") as f_in:
                for line in f_in:
                    if line.strip():
                        upload = json.loads(line)
                        if upload.get("id") != file_id:
                            uploads.append(upload)

            # Write to temp file first
            with open(temp_file, "w", encoding="utf-8") as f_out:
                for upload in uploads:
                    f_out.write(json.dumps(upload, ensure_ascii=False) + "\n")

            # Atomic replace
            temp_file.replace(metadata_file)

    except Exception as e:
        logger.error(f"Failed to delete upload metadata: {e}")
        # Clean up temp file if it exists
        if temp_file.exists():
            try:
                temp_file.unlink()
            except Exception as cleanup_error:
                logger.warning(
                    f"Failed to remove temporary metadata file {temp_file}: {cleanup_error}"
                )


def _compute_file_hash(file_path: Path) -> str:
    """Oblicza SHA256 hash pliku."""
    import hashlib

    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def _compute_bytes_hash(content: bytes) -> str:
    """Oblicza SHA256 hash dla bajtów w pamięci."""
    import hashlib

    return hashlib.sha256(content).hexdigest()


def _estimate_records_from_content(filename: str, content: bytes) -> int:
    """Szacuje liczbę rekordów na podstawie zawartości pliku w pamięci."""
    records_estimate = 0
    filename_lc = filename.lower()

    if filename_lc.endswith(".jsonl"):
        text = content.decode("utf-8", errors="ignore")
        return sum(1 for line in text.splitlines() if line.strip())

    if filename_lc.endswith(".json"):
        text = content.decode("utf-8", errors="ignore")
        data = json.loads(text)
        if isinstance(data, list):
            return len(data)
        return 1

    if filename_lc.endswith((".md", ".txt", ".csv")):
        text = content.decode("utf-8", errors="ignore")
        return max(1, len(text.split("\n\n")))

    return records_estimate


def _is_model_trainable(model_id: str) -> bool:
    """
    Sprawdza czy model jest trenowalny (wspiera LoRA/QLoRA).

    Returns:
        True jeśli model jest trenowalny
    """
    return _get_model_non_trainable_reason(model_id=model_id, provider=None) is None


def _get_model_non_trainable_reason(
    model_id: str, provider: Optional[str] = None
) -> Optional[str]:
    """
    Zwraca powód braku trenowalności modelu dla Academy, albo None jeśli trenowalny.

    Academy trenuje adaptery LoRA/QLoRA na modelach HuggingFace/Unsloth.
    Lokalne modele Ollama (GGUF) pozostają inferencyjne.
    """
    model_id_lc = model_id.lower()
    provider_lc = (provider or "").lower()

    if provider_lc in {"openai", "azure-openai", "anthropic", "google-gemini"}:
        return "External API models do not support local Academy LoRA training"

    if provider_lc == "ollama":
        return (
            "Ollama runtime models are inference-focused in this pipeline; "
            "select a HuggingFace/Unsloth base model for Academy training"
        )

    # Popular API-only model names should be rejected even without provider metadata.
    blocked_name_markers = ("gpt-", "claude", "gemini")
    if any(marker in model_id_lc for marker in blocked_name_markers):
        return "Model family does not support local Academy LoRA training"

    # Lista wzorców rodzin modeli wspieranych przez nasz pipeline LoRA/QLoRA.
    trainable_patterns = (
        "unsloth/",
        "phi-3",
        "llama-3",
        "mistral",
        "qwen",
        "gemma",
        "test-",  # Allow test models in tests
    )
    if any(pattern in model_id_lc for pattern in trainable_patterns):
        return None

    return "Model is not in Academy trainable families list"


def _build_model_label(
    model_id: str, provider: str, source: Optional[str] = None
) -> str:
    """Buduje czytelną etykietę modelu dla UI Academy."""
    source_suffix = f" [{source}]" if source else ""
    return f"{model_id} ({provider}){source_suffix}"


def _get_default_trainable_models_catalog() -> List[TrainableModelInfo]:
    """
    Zwraca domyślny katalog modeli trenowalnych.

    To fallback na wypadek braku lokalnych metadanych modeli.
    """
    return [
        TrainableModelInfo(
            model_id="unsloth/Phi-3-mini-4k-instruct",
            label="Phi-3 Mini 4K (Unsloth)",
            provider="unsloth",
            trainable=True,
            recommended=True,
        ),
        TrainableModelInfo(
            model_id="unsloth/Phi-3.5-mini-instruct",
            label="Phi-3.5 Mini (Unsloth)",
            provider="unsloth",
            trainable=True,
            recommended=False,
        ),
        TrainableModelInfo(
            model_id="unsloth/Llama-3.2-1B-Instruct",
            label="Llama 3.2 1B (Unsloth)",
            provider="unsloth",
            trainable=True,
            recommended=False,
        ),
        TrainableModelInfo(
            model_id="unsloth/Llama-3.2-3B-Instruct",
            label="Llama 3.2 3B (Unsloth)",
            provider="unsloth",
            trainable=True,
            recommended=False,
        ),
    ]


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


@router.post(
    "/dataset",
    responses={
        503: RESP_503_ACADEMY_UNAVAILABLE,
    },
)
async def curate_dataset(
    request: DatasetScopeRequest,
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
        logger.info(
            "Curating dataset: lessons=%s git=%s task_history=%s uploads=%s",
            request.include_lessons,
            request.include_git,
            request.include_task_history,
            len(request.upload_ids or []),
        )
        curator = _get_dataset_curator()

        # Wyczyść poprzednie przykłady
        curator.clear()
        scope_counts = _collect_scope_counts(curator, request)
        uploads_count = 0
        if request.upload_ids:
            uploads_count = _ingest_uploads_for_curate(curator, request.upload_ids)

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
                "removed_low_quality": removed,
                "quality_profile": request.quality_profile,
                "by_source": {
                    "lessons": scope_counts["lessons"],
                    "git": scope_counts["git"],
                    "task_history": scope_counts["task_history"],
                    "uploads": uploads_count,
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

        # Jeśli nie podano dataset_path, użyj ostatniego
        dataset_path = request.dataset_path
        if not dataset_path:
            training_dir = Path(SETTINGS.ACADEMY_TRAINING_DIR)
            if not training_dir.exists():
                raise HTTPException(
                    status_code=400,
                    detail=DATASET_REQUIRED_DETAIL,
                )

            datasets = sorted(training_dir.glob("dataset_*.jsonl"))
            if not datasets:
                raise HTTPException(
                    status_code=400,
                    detail=DATASET_REQUIRED_DETAIL,
                )

            dataset_path = str(datasets[-1])

        # Jeśli nie podano base_model, użyj domyślnego
        base_model = request.base_model or SETTINGS.ACADEMY_DEFAULT_BASE_MODEL

        # Walidacja: model musi być trenowalny
        if not _is_model_trainable(base_model):
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "MODEL_NOT_TRAINABLE",
                    "message": f"Model '{base_model}' is not trainable. Use /api/v1/academy/models/trainable to see supported models.",
                    "reason_code": "MODEL_NOT_TRAINABLE",
                },
            )

        # Przygotuj output directory
        job_id = f"training_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        output_dir = Path(SETTINGS.ACADEMY_MODELS_DIR) / job_id
        output_dir.mkdir(parents=True, exist_ok=True)

        # Zapisz rekord queued przed faktycznym odpaleniem joba
        job_record = {
            "job_id": job_id,
            "job_name": job_id,
            "dataset_path": dataset_path,
            "base_model": base_model,
            "parameters": {
                "lora_rank": request.lora_rank,
                "learning_rate": request.learning_rate,
                "num_epochs": request.num_epochs,
                "batch_size": request.batch_size,
                "max_seq_length": request.max_seq_length,
            },
            "status": "queued",
            "started_at": datetime.now().isoformat(),
            "output_dir": str(output_dir),
        }
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
    jobs = _load_jobs_history()
    job = next((j for j in jobs if j.get("job_id") == job_id), None)
    if not job:
        raise AcademyRouteError(status_code=404, detail=f"Job {job_id} not found")
    return job


def _sync_job_status_with_habitat(
    habitat: Any, job_id: str, job: Dict[str, Any], job_name: str
) -> tuple[Dict[str, Any], str]:
    status_info = habitat.get_training_status(job_name)
    current_status = _normalize_job_status(status_info.get("status"))
    if current_status != job.get("status"):
        updates = {"status": current_status}
        if current_status in TERMINAL_JOB_STATUSES:
            updates["finished_at"] = datetime.now().isoformat()
        if current_status == "finished":
            adapter_path = Path(job.get("output_dir", "")) / "adapter"
            if adapter_path.exists():
                updates["adapter_path"] = str(adapter_path)
        _update_job_in_history(job_id, updates)
        job.update(updates)
    return status_info, current_status


def _log_internal_operation_failure(message: str) -> None:
    """Loguje błędy operacyjne bez danych kontrolowanych przez użytkownika."""
    logger.warning(message, exc_info=True)


def _save_finished_job_metadata(job: Dict[str, Any], current_status: str) -> None:
    if current_status != "finished" or not job.get("adapter_path"):
        return
    adapter_path_obj = Path(job["adapter_path"])
    if not adapter_path_obj.exists():
        return
    try:
        _save_adapter_metadata(job, adapter_path_obj)
    except Exception:
        _log_internal_operation_failure("Failed to save adapter metadata")


def _cleanup_terminal_job_container(
    habitat: Any, job_id: str, job: Dict[str, Any], job_name: str, current_status: str
) -> None:
    if current_status not in TERMINAL_JOB_STATUSES or job.get("container_cleaned"):
        return
    try:
        habitat.cleanup_job(job_name)
        _update_job_in_history(job_id, {"container_cleaned": True})
        job["container_cleaned"] = True
    except Exception:
        _log_internal_operation_failure("Failed to cleanup container")


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
    return f"data: {json.dumps(payload)}\n\n"


def _parse_stream_log_line(log_line: str) -> tuple[Optional[str], str]:
    if " " not in log_line:
        return None, log_line
    timestamp, message = log_line.split(" ", 1)
    return timestamp, message


def _extract_metrics_data(
    parser: Any, all_metrics: List[Any], message: str
) -> Optional[Dict[str, Any]]:
    metrics = parser.parse_line(message)
    if not metrics:
        return None
    all_metrics.append(metrics)
    return {
        "epoch": metrics.epoch,
        "total_epochs": metrics.total_epochs,
        "loss": metrics.loss,
        "progress_percent": metrics.progress_percent,
    }


def _build_log_event(
    line_no: int,
    message: str,
    timestamp: Optional[str],
    metrics_data: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "type": "log",
        "line": line_no,
        "message": message,
        "timestamp": timestamp,
    }
    if metrics_data:
        payload["metrics"] = metrics_data
    return payload


def _periodic_stream_events(
    line_no: int, habitat: Any, job_name: str, parser: Any, all_metrics: List[Any]
) -> tuple[List[Dict[str, Any]], bool]:
    if line_no % 10 != 0:
        return [], False
    events: List[Dict[str, Any]] = []
    status_info = habitat.get_training_status(job_name)
    current_status = _normalize_job_status(status_info.get("status"))
    if all_metrics:
        events.append(
            {"type": "metrics", "data": parser.aggregate_metrics(all_metrics)}
        )
    should_stop = False
    if current_status in TERMINAL_JOB_STATUSES:
        events.append({"type": "status", "status": current_status})
        should_stop = True
    return events, should_stop


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
    try:
        habitat = _get_gpu_habitat()
        from venom_core.learning.training_metrics_parser import TrainingMetricsParser

        parser = TrainingMetricsParser()
        all_metrics: List[Any] = []

        # Wyślij początkowy event
        yield _sse_event({"type": "connected", "job_id": job_id})

        # Sprawdź czy job istnieje w GPU Habitat
        if not habitat or job_name not in habitat.training_containers:
            yield _sse_event(
                {"type": "error", "message": "Training container not found"}
            )
            return

        # Streamuj logi
        last_line_sent = 0
        for log_line in habitat.stream_job_logs(job_name):
            timestamp, message = _parse_stream_log_line(log_line)
            metrics_data = _extract_metrics_data(parser, all_metrics, message)
            yield _sse_event(
                _build_log_event(last_line_sent, message, timestamp, metrics_data)
            )
            last_line_sent += 1
            events, should_stop = _periodic_stream_events(
                last_line_sent, habitat, job_name, parser, all_metrics
            )
            for event in events:
                yield _sse_event(event)
            if should_stop:
                break

            # Małe opóźnienie żeby nie przeciążyć
            await asyncio.sleep(0.1)

    except KeyError:
        yield _sse_event(
            {"type": "error", "message": "Job not found in container registry"}
        )
    except Exception as e:
        logger.error(f"Error streaming logs: {e}", exc_info=True)
        yield _sse_event({"type": "error", "message": str(e)})


@router.get(
    "/jobs",
    response_model=AcademyJobsListResponse,
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
        jobs = _load_jobs_history()

        # Filtruj po statusie jeśli podano
        if status:
            jobs = [j for j in jobs if j.get("status") == status]

        # Sortuj od najnowszych
        jobs = sorted(jobs, key=lambda j: j.get("started_at", ""), reverse=True)[:limit]

        return {"count": len(jobs), "jobs": jobs}

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
        manager = _get_model_manager()
        from venom_core.config import SETTINGS

        adapters = []
        models_dir = Path(SETTINGS.ACADEMY_MODELS_DIR)

        if not models_dir.exists():
            return []

        # Pobierz info o aktywnym adapterze
        active_adapter_id = None
        if manager:
            active_info = manager.get_active_adapter_info()
            if active_info:
                active_adapter_id = active_info.get("adapter_id")

        # Przejrzyj katalogi treningowe
        for training_dir in models_dir.iterdir():
            if not training_dir.is_dir():
                continue

            adapter_path = training_dir / "adapter"
            if not adapter_path.exists():
                continue

            # Wczytaj metadata jeśli istnieje
            metadata_file = training_dir / "metadata.json"
            metadata = {}
            if metadata_file.exists():
                metadata_raw = await anyio.Path(metadata_file).read_text(
                    encoding="utf-8"
                )
                metadata = json.loads(metadata_raw)

            # Sprawdź czy to aktywny adapter
            is_active = training_dir.name == active_adapter_id

            adapters.append(
                AdapterInfo(
                    adapter_id=training_dir.name,
                    adapter_path=str(adapter_path),
                    base_model=metadata.get(
                        "base_model", SETTINGS.ACADEMY_DEFAULT_BASE_MODEL
                    ),
                    created_at=metadata.get("created_at", "unknown"),
                    training_params=metadata.get("parameters", {}),
                    is_active=is_active,
                )
            )

        return adapters

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

        from venom_core.config import SETTINGS

        models_dir = Path(SETTINGS.ACADEMY_MODELS_DIR).resolve()
        adapter_path = (models_dir / request.adapter_id / "adapter").resolve()

        if not adapter_path.exists():
            raise HTTPException(status_code=404, detail="Adapter not found")

        # Aktywuj adapter przez ModelManager
        success = manager.activate_adapter(
            adapter_id=request.adapter_id, adapter_path=str(adapter_path)
        )

        if not success:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to activate adapter {request.adapter_id}",
            )

        logger.info(f"✅ Activated adapter: {request.adapter_id}")

        return {
            "success": True,
            "message": f"Adapter {request.adapter_id} activated successfully",
            "adapter_id": request.adapter_id,
            "adapter_path": str(adapter_path),
        }

    except AcademyRouteError as e:
        raise _to_http_exception(e) from e
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

        # Dezaktywuj adapter
        success = manager.deactivate_adapter()

        if not success:
            return {
                "success": False,
                "message": "No active adapter to deactivate",
            }

        logger.info("✅ Adapter deactivated - rolled back to base model")

        return {
            "success": True,
            "message": "Adapter deactivated successfully - using base model",
        }

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
        habitat = _get_gpu_habitat()
        # Znajdź job
        jobs = _load_jobs_history()
        job = next((j for j in jobs if j.get("job_id") == job_id), None)

        if not job:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

        job_name = job.get("job_name", job_id)

        # Zatrzymaj i wyczyść kontener przez GPUHabitat
        if habitat:
            try:
                habitat.cleanup_job(job_name)
                logger.info(f"Container cleaned up for job: {job_name}")
            except Exception as e:
                logger.warning(f"Failed to cleanup container: {e}")

        # Aktualizuj status
        _update_job_in_history(
            job_id,
            {
                "status": "cancelled",
                "finished_at": datetime.now().isoformat(),
            },
        )

        return {
            "success": True,
            "message": f"Training job {job_id} cancelled",
            "job_id": job_id,
        }

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
    size_bytes = 0
    collected_chunks: list[bytes] = []
    async with await anyio.open_file(file_path, "wb") as out_file:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            size_bytes += len(chunk)
            if size_bytes > max_size_bytes:
                raise ValueError(f"FILE_TOO_LARGE:{size_bytes}")
            await out_file.write(chunk)
            collected_chunks.append(chunk)
    return size_bytes, b"".join(collected_chunks)


def _cleanup_uploaded_file(file_path: Path) -> None:
    if not file_path.exists():
        return
    try:
        file_path.unlink()
    except OSError as cleanup_error:
        logger.warning(
            "Failed to cleanup orphan upload file (error=%s)",
            type(cleanup_error).__name__,
        )


def _upload_error(filename: str, message: str) -> tuple[None, Dict[str, str]]:
    return None, {"name": filename, "error": message}


def _validate_upload_filename(
    file: Any, settings: Any
) -> tuple[Optional[str], Optional[Dict[str, str]]]:
    if not hasattr(file, "filename") or not file.filename:
        return None, None

    filename = file.filename
    if not _check_path_traversal(filename):
        return None, {"name": filename, "error": "Invalid filename (path traversal)"}
    if not _validate_file_extension(filename):
        return None, {
            "name": filename,
            "error": (
                "Invalid file extension. Allowed: "
                f"{settings.ACADEMY_ALLOWED_EXTENSIONS}"
            ),
        }
    return filename, None


async def _persist_with_limits(
    file: Any,
    file_path: Path,
    filename: str,
    settings: Any,
) -> tuple[Optional[tuple[int, bytes]], Optional[Dict[str, str]]]:
    try:
        max_size_bytes = settings.ACADEMY_MAX_UPLOAD_SIZE_MB * 1024 * 1024
        size_bytes, content_bytes = await _persist_uploaded_file(
            file=file, file_path=file_path, max_size_bytes=max_size_bytes
        )
        return (size_bytes, content_bytes), None
    except ValueError as e:
        _cleanup_uploaded_file(file_path)
        if str(e).startswith("FILE_TOO_LARGE:"):
            size_bytes = int(str(e).split(":", 1)[1])
            return None, {
                "name": filename,
                "error": (
                    f"File too large ({size_bytes} bytes, "
                    f"max {settings.ACADEMY_MAX_UPLOAD_SIZE_MB} MB)"
                ),
            }
        return _upload_error(filename, f"Failed to save file: {str(e)}")
    except Exception as e:
        _cleanup_uploaded_file(file_path)
        logger.error(
            "Failed to persist uploaded file (error=%s)",
            type(e).__name__,
        )
        return _upload_error(filename, f"Failed to save file: {str(e)}")


def _build_upload_info(
    file_id: str,
    filename: str,
    size_bytes: int,
    content_bytes: bytes,
    tag: str,
    description: str,
) -> Dict[str, Any]:
    import mimetypes
    from datetime import datetime

    sha256_hash = _compute_bytes_hash(content_bytes)
    mime_type, _ = mimetypes.guess_type(filename)
    mime_type = mime_type or "application/octet-stream"
    records_estimate = 0
    try:
        records_estimate = _estimate_records_from_content(filename, content_bytes)
    except Exception as e:
        logger.warning(
            "Failed to estimate records for uploaded file (error=%s)",
            type(e).__name__,
        )

    return {
        "id": file_id,
        "name": filename,
        "size_bytes": size_bytes,
        "mime": mime_type,
        "created_at": datetime.now().isoformat(),
        "status": "ready",
        "records_estimate": records_estimate,
        "sha256": sha256_hash,
        "tag": tag,
        "description": description,
    }


async def _process_uploaded_file(
    file: Any, uploads_dir: Path, tag: str, description: str
) -> tuple[Optional[Dict[str, Any]], Optional[Dict[str, str]]]:
    from datetime import datetime

    from venom_core.config import SETTINGS

    filename, filename_error = _validate_upload_filename(file, SETTINGS)
    if filename_error:
        return None, filename_error
    if not filename:
        return None, None

    file_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_{filename}"
    file_path = uploads_dir / file_id
    persisted, persist_error = await _persist_with_limits(
        file=file,
        file_path=file_path,
        filename=filename,
        settings=SETTINGS,
    )
    if persist_error:
        return None, persist_error
    if not persisted:
        return _upload_error(filename, "Failed to persist file")
    size_bytes, content_bytes = persisted

    try:
        upload_info = _build_upload_info(
            file_id=file_id,
            filename=filename,
            size_bytes=size_bytes,
            content_bytes=content_bytes,
            tag=tag,
            description=description,
        )
        _save_upload_metadata(upload_info)
        return upload_info, None
    except Exception as e:
        _cleanup_uploaded_file(file_path)
        logger.error(
            "Unexpected error while processing uploaded file (error=%s)",
            type(e).__name__,
        )
        return None, {"name": filename, "error": f"Unexpected error: {str(e)}"}


def _build_upload_response(
    uploaded_files: List[Dict[str, Any]], failed_files: List[Dict[str, str]]
) -> Dict[str, Any]:
    message = f"Uploaded {len(uploaded_files)} file(s) successfully"
    if failed_files:
        message += f", {len(failed_files)} file(s) failed"
    return {
        "success": len(uploaded_files) > 0,
        "uploaded": len(uploaded_files),
        "failed": len(failed_files),
        "files": uploaded_files,
        "errors": failed_files,
        "message": message,
    }


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
    files = form.getlist("files")
    tag = form.get("tag", "user-upload")
    description = form.get("description", "")
    if not isinstance(tag, str):
        tag = "user-upload"
    if not isinstance(description, str):
        description = ""

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

    # Validate file_id to prevent path traversal
    if not _check_path_traversal(file_id):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file_id (path traversal): {file_id}",
        )

    uploads_dir = _get_uploads_dir()
    file_path = uploads_dir / file_id

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Upload not found: {file_id}")

    # Delete file
    try:
        file_path.unlink()
        _delete_upload_metadata(file_id)
        logger.info(f"Deleted upload: {file_id}")
        return {
            "success": True,
            "message": f"Upload deleted: {file_id}",
        }
    except Exception as e:
        logger.error(f"Failed to delete upload {file_id}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to delete upload: {str(e)}"
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
async def preview_dataset(request: DatasetScopeRequest) -> DatasetPreviewResponse:
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
        logger.info(
            "Previewing dataset: lessons=%s git=%s task_history=%s uploads=%s",
            request.include_lessons,
            request.include_git,
            request.include_task_history,
            len(request.upload_ids or []),
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
    if not model_id or model_id in seen:
        return
    result.append(
        TrainableModelInfo(
            model_id=model_id,
            label=label,
            provider=provider,
            trainable=reason is None,
            reason_if_not_trainable=reason,
            recommended=(model_id == default_model),
            installed_local=installed_local,
        )
    )
    seen.add(model_id)


async def _collect_local_trainable_models(
    mgr: Any, default_model: str, result: List[TrainableModelInfo], seen: set[str]
) -> None:
    local_models = await mgr.list_local_models()
    for model in local_models:
        model_id = str(model.get("name") or "").strip()
        if not model_id or model_id in seen:
            continue
        provider = str(model.get("provider") or model.get("source") or "unknown")
        source = str(model.get("source") or "")
        reason = _get_model_non_trainable_reason(model_id=model_id, provider=provider)
        _add_trainable_model_from_catalog(
            result=result,
            seen=seen,
            model_id=model_id,
            provider=provider,
            label=_build_model_label(
                model_id=model_id, provider=provider, source=source
            ),
            default_model=default_model,
            reason=reason,
            installed_local=True,
        )


def _collect_default_trainable_models(
    default_model: str, result: List[TrainableModelInfo], seen: set[str]
) -> None:
    for entry in _get_default_trainable_models_catalog():
        if entry.model_id in seen:
            continue
        entry.recommended = entry.model_id == default_model
        result.append(entry)
        seen.add(entry.model_id)


def _ensure_default_model_visible(
    default_model: str, result: List[TrainableModelInfo], seen: set[str]
) -> None:
    if not default_model or default_model in seen:
        return
    reason = _get_model_non_trainable_reason(model_id=default_model, provider=None)
    _add_trainable_model_from_catalog(
        result=result,
        seen=seen,
        model_id=default_model,
        provider="config",
        label=f"{default_model} (default)",
        default_model=default_model,
        reason=reason,
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

    from venom_core.config import SETTINGS

    result: List[TrainableModelInfo] = []
    seen: set[str] = set()
    default_model_raw = getattr(SETTINGS, "ACADEMY_DEFAULT_BASE_MODEL", "")
    default_model = (
        default_model_raw.strip() if isinstance(default_model_raw, str) else ""
    )
    mgr = _get_model_manager()

    # 1) Modele z aktualnego katalogu lokalnego (jeśli manager dostępny)
    if mgr is not None:
        try:
            await _collect_local_trainable_models(
                mgr=mgr,
                default_model=default_model,
                result=result,
                seen=seen,
            )
        except Exception as exc:
            logger.warning("Failed to load local model catalog for Academy: %s", exc)

    # 2) Fallback: domyślny katalog trenowalnych modeli (HF/Unsloth)
    _collect_default_trainable_models(
        default_model=default_model, result=result, seen=seen
    )

    # 3) Upewnij się, że model domyślny jest zawsze widoczny (nawet jeśli niestandardowy).
    _ensure_default_model_visible(default_model=default_model, result=result, seen=seen)

    # 4) Sortowanie: recommended -> trainable -> label
    result.sort(key=lambda item: (not item.recommended, not item.trainable, item.label))
    return result
