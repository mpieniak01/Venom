"""Schemas for system LLM API endpoints."""

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ActiveLlmServerRequest(BaseModel):
    """Request for activating an LLM server."""

    server_name: str
    trace_id: Optional[UUID] = None


class LlmRuntimeActivateRequest(BaseModel):
    """Request for activating an LLM runtime (cloud provider)."""

    provider: str = Field(..., description="Docelowy provider runtime (openai/google)")
    model: Optional[str] = Field(default=None, description="Opcjonalny model LLM")
