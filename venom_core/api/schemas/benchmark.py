"""Schemas for benchmark API endpoints."""

from typing import Optional

from pydantic import BaseModel, Field


class BenchmarkStartRequest(BaseModel):
    """Request do rozpoczęcia benchmarku."""

    models: list[str] = Field(
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
    current_model: Optional[str] = None
    models: list[str]
    num_questions: int
    results: list[dict]
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_message: Optional[str] = None


class BenchmarkListResponse(BaseModel):
    """Response with list of benchmarks."""

    benchmarks: list[dict]
    count: int


class BenchmarkDeleteResponse(BaseModel):
    """Response after deleting benchmark(s)."""

    message: str
    count: Optional[int] = None
