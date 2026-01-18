"""Moduł: routes/benchmark - Endpointy API dla benchmarkingu modeli."""

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/benchmark", tags=["benchmark"])

# Zależność - będzie ustawiona w main.py
_benchmark_service = None


class BenchmarkStartRequest(BaseModel):
    """Request do rozpoczęcia benchmarku."""

    models: List[str] = Field(
        ..., description="Lista nazw modeli do przetestowania", min_length=1
    )
    num_questions: int = Field(
        default=5,
        description="Liczba pytań do zadania każdemu modelowi",
        ge=1,
        le=20,
    )


class BenchmarkStartResponse(BaseModel):
    """Response po rozpoczęciu benchmarku."""

    benchmark_id: str = Field(..., description="ID benchmarku do sprawdzania statusu")
    message: str = Field(default="Benchmark uruchomiony")


class BenchmarkStatusResponse(BaseModel):
    """Response ze statusem benchmarku."""

    benchmark_id: str
    status: str
    progress: str
    current_model: Optional[str]
    models: List[str]
    num_questions: int
    results: List[dict]
    created_at: str
    started_at: Optional[str]
    completed_at: Optional[str]
    error_message: Optional[str]


def set_dependencies(benchmark_service):
    """
    Ustaw zależności dla routera.

    Args:
        benchmark_service: Instancja BenchmarkService
    """
    global _benchmark_service
    _benchmark_service = benchmark_service


@router.post("/start", response_model=BenchmarkStartResponse)
async def start_benchmark(request: BenchmarkStartRequest):
    """
    Rozpoczyna benchmark wielu modeli.

    Benchmark testuje każdy model sekwencyjnie:
    1. Aktywuje model przez ModelRegistry
    2. Czeka na healthcheck
    3. Wysyła N losowych pytań
    4. Mierzy: latencję, tokens/s, szczytowe VRAM
    5. Zwraca wyniki

    Args:
        request: Parametry benchmarku (modele, liczba pytań)

    Returns:
        ID benchmarku do sprawdzania statusu

    Raises:
        HTTPException: 503 jeśli BenchmarkService nie jest dostępny
        HTTPException: 400 jeśli parametry są nieprawidłowe
    """
    if _benchmark_service is None:
        raise HTTPException(
            status_code=503, detail="BenchmarkService nie jest dostępny"
        )

    try:
        benchmark_id = await _benchmark_service.start_benchmark(
            models=request.models, num_questions=request.num_questions
        )

        return BenchmarkStartResponse(
            benchmark_id=benchmark_id,
            message=f"Benchmark uruchomiony dla {len(request.models)} modeli",
        )

    except ValueError as e:
        logger.error(f"Nieprawidłowe parametry benchmarku: {e}")
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception("Błąd podczas uruchamiania benchmarku")
        raise HTTPException(
            status_code=500,
            detail="Nie udało się uruchomić benchmarku. Sprawdź logi serwera.",
        ) from e


@router.get("/{benchmark_id}/status", response_model=BenchmarkStatusResponse)
async def get_benchmark_status(benchmark_id: str):
    """
    Zwraca status i wyniki benchmarku.

    Status może być:
    - pending: Benchmark w kolejce
    - running: Benchmark w trakcie (progress pokazuje aktualny model)
    - completed: Benchmark zakończony (results zawiera pełne wyniki)
    - failed: Benchmark nie powiódł się

    Args:
        benchmark_id: ID benchmarku

    Returns:
        Status benchmarku z wynikami częściowymi lub pełnymi

    Raises:
        HTTPException: 503 jeśli BenchmarkService nie jest dostępny
        HTTPException: 404 jeśli benchmark nie został znaleziony
    """
    if _benchmark_service is None:
        raise HTTPException(
            status_code=503, detail="BenchmarkService nie jest dostępny"
        )

    try:
        status = _benchmark_service.get_benchmark_status(benchmark_id)

        if status is None:
            raise HTTPException(
                status_code=404, detail=f"Benchmark {benchmark_id} nie znaleziony"
            )

        return BenchmarkStatusResponse(**status)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Błąd podczas pobierania statusu benchmarku")
        raise HTTPException(
            status_code=500,
            detail="Nie udało się pobrać statusu benchmarku. Sprawdź logi serwera.",
        ) from e


@router.get("/list")
async def list_benchmarks(limit: int = Query(default=10, ge=1, le=100)):
    """
    Lista ostatnich benchmarków.

    Args:
        limit: Maksymalna liczba wyników (domyślnie 10)

    Returns:
        Lista benchmarków posortowanych od najnowszych

    Raises:
        HTTPException: 503 jeśli BenchmarkService nie jest dostępny
    """
    if _benchmark_service is None:
        raise HTTPException(
            status_code=503, detail="BenchmarkService nie jest dostępny"
        )

    try:
        benchmarks = _benchmark_service.list_benchmarks(limit=limit)
        return {"benchmarks": benchmarks, "count": len(benchmarks)}

    except Exception as e:
        logger.exception("Błąd podczas pobierania listy benchmarków")
        raise HTTPException(
            status_code=500,
            detail="Nie udało się pobrać listy benchmarków. Sprawdź logi serwera.",
        ) from e


@router.delete("/all", status_code=200)
async def clear_all_benchmarks():
    """
    Usuwa wszystkie wyniki benchmarków.

    Returns:
        Informacja o liczbie usuniętych benchmarków

    Raises:
        HTTPException: 503 jeśli BenchmarkService nie jest dostępny
    """
    if _benchmark_service is None:
        raise HTTPException(
            status_code=503, detail="BenchmarkService nie jest dostępny"
        )

    try:
        count = _benchmark_service.clear_all_benchmarks()
        return {"message": f"Usunięto {count} benchmarków", "count": count}

    except Exception as e:
        logger.exception("Błąd podczas czyszczenia benchmarków")
        raise HTTPException(
            status_code=500,
            detail="Nie udało się wyczyścić benchmarków",
        ) from e


@router.delete("/{benchmark_id}", status_code=200)
async def delete_benchmark(benchmark_id: str):
    """
    Usuwa pojedynczy benchmark.

    Args:
        benchmark_id: ID benchmarku do usunięcia

    Raises:
        HTTPException: 503 jeśli BenchmarkService nie jest dostępny
        HTTPException: 404 jeśli benchmark nie został znaleziony
    """
    if _benchmark_service is None:
        raise HTTPException(
            status_code=503, detail="BenchmarkService nie jest dostępny"
        )

    try:
        success = _benchmark_service.delete_benchmark(benchmark_id)
        if not success:
            raise HTTPException(
                status_code=404, detail=f"Benchmark {benchmark_id} nie znaleziony"
            )
        return {"message": f"Benchmark {benchmark_id} został usunięty"}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Błąd podczas usuwania benchmarku {benchmark_id}")
        raise HTTPException(
            status_code=500,
            detail="Nie udało się usunąć benchmarku",
        ) from e
