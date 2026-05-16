"""Schemas for model introspection analysis endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ModelIntrospectionAnalyzeRequest(BaseModel):
    """Request for optional live model analysis from Inspector."""

    prompt: str = Field(..., min_length=1, max_length=50000)
    live_analysis_enabled: bool = Field(
        default=False,
        description="Enable live model execution; disabled by default to avoid stack load",
    )
    max_tokens: int | None = Field(default=128, ge=1, le=8192)
    temperature: float | None = Field(default=0.2, ge=0.0, le=2.0)
