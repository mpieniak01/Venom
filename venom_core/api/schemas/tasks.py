"""API schemas for tasks and history endpoints."""

from uuid import UUID

from pydantic import BaseModel


class HistoryRequestSummary(BaseModel):
    """Skrócony widok requestu dla listy historii."""

    request_id: UUID
    prompt: str
    status: str
    session_id: str | None = None
    created_at: str
    finished_at: str | None = None
    duration_seconds: float | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    llm_endpoint: str | None = None
    llm_config_hash: str | None = None
    llm_runtime_id: str | None = None
    forced_tool: str | None = None
    forced_provider: str | None = None
    forced_intent: str | None = None
    error_code: str | None = None
    error_class: str | None = None
    error_message: str | None = None
    error_details: dict | None = None
    error_stage: str | None = None
    error_retryable: bool | None = None
    feedback: dict | None = None
    result: str | None = None


class HistoryRequestDetail(BaseModel):
    """Szczegółowy widok requestu z krokami."""

    request_id: UUID
    prompt: str
    status: str
    session_id: str | None = None
    created_at: str
    finished_at: str | None = None
    duration_seconds: float | None = None
    steps: list
    llm_provider: str | None = None
    llm_model: str | None = None
    llm_endpoint: str | None = None
    llm_config_hash: str | None = None
    llm_runtime_id: str | None = None
    forced_tool: str | None = None
    forced_provider: str | None = None
    forced_intent: str | None = None
    first_token: dict | None = None
    streaming: dict | None = None
    context_preview: dict | None = None
    generation_params: dict | None = None
    llm_runtime: dict | None = None
    context_used: dict | None = None
    error_code: str | None = None
    error_class: str | None = None
    error_message: str | None = None
    error_details: dict | None = None
    error_stage: str | None = None
    error_retryable: bool | None = None
    result: str | None = None
    feedback: dict | None = None
