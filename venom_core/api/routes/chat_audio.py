"""On-demand audio building blocks for the shared text conversation controller."""

import asyncio
from collections.abc import AsyncIterator
from typing import Annotated, Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from starlette.datastructures import FormData, UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

from venom_core.api.dependencies import get_session_store
from venom_core.api.operator_origin import require_operator_origin
from venom_core.api.transport_access import (
    is_localhost_request,
    require_operator_request,
)
from venom_core.config import SETTINGS
from venom_core.services import ollama_audio, omni_pilot
from venom_core.services.background_priority import run_drainable_thread
from venom_core.services.chat_audio import (
    MAX_AUDIO_BYTES,
    complete_audio_work,
    synthesize_wav,
    transcribe_pcm,
    validate_pcm,
)
from venom_core.services.session_store import SessionStore
from venom_core.utils.helpers import get_utc_now_iso
from venom_core.utils.llm_runtime import LLMRuntimeInfo, get_active_llm_runtime

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
    prefer_native: bool = False
    language: Literal["pl", "en", "de"] = "pl"


def _engine(request: Request):
    if is_localhost_request(request):
        require_operator_origin(request, "audio_origin_denied")
    return getattr(request.app.state, "audio_engine", None)


def _native_omni(prefer_native: bool) -> LLMRuntimeInfo | None:
    if not prefer_native:
        return None
    runtime = get_active_llm_runtime()
    if runtime.model_name == ollama_audio.OMNI_MODEL_ID and ollama_audio.is_host_ollama(
        runtime
    ):
        return runtime
    return None


@router.get("/pipelines")
async def voice_pipelines(
    request: Request,
    language: Literal["pl", "en", "de"] = "pl",
    surface: Literal["chat2", "voice"] = "chat2",
):
    """Discover installed choices without loading models or opening the microphone."""
    _engine(request)
    runtime = get_active_llm_runtime()
    active = runtime.model_name if ollama_audio.is_host_ollama(runtime) else None
    result: dict[str, Any] = {
        "active_model": active,
        "gemma_models": [],
        "omni_model": None,
    }
    if active is None:
        return result
    endpoint = runtime.endpoint or ""
    result["gemma_models"] = await ollama_audio.installed_gemma_models(endpoint)
    if surface == "voice" and not ollama_audio.allows_native_route(
        route_profile=SETTINGS.VOICE_ROUTE_PROFILE,
        decoder_profile=SETTINGS.AUDIO_DECODER_PROFILE,
        decoder_chain=SETTINGS.AUDIO_DECODER_CHAIN,
    ):
        return result
    # Full Voice currently has a Polish transcription prompt and voice.
    voice_language = "pl" if surface == "voice" else language
    if await ollama_audio.has_omni_voice(endpoint, voice_language):
        result["omni_model"] = ollama_audio.OMNI_MODEL_ID
    return result


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
    prefer_native: bool = False,
):
    engine = _engine(request)
    runtime = _native_omni(prefer_native)
    if engine is None and runtime is None:
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
    if runtime is not None:
        from venom_core.services.ollama_audio import (
            require_local_capability,
            transcribe_pcm_audio,
        )

        pcm = bytes(content)
        validate_pcm(pcm, sample_rate)
        endpoint = runtime.endpoint or ""

        async def native_transcription():
            await require_local_capability(endpoint, runtime.model_name, "audio")
            return await transcribe_pcm_audio(
                endpoint, runtime.model_name, pcm, sample_rate, language
            )

        try:
            text = await complete_audio_work(native_transcription)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                503, {"reason_code": "audio_transcription_failed"}
            ) from exc
        return {"session_id": session_id, "text": text, "pipeline": "ollama_audio"}
    text = await transcribe_pcm(engine, bytes(content), sample_rate, language)
    return {"session_id": session_id, "text": text, "pipeline": "host_stt"}


class _PilotUploadTooLarge(MultiPartException):
    pass


async def _pilot_upload_stream(request: Request) -> AsyncIterator[bytes]:
    limit = MAX_AUDIO_BYTES + omni_pilot.MAX_IMAGE_BYTES + 16 * 1024
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            raise _PilotUploadTooLarge("omni_pilot_upload_too_large")
        yield chunk


async def _pilot_form(request: Request) -> FormData:
    if (
        request.headers.get("content-type", "").split(";", 1)[0]
        != "multipart/form-data"
    ):
        raise HTTPException(415, {"reason_code": "omni_pilot_multipart_required"})
    try:
        return await MultiPartParser(
            request.headers,
            _pilot_upload_stream(request),
            max_files=2,
            max_fields=3,
            max_part_size=1024,
        ).parse()
    except _PilotUploadTooLarge as exc:
        raise HTTPException(413, {"reason_code": exc.message}) from exc
    except MultiPartException as exc:
        raise HTTPException(422, {"reason_code": "omni_pilot_invalid_form"}) from exc


async def _pilot_inputs(form: FormData) -> tuple[str, int, bytes, bytes | None]:
    session_id = form.get("session_id")
    sample_rate = form.get("sample_rate")
    audio = form.get("audio")
    image = form.get("image")
    if (
        not isinstance(session_id, str)
        or not 1 <= len(session_id.strip()) <= 256
        or form.get("language", "pl") != "pl"
        or not isinstance(sample_rate, str)
        or not sample_rate.isascii()
        or not sample_rate.isdecimal()
        or not 8000 <= int(sample_rate) <= 96000
        or not isinstance(audio, UploadFile)
        or (image is not None and not isinstance(image, UploadFile))
    ):
        raise HTTPException(422, {"reason_code": "omni_pilot_invalid_form"})
    rate = int(sample_rate)
    pcm = await audio.read(MAX_AUDIO_BYTES + 1)
    validate_pcm(pcm, rate)
    image_bytes = None
    if isinstance(image, UploadFile):
        image_bytes = await image.read(omni_pilot.MAX_IMAGE_BYTES + 1)
        try:
            await asyncio.to_thread(omni_pilot.validate_image, image_bytes)
        except ValueError as exc:
            raise HTTPException(
                422, {"reason_code": "omni_pilot_invalid_image"}
            ) from exc
    return session_id, rate, pcm, image_bytes


@router.post(
    "/multimodal-turn",
    responses={
        413: {"description": "Multimodal upload exceeds limits"},
        415: {"description": "Multipart form required"},
        422: {"description": "Invalid image or audio input"},
    },
)
async def multimodal_turn(
    request: Request, store: Annotated[SessionStore, Depends(get_session_store)]
):
    _engine(request)
    runtime = omni_pilot.active_pilot_runtime()
    if runtime is None:
        raise HTTPException(503, {"reason_code": "omni_pilot_unavailable"})
    form = await _pilot_form(request)
    try:
        session_id, rate, pcm, image = await _pilot_inputs(form)
    finally:
        await form.close()
    if await request.is_disconnected():
        raise HTTPException(499, {"reason_code": "audio_request_cancelled"})

    async def run():
        if omni_pilot.active_pilot_runtime() != runtime:
            raise HTTPException(409, {"reason_code": "omni_pilot_runtime_changed"})
        history = store.get_history(session_id, limit=omni_pilot.MAX_HISTORY_ROWS)
        result = await omni_pilot.answer(runtime, pcm, rate, image, history)
        request_id = str(uuid4())
        timestamp = get_utc_now_iso()
        entries = [
            {
                **entry,
                "session_id": session_id,
                "request_id": request_id,
                "timestamp": timestamp,
                "status": "COMPLETED",
            }
            for entry in omni_pilot.conversation_pair(
                result, has_image=image is not None
            )
        ]
        if result.sources:
            entries[-1]["content"] = result.text + "\n\nŹródło: " + result.sources[0]
        if not await request.is_disconnected():
            await run_drainable_thread(
                store.append_turn_once, session_id, request_id, entries
            )
        return {
            "session_id": session_id,
            "text": result.text,
            "sources": result.sources,
        }

    try:
        return await complete_audio_work(run)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, {"reason_code": "omni_pilot_failed"}) from exc


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
    runtime = _native_omni(payload.prefer_native)
    if engine is None and runtime is None:
        raise HTTPException(503, {"reason_code": "audio_not_ready"})
    if not payload.text.strip():
        raise HTTPException(422, {"reason_code": "audio_empty_text"})
    if runtime is None:
        content = await synthesize_wav(engine, payload.text)
    else:
        from venom_core.services.ollama_audio import (
            require_local_capability,
            synthesize_speech,
        )

        endpoint = runtime.endpoint or ""
        voice = ollama_audio.OMNI_VOICES[payload.language]

        async def native_speech():
            show = await require_local_capability(
                endpoint, runtime.model_name, "speech"
            )
            if voice not in (show.get("voices") or []):
                raise RuntimeError("ollama_speech_voice_unavailable")
            return await synthesize_speech(
                endpoint, runtime.model_name, payload.text, voice=voice
            )

        try:
            content = await complete_audio_work(native_speech)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(503, {"reason_code": "audio_synthesis_failed"}) from exc
    return Response(
        content,
        media_type="audio/wav",
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
