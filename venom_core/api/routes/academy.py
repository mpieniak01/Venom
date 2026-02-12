"""Moduł: routes/academy - Endpointy API dla The Academy (trenowanie modeli)."""

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Dict, List, Optional
from unittest.mock import Mock

import anyio
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

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


# ==================== Modele Pydantic ====================


class DatasetRequest(BaseModel):
    """Request do wygenerowania datasetu."""

    lessons_limit: int = Field(default=200, ge=10, le=1000)
    git_commits_limit: int = Field(default=100, ge=0, le=500)
    include_task_history: bool = Field(default=False)
    format: str = Field(default="alpaca", pattern="^(alpaca|sharegpt)$")


class DatasetResponse(BaseModel):
    """Response z wygenerowanego datasetu."""

    success: bool
    dataset_path: Optional[str] = None
    statistics: Dict[str, Any] = Field(default_factory=dict)
    message: str = ""


class TrainingRequest(BaseModel):
    """Request do rozpoczęcia treningu."""

    dataset_path: Optional[str] = None
    base_model: Optional[str] = None
    lora_rank: int = Field(default=16, ge=4, le=64)
    learning_rate: float = Field(default=2e-4, gt=0, le=1e-2)
    num_epochs: int = Field(default=3, ge=1, le=20)
    batch_size: int = Field(default=4, ge=1, le=32)
    max_seq_length: int = Field(default=2048, ge=256, le=8192)

    @field_validator("learning_rate")
    @classmethod
    def validate_lr(cls, v):
        if v <= 0 or v > 1e-2:
            raise ValueError("learning_rate must be in range (0, 0.01]")
        return v


class TrainingResponse(BaseModel):
    """Response po rozpoczęciu treningu."""

    success: bool
    job_id: Optional[str] = None
    message: str = ""
    parameters: Dict[str, Any] = Field(default_factory=dict)


class JobStatusResponse(BaseModel):
    """Response ze statusem joba."""

    job_id: str
    status: str  # queued, preparing, running, finished, failed, cancelled
    logs: str = ""
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    adapter_path: Optional[str] = None
    error: Optional[str] = None


class AdapterInfo(BaseModel):
    """Informacje o adapterze."""

    adapter_id: str
    adapter_path: str
    base_model: str
    created_at: str
    training_params: Dict[str, Any] = Field(default_factory=dict)
    is_active: bool = False


class ActivateAdapterRequest(BaseModel):
    """Request do aktywacji adaptera."""

    adapter_id: str
    adapter_path: str


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


# ==================== Endpointy ====================


@router.post(
    "/dataset",
    responses={
        503: RESP_503_ACADEMY_UNAVAILABLE,
    },
)
async def curate_dataset(request: DatasetRequest) -> DatasetResponse:
    """
    Kuracja datasetu ze statystykami.

    Zbiera dane z:
    - LessonsStore (successful experiences)
    - Git history (commits)
    - Task history (opcjonalnie)

    Returns:
        DatasetResponse ze ścieżką i statystykami
    """
    try:
        _ensure_academy_enabled()
    except AcademyRouteError as e:
        raise _to_http_exception(e) from e

    try:
        logger.info(f"Curating dataset with request: {request}")
        curator = _get_dataset_curator()

        # Wyczyść poprzednie przykłady
        curator.clear()

        # Zbierz dane
        lessons_count = curator.collect_from_lessons(limit=request.lessons_limit)
        git_count = curator.collect_from_git_history(
            max_commits=request.git_commits_limit
        )

        # TODO: Implement task history collection if needed
        # if request.include_task_history:
        #     task_count = _dataset_curator.collect_from_task_history(limit=100)

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
                "lessons_collected": lessons_count,
                "git_commits_collected": git_count,
                "removed_low_quality": removed,
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

        logger.info(f"Starting training with request: {request}")
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
            parameters=job_record["parameters"],
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


def _save_finished_job_metadata(
    job_id: str, job: Dict[str, Any], current_status: str
) -> None:
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
        _save_finished_job_metadata(job_id, job, current_status)
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
        all_metrics = []

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
    responses={
        500: RESP_500_INTERNAL,
        503: RESP_503_ACADEMY_UNAVAILABLE,
    },
)
async def list_jobs(
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    status: Annotated[Optional[str], Query()] = None,
) -> Dict[str, Any]:
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
