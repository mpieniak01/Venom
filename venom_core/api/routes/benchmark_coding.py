"""Moduł: routes/benchmark_coding - Endpointy API dla coding benchmarków Ollama."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from venom_core.api.schemas.benchmark_coding import (
    CodingBenchmarkDeleteResponse,
    CodingBenchmarkListResponse,
    CodingBenchmarkStartRequest,
    CodingBenchmarkStartResponse,
    CodingBenchmarkStatusResponse,
)
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/benchmark/coding", tags=["benchmark-coding"])
CODING_SERVICE_UNAVAILABLE_DETAIL = "CodingBenchmarkService nie jest dostępny"

# Zależność - ustawiana przez router_wiring.py
_coding_benchmark_service = None


def set_dependencies(coding_benchmark_service) -> None:
    """Ustaw zależności dla routera."""
    global _coding_benchmark_service
    _coding_benchmark_service = coding_benchmark_service


@router.post(
    "/start",
    response_model=CodingBenchmarkStartResponse,
    responses={
        503: {"description": CODING_SERVICE_UNAVAILABLE_DETAIL},
        400: {"description": "Nieprawidłowe parametry benchmarku"},
        500: {"description": "Błąd wewnętrzny podczas uruchamiania benchmarku"},
    },
)
async def start_coding_benchmark(request: CodingBenchmarkStartRequest):
    """
    Uruchamia coding benchmark dla wybranych modeli i zadań.

    Uruchamia scheduler Ollama coding benchmark jako subproces w tle.

    Returns:
        run_id do sprawdzania statusu

    Raises:
        HTTPException: 503 jeśli serwis niedostępny
        HTTPException: 400 jeśli parametry nieprawidłowe
    """
    if _coding_benchmark_service is None:
        raise HTTPException(
            status_code=503, detail=CODING_SERVICE_UNAVAILABLE_DETAIL
        )

    try:
        run_id = _coding_benchmark_service.start_run(
            models=request.models,
            tasks=request.tasks,
            loop_task=request.loop_task,
            first_sieve_task=request.first_sieve_task,
            timeout=request.timeout,
            max_rounds=request.max_rounds,
            options=request.options,
            model_timeout_overrides=request.model_timeout_overrides,
            stop_on_failure=request.stop_on_failure,
            endpoint=request.endpoint,
        )
        return CodingBenchmarkStartResponse(
            run_id=run_id,
            message=f"Coding benchmark uruchomiony dla {len(request.models)} modeli, {len(request.tasks)} zadań",
        )
    except ValueError as exc:
        logger.error(f"Nieprawidłowe parametry coding benchmarku: {exc}")
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Błąd podczas uruchamiania coding benchmarku")
        raise HTTPException(
            status_code=500,
            detail="Nie udało się uruchomić coding benchmarku. Sprawdź logi serwera.",
        ) from exc


@router.get(
    "/list",
    response_model=CodingBenchmarkListResponse,
    responses={
        503: {"description": CODING_SERVICE_UNAVAILABLE_DETAIL},
    },
)
def list_coding_benchmarks(
    limit: Annotated[int, Query(ge=1, le=100)] = 10
):
    """
    Lista ostatnich coding benchmarków.

    Args:
        limit: Maksymalna liczba wyników

    Returns:
        Lista benchmarków posortowanych od najnowszych
    """
    if _coding_benchmark_service is None:
        raise HTTPException(
            status_code=503, detail=CODING_SERVICE_UNAVAILABLE_DETAIL
        )

    try:
        runs = _coding_benchmark_service.list_runs(limit=limit)
        return CodingBenchmarkListResponse(runs=runs, count=len(runs))
    except Exception as exc:
        logger.exception("Błąd podczas pobierania listy coding benchmarków")
        raise HTTPException(
            status_code=500,
            detail="Nie udało się pobrać listy coding benchmarków.",
        ) from exc


@router.delete(
    "/all",
    status_code=200,
    response_model=CodingBenchmarkDeleteResponse,
    responses={
        503: {"description": CODING_SERVICE_UNAVAILABLE_DETAIL},
    },
)
def clear_all_coding_benchmarks():
    """
    Usuwa wszystkie wyniki coding benchmarków.

    Returns:
        Informacja o liczbie usuniętych run
    """
    if _coding_benchmark_service is None:
        raise HTTPException(
            status_code=503, detail=CODING_SERVICE_UNAVAILABLE_DETAIL
        )

    try:
        count = _coding_benchmark_service.clear_all_runs()
        return CodingBenchmarkDeleteResponse(
            message=f"Usunięto {count} coding benchmarków", count=count
        )
    except Exception as exc:
        logger.exception("Błąd podczas czyszczenia coding benchmarków")
        raise HTTPException(
            status_code=500,
            detail="Nie udało się wyczyścić coding benchmarków.",
        ) from exc


@router.get(
    "/{run_id}/status",
    response_model=CodingBenchmarkStatusResponse,
    responses={
        503: {"description": CODING_SERVICE_UNAVAILABLE_DETAIL},
        404: {"description": "Run nie znaleziony"},
    },
)
def get_coding_benchmark_status(run_id: str):
    """
    Zwraca status i wyniki coding benchmarku.

    Status może być: pending | running | completed | failed

    Args:
        run_id: ID uruchomienia benchmarku

    Returns:
        Status run z listą jobów i metrykami

    Raises:
        HTTPException: 404 jeśli run nie znaleziony
    """
    if _coding_benchmark_service is None:
        raise HTTPException(
            status_code=503, detail=CODING_SERVICE_UNAVAILABLE_DETAIL
        )

    try:
        status = _coding_benchmark_service.get_run_status(run_id)
        if status is None:
            raise HTTPException(
                status_code=404, detail=f"Coding benchmark run {run_id} nie znaleziony"
            )
        return CodingBenchmarkStatusResponse(**status)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(f"Błąd podczas pobierania statusu coding benchmarku {run_id}")
        raise HTTPException(
            status_code=500,
            detail="Nie udało się pobrać statusu coding benchmarku.",
        ) from exc


@router.delete(
    "/{run_id}",
    status_code=200,
    response_model=CodingBenchmarkDeleteResponse,
    responses={
        503: {"description": CODING_SERVICE_UNAVAILABLE_DETAIL},
        404: {"description": "Run nie znaleziony"},
    },
)
def delete_coding_benchmark(run_id: str):
    """
    Usuwa pojedynczy coding benchmark run.

    Args:
        run_id: ID uruchomienia do usunięcia

    Raises:
        HTTPException: 404 jeśli run nie znaleziony
    """
    if _coding_benchmark_service is None:
        raise HTTPException(
            status_code=503, detail=CODING_SERVICE_UNAVAILABLE_DETAIL
        )

    try:
        success = _coding_benchmark_service.delete_run(run_id)
        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"Coding benchmark run {run_id} nie znaleziony",
            )
        return CodingBenchmarkDeleteResponse(
            message=f"Coding benchmark run {run_id} usunięty"
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(f"Błąd podczas usuwania coding benchmarku {run_id}")
        raise HTTPException(
            status_code=500,
            detail="Nie udało się usunąć coding benchmark run.",
        ) from exc
