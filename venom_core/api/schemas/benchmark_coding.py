"""Schemas for coding benchmark API endpoints."""

from typing import Any, Optional

from pydantic import BaseModel, Field


class CodingBenchmarkStartRequest(BaseModel):
    """Request do rozpoczęcia coding benchmarku."""

    models: list[str] = Field(
        ..., description="Lista nazw modeli Ollama do przetestowania", min_length=1
    )
    tasks: list[str] = Field(
        default=["python_complex"],
        description="Zadania codingowe do uruchomienia (python_sanity, python_simple, python_complex, python_complex_bugfix)",
        min_length=1,
    )
    loop_task: str = Field(
        default="python_complex_bugfix",
        description="Zadanie w trybie pętli (feedback loop). Pusty string wyłącza.",
    )
    first_sieve_task: str = Field(
        default="",
        description="Opcjonalne zadanie sito - modele które je nie zdadzą są pomijane.",
    )
    timeout: int = Field(
        default=180,
        description="Globalny timeout w sekundach dla każdego zadania",
        ge=10,
        le=3600,
    )
    max_rounds: int = Field(
        default=3,
        description="Maksymalna liczba rund w pętli feedback loop",
        ge=1,
        le=20,
    )
    options: dict[str, Any] = Field(
        default_factory=lambda: {"temperature": 0.1, "top_p": 0.9},
        description="Parametry generacji Ollama (temperature, top_p itp.)",
    )
    model_timeout_overrides: dict[str, int] = Field(
        default_factory=dict,
        description="Nadpisanie timeout per model (JSON: model->timeout_seconds)",
    )
    stop_on_failure: bool = Field(
        default=False,
        description="Zatrzymaj scheduler przy pierwszym błędzie",
    )
    endpoint: str = Field(
        default="http://127.0.0.1:11434",
        description="Adres Ollama API",
    )


class CodingJobResponse(BaseModel):
    """Stan pojedynczego joba schedulera."""

    id: str
    model: str
    mode: str  # single | loop
    task: str
    role: str = "main"  # main | sieve
    status: str = "pending"
    created_at: str = ""
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    rc: Optional[int] = None
    artifact: Optional[str] = None
    passed: Optional[bool] = None
    warmup_seconds: Optional[float] = None
    coding_seconds: Optional[float] = None
    request_wall_seconds: Optional[float] = None
    total_seconds: Optional[float] = None
    error: Optional[str] = None


class CodingBenchmarkSummary(BaseModel):
    """Skrócone podsumowanie wyników coding benchmarku."""

    total_jobs: int = 0
    completed: int = 0
    failed: int = 0
    pending: int = 0
    running: int = 0
    skipped: int = 0
    queue_finished: bool = False
    success_rate: float = 0.0


class CodingBenchmarkRunConfig(BaseModel):
    """Konfiguracja uruchomionego benchmarku (do podglądu statusu)."""

    models: list[str]
    tasks: list[str]
    loop_task: str
    first_sieve_task: str
    timeout: int
    max_rounds: int
    endpoint: str
    stop_on_failure: bool


class CodingBenchmarkStartResponse(BaseModel):
    """Response po uruchomieniu coding benchmarku."""

    run_id: str = Field(..., description="ID uruchomienia do sprawdzania statusu")
    message: str = Field(default="Coding benchmark uruchomiony")


class CodingBenchmarkStatusResponse(BaseModel):
    """Status i wyniki coding benchmarku."""

    run_id: str
    status: str  # pending | running | completed | completed_with_failures | failed
    config: CodingBenchmarkRunConfig
    jobs: list[CodingJobResponse] = Field(default_factory=list)
    summary: Optional[CodingBenchmarkSummary] = None
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    error_message: Optional[str] = None


class CodingBenchmarkListItem(BaseModel):
    """Skrócony widok coding benchmarku na liście."""

    run_id: str
    status: str  # pending | running | completed | completed_with_failures | failed
    config: CodingBenchmarkRunConfig
    summary: Optional[CodingBenchmarkSummary] = None
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    error_message: Optional[str] = None


class CodingBenchmarkListResponse(BaseModel):
    """Lista coding benchmarków."""

    runs: list[CodingBenchmarkListItem]
    count: int


class CodingBenchmarkDeleteResponse(BaseModel):
    """Response po usunięciu coding benchmarku."""

    message: str
    count: Optional[int] = None
