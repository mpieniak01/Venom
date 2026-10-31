"""On-demand audio building blocks for the shared text conversation controller."""

from typing import Annotated, Any, Literal

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

AUDIO_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    403: {"description": "Operator access or audio request origin denied"},
    409: {"description": "Shared runtime admission is busy or unavailable"},
    503: {
        "description": "Configured audio is unavailable, processing failed, or synthesized output is invalid"
    },
}

router = APIRouter(
    prefix="/api/v1/chat/audio",
    tags=["chat-audio"],
    responses=AUDIO_ERROR_RESPONSES,
    dependencies=[Depends(require_operator_request)],
)


class ChatSpeechRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=256)
    text: str = Field(min_length=1, max_length=6000)


def _engine(request: Request):
    if is_localhost_request(request):
        require_operator_origin(request, "audio_origin_denied")
    return getattr(request.app.state, "audio_engine", None)


@router.post(
    "/transcribe",
    responses={
        403: AUDIO_ERROR_RESPONSES[403],
        409: AUDIO_ERROR_RESPONSES[409],
        503: AUDIO_ERROR_RESPONSES[503],
        413: {
            "description": "PCM exceeds the upload byte limit or recording duration limit"
        },
        415: {"description": "Raw PCM requires application/octet-stream content type"},
        422: {
            "description": "Invalid request parameters or empty/unaligned signed 16-bit PCM"
        },
        499: {"description": "Client disconnected before transcription was submitted"},
    },
)
async def transcribe(
    request: Request,
    session_id: Annotated[str, Query(min_length=1, max_length=256)],
    sample_rate: Annotated[int, Query(ge=8000, le=96000)] = 16000,
    language: Literal["pl", "en", "de"] = "pl",
):
    engine = _engine(request)
    if engine is None:
        raise HTTPException(503, {"reason_code": "audio_not_ready"})
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


@router.post(
    "/speak",
    responses={
        403: AUDIO_ERROR_RESPONSES[403],
        409: AUDIO_ERROR_RESPONSES[409],
        503: AUDIO_ERROR_RESPONSES[503],
        422: {
            "description": "Invalid speech request or text containing only whitespace"
        },
    },
)
async def speak(request: Request, payload: ChatSpeechRequest):
    engine = _engine(request)
    if engine is None:
        raise HTTPException(503, {"reason_code": "audio_not_ready"})
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
