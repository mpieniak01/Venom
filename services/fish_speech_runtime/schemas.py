"""Pydantic schemas for Fish Speech TTS runtime service."""

from __future__ import annotations

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    message: str


class StatusResponse(BaseModel):
    service: str = "fish_speech"
    status: str
    model_loaded: bool
    model_id: str
    device: str
    endpoint: str
    timestamp_ms: int


class TtsRequest(BaseModel):
    text: str = Field(..., min_length=1)
    language: str = "pl"
    voice_id: str | None = None
    voice_mode: str | None = None
    sample_rate: int = 24000


class TtsErrorResponse(BaseModel):
    error: str
    detail: str | None = None
