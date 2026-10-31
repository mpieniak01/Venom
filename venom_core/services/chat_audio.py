"""Bounded STT/TTS using the host's existing models, never another LLM route."""

import asyncio
import io
import wave
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any

from fastapi import HTTPException

from venom_core.services.runtime_admission import get_runtime_admission

MAX_AUDIO_BYTES = 8 * 1024 * 1024
MAX_AUDIO_SECONDS = 60


async def complete_audio_work[T](factory: Callable[[], Awaitable[T]]) -> T:
    """Hold admission through real native completion even if HTTP is cancelled."""
    worker: asyncio.Task[T] | None = None
    with get_runtime_admission().operation(
        kind="chat_audio", confirm_quiescent=lambda: worker is None or worker.done()
    ):

        async def execute() -> T:
            return await factory()

        worker = asyncio.create_task(execute())
        try:
            return await asyncio.shield(worker)
        except asyncio.CancelledError:
            while not worker.done():
                with suppress(asyncio.CancelledError):
                    try:
                        await asyncio.shield(worker)
                    except Exception:
                        break
            if not worker.cancelled():
                worker.exception()
            raise


async def transcribe_pcm(
    engine: Any, content: bytes, sample_rate: int, language: str
) -> str:
    if not content or len(content) % 2:
        raise HTTPException(422, {"reason_code": "audio_invalid_pcm"})
    if len(content) > min(MAX_AUDIO_BYTES, sample_rate * MAX_AUDIO_SECONDS * 2):
        raise HTTPException(413, {"reason_code": "audio_too_large"})
    # NumPy is imported only on an explicit audio request, not by the route registry.
    import numpy as np

    pcm = np.frombuffer(content, dtype="<i2")
    try:
        result = await complete_audio_work(
            lambda: engine.transcribe_checked(
                pcm, language=language, sample_rate=sample_rate
            )
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, {"reason_code": "audio_transcription_failed"}) from exc
    return str(result).strip()


async def synthesize_wav(engine: Any, text: str) -> bytes:
    try:
        audio = await complete_audio_work(lambda: engine.speak(text))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, {"reason_code": "audio_synthesis_failed"}) from exc
    if audio is None or getattr(
        getattr(engine, "voice", None), "is_fallback_mode", False
    ):
        raise HTTPException(503, {"reason_code": "audio_synthesis_failed"})
    sample_rate = int(
        getattr(getattr(engine, "voice", None), "output_sample_rate", 22050)
    )
    if not 8000 <= sample_rate <= 96000:
        raise HTTPException(503, {"reason_code": "audio_invalid_output"})
    raw = (
        bytes(audio)
        if isinstance(audio, (bytes, bytearray, memoryview))
        else audio.astype("<i2", copy=False).tobytes()
    )
    if not raw or len(raw) % 2 or len(raw) > 32 * 1024 * 1024:
        raise HTTPException(503, {"reason_code": "audio_invalid_output"})
    output = io.BytesIO()
    with wave.open(output, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(sample_rate)
        stream.writeframes(raw)
    return output.getvalue()
