"""FastAPI application for Gemma 4 Audio Runtime Service."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import numpy as np
import uvicorn
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from .audio import audio_from_bytes, audio_from_file, get_audio_duration
from .engine import Gemma4AudioEngine, InferenceError
from .schemas import (
    AudioMetadata,
    Capabilities,
    GenerationConfig,
    HealthResponse,
    ModelInfo,
    RespondRequest,
    RespondResponse,
    StatusResponse,
    TranscribeResponse,
)

logger = logging.getLogger(__name__)


# Global engine instance
_engine: Optional[Gemma4AudioEngine] = None
_start_time: float = 0
_warming: bool = False
_startup_error: Optional[str] = None


def get_engine() -> Gemma4AudioEngine:
    """Get the global engine instance."""
    global _engine
    if _engine is None:
        raise RuntimeError("Engine not initialized")
    return _engine


async def initialize_engine(
    model_id: str, cache_dir: str, device: str = "auto", max_new_tokens: int = 128
) -> None:
    """Initialize the engine with model loading."""
    global _engine, _warming, _startup_error

    _warming = True
    _startup_error = None
    try:
        logger.info(f"Initializing Gemma 4 Audio Engine with model {model_id}")
        _engine = Gemma4AudioEngine(
            model_id=model_id,
            cache_dir=cache_dir,
            device=device,
            max_new_tokens=max_new_tokens,
        )
        logger.info("Loading model...")
        await asyncio.to_thread(_engine.load)
        logger.info(f"Model loaded successfully. Class: {_engine.model_class_name}")
        _warming = False
    except Exception as e:
        logger.error(f"Failed to initialize engine: {e}")
        _startup_error = str(e)
        _warming = False


async def _startup_model_loader() -> None:
    """Background model loader that keeps the API server available during warmup."""
    model_id = os.getenv("GEMMA4_AUDIO_MODEL_ID", "google/gemma-4-E2B-it")
    cache_dir = os.getenv("GEMMA4_AUDIO_CACHE_DIR", "models_cache/hf")
    device = os.getenv("GEMMA4_AUDIO_DEVICE", "auto")
    max_tokens = int(os.getenv("GEMMA4_AUDIO_MAX_NEW_TOKENS", "128"))
    await initialize_engine(model_id, cache_dir, device, max_tokens)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager."""
    global _start_time
    _start_time = time.time()

    # Startup: keep API available while the model is loading in background.
    asyncio.create_task(_startup_model_loader())

    yield

    # Shutdown
    if _engine is not None:
        _engine.unload()
        logger.info("Engine unloaded")


async def _parse_respond_request(
    request: Request,
) -> tuple[RespondRequest, bytes | None]:
    """Parse /v1/respond input from JSON or multipart form."""
    content_type = request.headers.get("content-type", "").lower()
    if "multipart/form-data" in content_type:
        form = await request.form()
        raw_request = form.get("request")
        if not raw_request:
            raise HTTPException(status_code=400, detail="Missing request form field")
        request_payload = RespondRequest.model_validate_json(str(raw_request))
        audio_file = form.get("audio")
        audio_bytes = None
        if isinstance(audio_file, UploadFile):
            audio_bytes = await audio_file.read()
        return request_payload, audio_bytes

    payload = await request.json()
    return RespondRequest.model_validate(payload), None


app = FastAPI(
    title="Gemma 4 Audio Runtime Service",
    description="Local native audio inference daemon for Gemma 4 models",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check endpoint."""
    try:
        engine = get_engine()
        if _warming:
            return HealthResponse(
                status="warming",
                message="Model is warming up, please wait...",
            )
        if not engine.is_loaded():
            return HealthResponse(
                status="error",
                message="Model is not loaded",
            )
        return HealthResponse(
            status="ok",
            message="Service is healthy and ready",
        )
    except RuntimeError:
        if _startup_error:
            return HealthResponse(
                status="error",
                message=f"Startup failed: {_startup_error}",
            )
        if _warming:
            return HealthResponse(
                status="warming",
                message="Service is initializing...",
            )
        return HealthResponse(
            status="error",
            message="Service not initialized",
        )


@app.get("/v1/health", response_model=HealthResponse)
async def v1_health() -> HealthResponse:
    """Compatibility health endpoint for clients probing /v1/health."""
    return await health()


@app.get("/status", response_model=StatusResponse)
async def status() -> StatusResponse:
    """Get service status."""
    try:
        engine = get_engine()
        is_loaded = engine.is_loaded()

        model_info = None
        if is_loaded:
            model_info = ModelInfo(
                model_id=engine.model_id,
                instruction_tuned=True,
                supports_text_input=True,
                supports_audio_input=True,
                supports_image_input=False,
                supports_text_output=True,
                runtime_mode="processor_model",
                status="loaded",
            )

        status_val = "warming" if _warming else ("running" if is_loaded else "error")

        return StatusResponse(
            service="gemma4_audio",
            status=status_val,
            model_loaded=is_loaded,
            model_info=model_info,
            timestamp_ms=int(time.time() * 1000),
        )
    except RuntimeError:
        return StatusResponse(
            service="gemma4_audio",
            status="warming" if _warming else "error",
            model_loaded=False,
            timestamp_ms=int(time.time() * 1000),
        )


@app.get("/v1/models")
async def list_models():
    """List available models."""
    try:
        engine = get_engine()
        return {
            "object": "list",
            "data": [
                {
                    "id": engine.model_id,
                    "object": "model",
                    "owned_by": "google",
                    "instruction_tuned": True,
                    "supports_text_input": True,
                    "supports_audio_input": True,
                    "supports_image_input": False,
                    "supports_text_output": True,
                    "runtime_mode": "processor_model",
                    "status": "loaded" if engine.is_loaded() else "warming",
                }
            ],
        }
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Service not initialized")


@app.post("/v1/respond", response_model=RespondResponse)
async def respond(
    request: Request,
) -> RespondResponse:
    """Generate response from multimodal input (audio and/or text)."""
    try:
        engine = get_engine()

        if not engine.is_loaded():
            raise HTTPException(status_code=503, detail="Model not loaded")

        request_payload, audio_bytes = await _parse_respond_request(request)

        start_time = time.time()

        # Extract audio and text from messages
        audio_array = None
        sample_rate = 16000
        text_content = None

        if audio_bytes is not None:
            try:
                audio_array, sample_rate = audio_from_bytes(audio_bytes)
            except Exception as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Failed to process uploaded audio: {e}",
                )
        else:
            for message in request_payload.messages:
                for content in message.content:
                    if content.type == "audio" and content.path:
                        # Audio referenced by path - load from file
                        audio_path = Path(content.path)
                        try:
                            audio_array, sample_rate = audio_from_file(audio_path)
                        except Exception as e:
                            raise HTTPException(
                                status_code=400,
                                detail=f"Failed to load audio from {content.path}: {e}",
                            )
                    elif content.type == "text" and content.text:
                        text_content = content.text

        if audio_array is None and not text_content:
            raise HTTPException(
                status_code=400, detail="No audio or text content provided"
            )

        # Use provided prompt or build from task
        prompt = text_content or request_payload.system_prompt or "Respond to the audio"

        # Run inference
        try:
            generated_text, duration = engine.respond(
                audio_array
                if audio_array is not None
                else np.zeros(16000, dtype=np.float32),
                sample_rate=sample_rate,
                prompt=prompt,
                task=request_payload.task,
                question=request_payload.question,
                system_prompt=request_payload.system_prompt,
                max_new_tokens=request_payload.max_new_tokens,
                temperature=request_payload.temperature,
                top_p=request_payload.top_p,
                do_sample=request_payload.do_sample,
            )
        except InferenceError as e:
            raise HTTPException(status_code=500, detail=f"Inference failed: {e}")

        total_duration_ms = int((time.time() - start_time) * 1000)

        return RespondResponse(
            model=engine.model_id,
            task=request_payload.task,
            text=generated_text,
            duration_ms=total_duration_ms,
            audio=AudioMetadata(
                sample_rate=sample_rate,
                duration_sec=duration,
            ),
            input_modalities=["text", "audio"] if audio_array is not None else ["text"],
            output_modalities=["text"],
            runtime_mode="processor_model",
            capabilities=Capabilities(
                audio_input="verified" if audio_array is not None else "unknown",
                audio_reasoning="verified" if audio_array is not None else "unknown",
                audio_transcription="verified"
                if audio_array is not None
                else "unknown",
            ),
            generation_config=GenerationConfig(
                max_new_tokens=request_payload.max_new_tokens,
                temperature=request_payload.temperature,
                top_p=request_payload.top_p,
                do_sample=request_payload.do_sample,
            ),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Respond endpoint error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")


def _extract_text_prompt_from_openai_messages(messages: list[dict]) -> str:
    """Extract a text prompt from OpenAI-style chat messages."""
    for message in reversed(messages):
        if str(message.get("role", "")).strip().lower() != "user":
            continue
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
        if isinstance(content, list):
            for item in content:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "text":
                    text = str(item.get("text", "")).strip()
                    if text:
                        return text
    return "Hello"


class ChatCompletionContentPart(BaseModel):
    type: str
    text: str | None = None


class ChatCompletionMessage(BaseModel):
    role: str
    content: str | list[ChatCompletionContentPart]


class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str | None = None
    messages: list[ChatCompletionMessage] = Field(default_factory=list)
    max_tokens: int | None = None
    max_completion_tokens: int | None = None
    temperature: float | None = None
    top_p: float | None = None
    stream: bool = False


@app.post("/v1/chat/completions")
async def chat_completions(payload: ChatCompletionRequest) -> dict:
    """OpenAI-compatible text chat endpoint for Semantic Kernel connectors."""
    try:
        engine = get_engine()
        if not engine.is_loaded():
            raise HTTPException(status_code=503, detail="Model not loaded")

        model = str(payload.model or engine.model_id)
        messages = [message.model_dump(mode="python") for message in payload.messages]

        prompt = _extract_text_prompt_from_openai_messages(messages)
        max_tokens = int(payload.max_tokens or payload.max_completion_tokens or 128)
        temperature_raw = payload.temperature
        top_p_raw = payload.top_p
        if payload.stream:
            raise HTTPException(
                status_code=400,
                detail="Streaming is not supported by gemma4_audio runtime",
            )

        # Text-only path: use 1s silence placeholder expected by the current engine API.
        dummy_audio = np.zeros(16000, dtype=np.float32)
        text, _ = engine.respond(
            dummy_audio,
            sample_rate=16000,
            prompt=prompt,
            max_new_tokens=max_tokens,
            temperature=float(temperature_raw) if temperature_raw is not None else None,
            top_p=float(top_p_raw) if top_p_raw is not None else None,
            do_sample=bool(temperature_raw is not None or top_p_raw is not None),
        )

        now = int(time.time())
        completion_tokens = max(1, len(text) // 4)
        prompt_tokens = max(1, len(prompt) // 4)
        return {
            "id": f"chatcmpl-gemma4-{int(time.time() * 1000)}",
            "object": "chat.completion",
            "created": now,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": text},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"chat/completions error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")


@app.post("/audio/transcribe", response_model=TranscribeResponse)
async def transcribe(
    audio: UploadFile = File(...),
) -> TranscribeResponse:
    """Transcribe audio file."""
    try:
        engine = get_engine()

        if not engine.is_loaded():
            raise HTTPException(status_code=503, detail="Model not loaded")

        start_time = time.time()

        # Read uploaded file
        try:
            file_bytes = await audio.read()
            audio_array, sample_rate = audio_from_bytes(file_bytes)
        except Exception as e:
            raise HTTPException(
                status_code=400, detail=f"Failed to process audio file: {e}"
            )

        # Transcribe
        try:
            text = engine.transcribe(audio_array, sample_rate)
        except InferenceError as e:
            raise HTTPException(status_code=500, detail=f"Transcription failed: {e}")

        duration_sec = get_audio_duration(audio_array, sample_rate)
        duration_ms = int((time.time() - start_time) * 1000)

        return TranscribeResponse(
            text=text,
            duration_ms=duration_ms,
            audio=AudioMetadata(
                sample_rate=sample_rate,
                duration_sec=duration_sec,
            ),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Transcribe endpoint error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")


@app.post("/warmup")
async def warmup():
    """Warmup the model by running a dummy inference."""
    try:
        engine = get_engine()

        if not engine.is_loaded():
            raise HTTPException(status_code=503, detail="Model not loaded")

        # Run a small dummy inference to warm up
        dummy_audio = np.zeros(16000, dtype=np.float32)  # 1 second of silence
        try:
            text, _ = engine.respond(
                dummy_audio,
                sample_rate=16000,
                prompt="Say hello",
                max_new_tokens=10,
            )
            return {"status": "warmed", "sample_output": text}
        except InferenceError as e:
            raise HTTPException(status_code=500, detail=f"Warmup failed: {e}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Warmup error: {e}")
        raise HTTPException(status_code=500, detail=f"Warmup failed: {e}")


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "Gemma 4 Audio Runtime",
        "version": "0.1.0",
        "status": "running",
    }


def configure_logging(log_file: Optional[str] = None, level: int = logging.INFO):
    """Configure logging for the service."""
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    logger.info(f"Logging configured. Level: {logging.getLevelName(level)}")


def run_server(
    host: str = "127.0.0.1",
    port: int = 8014,
    log_file: Optional[str] = None,
):
    """Run the FastAPI server."""
    configure_logging(log_file)

    logger.info(f"Starting Gemma 4 Audio Runtime Service on {host}:{port}")

    uvicorn.run(
        "services.gemma4_audio_runtime.main:app",
        host=host,
        port=port,
        log_level="info",
        reload=False,
    )


if __name__ == "__main__":
    # Get configuration from environment
    host = os.getenv("GEMMA4_AUDIO_HOST", "127.0.0.1")
    port = int(os.getenv("GEMMA4_AUDIO_PORT", "8014"))
    log_file = os.getenv("GEMMA4_AUDIO_LOG_PATH", "logs/gemma4_audio_service.log")

    run_server(host, port, log_file)
