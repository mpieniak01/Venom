"""Schemas for model introspection analysis endpoints."""

from __future__ import annotations

from typing import Literal

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
    top_p: float | None = Field(default=0.9, gt=0.0, le=1.0)


class ModelIntrospectionProbeRequest(BaseModel):
    """Request for probe-level model internals through active multi_runtime."""

    prompt: str = Field(..., min_length=1, max_length=50000)
    mode: Literal["hidden", "attention", "logits"] = Field(default="hidden")
    layer_selection: list[int] = Field(default_factory=list, max_length=64)
    top_k: int = Field(default=8, ge=1, le=256)
