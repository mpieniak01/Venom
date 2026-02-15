"""API schemas for tasks and history endpoints."""

from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class HistoryRequestSummary(BaseModel):
    """Skrócony widok requestu dla listy historii."""

    request_id: UUID
    prompt: str
    status: str
    session_id: Optional[str] = None
    created_at: str
    finished_at: Optional[str] = None
    duration_seconds: Optional[float] = None
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    llm_endpoint: Optional[str] = None
    llm_config_hash: Optional[str] = None
    llm_runtime_id: Optional[str] = None
    forced_tool: Optional[str] = None
    forced_provider: Optional[str] = None
    forced_intent: Optional[str] = None
    error_code: Optional[str] = None
    error_class: Optional[str] = None
    error_message: Optional[str] = None
    error_details: Optional[dict] = None
    error_stage: Optional[str] = None
    error_retryable: Optional[bool] = None
    feedback: Optional[dict] = None
    result: Optional[str] = None


class HistoryRequestDetail(BaseModel):
    """Szczegółowy widok requestu z krokami."""

    request_id: UUID
    prompt: str
    status: str
    session_id: Optional[str] = None
    created_at: str
    finished_at: Optional[str] = None
    duration_seconds: Optional[float] = None
    steps: list
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    llm_endpoint: Optional[str] = None
    llm_config_hash: Optional[str] = None
    llm_runtime_id: Optional[str] = None
    forced_tool: Optional[str] = None
    forced_provider: Optional[str] = None
    forced_intent: Optional[str] = None
    first_token: Optional[dict] = None
    streaming: Optional[dict] = None
    context_preview: Optional[dict] = None
    generation_params: Optional[dict] = None
    llm_runtime: Optional[dict] = None
    context_used: Optional[dict] = None
    error_code: Optional[str] = None
    error_class: Optional[str] = None
    error_message: Optional[str] = None
    error_details: Optional[dict] = None
    error_stage: Optional[str] = None
    error_retryable: Optional[bool] = None
    result: Optional[str] = None
    feedback: Optional[dict] = None
