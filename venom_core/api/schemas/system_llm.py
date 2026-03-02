"""Schemas for system LLM API endpoints."""

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ActiveLlmServerRequest(BaseModel):
    """Request for activating an LLM server."""

    server_name: str
    trace_id: Optional[UUID] = None
    model: Optional[str] = Field(
        default=None,
        description="Opcjonalny model do aktywacji na wybranym serwerze",
    )
    model_alias: Optional[str] = Field(
        default=None,
        description=(
            "Opcjonalny alias klasy modelu (np. OpenCodeInterpreter-Qwen2.5-7B)"
        ),
    )
    exact_only: bool = Field(
        default=False,
        description="Gdy true, blokuje fallback przy rozwiązywaniu aliasu modelu",
    )


class LlmRuntimeActivateRequest(BaseModel):
    """Request for activating an LLM runtime (cloud provider)."""

    provider: str = Field(
        ..., description="Docelowy provider runtime (openai/google/onnx)"
    )
    model: Optional[str] = Field(default=None, description="Opcjonalny model LLM")
