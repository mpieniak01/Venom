"""Native Ollama speech input and output."""

from __future__ import annotations

import asyncio
import base64
import io
import math
import wave
from collections.abc import Callable
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING, cast
from urllib.parse import urlsplit

import httpx
import numpy as np
from fastapi import HTTPException
from numpy.typing import NDArray

from venom_core.core.model_registry_clients import OllamaClient
from venom_core.core.ollama_runtime_capabilities import is_gemma4_model_name
from venom_core.infrastructure.traffic_control import TrafficControlledHttpClient

if TYPE_CHECKING:
    from venom_core.utils.llm_runtime import LLMRuntimeInfo

OMNI_MODEL_ID = "lfm3-omni:2b"
OMNI_VOICES = {
    "pl": "female-polish",
    "en": "female-american-english",
    "de": "female-german",
}
MAX_AUDIO_BYTES = 25 * 1024 * 1024
MIN_SAMPLE_RATE = 8000
MAX_SAMPLE_RATE = 192000
_POLISH_ASR_PROMPT = "Perform ASR in Polish."
_ASR_UNCERTAIN_SCORE = -0.35
_ASR_RETRY_MARGIN = 0.1
_ASR_RETRY_TIMEOUT_SECONDS = 6.0
_ASR_RETRY_INPUT_RATE = 17280  # 8% faster when resampled to 16 kHz.
type _ResamplePoly = Callable[[NDArray[np.float32], int, int], NDArray[np.float32]]


def allows_native_route(
    *, route_profile: str, decoder_profile: str, decoder_chain: str
) -> bool:
    """Respect explicit host/daemon routes and configured decoder chains."""
    return (
        route_profile.strip().lower()
        not in {"runtime_lokalny", "venom-agent", "gemma4"}
        and decoder_profile.strip().lower() not in {"faster_whisper", "gemma_native"}
        and not decoder_chain.strip()
    )


def _load_resample_poly() -> _ResamplePoly:
    """Type only the optional SciPy API used here; import it on demand."""
    module = import_module("scipy.signal")
    try:
        resampler = module.resample_poly
    except AttributeError as exc:
        # Preserve the missing-name ImportError semantics of a direct import.
        raise ImportError("scipy.signal.resample_poly is unavailable") from exc
    return cast(_ResamplePoly, resampler)


def encode_audio_input(path: Path) -> str:
    """Produce mono PCM16 16 kHz WAV bytes, never a filename or raw PCM."""
    samples, rate = _read_pcm_wav(path)
    return encode_pcm_audio(samples, rate)


def _read_pcm_wav(path: Path) -> tuple[NDArray[np.int16], int]:
    """Validate the container before reading its declared PCM frames."""
    input_size = path.stat().st_size
    if input_size > MAX_AUDIO_BYTES:
        raise ValueError("audio_input_too_large")
    with wave.open(str(path), "rb") as source:
        if source.getnchannels() != 1 or source.getsampwidth() != 2:
            raise ValueError("audio_input_requires_mono_pcm16")
        rate = source.getframerate()
        if not MIN_SAMPLE_RATE <= rate <= MAX_SAMPLE_RATE:
            raise ValueError("audio_input_unsupported_sample_rate")
        frames = source.getnframes()
        if frames * 2 > input_size - 44:
            raise ValueError("audio_input_invalid_frame_count")
        output_frames = (frames * 16000 + rate - 1) // rate
        if output_frames * 2 + 44 > MAX_AUDIO_BYTES:
            raise ValueError("audio_output_too_large")
        samples = np.frombuffer(source.readframes(frames), dtype="<i2")
    if samples.size != frames:
        raise ValueError("audio_input_invalid_frame_count")
    return samples, rate


def encode_pcm_audio(samples: NDArray[np.int16], rate: int) -> str:
    """Encode signed PCM as bounded Base64 WAV at the model's input rate."""
    if samples.size == 0:
        raise ValueError("audio_input_empty")
    if rate != 16000:
        divisor = math.gcd(rate, 16000)
        converted: NDArray[np.float32] | NDArray[np.float64]
        try:
            resample_poly = _load_resample_poly()
            converted = resample_poly(
                samples.astype(np.float32), 16000 // divisor, rate // divisor
            )
        except ImportError:
            target_length = max(1, round(samples.size * 16000 / rate))
            converted = np.interp(
                np.linspace(0, samples.size - 1, target_length),
                np.arange(samples.size),
                samples.astype(np.float32),
            )
        samples = np.clip(np.rint(converted), -32768, 32767).astype("<i2")
    output = io.BytesIO()
    with wave.open(output, "wb") as destination:
        destination.setnchannels(1)
        destination.setsampwidth(2)
        destination.setframerate(16000)
        destination.writeframes(samples.tobytes())
    return base64.b64encode(output.getvalue()).decode("ascii")


async def supports_audio(endpoint: str, model: str) -> bool:
    """Read declared capabilities without loading weights or probing generation."""
    show = await OllamaClient(endpoint).get_model_show(model)
    return is_local_model(show) and "audio" in show.get("capabilities", [])


def is_host_ollama(runtime: LLMRuntimeInfo) -> bool:
    """Identify Ollama runtimes bound to a loopback endpoint on this host."""
    return bool(
        runtime.provider == "ollama"
        and runtime.host_local is not False
        and runtime.endpoint
        and urlsplit(runtime.endpoint).hostname in {"localhost", "127.0.0.1", "::1"}
    )


def is_local_model(show: dict) -> bool:
    """Exclude entries whose model execution resolves to a remote host."""
    return not (show.get("remote_model") or show.get("remote_host"))


def supports_omni_voice(show: dict, language: str) -> bool:
    """Check that the local model handles audio and exposes the requested voice."""
    return (
        is_local_model(show)
        and {"audio", "speech"}.issubset(show.get("capabilities") or [])
        and OMNI_VOICES[language] in (show.get("voices") or [])
    )


async def installed_gemma_models(endpoint: str) -> list[str]:
    """List installed local Gemma 4 tags without loading their weights."""
    client = OllamaClient(endpoint)
    tags = await client.list_tags()
    return sorted(
        {
            entry["name"]
            for entry in tags.get("models", [])
            if isinstance(entry.get("name"), str)
            and is_gemma4_model_name(entry["name"])
            and not entry["name"].lower().endswith("-cloud")
            and is_local_model(entry)
        }
    )


async def has_omni_voice(endpoint: str, language: str) -> bool:
    """Read model metadata to determine native voice availability."""
    show = await OllamaClient(endpoint).get_model_show(OMNI_MODEL_ID)
    return supports_omni_voice(show, language)


async def require_local_capability(endpoint: str, model: str, capability: str) -> dict:
    """Return model metadata only when the capability is available locally."""
    payload = await OllamaClient(endpoint).get_model_show(model)
    if not is_local_model(payload) or capability not in (
        payload.get("capabilities") or []
    ):
        raise RuntimeError("ollama_audio_capability_unavailable")
    return payload


async def transcribe_audio(
    endpoint: str, model: str, path: Path, *, context_length: int = 4096
) -> str:
    """Use the same native ASR request for Full WAV and Studio PCM input."""
    samples, rate = await asyncio.to_thread(_read_pcm_wav, path)
    return await transcribe_pcm_audio(
        endpoint, model, samples.tobytes(), rate, "pl", context_length=context_length
    )


async def transcribe_pcm_audio(
    endpoint: str,
    model: str,
    pcm: bytes,
    rate: int,
    language: str,
    *,
    context_length: int = 4096,
) -> str:
    samples = np.frombuffer(pcm, dtype="<i2")
    if not samples.size:
        raise ValueError("audio_input_empty")
    # Browser scheduling adds variable digital silence at the recording edges.
    # Canonicalize it before resampling so identical speech has identical input.
    # No energy threshold: preserve quiet speech and every pause within the clip.
    samples = np.trim_zeros(samples)
    if not samples.size:
        return ""
    audio = await asyncio.to_thread(encode_pcm_audio, samples, rate)
    language_name = {"pl": "Polish", "en": "English", "de": "German"}[language]
    if is_gemma4_model_name(model):
        prompt = (
            f"Transcribe the following speech segment in {language_name} into "
            f"{language_name} text. Only output the transcription, with no newlines. "
            "Write numbers using digits."
        )
        return await _transcribe(endpoint, model, audio, prompt, context_length)
    # LiquidAI's documented ASR task: system instruction + audio-only user turn.
    return await _transcribe(
        endpoint, model, audio, f"Perform ASR in {language_name}.", context_length
    )


async def _transcribe(
    endpoint: str, model: str, audio: str, prompt: str, context_length: int
) -> str:
    client = OllamaClient(endpoint)
    url = f"{client.endpoint}/api/chat"
    retry_uncertain = model == OMNI_MODEL_ID and prompt == _POLISH_ASR_PROMPT
    payload = {
        "model": model,
        "messages": (
            [{"role": "user", "content": prompt, "images": [audio]}]
            if is_gemma4_model_name(model)
            else [
                {"role": "system", "content": prompt},
                {"role": "user", "content": "", "images": [audio]},
            ]
        ),
        "stream": False,
        "think": False,
        "options": {
            "temperature": 0,
            "num_ctx": context_length,
            "num_predict": 256,
        },
    }
    if retry_uncertain:
        payload["logprobs"] = True

    async with TrafficControlledHttpClient(provider="ollama", timeout=120.0) as http:
        text, confidence = await _request_asr(http, url, payload)
        if (
            not retry_uncertain
            or not text
            or confidence is None
            or confidence >= _ASR_UNCERTAIN_SCORE
        ):
            return text

        # Some Polish word boundaries are sensitive to capture timing. Compare
        # one faster decode of the same audio only when the first is uncertain.
        try:
            async with asyncio.timeout(_ASR_RETRY_TIMEOUT_SECONDS):
                faster_audio = await asyncio.to_thread(_faster_asr_audio, audio)
                retry_payload = {
                    **payload,
                    "messages": [
                        payload["messages"][0],
                        {"role": "user", "content": "", "images": [faster_audio]},
                    ],
                }
                retry_text, retry_confidence = await _request_asr(
                    http, url, retry_payload
                )
        except (HTTPException, httpx.HTTPError, TimeoutError, RuntimeError, ValueError):
            return text

    if (
        retry_text
        and retry_confidence is not None
        and retry_confidence > confidence + _ASR_RETRY_MARGIN
    ):
        return retry_text
    return text


def _faster_asr_audio(encoded: str) -> str:
    with wave.open(io.BytesIO(base64.b64decode(encoded)), "rb") as wav:
        samples = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2")
    return encode_pcm_audio(samples, _ASR_RETRY_INPUT_RATE)


def _asr_confidence(logprobs: object) -> float | None:
    if not isinstance(logprobs, list):
        return None
    scores = []
    for item in logprobs:
        if not isinstance(item, dict):
            continue
        token, value = item.get("token"), item.get("logprob")
        if (
            isinstance(token, str)
            and token.strip(" .,!?")
            and isinstance(value, (float, int))
            and math.isfinite(value)
        ):
            scores.append(float(value))
    if not scores:
        return None
    # A few confidently decoded words can hide an uncertain span in the mean.
    lowest = sorted(scores)[: max(1, len(scores) // 5)]
    return sum(lowest) / len(lowest)


async def _request_asr(
    http: TrafficControlledHttpClient, url: str, payload: dict
) -> tuple[str, float | None]:
    response = await http.apost(url, json=payload, disable_retry=True)
    result = response.json()
    if (
        result.get("error")
        or result.get("done") is not True
        or result.get("done_reason") == "length"
    ):
        raise RuntimeError("ollama_audio_incomplete_response")
    message = result.get("message")
    if not isinstance(message, dict) or not isinstance(message.get("content"), str):
        raise RuntimeError("ollama_audio_invalid_response")
    return message["content"].strip(), _asr_confidence(result.get("logprobs"))


async def synthesize_speech(
    endpoint: str, model: str, text: str, *, voice: str
) -> bytes:
    client = OllamaClient(endpoint)
    body = bytearray()
    async with asyncio.timeout(90):
        async with TrafficControlledHttpClient(provider="ollama", timeout=90.0) as http:
            async with http.astream(
                "POST",
                f"{client.endpoint}/v1/audio/speech",
                json={
                    "model": model,
                    "input": text,
                    "voice": voice,
                    "response_format": "wav",
                },
                disable_retry=True,
            ) as response:
                async for chunk in response.aiter_bytes():
                    if len(body) + len(chunk) > MAX_AUDIO_BYTES:
                        raise ValueError("ollama_speech_too_large")
                    body.extend(chunk)
    # Ollama writes an open-ended length in the streamed RIFF header.
    with wave.open(io.BytesIO(body), "rb") as source:
        if (source.getnchannels(), source.getsampwidth(), source.getframerate()) != (
            1,
            2,
            24000,
        ):
            raise ValueError("ollama_speech_invalid_format")
        pcm = source.readframes(len(body) // 2)
    if not pcm or len(pcm) % 2:
        raise ValueError("ollama_speech_invalid_pcm")
    output = io.BytesIO()
    with wave.open(output, "wb") as destination:
        destination.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
        destination.writeframes(pcm)
    return output.getvalue()
