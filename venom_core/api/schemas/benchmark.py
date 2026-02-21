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


class BenchmarkModelResultResponse(BaseModel):
    """Response model for single benchmarked model metrics."""

    model_name: str = Field(..., description="Nazwa modelu")
    status: str = Field(..., description="Status testu modelu")
    latency_ms: float | None = Field(
        default=None, description="Średnia latencja odpowiedzi modelu (ms)"
    )
    tokens_per_second: float | None = Field(
        default=None, description="Prędkość generacji tokenów na sekundę"
    )
    peak_vram_mb: float | None = Field(
        default=None, description="Szczytowe zużycie VRAM (MB)"
    )
    time_to_first_token_ms: float | None = Field(
        default=None, description="Czas do pierwszego tokena (ms)"
    )
    total_duration_ms: float | None = Field(
        default=None, description="Całkowity czas testu modelu (ms)"
    )
    startup_latency_ms: float | None = Field(
        default=None, description="Czas restartu/healthchecku runtime (ms)"
    )
    questions_tested: int = Field(default=0, description="Liczba przetestowanych pytań")
    error_message: str | None = Field(default=None, description="Komunikat błędu")
    started_at: str | None = Field(default=None, description="Czas startu testu modelu")
    completed_at: str | None = Field(
        default=None, description="Czas zakończenia testu modelu"
    )


class BenchmarkJobResponse(BaseModel):
    """Shared response model for benchmark job data."""

    benchmark_id: str
    status: str
    progress: str
    current_model: Optional[str] = None
    models: list[str]
    num_questions: int
    results: list[BenchmarkModelResultResponse]
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_message: Optional[str] = None


class BenchmarkStatusResponse(BenchmarkJobResponse):
    """Response ze statusem benchmarku."""


class BenchmarkListResponse(BaseModel):
    """Response with list of benchmarks."""

    benchmarks: list[BenchmarkJobResponse]
    count: int


class BenchmarkDeleteResponse(BaseModel):
    """Response after deleting benchmark(s)."""

    message: str
    count: Optional[int] = None
