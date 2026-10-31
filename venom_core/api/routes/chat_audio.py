"""On-demand audio building blocks for the shared text conversation controller."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from venom_core.api.operator_origin import require_operator_origin
from venom_core.api.transport_access import (
    is_localhost_request,
    require_operator_request,
)
from venom_core.services.chat_audio import (
    MAX_AUDIO_BYTES,
    synthesize_wav,
    transcribe_pcm,
)

router = APIRouter(
    prefix="/api/v1/chat/audio",
    tags=["chat-audio"],
    dependencies=[Depends(require_operator_request)],
)


class ChatSpeechRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=256)
    text: str = Field(min_length=1, max_length=6000)


def _engine(request: Request):
    if is_localhost_request(request):
        require_operator_origin(request, "audio_origin_denied")
    engine = getattr(request.app.state, "audio_engine", None)
    if engine is None:
        raise HTTPException(503, {"reason_code": "audio_not_ready"})
    return engine


@router.post("/transcribe")
async def transcribe(
    request: Request,
    session_id: str = Query(min_length=1, max_length=256),
    sample_rate: int = Query(default=16000, ge=8000, le=96000),
    language: Literal["pl", "en", "de"] = "pl",
):
    engine = _engine(request)
    if (
        request.headers.get("content-type", "").split(";", 1)[0]
        != "application/octet-stream"
    ):
        raise HTTPException(415, {"reason_code": "audio_pcm_required"})
    declared = request.headers.get("content-length", "")
    if declared.isdecimal() and int(declared) > MAX_AUDIO_BYTES:
        raise HTTPException(413, {"reason_code": "audio_too_large"})
    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > MAX_AUDIO_BYTES:
            raise HTTPException(413, {"reason_code": "audio_too_large"})
        content.extend(chunk)
    if await request.is_disconnected():
        raise HTTPException(499, {"reason_code": "audio_request_cancelled"})
    text = await transcribe_pcm(engine, bytes(content), sample_rate, language)
    return {"session_id": session_id, "text": text, "pipeline": "host_stt"}


@router.post("/speak")
async def speak(request: Request, payload: ChatSpeechRequest):
    engine = _engine(request)
    if not payload.text.strip():
        raise HTTPException(422, {"reason_code": "audio_empty_text"})
    content = await synthesize_wav(engine, payload.text)
    return Response(
        content,
        media_type="audio/wav",
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
