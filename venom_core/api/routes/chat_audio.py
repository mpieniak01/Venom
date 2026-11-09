"""On-demand audio building blocks for the shared text conversation controller."""

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from venom_core.api.operator_origin import require_operator_origin
from venom_core.api.transport_access import (
    is_localhost_request,
    require_operator_request,
)
from venom_core.config import SETTINGS
from venom_core.core.model_registry_clients import OllamaClient
from venom_core.services import ollama_audio
from venom_core.services.chat_audio import (
    MAX_AUDIO_BYTES,
    complete_audio_work,
    synthesize_wav,
    transcribe_pcm,
    validate_pcm,
)
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
    client = OllamaClient(runtime.endpoint)
    tags = await client.list_tags()
    result["gemma_models"] = sorted(
        {
            entry["name"]
            for entry in tags.get("models", [])
            if isinstance(entry.get("name"), str)
            and entry["name"].lower().startswith("gemma4")
            and not entry["name"].lower().endswith("-cloud")
            and ollama_audio.is_local_model(entry)
        }
    )
    if surface == "voice" and not ollama_audio.allows_native_route(
        route_profile=SETTINGS.VOICE_ROUTE_PROFILE,
        decoder_profile=SETTINGS.AUDIO_DECODER_PROFILE,
        decoder_chain=SETTINGS.AUDIO_DECODER_CHAIN,
    ):
        return result
    # Full Voice currently has a Polish transcription prompt and voice.
    voice_language = "pl" if surface == "voice" else language
    show = await client.get_model_show(ollama_audio.OMNI_MODEL_ID)
    if ollama_audio.supports_omni_voice(show, voice_language):
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
