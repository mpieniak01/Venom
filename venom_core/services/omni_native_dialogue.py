"""Experimental, one-generation Omni speech in a bounded local CUDA worker."""

from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import signal
import sys
import wave
from contextlib import suppress
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Literal

import numpy as np

from venom_core.services import ollama_audio
from venom_core.services.omni_pilot import MAX_IMAGE_BYTES
from venom_core.utils.llm_runtime import LLMRuntimeInfo

NativeMode = Literal["audio", "interleaved"]
NATIVE_MODES: tuple[NativeMode, ...] = ("interleaved", "audio")
NATIVE_MODEL_REVISION = "21d75123f86c1f7ffb4bef1ea202710c4e7ebe67"
_WORKER_SCRIPT = (
    Path(__file__).resolve().parents[2] / "scripts" / "llm" / "omni_native_sandbox.sh"
)
_SNAPSHOT_MANIFEST = _WORKER_SCRIPT.with_name("omni_native_snapshot.json")
_WORKER_TIMEOUT_SECONDS = 90
_MAX_TURN_SECONDS = 30
_MAX_HISTORY_ROWS = 6
_MAX_HISTORY_AUDIO_SECONDS = 30
_MAX_HISTORY_CHARS = 1000
_MAX_WAV_BYTES = 2 * 1024 * 1024
_TIMINGS = {"load", "prepare", "generate", "decode"}
_WORKER_ERRORS = {
    "omni_native_snapshot_invalid",
    "omni_native_cuda_unavailable",
    "omni_native_gpu_busy",
    "omni_native_context_too_large",
    "omni_native_no_audio",
}
_GENERATION_LOCK = asyncio.Lock()


class NativeDialogueError(RuntimeError):
    """The worker has exited or never started; reason is safe for clients."""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


@dataclass(frozen=True)
class NativeDialogueResult:
    mode: NativeMode
    text: str | None
    wav: bytes | None
    no_speech: bool
    timings_ms: dict[str, int]
    model_revision: str = NATIVE_MODEL_REVISION
    generation_count: int = 0
    peak_reserved_mib: int | None = None


@lru_cache(maxsize=1)
def _snapshot_files() -> tuple[str, ...]:
    return tuple(json.loads(_SNAPSHOT_MANIFEST.read_text(encoding="utf-8"))["files"])


def _configured_snapshot(runtime: LLMRuntimeInfo) -> Path | None:
    setting = os.getenv("OMNI_NATIVE_SNAPSHOT")
    if (
        not setting
        or not sys.platform.startswith("linux")
        or runtime.model_name != ollama_audio.OMNI_MODEL_ID
        or not ollama_audio.is_host_ollama(runtime)
    ):
        return None
    snapshot = Path(setting)
    if not snapshot.is_absolute():
        return None
    try:
        snapshot = snapshot.resolve(strict=True)
        # Match the sandbox mount rules. A Hub cache snapshot needs to be materialized.
        for name in _snapshot_files():
            path = snapshot / name
            if path.resolve(strict=True) != path or not path.is_file():
                return None
    except (OSError, RuntimeError):
        return None
    return snapshot


def native_dialogue_available(runtime: LLMRuntimeInfo) -> bool:
    """Report local opt-in without loading weights or probing generation."""
    return _configured_snapshot(runtime) is not None


def _media(pcm: bytes, sample_rate: int, image: bytes | None) -> dict[str, Any]:
    if (
        not 8000 <= sample_rate <= 96000
        or not pcm
        or len(pcm) % 2
        or (image is not None and len(image) > MAX_IMAGE_BYTES)
    ):
        raise NativeDialogueError("omni_native_invalid_input")
    if len(pcm) > sample_rate * _MAX_TURN_SECONDS * 2:
        raise NativeDialogueError("audio_too_large")
    return {
        "pcm": base64.b64encode(pcm).decode("ascii"),
        "sample_rate": sample_rate,
        "image": base64.b64encode(image).decode("ascii") if image else None,
    }


def _history_sample_rate(row: dict[str, object]) -> int:
    rate = row.get("sample_rate")
    if type(rate) is not int or rate < 8000:
        raise NativeDialogueError("omni_native_invalid_input")
    return rate


def _history(rows: list[dict[str, object]]) -> list[dict[str, Any]]:
    encoded: list[dict[str, Any]] = []
    audio_seconds = 0.0
    for row in reversed(rows[-_MAX_HISTORY_ROWS:]):
        role, pcm = row.get("role"), row.get("pcm")
        if role not in ("user", "assistant"):
            continue
        if role == "user" and isinstance(pcm, bytes):
            rate, image = _history_sample_rate(row), row.get("image")
            audio_seconds += len(pcm) / (2 * rate)
            if audio_seconds > _MAX_HISTORY_AUDIO_SECONDS:
                break
            encoded.append(
                {
                    "role": role,
                    **_media(pcm, rate, image if isinstance(image, bytes) else None),
                }
            )
        elif isinstance(content := row.get("content"), str) and content.strip():
            encoded.append({"role": role, "content": content[:_MAX_HISTORY_CHARS]})
    return list(reversed(encoded))


def _silence(pcm: bytes) -> bool:
    samples = np.frombuffer(pcm, dtype="<i2")
    return int(np.max(np.abs(samples.astype(np.int32)))) < 64


async def _finish[T](task: asyncio.Task[T]) -> T:
    """Join work even when the caller is cancelled again during cleanup."""
    while True:
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            if task.cancelled():
                raise


async def _terminate(
    worker: asyncio.subprocess.Process,
    exchange: asyncio.Task[tuple[bytes, bytes]] | None,
) -> None:
    try:
        if worker.returncode is None:
            with suppress(ProcessLookupError):
                os.killpg(worker.pid, signal.SIGKILL)
        if exchange is None:
            exchange = asyncio.create_task(worker.communicate())
        await _finish(exchange)
    except OSError as exc:
        # A cleanup error has no quiescence proof and must reach host admission.
        raise RuntimeError("omni_native_cleanup_failed") from exc


async def _invoke(snapshot: Path, payload: bytes) -> bytes:
    with TemporaryDirectory(prefix="venom-omni-native-") as sandbox:
        start = asyncio.create_task(
            asyncio.create_subprocess_exec(
                "/usr/bin/unshare",
                "--user",
                "--map-root-user",
                "--mount",
                "--net",
                "--pid",
                "--fork",
                "--kill-child=SIGKILL",
                "--propagation",
                "private",
                "/bin/bash",
                str(_WORKER_SCRIPT),
                str(snapshot),
                sandbox,
                sys.prefix,
                sys.base_prefix,
                sys.executable,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                start_new_session=True,
            )
        )
        worker = None
        exchange = None
        try:
            async with asyncio.timeout(_WORKER_TIMEOUT_SECONDS):
                worker = await asyncio.shield(start)
                exchange = asyncio.create_task(worker.communicate(payload))
                output, _ = await asyncio.shield(exchange)
        except BaseException:
            # Creation can finish after cancellation. Reap that process too.
            if worker is None:
                with suppress(OSError):
                    worker = await _finish(start)
            if worker is not None:
                await _terminate(worker, exchange)
            raise
        if worker.returncode != 0:
            raise NativeDialogueError("omni_native_worker_failed")
        return output


def _valid_wav(encoded: str) -> bytes:
    if len(encoded) > (_MAX_WAV_BYTES * 4 + 2) // 3:
        raise ValueError("native audio too large")
    wav = base64.b64decode(encoded, validate=True)
    with wave.open(io.BytesIO(wav), "rb") as source:
        if (
            (source.getnchannels(), source.getsampwidth(), source.getframerate())
            != (1, 2, 24000)
            or source.getnframes() < 1
            or len(source.readframes(source.getnframes())) != source.getnframes() * 2
        ):
            raise ValueError("native audio invalid")
    return wav


def _result(output: bytes, mode: NativeMode) -> NativeDialogueResult:
    try:
        data = json.loads(output)
        if data.get("error") in _WORKER_ERRORS:
            raise NativeDialogueError(data["error"])
        timing = data["timings_ms"]
        peak = data["peak_reserved_mib"]
        text = data["text"]
        if (
            data["model_revision"] != NATIVE_MODEL_REVISION
            or data["generation_count"] != 1
            or set(timing) != _TIMINGS
            or any(type(value) is not int or value < 0 for value in timing.values())
            or type(peak) is not int
            or peak < 1
            or (text is not None and not isinstance(text, str))
            or (mode == "audio" and text is not None)
            or (mode == "interleaved" and not text)
        ):
            raise ValueError("native result invalid")
        wav = _valid_wav(data["wav"])
    except (
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
        EOFError,
        wave.Error,
    ) as exc:
        raise NativeDialogueError("omni_native_invalid_output") from exc
    return NativeDialogueResult(
        mode,
        text,
        wav,
        False,
        timing,
        generation_count=1,
        peak_reserved_mib=peak,
    )


async def generate_native_turn(
    runtime: LLMRuntimeInfo,
    pcm: bytes,
    sample_rate: int,
    image: bytes | None,
    history: list[dict[str, object]],
    *,
    mode: NativeMode,
) -> NativeDialogueResult:
    """Caller holds host admission until the isolated GPU process is reaped."""
    snapshot = _configured_snapshot(runtime)
    if snapshot is None:
        raise NativeDialogueError("omni_native_unavailable")
    if mode not in NATIVE_MODES:
        raise NativeDialogueError("omni_native_invalid_input")
    current = _media(pcm, sample_rate, image)
    if _silence(pcm):
        return NativeDialogueResult(mode, None, None, True, {})
    payload = json.dumps(
        {**current, "mode": mode, "history": _history(history)},
        ensure_ascii=False,
    ).encode("utf-8")
    if _GENERATION_LOCK.locked():
        raise NativeDialogueError("omni_native_gpu_busy")
    try:
        async with _GENERATION_LOCK:
            output = await _invoke(snapshot, payload)
    except TimeoutError as exc:
        raise NativeDialogueError("omni_native_timeout") from exc
    except OSError as exc:
        raise NativeDialogueError("omni_native_worker_failed") from exc
    return _result(output, mode)
