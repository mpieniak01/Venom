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

    type: Literal["text", "audio", "image"] = Field(..., description="Content type")
    text: Optional[str] = Field(None, description="Text content (for type='text')")
    path: Optional[str] = Field(
        None,
        description="Local path for audio/image content (for multipart or local files)",
    )
    url: Optional[str] = Field(None, description="Remote image URL (for type='image')")
    data: Optional[str] = Field(
        None, description="Image as data URL or raw base64 string (for type='image')"
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
    image_input: Literal["verified", "failed", "unknown"] = Field(
        "unknown", description="Image input capability status"
    )
    image_ocr: Literal["verified", "failed", "unknown"] = Field(
        "unknown", description="Image OCR capability status"
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
    audio: Optional[AudioMetadata] = Field(
        None, description="Input audio metadata (present when audio was provided)"
    )
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
    raw_thinking_available: bool = Field(
        False, description="Whether raw thinking output is available"
    )
    reasoning_summary_status: Literal["disabled", "summary", "raw_available"] = Field(
        "disabled", description="Reasoning summary visibility state"
    )
    reasoning_summary: Optional[str] = Field(
        None, description="Short reasoning summary for diagnostics"
    )
    emotion_label: Optional[str] = Field(
        None, description="Heuristic emotion label inferred from the voice input"
    )
    emotion_confidence: Optional[float] = Field(
        None, description="Confidence score for the inferred emotion label"
    )
    emotion_source: Optional[str] = Field(
        None, description="Emotion source used for inference"
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


# ---------------------------------------------------------------------------
# Daemon control schemas
# ---------------------------------------------------------------------------


class VRAMStatus(BaseModel):
    backend: str = Field("cpu")
    allocated_mb: float = Field(0.0)
    reserved_mb: float = Field(0.0)
    total_mb: float = Field(0.0)
    free_mb: float = Field(0.0)


class DaemonParamsInfo(BaseModel):
    max_new_tokens: int
    enable_thinking: bool
    image_token_budget: int = 280
    reasoning_summary_enabled: bool = False
    emotion_detection_enabled: bool = False
    emotion_response_style_enabled: bool = False
    cache_implementation: Optional[str] = None


class DaemonStatusResponse(BaseModel):
    """Full daemon state: models, params, VRAM, reload signal."""

    target_model: str
    assistant_model: Optional[str] = None
    mode: Literal["target_only", "target_with_assistant"]
    target_loaded: bool
    assistant_loaded: bool
    params: DaemonParamsInfo
    vram: VRAMStatus
    raw_thinking_available: bool = Field(
        False, description="Whether the current target can emit raw thinking"
    )
    reasoning_summary_status: Literal["disabled", "summary", "raw_available"] = Field(
        "disabled", description="Reasoning summary visibility state"
    )
    reasoning_summary: Optional[str] = Field(
        None, description="Short reasoning summary for diagnostics"
    )
    emotion_label: Optional[str] = Field(
        None,
        description="Heuristic emotion label inferred from the current voice session",
    )
    emotion_confidence: Optional[float] = Field(
        None, description="Confidence score for the inferred emotion label"
    )
    emotion_source: Optional[str] = Field(
        None, description="Emotion source used for inference"
    )
    pending_reload: bool
    reload_reason: Optional[str] = None
    supports_image_input: bool = True


class DaemonConfigRequest(BaseModel):
    """Live parameter update. Returns required reload signal."""

    max_new_tokens: Optional[int] = Field(None, ge=1, le=32768)
    enable_thinking: Optional[bool] = None
    image_token_budget: Optional[int] = Field(None, ge=70, le=1120)
    reasoning_summary_enabled: Optional[bool] = None
    emotion_detection_enabled: Optional[bool] = None
    emotion_response_style_enabled: Optional[bool] = None
    cache_implementation: Optional[str] = None


class DaemonConfigResponse(BaseModel):
    reload_signal: Literal["none", "soft_reload", "hard_restart"]
    applied: DaemonParamsInfo
    message: str


class AssistantAttachRequest(BaseModel):
    model_id: str = Field(..., description="HuggingFace model ID of the assistant")


class AssistantAttachResponse(BaseModel):
    assistant_model: str
    mode: Literal["target_only", "target_with_assistant"]
    message: str


class SoftReloadResponse(BaseModel):
    reason: str
    target_model: str
    message: str


class FallbackResponse(BaseModel):
    reload_signal: Literal["none", "soft_reload", "hard_restart"]
    target_model: str
    message: str


class RestartResponse(BaseModel):
    status: Literal["restarting"]
    message: str
