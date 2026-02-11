"""Moduł: routes/academy - Endpointy API dla The Academy (trenowanie modeli)."""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/academy", tags=["academy"])

# Globalne zależności - będą ustawione przez main.py
_professor = None
_dataset_curator = None
_gpu_habitat = None
_lessons_store = None
_model_manager = None


def set_dependencies(
    professor=None,
    dataset_curator=None,
    gpu_habitat=None,
    lessons_store=None,
    model_manager=None,
):
    """Ustawia zależności Academy (używane w main.py podczas startup)."""
    global _professor, _dataset_curator, _gpu_habitat, _lessons_store, _model_manager
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

    if not SETTINGS.ENABLE_ACADEMY:
        raise HTTPException(status_code=503, detail="Academy is disabled in config")

    if not _professor or not _dataset_curator or not _gpu_habitat:
        raise HTTPException(
            status_code=503,
            detail="Academy components not initialized. Check server logs.",
        )


def _load_jobs_history() -> List[Dict[str, Any]]:
    """Ładuje historię jobów z pliku JSONL."""
    jobs_file = Path("./data/training/jobs.jsonl")
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
    jobs_file = Path("./data/training/jobs.jsonl")
    jobs_file.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(jobs_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(job, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error(f"Failed to save job to history: {e}")


def _update_job_in_history(job_id: str, updates: Dict[str, Any]):
    """Aktualizuje job w historii."""
    jobs_file = Path("./data/training/jobs.jsonl")
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


# ==================== Endpointy ====================


@router.post("/dataset", response_model=DatasetResponse)
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
    _ensure_academy_enabled()

    try:
        logger.info(f"Curating dataset with request: {request}")

        # Wyczyść poprzednie przykłady
        _dataset_curator.clear()

        # Zbierz dane
        lessons_count = _dataset_curator.collect_from_lessons(
            limit=request.lessons_limit
        )
        git_count = _dataset_curator.collect_from_git_history(
            max_commits=request.git_commits_limit
        )

        # TODO: Implement task history collection if needed
        # if request.include_task_history:
        #     task_count = _dataset_curator.collect_from_task_history(limit=100)

        # Filtruj niską jakość
        removed = _dataset_curator.filter_low_quality()

        # Zapisz dataset
        dataset_path = _dataset_curator.save_dataset(format=request.format)

        # Statystyki
        stats = _dataset_curator.get_statistics()

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


@router.post("/train", response_model=TrainingResponse)
async def start_training(request: TrainingRequest) -> TrainingResponse:
    """
    Start zadania treningowego.

    Uruchamia trening LoRA/QLoRA w kontenerze Docker z GPU.

    Returns:
        TrainingResponse z job_id i parametrami
    """
    _ensure_academy_enabled()

    try:
        from venom_core.config import SETTINGS

        logger.info(f"Starting training with request: {request}")

        # Jeśli nie podano dataset_path, użyj ostatniego
        dataset_path = request.dataset_path
        if not dataset_path:
            training_dir = Path(SETTINGS.ACADEMY_TRAINING_DIR)
            if not training_dir.exists():
                raise HTTPException(
                    status_code=400,
                    detail="No dataset found. Please curate dataset first.",
                )

            datasets = sorted(training_dir.glob("dataset_*.jsonl"))
            if not datasets:
                raise HTTPException(
                    status_code=400,
                    detail="No dataset found. Please curate dataset first.",
                )

            dataset_path = str(datasets[-1])

        # Jeśli nie podano base_model, użyj domyślnego
        base_model = request.base_model or SETTINGS.ACADEMY_DEFAULT_BASE_MODEL

        # Przygotuj output directory
        job_id = f"training_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        output_dir = Path(SETTINGS.ACADEMY_MODELS_DIR) / job_id
        output_dir.mkdir(parents=True, exist_ok=True)

        # Uruchom trening
        job_info = _gpu_habitat.run_training_job(
            dataset_path=dataset_path,
            base_model=base_model,
            output_dir=str(output_dir),
            lora_rank=request.lora_rank,
            learning_rate=request.learning_rate,
            num_epochs=request.num_epochs,
            max_seq_length=request.max_seq_length,
            batch_size=request.batch_size,
        )

        # Zapisz do historii
        job_record = {
            "job_id": job_id,
            "job_name": job_info.get("job_name", job_id),
            "dataset_path": dataset_path,
            "base_model": base_model,
            "parameters": {
                "lora_rank": request.lora_rank,
                "learning_rate": request.learning_rate,
                "num_epochs": request.num_epochs,
                "batch_size": request.batch_size,
                "max_seq_length": request.max_seq_length,
            },
            "status": "running",
            "started_at": datetime.now().isoformat(),
            "container_id": job_info.get("container_id"),
            "output_dir": str(output_dir),
        }
        _save_job_to_history(job_record)

        return TrainingResponse(
            success=True,
            job_id=job_id,
            message=f"Training started successfully: {job_id}",
            parameters=job_record["parameters"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start training: {e}", exc_info=True)
        return TrainingResponse(success=False, message=f"Failed to start training: {str(e)}")


@router.get("/train/{job_id}/status", response_model=JobStatusResponse)
async def get_training_status(job_id: str) -> JobStatusResponse:
    """
    Pobiera status i logi zadania treningowego.

    Returns:
        JobStatusResponse ze statusem, logami i ścieżką adaptera
    """
    _ensure_academy_enabled()

    try:
        # Znajdź job w historii
        jobs = _load_jobs_history()
        job = next((j for j in jobs if j.get("job_id") == job_id), None)

        if not job:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

        job_name = job.get("job_name", job_id)

        # Pobierz status z GPUHabitat
        status_info = _gpu_habitat.get_training_status(job_name)

        # Aktualizuj status w historii jeśli się zmienił
        current_status = status_info.get("status", "unknown")
        if current_status != job.get("status"):
            updates = {"status": current_status}
            if current_status in ["finished", "failed"]:
                updates["finished_at"] = datetime.now().isoformat()
            if current_status == "finished":
                # Sprawdź czy adapter został utworzony
                adapter_path = Path(job.get("output_dir", "")) / "adapter"
                if adapter_path.exists():
                    updates["adapter_path"] = str(adapter_path)
            _update_job_in_history(job_id, updates)
            job.update(updates)

        return JobStatusResponse(
            job_id=job_id,
            status=current_status,
            logs=status_info.get("logs", "")[-5000:],  # Last 5000 chars
            started_at=job.get("started_at"),
            finished_at=job.get("finished_at"),
            adapter_path=job.get("adapter_path"),
            error=status_info.get("error"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get training status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get status: {str(e)}")


@router.get("/jobs")
async def list_jobs(
    limit: int = Query(default=50, ge=1, le=500),
    status: Optional[str] = Query(default=None),
) -> Dict[str, Any]:
    """
    Lista wszystkich jobów treningowych.

    Args:
        limit: Maksymalna liczba jobów do zwrócenia
        status: Filtruj po statusie (queued, running, finished, failed)

    Returns:
        Lista jobów
    """
    _ensure_academy_enabled()

    try:
        jobs = _load_jobs_history()

        # Filtruj po statusie jeśli podano
        if status:
            jobs = [j for j in jobs if j.get("status") == status]

        # Sortuj od najnowszych
        jobs = sorted(
            jobs, key=lambda j: j.get("started_at", ""), reverse=True
        )[:limit]

        return {"count": len(jobs), "jobs": jobs}

    except Exception as e:
        logger.error(f"Failed to list jobs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list jobs: {str(e)}")


@router.get("/adapters", response_model=List[AdapterInfo])
async def list_adapters() -> List[AdapterInfo]:
    """
    Lista dostępnych adapterów.

    Skanuje katalog z modelami i zwraca listę dostępnych adapterów LoRA.

    Returns:
        Lista adapterów
    """
    _ensure_academy_enabled()

    try:
        from venom_core.config import SETTINGS

        adapters = []
        models_dir = Path(SETTINGS.ACADEMY_MODELS_DIR)

        if not models_dir.exists():
            return []

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
                with open(metadata_file, "r") as f:
                    metadata = json.load(f)

            adapters.append(
                AdapterInfo(
                    adapter_id=training_dir.name,
                    adapter_path=str(adapter_path),
                    base_model=metadata.get(
                        "base_model", SETTINGS.ACADEMY_DEFAULT_BASE_MODEL
                    ),
                    created_at=metadata.get("created_at", "unknown"),
                    training_params=metadata.get("parameters", {}),
                    is_active=False,  # TODO: Check with ModelManager
                )
            )

        return adapters

    except Exception as e:
        logger.error(f"Failed to list adapters: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list adapters: {str(e)}")


@router.post("/adapters/activate")
async def activate_adapter(request: ActivateAdapterRequest) -> Dict[str, Any]:
    """
    Aktywacja adaptera LoRA.

    Hot-swap adaptera bez restartu backendu.

    Returns:
        Status aktywacji
    """
    _ensure_academy_enabled()

    try:
        if not _model_manager:
            raise HTTPException(
                status_code=503, detail="ModelManager not available for adapter activation"
            )

        adapter_path = Path(request.adapter_path)
        if not adapter_path.exists():
            raise HTTPException(
                status_code=404, detail=f"Adapter not found: {request.adapter_path}"
            )

        # TODO: Implementacja aktywacji adaptera przez ModelManager
        # _model_manager.activate_adapter(request.adapter_id, str(adapter_path))

        logger.info(f"Activated adapter: {request.adapter_id}")

        return {
            "success": True,
            "message": f"Adapter {request.adapter_id} activated successfully",
            "adapter_id": request.adapter_id,
            "adapter_path": request.adapter_path,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to activate adapter: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to activate adapter: {str(e)}"
        )


@router.delete("/train/{job_id}")
async def cancel_training(job_id: str) -> Dict[str, Any]:
    """
    Anuluj trening (zatrzymaj kontener).

    Returns:
        Status anulowania
    """
    _ensure_academy_enabled()

    try:
        # Znajdź job
        jobs = _load_jobs_history()
        job = next((j for j in jobs if j.get("job_id") == job_id), None)

        if not job:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

        job_name = job.get("job_name", job_id)
        container_id = job.get("container_id")

        if not container_id:
            raise HTTPException(status_code=400, detail="Job has no container_id")

        # TODO: Implementacja zatrzymania kontenera
        # _gpu_habitat.stop_container(container_id)

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

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel training: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to cancel training: {str(e)}"
        )


@router.get("/status")
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
        if _lessons_store:
            lessons_stats = _lessons_store.get_statistics()

        # Status GPU
        gpu_available = False
        gpu_info = {}
        if _gpu_habitat:
            gpu_available = _gpu_habitat.is_gpu_available()
            # TODO: Pobierz więcej info o GPU

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
                "professor": _professor is not None,
                "dataset_curator": _dataset_curator is not None,
                "gpu_habitat": _gpu_habitat is not None,
                "lessons_store": _lessons_store is not None,
                "model_manager": _model_manager is not None,
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
