"""Fish Speech native TTS runtime service."""

from __future__ import annotations

import os
import time
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from starlette.responses import Response

from services.fish_speech_runtime.engine import get_engine
from services.fish_speech_runtime.schemas import (
    HealthResponse,
    StatusResponse,
    TtsRequest,
)

_START_TIME = time.time()


def _is_enabled() -> bool:
    return os.getenv("FISH_SPEECH_ENABLED", "false").strip().lower() == "true"


def _runtime_status() -> tuple[str, str]:
    if not _is_enabled():
        return "disabled", "Set FISH_SPEECH_ENABLED=true to enable runtime"
    model_id = os.getenv("FISH_SPEECH_MODEL_ID", "fishaudio/fish-speech-1.5")
    cache_dir = Path(os.getenv("FISH_SPEECH_CACHE_DIR", "models_cache/hf"))
    model_slug = model_id.replace("/", "--")
    expected_cache_prefix = f"models--{model_slug}"
    if not cache_dir.exists():
        return "warming", f"Cache dir missing: {cache_dir}"
    has_cached_model = any(
        path.name.startswith(expected_cache_prefix) for path in cache_dir.iterdir()
    )
    if not has_cached_model:
        return "warming", f"Model cache for {model_id} not found in {cache_dir}"
    engine = get_engine()
    if engine.is_loaded:
        return "ok", "Runtime ready"
    if engine.load_error:
        return "error", engine.load_error
    return "ok", "Runtime ready (model not yet warmed up)"


app = FastAPI(
    title="Fish Speech Native TTS Runtime Service",
    description="Local Fish Speech TTS daemon for Venom",
    version="0.2.0",
)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    status, message = _runtime_status()
    return HealthResponse(status=status, message=message)


@app.get("/status", response_model=StatusResponse)
async def status() -> StatusResponse:
    status_value, _ = _runtime_status()
    return StatusResponse(
        status=status_value,
        model_loaded=get_engine().is_loaded,
        model_id=os.getenv("FISH_SPEECH_MODEL_ID", "fishaudio/fish-speech-1.5"),
        device=os.getenv("FISH_SPEECH_DEVICE", "auto"),
        endpoint=os.getenv("FISH_SPEECH_ENDPOINT", "http://127.0.0.1:8024/v1"),
        timestamp_ms=int(time.time() * 1000),
    )


@app.post("/v1/tts")
async def tts(request: TtsRequest) -> Response:
    status_value, message = _runtime_status()
    if status_value in ("disabled", "warming"):
        raise HTTPException(status_code=503, detail=message)
    if status_value == "error":
        raise HTTPException(status_code=503, detail=message)

    engine = get_engine()
    if not engine.is_loaded:
        loaded = await _load_engine_async(engine)
        if not loaded:
            raise HTTPException(
                status_code=503,
                detail=engine.load_error or "Engine failed to load",
            )

    import asyncio

    try:
        wav_bytes = await asyncio.to_thread(
            engine.synthesize,
            request.text,
            request.language,
            request.sample_rate,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return Response(
        content=wav_bytes,
        media_type="audio/wav",
        headers={"X-Fish-Speech-Language": request.language},
    )


async def _load_engine_async(engine: object) -> bool:
    import asyncio

    return await asyncio.to_thread(engine.load)  # type: ignore[attr-defined]


@app.get("/uptime")
async def uptime() -> dict[str, float]:
    return {"uptime_seconds": time.time() - _START_TIME}


if __name__ == "__main__":
    host = os.getenv("FISH_SPEECH_HOST", "127.0.0.1")
    port = int(os.getenv("FISH_SPEECH_PORT", "8024"))
    uvicorn.run(
        "services.fish_speech_runtime.main:app",
        host=host,
        port=port,
        log_level="info",
        reload=False,
    )
