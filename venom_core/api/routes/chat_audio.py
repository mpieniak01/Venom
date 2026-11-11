"""On-demand audio building blocks for the shared text conversation controller."""

import asyncio
import base64
from collections.abc import AsyncGenerator
from typing import Annotated, Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from starlette.datastructures import FormData, UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

from venom_core.api import omni_native_voice
from venom_core.api.dependencies import get_session_store
from venom_core.api.operator_origin import require_operator_origin
from venom_core.api.transport_access import (
    is_localhost_request,
    require_operator_request,
)
from venom_core.config import SETTINGS
from venom_core.services import ollama_audio, omni_native_dialogue, omni_pilot
from venom_core.services.background_priority import run_drainable_thread
from venom_core.services.chat_audio import (
    MAX_AUDIO_BYTES,
    complete_audio_work,
    decode_pilot_recording,
    synthesize_wav,
    transcribe_pcm,
    validate_pcm,
)
from venom_core.services.omni_native_dialogue import (
    NativeDialogueError,
    NativeDialogueResult,
    NativeMode,
)
from venom_core.services.session_store import SessionStore
from venom_core.utils.helpers import get_utc_now_iso
from venom_core.utils.llm_runtime import LLMRuntimeInfo, get_active_llm_runtime
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

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


class VoicePipelineChoices(BaseModel):
    active_model: str | None
    gemma_models: list[str]
    omni_model: str | None
    native_dialogue_modes: list[NativeMode] = Field(default_factory=list)


class MultimodalVoiceReply(BaseModel):
    session_id: str
    text: str | None
    sources: list[str]
    no_speech: bool = False
    generation_mode: NativeMode | None = None
    audio_base64: str | None = None
    model_revision: str | None = None
    timings_ms: dict[str, int] | None = None
    pipeline_id: str | None = None
    generation_count: int | None = None
    peak_reserved_mib: int | None = None
    has_image: bool | None = None


def _native_contexts(request: Request) -> omni_native_voice.NativeTurnContexts:
    contexts = getattr(request.app.state, "omni_native_contexts", None)
    if contexts is None:
        contexts = omni_native_voice.NativeTurnContexts()
        request.app.state.omni_native_contexts = contexts
    return contexts


def _engine(request: Request):
    if is_localhost_request(request):
        require_operator_origin(request, "audio_origin_denied")
    return getattr(request.app.state, "audio_engine", None)


def _native_omni(prefer_native: bool) -> LLMRuntimeInfo | None:
    """Return the active local Omni runtime when the caller opts in."""
    if not prefer_native:
        return None
    runtime = get_active_llm_runtime()
    if runtime.model_name == ollama_audio.OMNI_MODEL_ID and ollama_audio.is_host_ollama(
        runtime
    ):
        return runtime
    return None


@router.get(
    "/pipelines",
    response_model=VoicePipelineChoices,
    response_model_exclude_unset=True,
)
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
    if voice_language == "pl" and omni_native_dialogue.native_dialogue_available(
        runtime
    ):
        result["native_dialogue_modes"] = omni_native_voice.MODES
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
    """Transcribe bounded PCM using the selected local or host decoder."""
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
    pcm = bytes(content)
    if runtime is not None:
        from venom_core.services.ollama_audio import (
            require_local_capability,
            transcribe_pcm_audio,
        )

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
        has_text = bool(text.strip())
        logger.info(
            "chat_audio_transcription pipeline=ollama_audio has_text={}", has_text
        )
        return {"session_id": session_id, "text": text, "pipeline": "ollama_audio"}
    text = await transcribe_pcm(engine, pcm, sample_rate, language)
    logger.info(
        "chat_audio_transcription pipeline=host_stt has_text={}", bool(text.strip())
    )
    return {"session_id": session_id, "text": text, "pipeline": "host_stt"}


class _PilotUploadTooLarge(MultiPartException):
    pass


async def _pilot_upload_stream(request: Request) -> AsyncGenerator[bytes, None]:
    """Bound total multipart bytes before the parser spools individual parts."""
    limit = MAX_AUDIO_BYTES + omni_pilot.MAX_IMAGE_BYTES + 16 * 1024
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            raise _PilotUploadTooLarge("omni_pilot_upload_too_large")
        yield chunk


async def _pilot_form(request: Request) -> FormData:
    """Parse the pilot's bounded multipart upload and classify input failures."""
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
            max_fields=4,
            max_part_size=1024,
        ).parse()
    except _PilotUploadTooLarge as exc:
        raise HTTPException(413, {"reason_code": exc.message}) from exc
    except MultiPartException as exc:
        raise HTTPException(422, {"reason_code": "omni_pilot_invalid_form"}) from exc


async def _pilot_inputs(form: FormData) -> tuple[str, int, bytes, bytes | None]:
    """Validate the session, Polish audio format, and optional image."""
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
    image_bytes = None
    if isinstance(image, UploadFile):
        image_bytes = await image.read(omni_pilot.MAX_IMAGE_BYTES + 1)
        try:
            await asyncio.to_thread(omni_pilot.validate_image, image_bytes)
        except ValueError as exc:
            raise HTTPException(
                422, {"reason_code": "omni_pilot_invalid_image"}
            ) from exc
    pcm = await audio.read(MAX_AUDIO_BYTES + 1)
    media_type = (audio.content_type or "").split(";", 1)[0].strip().lower()
    if media_type != "application/octet-stream":
        input_format = omni_native_voice.PILOT_AUDIO_FORMATS.get(media_type)
        if input_format is None:
            raise HTTPException(422, {"reason_code": "audio_invalid_recording"})
        pcm, rate = await run_drainable_thread(
            decode_pilot_recording, pcm, input_format
        )
    validate_pcm(pcm, rate)
    return session_id, rate, pcm, image_bytes


async def _await_native_turn(
    request: Request,
    runtime: LLMRuntimeInfo,
    pcm: bytes,
    rate: int,
    image: bytes | None,
    history: list[dict[str, object]],
    mode: NativeMode,
) -> NativeDialogueResult:
    """Cancel the owned generator and wait for cleanup if the client disappears."""
    worker = asyncio.create_task(
        omni_native_voice.run_turn(runtime, pcm, rate, image, history, mode)
    )
    disconnect = asyncio.create_task(omni_native_voice.wait_for_disconnect(request))
    try:
        done, _ = await asyncio.wait(
            {worker, disconnect}, return_when=asyncio.FIRST_COMPLETED
        )
        if disconnect in done:
            raise HTTPException(499, {"reason_code": "audio_request_cancelled"})
        return worker.result()
    finally:
        for task in (worker, disconnect):
            if not task.done():
                task.cancel()
        await asyncio.gather(worker, disconnect, return_exceptions=True)


async def _native_multimodal_turn(
    request: Request,
    store: SessionStore,
    runtime: LLMRuntimeInfo,
    session_id: str,
    rate: int,
    pcm: bytes,
    image: bytes | None,
    mode: NativeMode,
) -> dict[str, Any]:
    if not omni_native_dialogue.native_dialogue_available(runtime):
        raise HTTPException(503, {"reason_code": "omni_native_unavailable"})
    contexts = _native_contexts(request)
    with contexts.turn(session_id):
        retained_image, retained, retained_request_id = contexts.inputs(
            session_id, runtime, mode, image
        )
        rows = store.get_history(session_id, limit=omni_pilot.MAX_HISTORY_ROWS)
        if retained_request_id is not None and not any(
            row.get("request_id") == retained_request_id for row in rows
        ):
            # Both session clearing paths remove the marker for this in-memory turn.
            contexts.discard(session_id)
            retained_image, retained, retained_request_id = image, [], None
        image = retained_image
        history = omni_native_voice.text_context(rows, retained, retained_request_id)
        try:
            result = await _await_native_turn(
                request, runtime, pcm, rate, image, history, mode
            )
        except NativeDialogueError as exc:
            status = {
                "omni_native_gpu_busy": 409,
                "audio_too_large": 413,
                "omni_native_invalid_input": 422,
                "omni_native_timeout": 504,
            }.get(exc.reason_code, 503)
            raise HTTPException(status, {"reason_code": exc.reason_code}) from exc
        if result.no_speech:
            return {
                "session_id": session_id,
                "text": None,
                "sources": [],
                "generation_mode": mode,
                "no_speech": True,
                "pipeline_id": omni_native_voice.PIPELINE,
                "generation_count": 0,
            }
        if not result.wav:
            raise HTTPException(503, {"reason_code": "omni_native_failed"})
        if await request.is_disconnected():
            raise HTTPException(499, {"reason_code": "audio_request_cancelled"})
        request_id = await omni_native_voice.persist_turn(
            store, session_id, mode, result.text
        )
        if mode == "interleaved" and result.text:
            contexts.remember(
                session_id,
                runtime,
                image,
                pcm,
                rate,
                result.text,
                request_id=request_id,
            )
        return {
            "session_id": session_id,
            "text": result.text,
            "sources": [],
            "generation_mode": mode,
            "audio_base64": base64.b64encode(result.wav).decode("ascii"),
            "model_revision": result.model_revision,
            "timings_ms": result.timings_ms,
            "pipeline_id": omni_native_voice.PIPELINE,
            "generation_count": result.generation_count,
            "peak_reserved_mib": result.peak_reserved_mib,
            "has_image": image is not None,
        }


@router.post(
    "/multimodal-turn",
    response_model=MultimodalVoiceReply,
    response_model_exclude_unset=True,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": ["session_id", "sample_rate", "audio"],
                        "properties": {
                            "session_id": {"type": "string"},
                            "sample_rate": {
                                "type": "integer",
                                "minimum": 8000,
                                "maximum": 96000,
                            },
                            "language": {
                                "type": "string",
                                "enum": ["pl"],
                                "default": "pl",
                            },
                            "audio": {"type": "string", "format": "binary"},
                            "image": {"type": "string", "format": "binary"},
                            "generation_mode": {
                                "type": "string",
                                "enum": list(omni_native_voice.MODES),
                            },
                        },
                    },
                },
            },
        },
    },
    responses={
        413: {"description": "Multimodal upload exceeds limits"},
        415: {"description": "Multipart form required"},
        422: {"description": "Invalid image or audio input"},
        499: {"description": "Client disconnected before the pilot turn was submitted"},
        503: {"description": "Local Omni is unavailable or the pilot turn failed"},
        504: {"description": "Native Omni generation timed out"},
    },
)
async def multimodal_turn(
    request: Request, store: Annotated[SessionStore, Depends(get_session_store)]
):
    """Answer one pilot turn and append the completed pair to session history."""
    _engine(request)
    runtime = omni_pilot.active_pilot_runtime()
    form = await _pilot_form(request)
    try:
        if len(form.getlist("generation_mode")) > 1:
            raise HTTPException(422, {"reason_code": "omni_native_invalid_input"})
        mode = omni_native_voice.parse_mode(form.get("generation_mode"))
        if runtime is None:
            reason = (
                "omni_pilot_unavailable" if mode is None else "omni_native_unavailable"
            )
            raise HTTPException(503, {"reason_code": reason})
        session_id, rate, pcm, image = await _pilot_inputs(form)
    finally:
        await form.close()
    if await request.is_disconnected():
        raise HTTPException(499, {"reason_code": "audio_request_cancelled"})
    if mode is not None:
        return await _native_multimodal_turn(
            request, store, runtime, session_id, rate, pcm, image, mode
        )

    async def run():
        """Recheck the runtime under admission and persist only connected turns."""
        if omni_pilot.active_pilot_runtime() != runtime:
            raise HTTPException(409, {"reason_code": "omni_pilot_runtime_changed"})
        history = store.get_history(session_id, limit=omni_pilot.MAX_HISTORY_ROWS)
        result = await omni_pilot.answer(runtime, pcm, rate, image, history)
        if result.no_speech:
            return {
                "session_id": session_id,
                "text": result.text,
                "sources": (),
                "no_speech": True,
            }
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
        if not await request.is_disconnected():
            await run_drainable_thread(
                store.append_turn_once, session_id, request_id, entries
            )
        return {
            "session_id": session_id,
            "text": result.text,
            "sources": result.sources,
        }

    contexts = _native_contexts(request)
    try:
        with contexts.turn(session_id):
            contexts.discard(session_id)
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
    """Synthesize a WAV using the opted-in local voice or the host audio engine."""
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
            """Check the requested voice before asking Ollama to synthesize it."""
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
