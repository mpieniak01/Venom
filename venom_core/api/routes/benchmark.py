"""Moduł: routes/benchmark - Endpointy API dla benchmarkingu modeli."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from venom_core.api.schemas.benchmark import (
    BenchmarkDeleteResponse,
    BenchmarkListResponse,
    BenchmarkStartRequest,
    BenchmarkStartResponse,
    BenchmarkStatusResponse,
)
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/benchmark", tags=["benchmark"])
BENCHMARK_SERVICE_UNAVAILABLE_DETAIL = "BenchmarkService nie jest dostępny"

# Zależność - będzie ustawiona w main.py
_benchmark_service = None


def set_dependencies(benchmark_service):
    """
    Ustaw zależności dla routera.

    Args:
        benchmark_service: Instancja BenchmarkService
    """
    global _benchmark_service
    _benchmark_service = benchmark_service


@router.post(
    "/start",
    response_model=BenchmarkStartResponse,
    responses={
        503: {"description": BENCHMARK_SERVICE_UNAVAILABLE_DETAIL},
        400: {"description": "Nieprawidłowe parametry benchmarku"},
        500: {"description": "Błąd wewnętrzny podczas uruchamiania benchmarku"},
    },
)
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
        HTTPException: 503 jeśli serwis benchmarku jest niedostępny
        HTTPException: 400 jeśli parametry są nieprawidłowe
    """
    if _benchmark_service is None:
        raise HTTPException(
            status_code=503, detail=BENCHMARK_SERVICE_UNAVAILABLE_DETAIL
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


@router.get(
    "/{benchmark_id}/status",
    response_model=BenchmarkStatusResponse,
    responses={
        503: {"description": BENCHMARK_SERVICE_UNAVAILABLE_DETAIL},
        404: {"description": "Benchmark nie został znaleziony"},
        500: {"description": "Błąd wewnętrzny podczas pobierania statusu"},
    },
)
def get_benchmark_status(benchmark_id: str):
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
        HTTPException: 503 jeśli serwis benchmarku jest niedostępny
        HTTPException: 404 jeśli benchmark nie został znaleziony
    """
    if _benchmark_service is None:
        raise HTTPException(
            status_code=503, detail=BENCHMARK_SERVICE_UNAVAILABLE_DETAIL
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


@router.get(
    "/list",
    response_model=BenchmarkListResponse,
    responses={
        503: {"description": BENCHMARK_SERVICE_UNAVAILABLE_DETAIL},
        500: {"description": "Błąd wewnętrzny podczas pobierania listy"},
    },
)
def list_benchmarks(limit: Annotated[int, Query(ge=1, le=100)] = 10):
    """
    Lista ostatnich benchmarków.

    Args:
        limit: Maksymalna liczba wyników (domyślnie 10)

    Returns:
        Lista benchmarków posortowanych od najnowszych

    Raises:
        HTTPException: 503 jeśli serwis benchmarku jest niedostępny
    """
    if _benchmark_service is None:
        raise HTTPException(
            status_code=503, detail=BENCHMARK_SERVICE_UNAVAILABLE_DETAIL
        )

    try:
        benchmarks = _benchmark_service.list_benchmarks(limit=limit)
        return BenchmarkListResponse(benchmarks=benchmarks, count=len(benchmarks))

    except Exception as e:
        logger.exception("Błąd podczas pobierania listy benchmarków")
        raise HTTPException(
            status_code=500,
            detail="Nie udało się pobrać listy benchmarków. Sprawdź logi serwera.",
        ) from e


@router.delete(
    "/all",
    status_code=200,
    response_model=BenchmarkDeleteResponse,
    responses={
        503: {"description": BENCHMARK_SERVICE_UNAVAILABLE_DETAIL},
        500: {"description": "Błąd wewnętrzny podczas czyszczenia benchmarków"},
    },
)
def clear_all_benchmarks():
    """
    Usuwa wszystkie wyniki benchmarków.

    Returns:
        Informacja o liczbie usuniętych benchmarków

    Raises:
        HTTPException: 503 jeśli serwis benchmarku jest niedostępny
    """
    if _benchmark_service is None:
        raise HTTPException(
            status_code=503, detail=BENCHMARK_SERVICE_UNAVAILABLE_DETAIL
        )

    try:
        count = _benchmark_service.clear_all_benchmarks()
        return BenchmarkDeleteResponse(
            message=f"Usunięto {count} benchmarków", count=count
        )

    except Exception as e:
        logger.exception("Błąd podczas czyszczenia benchmarków")
        raise HTTPException(
            status_code=500,
            detail="Nie udało się wyczyścić benchmarków",
        ) from e


@router.delete(
    "/{benchmark_id}",
    status_code=200,
    response_model=BenchmarkDeleteResponse,
    responses={
        503: {"description": BENCHMARK_SERVICE_UNAVAILABLE_DETAIL},
        404: {"description": "Benchmark nie został znaleziony"},
        500: {"description": "Błąd wewnętrzny podczas usuwania benchmarku"},
    },
)
def delete_benchmark(benchmark_id: str):
    """
    Usuwa pojedynczy benchmark.

    Args:
        benchmark_id: ID benchmarku do usunięcia

    Raises:
        HTTPException: 503 jeśli serwis benchmarku jest niedostępny
        HTTPException: 404 jeśli benchmark nie został znaleziony
    """
    if _benchmark_service is None:
        raise HTTPException(
            status_code=503, detail=BENCHMARK_SERVICE_UNAVAILABLE_DETAIL
        )

    try:
        success = _benchmark_service.delete_benchmark(benchmark_id)
        if not success:
            raise HTTPException(
                status_code=404, detail=f"Benchmark {benchmark_id} nie znaleziony"
            )
        return BenchmarkDeleteResponse(
            message=f"Benchmark {benchmark_id} został usunięty"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Błąd podczas usuwania benchmarku {benchmark_id}")
        raise HTTPException(
            status_code=500,
            detail="Nie udało się usunąć benchmarku",
        ) from e
