"""Request/response schemas for Gemma 4 Audio Runtime Service."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class AudioMetadata(BaseModel):
    """Metadata about audio input."""

    sample_rate: int = Field(..., description="Audio sample rate in Hz")
    duration_sec: float = Field(..., description="Audio duration in seconds")


class ContentItem(BaseModel):
    """Individual content item in a message (text or audio reference)."""

    type: Literal["text", "audio"] = Field(..., description="Content type")
    text: Optional[str] = Field(None, description="Text content (for type='text')")
    path: Optional[str] = Field(
        None, description="Audio file path (for type='audio', sent via multipart)"
    )


class MessageItem(BaseModel):
    """Single message in conversation history."""

    role: Literal["system", "user", "assistant"] = Field(
        ..., description="Message role"
    )
    content: list[ContentItem] = Field(..., description="List of content items")


class RespondRequest(BaseModel):
    """Request to generate text response from multimodal input."""

    model: Optional[str] = Field(
        None, description="Model ID override; if not set, uses current runtime model"
    )
    messages: list[MessageItem] = Field(..., description="Messages with content")
    task: Optional[str] = Field(
        None,
        description="Preset task: 'transcribe', 'question', 'math-5x5', or None for generic",
    )
    question: Optional[str] = Field(None, description="Question to answer from audio")
    system_prompt: Optional[str] = Field(None, description="System message override")
    max_new_tokens: int = Field(128, description="Generation budget")
    temperature: Optional[float] = Field(None, description="Sampling temperature")
    top_p: Optional[float] = Field(None, description="Top-p sampling")
    do_sample: Optional[bool] = Field(None, description="Use sampling vs greedy")


class Capabilities(BaseModel):
    """Runtime capabilities for this inference."""

    audio_input: Literal["verified", "failed", "unknown"] = Field(
        ..., description="Audio input capability status"
    )
    audio_reasoning: Literal["verified", "failed", "unknown"] = Field(
        ..., description="Audio reasoning capability status"
    )
    audio_transcription: Literal["verified", "failed", "unknown"] = Field(
        ..., description="Audio transcription capability status"
    )


class GenerationConfig(BaseModel):
    """Configuration used for generation."""

    max_new_tokens: int
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    do_sample: Optional[bool] = None


class RespondResponse(BaseModel):
    """Response from Gemma 4 Audio Runtime."""

    model: str = Field(..., description="Model ID used for inference")
    task: Optional[str] = Field(None, description="Task executed")
    text: str = Field(..., description="Generated text response")
    duration_ms: int = Field(..., description="Total request duration in milliseconds")
    audio: AudioMetadata = Field(..., description="Input audio metadata")
    input_modalities: list[str] = Field(
        default_factory=lambda: ["text", "audio"],
        description="Input modalities used",
    )
    output_modalities: list[str] = Field(
        default_factory=lambda: ["text"], description="Output modalities produced"
    )
    runtime_mode: str = Field(
        default="processor_model", description="Inference mode used (processor_model)"
    )
    capabilities: Capabilities = Field(..., description="Verified capabilities")
    generation_config: GenerationConfig = Field(
        ..., description="Configuration used for generation"
    )
    warnings: list[str] = Field(default_factory=list, description="Any warnings")
    trace_id: Optional[str] = Field(None, description="Request trace ID")


class TranscribeRequest(BaseModel):
    """Request to transcribe audio only."""

    model: Optional[str] = Field(None, description="Model ID override")
    task: Literal["transcribe"] = Field("transcribe")


class TranscribeResponse(BaseModel):
    """Response from transcription."""

    text: str = Field(..., description="Transcribed text")
    duration_ms: int = Field(..., description="Processing duration")
    audio: AudioMetadata = Field(..., description="Input audio metadata")


class ModelInfo(BaseModel):
    """Information about available model."""

    model_id: str = Field(..., description="Model identifier")
    instruction_tuned: bool = Field(
        True, description="Whether model is instruction-tuned"
    )
    supports_text_input: bool = Field(True)
    supports_audio_input: bool = Field(True)
    supports_image_input: bool = Field(False)
    supports_text_output: bool = Field(True)
    runtime_mode: str = Field("processor_model")
    status: Literal["loaded", "warming", "error"] = Field("loaded")


class StatusResponse(BaseModel):
    """Service status response."""

    service: str = Field("gemma4_audio")
    status: Literal["running", "warming", "error"] = Field("running")
    model_loaded: bool = Field(..., description="Whether model is currently loaded")
    model_info: Optional[ModelInfo] = Field(None, description="Loaded model info")
    timestamp_ms: int = Field(..., description="Server timestamp in ms")


class HealthResponse(BaseModel):
    """Health check response."""

    status: Literal["ok", "warming", "error"] = Field("ok")
    message: str = Field(...)
