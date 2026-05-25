"""Moduł: audio_stream - WebSocket endpoint dla streamingu audio."""

import asyncio
import base64
import hashlib
import importlib.util
import inspect
import json
import shutil
import subprocess
import time
import uuid
import wave
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, TypedDict

import anyio
import httpx
import numpy as np
from fastapi import WebSocket, WebSocketDisconnect

from venom_core.config import SETTINGS
from venom_core.perception.audio_engine import AudioEngine
from venom_core.services.multi_runtime_models import multi_runtime_available_models
from venom_core.services.runtime_switch_gate import (
    assert_runtime_request_allowed,
    get_runtime_switch_gate_status,
    runtime_request_guard,
)
from venom_core.utils.llm_runtime import get_active_llm_runtime
from venom_core.utils.logger import get_logger
from venom_core.utils.mode_contracts import (
    VOICE_EXECUTION_CONTEXT,
    VOICE_HISTORY_SCOPE,
    mode_contracts_payload,
)
from venom_core.utils.runtime_names import MULTI_RUNTIME_ID, is_multi_runtime
from venom_core.utils.voice_metadata import (
    build_voice_session_insights,
    build_voice_trace_annotations,
    infer_voice_session_mode,
)

logger = get_logger(__name__)


def _detect_project_root() -> Path:
    this_file = Path(__file__).resolve()
    for parent in this_file.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return Path.cwd()


PROJECT_ROOT = _detect_project_root()
VOICE_SESSION_ROOT = PROJECT_ROOT / "data" / "audio" / "voice_sessions"
MIN_VOICE_SESSION_DURATION_SEC = 0.25
VOICE_SESSION_WAV_FILENAME = "recording.wav"
VOICE_SESSION_METADATA_FILENAME = "metadata.json"
GEMMA4_AUDIO_HEALTH_TIMEOUT_SEC = 5.0
GEMMA4_AUDIO_REQUEST_TIMEOUT_SEC = 120.0
_VOICE_ROUTE_PROFILES = {
    "auto",
    "gemma4",
    "runtime_lokalny",
    "venom-agent",
    "chat_tekstowy",
}
_AUDIO_DECODER_ALIASES = {
    "gemma_native": "gemma_native",
    "native_audio": "gemma_native",
    "multi_runtime": "gemma_native",
    "faster_whisper": "faster_whisper",
    "whisper": "faster_whisper",
    "stt_whisper": "faster_whisper",
}
_AUDIO_DECODER_PROFILES = {
    "auto",
    "gemma_native",
    "faster_whisper",
    "hybrid",
}


def _load_voice_session_metadata(metadata_path: Path) -> dict[str, Any]:
    if not metadata_path.exists():
        return {}
    try:
        return json.loads(metadata_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _is_voice_session_eligible(metadata: dict[str, Any]) -> bool:
    duration_sec = metadata.get("duration_sec")
    samples = metadata.get("samples")
    try:
        if (
            duration_sec is not None
            and float(duration_sec) < MIN_VOICE_SESSION_DURATION_SEC
        ):
            return False
    except Exception:
        pass
    try:
        if samples is not None and int(samples) < 4096:
            return False
    except Exception:
        pass
    return True


def _build_voice_session_record(
    session_dir: Path, metadata: dict[str, Any]
) -> dict[str, Any]:
    voice_pipeline_mode = metadata.get("voice_pipeline_mode")
    pipeline_id = metadata.get("pipeline_id")
    decoder_source = metadata.get("decoder_source")
    native_audio_ms = metadata.get("native_audio_ms")
    execution_trace = metadata.get("execution_trace") or []
    transcription = _coerce_str(metadata.get("transcription"), "")
    transcription_used_for_generation = _coerce_str(
        metadata.get("transcription_used_for_generation"),
        transcription,
    )
    trace_inconsistent = _resolve_trace_inconsistent_flag(
        metadata=metadata,
        transcription=transcription,
        transcription_used_for_generation=transcription_used_for_generation,
    )
    return {
        "session_id": session_dir.name,
        "created_at": metadata.get("created_at"),
        "duration_sec": metadata.get("duration_sec"),
        "sample_rate": metadata.get("sample_rate"),
        "input_format": metadata.get("input_format"),
        "mime_type": metadata.get("mime_type"),
        "voice_mode": metadata.get("voice_mode") or "standard",
        "gain_applied": metadata.get("gain_applied"),
        "peak_before_normalization": metadata.get("peak_before_normalization"),
        "dc_offset": metadata.get("dc_offset"),
        "rms_before_normalization": metadata.get("rms_before_normalization"),
        "rms_after_normalization": metadata.get("rms_after_normalization"),
        "peak_after_normalization": metadata.get("peak_after_normalization"),
        "timings_ms": metadata.get("timings_ms") or {},
        "runtime": metadata.get("runtime") or {},
        "pipeline_id": metadata.get("pipeline_id"),
        "voice_pipeline_mode": metadata.get("voice_pipeline_mode"),
        "audio_runtime_provider": metadata.get("audio_runtime_provider"),
        "audio_runtime_model": metadata.get("audio_runtime_model"),
        "audio_input_status": metadata.get("audio_input_status"),
        "decoder_source": metadata.get("decoder_source"),
        "voice_route_profile": metadata.get("voice_route_profile"),
        "audio_decoder_profile": metadata.get("audio_decoder_profile"),
        "audio_decoder_chain": metadata.get("audio_decoder_chain") or [],
        "decoder_selected": metadata.get("decoder_selected"),
        "decoder_effective": metadata.get("decoder_effective"),
        "decoder_fallback_reason": metadata.get("decoder_fallback_reason"),
        "fallback_reason": metadata.get("fallback_reason"),
        "native_audio_ms": metadata.get("native_audio_ms"),
        "voice_session_mode": metadata.get("voice_session_mode")
        or infer_voice_session_mode(
            voice_pipeline_mode=voice_pipeline_mode,
            pipeline_id=pipeline_id,
            decoder_source=decoder_source,
            native_audio_ms=native_audio_ms,
        ),
        "runtime_log_path": metadata.get("runtime_log_path"),
        "reasoning_summary_enabled": metadata.get("reasoning_summary_enabled"),
        "reasoning_summary_status": metadata.get("reasoning_summary_status"),
        "reasoning_summary": metadata.get("reasoning_summary"),
        "raw_thinking_available": metadata.get("raw_thinking_available"),
        "emotion_detection_enabled": metadata.get("emotion_detection_enabled"),
        "emotion_response_style_enabled": metadata.get(
            "emotion_response_style_enabled"
        ),
        "emotion_source": metadata.get("emotion_source"),
        "emotion_label": metadata.get("emotion_label"),
        "emotion_confidence": metadata.get("emotion_confidence"),
        "transcription": transcription,
        "transcription_used_for_generation": transcription_used_for_generation,
        "trace_inconsistent": trace_inconsistent,
        "request_id": _coerce_str(metadata.get("request_id"), ""),
        "trace_id": _coerce_str(metadata.get("trace_id"), ""),
        "audio_hash": _coerce_str(metadata.get("audio_hash"), ""),
        "response_text": metadata.get("response_text") or "",
        "execution_trace": execution_trace,
        "execution_trace_annotations": metadata.get("execution_trace_annotations")
        or build_voice_trace_annotations(
            execution_trace,
            voice_pipeline_mode=voice_pipeline_mode,
            pipeline_id=pipeline_id,
            decoder_source=decoder_source,
            native_audio_ms=native_audio_ms,
        ),
        "execution_trace_mode": metadata.get("execution_trace_mode")
        or (
            "audio_only"
            if infer_voice_session_mode(
                voice_pipeline_mode=voice_pipeline_mode,
                pipeline_id=pipeline_id,
                decoder_source=decoder_source,
                native_audio_ms=native_audio_ms,
            )
            != "unknown"
            else "unknown"
        ),
        "selected_policy": metadata.get("selected_policy"),
        "selected_image_strategy": metadata.get("selected_image_strategy"),
        "retrieval_used": metadata.get("retrieval_used"),
        "retrieval_context_items": metadata.get("retrieval_context_items"),
        "retrieval_route": metadata.get("retrieval_route"),
        "assistant_used": metadata.get("assistant_used"),
        "economy_mode_activated": metadata.get("economy_mode_activated"),
        "degradation_reasons": metadata.get("degradation_reasons") or [],
        "component_snapshot": metadata.get("component_snapshot") or [],
        "execution_context": metadata.get("execution_context"),
        "history_scope": metadata.get("history_scope"),
    }


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_str(value: Any, default: str) -> str:
    if not isinstance(value, str):
        return default
    text = value.strip()
    return text or default


def _resolve_trace_inconsistent_flag(
    *,
    metadata: dict[str, Any],
    transcription: str,
    transcription_used_for_generation: str,
) -> bool:
    trace_inconsistent = metadata.get("trace_inconsistent")
    if isinstance(trace_inconsistent, bool):
        return trace_inconsistent
    if not transcription and not transcription_used_for_generation:
        return False
    return transcription.strip() != transcription_used_for_generation.strip()


def _multi_runtime_setting(name: str, default: Any) -> Any:
    return getattr(SETTINGS, name, default)


def _multi_runtime_voice_flags() -> dict[str, bool]:
    return {
        "reasoning_summary_enabled": bool(
            _multi_runtime_setting("GEMMA4_AUDIO_REASONING_SUMMARY_ENABLED", False)
        ),
        "emotion_detection_enabled": bool(
            _multi_runtime_setting("GEMMA4_AUDIO_EMOTION_DETECTION_ENABLED", False)
        ),
        "emotion_response_style_enabled": bool(
            _multi_runtime_setting(
                "GEMMA4_AUDIO_EMOTION_RESPONSE_STYLE_ENABLED",
                False,
            )
        ),
    }


def _normalize_voice_route_profile(raw: Any) -> str:
    profile = _coerce_str(raw, "auto").lower()
    return profile if profile in _VOICE_ROUTE_PROFILES else "auto"


def _normalize_audio_decoder_id(raw: Any) -> str:
    decoder = _coerce_str(raw, "").lower()
    return _AUDIO_DECODER_ALIASES.get(decoder, "")


def _normalize_audio_decoder_profile(raw: Any) -> str:
    profile = _coerce_str(raw, "auto").lower()
    return profile if profile in _AUDIO_DECODER_PROFILES else "auto"


def _parse_audio_decoder_chain(raw: Any) -> list[str]:
    if not isinstance(raw, str):
        return []
    chain: list[str] = []
    for part in raw.split(","):
        decoder = _normalize_audio_decoder_id(part)
        if not decoder or decoder in chain:
            continue
        chain.append(decoder)
    return chain


def _build_voice_session_insights_payload(
    *,
    transcript: str = "",
    response: str = "",
    voice_mode: str = "standard",
    pipeline_id: str | None = None,
    reasoning_summary_enabled: bool = False,
    emotion_detection_enabled: bool = False,
    emotion_response_style_enabled: bool = False,
    raw_thinking_available: bool = False,
) -> dict[str, Any]:
    return build_voice_session_insights(
        transcript=transcript,
        response=response,
        voice_mode=voice_mode,
        pipeline_id=pipeline_id,
        reasoning_summary_enabled=reasoning_summary_enabled,
        emotion_detection_enabled=emotion_detection_enabled,
        emotion_response_style_enabled=emotion_response_style_enabled,
        raw_thinking_available=raw_thinking_available,
    )


async def _invoke_operator_agent(
    operator_agent: object,
    text: str,
    *,
    mode: str,
    voice_context: dict[str, Any] | None = None,
) -> str:
    """Call the operator agent while keeping backward compatibility."""

    process = getattr(operator_agent, "process", None)
    if not callable(process):
        raise RuntimeError("Operator agent does not expose process()")

    kwargs: dict[str, Any] = {}
    try:
        signature = inspect.signature(process)
    except (TypeError, ValueError):
        signature = None

    if signature is not None:
        parameters = signature.parameters
        accepts_kwargs = any(
            parameter.kind is inspect.Parameter.VAR_KEYWORD
            for parameter in parameters.values()
        )
        if accepts_kwargs or "mode" in parameters:
            kwargs["mode"] = mode
        if voice_context is not None and (
            accepts_kwargs or "voice_context" in parameters
        ):
            kwargs["voice_context"] = voice_context
    else:
        kwargs["mode"] = mode
        if voice_context is not None:
            kwargs["voice_context"] = voice_context

    return await process(text, **kwargs)


def collect_latest_voice_session_record(
    session_root: Path = VOICE_SESSION_ROOT,
) -> dict[str, Any] | None:
    """Zwraca najnowszą sesję voice z katalogu sesji."""
    if not session_root.exists():
        return None

    candidates: list[tuple[float, Path, dict[str, Any]]] = []
    for session_dir in session_root.iterdir():
        if not session_dir.is_dir():
            continue
        wav_path = session_dir / VOICE_SESSION_WAV_FILENAME
        if not wav_path.exists():
            continue

        metadata_path = session_dir / VOICE_SESSION_METADATA_FILENAME
        stat_source = metadata_path if metadata_path.exists() else wav_path
        try:
            mtime = stat_source.stat().st_mtime
        except OSError:
            continue

        metadata = _load_voice_session_metadata(metadata_path)
        candidates.append((mtime, session_dir, metadata))

    for _mtime, latest_dir, metadata in sorted(
        candidates, key=lambda item: item[0], reverse=True
    ):
        if not _is_voice_session_eligible(metadata):
            continue
        return _build_voice_session_record(latest_dir, metadata)

    return None


def _create_voice_session_dir(connection_id: int) -> Path:
    """Tworzy unikalny katalog sesji voice bez ryzyka kolizji nazw."""
    for _attempt in range(3):
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")
        session_id = f"{timestamp}_{connection_id}_{uuid.uuid4().hex[:8]}"
        session_dir = VOICE_SESSION_ROOT / session_id
        try:
            session_dir.mkdir(parents=True, exist_ok=False)
            return session_dir
        except FileExistsError:
            continue
    raise RuntimeError("Nie udało się utworzyć unikalnego katalogu sesji voice.")


class AudioStreamHandler:
    """
    Handler do obsługi streaming audio przez WebSocket.
    Obsługuje VAD (Voice Activity Detection) i dwukierunkowy przepływ audio.
    """

    def __init__(
        self,
        audio_engine: Optional[AudioEngine] = None,
        vad_threshold: float = 0.5,
        silence_duration: float = 1.5,
    ):
        """
        Inicjalizacja handlera.

        Args:
            audio_engine: Silnik audio (STT/TTS)
            vad_threshold: Próg dla Voice Activity Detection (0-1)
            silence_duration: Ile sekund ciszy oznacza koniec wypowiedzi
        """
        self.audio_engine = audio_engine
        self.vad_threshold = vad_threshold
        self.silence_duration = silence_duration
        self.active_connections: Dict[int, AudioStreamHandler._ConnectionState] = {}
        logger.info("AudioStreamHandler zainicjalizowany")

    class _ConnectionState(TypedDict):
        websocket: WebSocket
        audio_buffer: List[np.ndarray]
        audio_bytes_buffer: List[bytes]
        is_speaking: bool
        silence_finalize_task: asyncio.Task[None] | None
        sample_rate: int
        channels: int
        speech_detected: bool
        recording_format: str
        mime_type: str
        audio_config: dict[str, object]
        voice_mode: str

    def get_status(self, operator_agent: object | None = None) -> dict:
        """Zwraca stan kanału audio dla healthchecków i UI."""
        audio_engine = self.audio_engine
        whisper = getattr(audio_engine, "whisper", None) if audio_engine else None
        voice = getattr(audio_engine, "voice", None) if audio_engine else None
        whisper_loaded = bool(getattr(whisper, "model", None))
        voice_loaded = bool(getattr(voice, "voice", None))
        dependencies = {
            "ffmpeg": shutil.which("ffmpeg") is not None,
            "faster_whisper": importlib.util.find_spec("faster_whisper") is not None,
            "piper": importlib.util.find_spec("piper") is not None,
            "sounddevice": importlib.util.find_spec("sounddevice") is not None,
        }
        return {
            "enabled": audio_engine is not None,
            "connected_clients": len(self.active_connections),
            "active_recordings": sum(
                1 for state in self.active_connections.values() if state["is_speaking"]
            ),
            "vad_threshold": self.vad_threshold,
            "silence_duration": self.silence_duration,
            "operator_ready": operator_agent is not None,
            "stt_backend": "faster-whisper" if whisper else None,
            "stt_ready": whisper_loaded,
            "whisper_model_size": getattr(whisper, "model_size", None),
            "whisper_device": getattr(whisper, "device", None),
            "tts_backend": "piper" if voice else None,
            "tts_ready": voice_loaded
            and not bool(getattr(voice, "is_fallback_mode", False)),
            "tts_model_path": getattr(voice, "model_path", None),
            "tts_fallback": getattr(voice, "is_fallback_mode", None),
            "dependencies": dependencies,
            "mode_contracts": mode_contracts_payload(),
            "runtime_switch_gate": get_runtime_switch_gate_status(),
            **self._multi_runtime_runtime_snapshot(),
        }

    def get_latest_voice_session(self) -> dict[str, object] | None:
        """Zwraca metadane ostatniej zapisanej sesji głosowej."""
        return collect_latest_voice_session_record(VOICE_SESSION_ROOT)

    async def handle_websocket(
        self,
        websocket: WebSocket,
        operator_agent=None,
    ):
        """
        Obsługuje połączenie WebSocket dla audio.

        Args:
            websocket: Połączenie WebSocket
            operator_agent: Agent do przetwarzania komend głosowych (opcjonalny)
        """
        await websocket.accept()
        connection_id = id(websocket)
        self.active_connections[connection_id] = {
            "websocket": websocket,
            "audio_buffer": [],
            "audio_bytes_buffer": [],
            "is_speaking": False,
            "silence_finalize_task": None,
            "sample_rate": 16000,
            "channels": 1,
            "speech_detected": False,
            "recording_format": "pcm16",
            "mime_type": "",
            "audio_config": {},
            "voice_mode": "standard",
        }

        logger.info(f"Nowe połączenie audio WebSocket: {connection_id}")

        try:
            while True:
                # Odbierz wiadomość
                data = await websocket.receive()

                if "text" in data:
                    # Komenda sterująca (JSON)
                    await self._handle_control_message(
                        connection_id, data["text"], operator_agent
                    )

                elif "bytes" in data:
                    # Audio blob
                    self._handle_audio_data(
                        connection_id, data["bytes"], operator_agent
                    )

        except WebSocketDisconnect:
            logger.info(f"Rozłączono WebSocket audio: {connection_id}")
        except Exception as e:
            logger.error(f"Błąd w WebSocket audio: {e}")
        finally:
            if connection_id in self.active_connections:
                del self.active_connections[connection_id]

    async def _handle_control_message(
        self, connection_id: int, message: str, operator_agent
    ) -> None:
        """
        Obsługuje wiadomości sterujące (JSON).

        Args:
            connection_id: ID połączenia
            message: Wiadomość JSON
            operator_agent: Agent operatora
        """
        import json

        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            logger.error(f"Nieprawidłowy JSON: {message}")
            return

        command = data.get("command")
        if command == "start_recording":
            await self._start_recording(connection_id, data)
            return
        if command == "audio_config":
            await self._apply_audio_config(connection_id, data)
            return
        if command == "voice_mode":
            await self._apply_voice_mode(connection_id, data)
            return
        if command == "stop_recording":
            await self._stop_recording(connection_id, operator_agent)
            return
        if command == "ping":
            await self._send_json(connection_id, {"type": "pong"})

    async def _start_recording(self, connection_id: int, data: dict[str, Any]) -> None:
        conn = self.active_connections[connection_id]
        conn["audio_buffer"] = []
        conn["audio_bytes_buffer"] = []
        conn["is_speaking"] = True
        self._cancel_silence_finalize_task(conn)
        audio_config = conn["audio_config"]
        conn["sample_rate"] = _coerce_int(
            data.get("sample_rate") or audio_config.get("sample_rate"), 16000
        )
        conn["speech_detected"] = False
        conn["recording_format"] = _coerce_str(
            data.get("format") or audio_config.get("format"), "pcm16"
        )
        conn["mime_type"] = _coerce_str(
            data.get("mime_type") or audio_config.get("mime_type"), ""
        )
        conn["channels"] = _coerce_int(
            data.get("channels") or audio_config.get("channels"), 1
        )
        conn["audio_config"] = {
            "sample_rate": conn["sample_rate"],
            "channels": conn["channels"],
            "format": conn["recording_format"],
            "mime_type": conn["mime_type"],
        }
        logger.info(
            "Rozpoczęto nagrywanie: %s config=%s", connection_id, conn["audio_config"]
        )
        await self._send_json(
            connection_id, {"type": "recording_started", "status": "ok"}
        )

    async def _apply_audio_config(
        self, connection_id: int, data: dict[str, Any]
    ) -> None:
        conn = self.active_connections[connection_id]
        conn["audio_config"] = {
            "sample_rate": _coerce_int(data.get("sample_rate"), 16000),
            "channels": _coerce_int(data.get("channels"), 1),
            "format": _coerce_str(data.get("format"), "pcm16"),
            "mime_type": _coerce_str(data.get("mime_type"), ""),
        }
        if data.get("sample_rate"):
            conn["sample_rate"] = _coerce_int(data.get("sample_rate"), 16000)
        if data.get("format"):
            conn["recording_format"] = _coerce_str(data.get("format"), "pcm16")
        if data.get("mime_type"):
            conn["mime_type"] = _coerce_str(data.get("mime_type"), "")
        logger.info(
            "Ustawiono audio_config dla %s: %s", connection_id, conn["audio_config"]
        )
        await self._send_json(
            connection_id,
            {
                "type": "audio_config",
                "status": "ok",
                "config": conn["audio_config"],
            },
        )

    async def _apply_voice_mode(self, connection_id: int, data: dict[str, Any]) -> None:
        conn = self.active_connections[connection_id]
        voice_mode = _coerce_str(data.get("mode"), "standard")
        conn["voice_mode"] = voice_mode
        logger.info("Ustawiono voice_mode dla %s: %s", connection_id, voice_mode)
        await self._send_json(
            connection_id,
            {
                "type": "voice_mode",
                "status": "ok",
                "mode": voice_mode,
            },
        )

    async def _stop_recording(self, connection_id: int, operator_agent) -> None:
        conn = self.active_connections[connection_id]
        conn["is_speaking"] = False
        self._cancel_silence_finalize_task(conn)
        logger.info(
            "Zakończono nagrywanie: %s (pcm_chunks=%s, encoded_chunks=%s, format=%s)",
            connection_id,
            len(conn["audio_buffer"]),
            len(conn["audio_bytes_buffer"]),
            conn["recording_format"],
        )
        if conn["audio_bytes_buffer"] and conn["recording_format"] != "pcm16":
            await self._process_encoded_audio_buffer(
                connection_id,
                conn["audio_bytes_buffer"],
                operator_agent,
                mime_type=_coerce_str(conn.get("mime_type"), ""),
            )
            conn["audio_bytes_buffer"] = []
            return
        if conn["audio_buffer"]:
            await self._process_audio_buffer(
                connection_id,
                conn["audio_buffer"],
                operator_agent,
                sample_rate=_coerce_int(conn.get("sample_rate"), 16000),
            )
            conn["audio_buffer"] = []

    def _handle_audio_data(
        self, connection_id: int, audio_bytes: bytes, operator_agent
    ):
        """
        Obsługuje dane audio (blob).

        Args:
            connection_id: ID połączenia
            audio_bytes: Surowe dane audio
            operator_agent: Agent operatora
        """
        conn = self.active_connections[connection_id]
        if conn.get("recording_format") != "pcm16":
            conn["audio_bytes_buffer"].append(audio_bytes)
            conn["speech_detected"] = True
            self._cancel_silence_finalize_task(conn)
            logger.debug(
                f"Odebrano encoded audio chunk: {len(audio_bytes)} B od {connection_id}"
            )
            return

        # Konwertuj bytes na numpy array
        # Zakładamy: 16-bit PCM, mono, 16kHz
        audio_data = np.frombuffer(audio_bytes, dtype=np.int16)
        logger.debug(
            f"Odebrano audio chunk: {audio_data.size} próbek od {connection_id}"
        )

        # Dodaj do bufora
        conn["audio_buffer"].append(audio_data)

        # Sprawdź VAD (czy użytkownik nadal mówi)
        is_voice = self._detect_voice_activity(audio_data)
        if is_voice:
            conn["speech_detected"] = True
            self._cancel_silence_finalize_task(conn)
        elif conn["is_speaking"] and conn["speech_detected"]:
            self._schedule_silence_finalize(
                connection_id,
                operator_agent,
                sample_rate=_coerce_int(conn.get("sample_rate"), 16000),
            )

    def _detect_voice_activity(self, audio_data: np.ndarray) -> bool:
        """
        Prosta detekcja aktywności głosowej na podstawie RMS.

        Args:
            audio_data: Fragment audio

        Returns:
            True jeśli wykryto głos
        """
        try:
            if audio_data.size == 0:
                return False

            # Oblicz RMS (Root Mean Square)
            rms = np.sqrt(np.mean(audio_data.astype(float) ** 2))

            # Normalizuj do 0-1
            normalized_rms = rms / 32768.0  # 16-bit audio max

            # Porównaj z progiem
            is_voice = normalized_rms > self.vad_threshold

            return bool(is_voice)

        except Exception:
            return False

    def _cancel_silence_finalize_task(self, conn: Any | None) -> None:
        if not conn:
            return
        task = conn.get("silence_finalize_task")
        if isinstance(task, asyncio.Task) and not task.done():
            task.cancel()
        conn["silence_finalize_task"] = None

    def _schedule_silence_finalize(
        self,
        connection_id: int,
        operator_agent,
        sample_rate: int = 16000,
    ) -> None:
        conn = self.active_connections.get(connection_id)
        if not conn:
            return
        existing_task = conn.get("silence_finalize_task")
        if isinstance(existing_task, asyncio.Task) and not existing_task.done():
            return

        async def finalize_after_silence() -> None:
            try:
                await asyncio.sleep(self.silence_duration)
                current = self.active_connections.get(connection_id)
                if (
                    not current
                    or not current["is_speaking"]
                    or not current["audio_buffer"]
                    or not current["speech_detected"]
                    or self._detect_voice_activity(current["audio_buffer"][-1])
                ):
                    return
                current["is_speaking"] = False
                audio_buffer = list(current["audio_buffer"])
                current["audio_buffer"] = []
                await self._process_audio_buffer(
                    connection_id,
                    audio_buffer,
                    operator_agent,
                    sample_rate=sample_rate,
                )
            finally:
                current = self.active_connections.get(connection_id)
                if current and current.get("silence_finalize_task") is task:
                    current["silence_finalize_task"] = None

        task = asyncio.create_task(finalize_after_silence())
        conn["silence_finalize_task"] = task

    def _connection_voice_mode(self, connection_id: int) -> str:
        conn = self.active_connections.get(connection_id)
        if not conn:
            return "standard"
        voice_mode = conn["voice_mode"]
        return str(voice_mode).strip() or "standard"

    def _voice_contract_payload(self, connection_id: int) -> dict[str, str]:
        return {
            "execution_context": VOICE_EXECUTION_CONTEXT,
            "history_scope": VOICE_HISTORY_SCOPE,
            "voice_mode": self._connection_voice_mode(connection_id),
        }

    def _multi_runtime_runtime_snapshot(self) -> dict[str, Any]:
        endpoint = _coerce_str(_multi_runtime_setting("GEMMA4_AUDIO_ENDPOINT", ""), "")
        log_path = _coerce_str(_multi_runtime_setting("GEMMA4_AUDIO_LOG_PATH", ""), "")
        pid_path = _coerce_str(_multi_runtime_setting("GEMMA4_AUDIO_PID_PATH", ""), "")
        return {
            "audio_runtime_provider": MULTI_RUNTIME_ID,
            "audio_runtime_model": _coerce_str(
                _multi_runtime_setting("GEMMA4_AUDIO_MODEL_ID", ""), ""
            ),
            "audio_runtime_endpoint": endpoint,
            "audio_runtime_enabled": bool(
                _multi_runtime_setting("GEMMA4_AUDIO_ENABLED", False)
            ),
            "audio_runtime_selected": self._multi_runtime_runtime_selected(),
            "audio_runtime_supports_audio": bool(
                _multi_runtime_setting("GEMMA4_AUDIO_SUPPORTS_AUDIO", True)
            ),
            "audio_runtime_supports_text": bool(
                _multi_runtime_setting("GEMMA4_AUDIO_SUPPORTS_TEXT", True)
            ),
            "audio_runtime_supports_image": True,
            "audio_runtime_supports_unified_multimodal_respond": True,
            "audio_runtime_runtime_mode": "processor_model",
            "audio_runtime_image_token_budget": _coerce_int(
                _multi_runtime_setting("GEMMA4_AUDIO_IMAGE_TOKEN_BUDGET", 280),
                280,
            ),
            "assistant_models": multi_runtime_available_models(role="assistant"),
            "audio_runtime_log_path": log_path,
            "audio_runtime_pid_path": pid_path,
        }

    def _multi_runtime_service_origin(self) -> str:
        endpoint = _coerce_str(_multi_runtime_setting("GEMMA4_AUDIO_ENDPOINT", ""), "")
        if not endpoint:
            return ""
        endpoint = endpoint.rstrip("/")
        if endpoint.endswith("/v1"):
            return endpoint[:-3].rstrip("/")
        return endpoint

    def _multi_runtime_respond_url(self) -> str:
        origin = self._multi_runtime_service_origin()
        return f"{origin}/v1/respond" if origin else ""

    def _multi_runtime_transcribe_url(self) -> str:
        origin = self._multi_runtime_service_origin()
        return f"{origin}/audio/transcribe" if origin else ""

    def _multi_runtime_health_url(self) -> str:
        origin = self._multi_runtime_service_origin()
        return f"{origin}/health" if origin else ""

    def _multi_runtime_runtime_enabled(self) -> bool:
        return bool(_multi_runtime_setting("GEMMA4_AUDIO_ENABLED", False))

    def _multi_runtime_runtime_selected(self) -> bool:
        if not self._multi_runtime_runtime_enabled():
            return False
        try:
            runtime = get_active_llm_runtime()
            if is_multi_runtime(getattr(runtime, "provider", "")):
                return True
        except Exception:
            # Compatibility fallback for early bootstrap and partial runtime init.
            pass
        active_server = _coerce_str(_multi_runtime_setting("ACTIVE_LLM_SERVER", ""), "")
        return is_multi_runtime(active_server)

    def _voice_pipeline_mode(self) -> str:
        """Resolve voice pipeline contract for current runtime selection.

        Contract:
        - multi_runtime (Gemma4): native voice pipeline allowed.
        - ollama/vllm/onnx/other: always local intermediary STT -> LLM -> TTS.
        """
        decoder_plan = self._resolve_audio_decoder_plan()
        return (
            "native_multi_runtime"
            if decoder_plan["effective"] == "gemma_native"
            else "intermediary_local_stt"
        )

    def _voice_route_profile(self) -> str:
        return _normalize_voice_route_profile(
            _multi_runtime_setting("VOICE_ROUTE_PROFILE", "auto")
        )

    def _audio_decoder_profile(self) -> str:
        return _normalize_audio_decoder_profile(
            _multi_runtime_setting("AUDIO_DECODER_PROFILE", "auto")
        )

    def _audio_decoder_chain(self) -> list[str]:
        route_profile = self._voice_route_profile()
        configured_chain = _parse_audio_decoder_chain(
            _multi_runtime_setting("AUDIO_DECODER_CHAIN", "")
        )
        if configured_chain:
            if route_profile in {"runtime_lokalny", "venom-agent"}:
                return [
                    item for item in configured_chain if item == "faster_whisper"
                ] or ["faster_whisper"]
            return configured_chain
        profile = self._audio_decoder_profile()
        if profile == "gemma_native":
            return (
                ["faster_whisper"]
                if route_profile in {"runtime_lokalny", "venom-agent"}
                else ["gemma_native"]
            )
        if profile == "faster_whisper":
            return ["faster_whisper"]
        if profile == "hybrid":
            return (
                ["faster_whisper"]
                if route_profile in {"runtime_lokalny", "venom-agent"}
                else ["gemma_native", "faster_whisper"]
            )
        if route_profile in {"runtime_lokalny", "venom-agent"}:
            return ["faster_whisper"]
        if self._multi_runtime_runtime_selected():
            return ["gemma_native", "faster_whisper"]
        return ["faster_whisper"]

    def _voice_route_runtime_config(self) -> dict[str, Any]:
        profile = self._voice_route_profile()
        decoder_profile = self._audio_decoder_profile()
        chain = self._audio_decoder_chain()
        return {
            "voice_route_profile": profile,
            "audio_decoder_profile": decoder_profile,
            "audio_decoder_chain": chain,
        }

    def _voice_route_contract_error(self) -> str:
        config = self._voice_route_runtime_config()
        profile = str(config["voice_route_profile"])
        chain = list(config["audio_decoder_chain"])
        if profile == "gemma4" and not chain:
            return (
                "voice route contract invalid: gemma4 requires non-empty audio "
                "decoder chain"
            )
        if profile == "gemma4" and chain[0] != "gemma_native":
            return (
                "voice route contract invalid: gemma4 requires gemma_native as "
                "the first decoder"
            )
        if profile in {"runtime_lokalny", "venom-agent"} and any(
            decoder != "faster_whisper" for decoder in chain
        ):
            return (
                f"voice route contract invalid: {profile} supports only "
                "faster_whisper decoder"
            )
        return ""

    def _build_audio_decoder_plan(
        self,
        *,
        chain: list[str],
        selected: str,
        effective: str,
        should_try_native: bool,
        fallback_reason: str,
    ) -> dict[str, Any]:
        return {
            "chain": chain,
            "selected": selected,
            "effective": effective,
            "should_try_native": should_try_native,
            "fallback_reason": fallback_reason,
        }

    def _resolve_audio_decoder_plan(self) -> dict[str, Any]:
        profile = self._voice_route_profile()
        runtime_selected = self._multi_runtime_runtime_selected()
        if profile == "chat_tekstowy":
            # Voice input should remain processable even when text-chat profile is staged.
            # We override to a safe decoder path instead of hard-failing the session.
            chain = (
                ["gemma_native", "faster_whisper"]
                if runtime_selected
                else ["faster_whisper"]
            )
            selected = chain[0]
            fallback_reason = (
                "voice input override: chat_tekstowy profile bypassed for "
                "audio transcription"
            )
            if selected == "gemma_native" and runtime_selected:
                return self._build_audio_decoder_plan(
                    chain=chain,
                    selected=selected,
                    effective="gemma_native",
                    should_try_native=True,
                    fallback_reason=fallback_reason,
                )
            return self._build_audio_decoder_plan(
                chain=chain,
                selected=selected,
                effective="faster_whisper",
                should_try_native=False,
                fallback_reason=fallback_reason,
            )

        contract_error = self._voice_route_contract_error()
        if contract_error:
            return self._build_audio_decoder_plan(
                chain=[],
                selected="",
                effective="none",
                should_try_native=False,
                fallback_reason=contract_error,
            )
        chain = self._audio_decoder_chain() or ["faster_whisper"]
        selected = chain[0]
        if selected == "gemma_native" and runtime_selected:
            return self._build_audio_decoder_plan(
                chain=chain,
                selected=selected,
                effective="gemma_native",
                should_try_native=True,
                fallback_reason="",
            )
        if selected == "gemma_native":
            return self._build_audio_decoder_plan(
                chain=chain,
                selected=selected,
                effective="faster_whisper",
                should_try_native=False,
                fallback_reason=self._voice_pipeline_fallback_reason(),
            )
        return self._build_audio_decoder_plan(
            chain=chain,
            selected=selected,
            effective="faster_whisper",
            should_try_native=False,
            fallback_reason="audio decoder profile forced faster_whisper",
        )

    def _voice_pipeline_fallback_reason(self) -> str:
        active_server = ""
        try:
            runtime = get_active_llm_runtime()
            active_server = _coerce_str(getattr(runtime, "provider", ""), "")
        except Exception:
            active_server = _coerce_str(
                _multi_runtime_setting("ACTIVE_LLM_SERVER", ""), ""
            )
        if not active_server:
            return "native voice disabled: ACTIVE_LLM_SERVER is empty"
        return f"native voice disabled for active runtime: {active_server}"

    async def _multi_runtime_health_ok(self) -> bool:
        health_url = self._multi_runtime_health_url()
        if not health_url:
            return False
        try:
            timeout = httpx.Timeout(GEMMA4_AUDIO_HEALTH_TIMEOUT_SEC, connect=2.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(health_url)
            if response.status_code != 200:
                return False
            payload = response.json()
            status = str(payload.get("status") or "").strip().lower()
            return status in {"ok", "warming"}
        except Exception:
            return False

    async def _invoke_multi_runtime(
        self,
        wav_path: Path,
        connection_id: int,
    ) -> dict[str, Any]:
        respond_url = self._multi_runtime_respond_url()
        if not respond_url:
            raise RuntimeError("Gemma4 audio endpoint is not configured")

        prompt = (
            "Odpowiedz po polsku na wypowiedź użytkownika z nagrania. "
            "Jeśli to polecenie, wykonaj je krótko i bez dodatkowych komentarzy."
        )
        payload = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "audio", "path": str(wav_path.name)},
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
            "task": "question",
            "system_prompt": _coerce_str(
                _multi_runtime_setting("SIMPLE_MODE_SYSTEM_PROMPT", ""), ""
            ),
            "max_new_tokens": _coerce_int(
                _multi_runtime_setting("GEMMA4_AUDIO_MAX_NEW_TOKENS", 128), 128
            ),
            "release_after_response": True,
        }

        timeout = httpx.Timeout(GEMMA4_AUDIO_REQUEST_TIMEOUT_SEC, connect=5.0)
        async with await anyio.open_file(wav_path, "rb") as audio_file:
            audio_bytes = await audio_file.read()
            audio_hash = hashlib.sha256(audio_bytes).hexdigest()
            files = {
                "audio": (wav_path.name, audio_bytes, "audio/wav"),
            }
            async with httpx.AsyncClient(timeout=timeout) as client:
                data = {
                    "request": json.dumps(payload, ensure_ascii=False),
                }
                response = await client.post(respond_url, data=data, files=files)

        if response.status_code >= 400:
            raise RuntimeError(
                f"Gemma4 audio runtime HTTP {response.status_code}: {response.text}"
            )

        data = response.json()
        transcription = _coerce_str(data.get("transcription"), "")
        transcription_used_for_generation = _coerce_str(
            data.get("transcription_used_for_generation"), ""
        )
        if not transcription:
            transcription = transcription_used_for_generation
        if not transcription:
            raise RuntimeError(
                "Gemma4 audio runtime returned an empty transcription in /v1/respond"
            )
        response_text = _coerce_str(data.get("text"), "")
        if not response_text:
            response_text = _coerce_str(data.get("response_text"), "")
        if not response_text:
            response_text = _coerce_str(data.get("generated_text"), "")
        if not response_text:
            message = data.get("message")
            if isinstance(message, dict):
                response_text = _coerce_str(message.get("content"), "")
        if not response_text:
            raise RuntimeError("Gemma4 audio runtime returned an empty response")

        return {
            "text": transcription,
            "transcription": transcription,
            "transcription_used_for_generation": (
                transcription_used_for_generation or transcription
            ),
            "response_text": response_text,
            "model": _coerce_str(
                data.get("model")
                or _multi_runtime_setting("GEMMA4_AUDIO_MODEL_ID", ""),
                "",
            ),
            "request_id": _coerce_str(
                data.get("request_id"),
                _coerce_str(data.get("trace_id"), ""),
            ),
            "trace_id": _coerce_str(
                data.get("trace_id"),
                _coerce_str(data.get("request_id"), ""),
            ),
            "audio_hash": audio_hash,
            "duration_ms": data.get("duration_ms"),
            "connection_id": connection_id,
            "reasoning_summary": data.get("reasoning_summary"),
            "reasoning_summary_status": data.get("reasoning_summary_status"),
            "raw_thinking_available": data.get("raw_thinking_available"),
            "emotion_label": data.get("emotion_label"),
            "emotion_confidence": data.get("emotion_confidence"),
            "emotion_source": data.get("emotion_source"),
            "execution_trace": data.get("execution_trace") or [],
            "selected_policy": data.get("selected_policy"),
            "selected_image_strategy": data.get("selected_image_strategy"),
            "retrieval_used": bool(data.get("retrieval_used", False)),
            "retrieval_context_items": data.get("retrieval_context_items"),
            "retrieval_route": data.get("retrieval_route"),
            "assistant_used": bool(data.get("assistant_used", False)),
            "economy_mode_activated": bool(data.get("economy_mode_activated", False)),
            "degradation_reasons": data.get("degradation_reasons") or [],
            "component_snapshot": data.get("component_snapshot") or [],
        }

    async def _process_native_multi_runtime_pipeline(
        self,
        connection_id: int,
        session_dir: Path,
        wav_path: Path,
        timings_ms: dict[str, float],
        total_started_at: float,
        operator_agent,
        *,
        decoder_selected: str = "gemma_native",
    ) -> bool:
        if not self._multi_runtime_runtime_selected():
            return False
        if not await self._ensure_native_audio_engine_available(connection_id):
            return True

        snapshot = self._multi_runtime_runtime_snapshot()
        if not await self._multi_runtime_health_ok():
            logger.warning(
                "multi_runtime health precheck failed for connection_id=%s; attempting native pipeline anyway",
                connection_id,
            )

        await self._send_json(
            connection_id, {"type": "processing", "status": "native_audio"}
        )

        async with runtime_request_guard(
            request_kind="voice_native_runtime",
            provider=MULTI_RUNTIME_ID,
            model=_coerce_str(snapshot.get("audio_runtime_model"), ""),
        ):
            native_started_at = time.perf_counter()
            try:
                runtime_result = await self._invoke_multi_runtime(
                    wav_path, connection_id
                )
            except Exception as exc:
                timings_ms["native_audio_ms"] = self._elapsed_ms(native_started_at)
                self._persist_native_runtime_failure(
                    connection_id=connection_id,
                    session_dir=session_dir,
                    snapshot=snapshot,
                    timings_ms=timings_ms,
                    operator_agent=operator_agent,
                    decoder_selected=decoder_selected,
                )
                logger.warning(
                    "Gemma4 audio runtime failed for connection_id=%s: %s",
                    connection_id,
                    exc,
                )
                await self._send_json(
                    connection_id,
                    {
                        "type": "error",
                        "message": "Gemma4 native audio pipeline failed. Check runtime status.",
                    },
                )
                return True

            timings_ms["native_audio_ms"] = self._elapsed_ms(native_started_at)
            transcription = _coerce_str(
                runtime_result.get("transcription"), ""
            ) or _coerce_str(runtime_result.get("text"), "")
            response_text = _coerce_str(runtime_result.get("response_text"), "")
            if not transcription or not response_text:
                self._persist_native_runtime_incomplete_result(
                    connection_id=connection_id,
                    session_dir=session_dir,
                    snapshot=snapshot,
                    timings_ms=timings_ms,
                    runtime_result=runtime_result,
                    transcription=transcription,
                    response_text=response_text,
                    operator_agent=operator_agent,
                    decoder_selected=decoder_selected,
                )
                await self._send_json(
                    connection_id,
                    {
                        "type": "error",
                        "message": "Gemma4 native audio pipeline returned an incomplete result.",
                    },
                )
                return True
            insights = _build_voice_session_insights_payload(
                transcript=transcription,
                response=response_text,
                voice_mode=self._connection_voice_mode(connection_id),
                pipeline_id="multi_runtime_piper",
                **_multi_runtime_voice_flags(),
                raw_thinking_available=bool(
                    runtime_result.get("raw_thinking_available", False)
                ),
            )

            self._update_voice_session_metadata(
                session_dir,
                {
                    **snapshot,
                    "pipeline_id": "multi_runtime_piper",
                    "audio_runtime_provider": MULTI_RUNTIME_ID,
                    "audio_runtime_model": _coerce_str(runtime_result.get("model"), ""),
                    "audio_input_status": "verified",
                    "decoder_source": "multi_runtime",
                    "decoder_selected": decoder_selected,
                    "decoder_effective": "gemma_native",
                    "decoder_fallback_reason": "",
                    "fallback_reason": "",
                    "request_id": _coerce_str(runtime_result.get("request_id"), ""),
                    "trace_id": _coerce_str(runtime_result.get("trace_id"), ""),
                    "audio_hash": _coerce_str(runtime_result.get("audio_hash"), ""),
                    "transcription_used_for_generation": _coerce_str(
                        runtime_result.get("transcription_used_for_generation"),
                        "",
                    )
                    or transcription,
                    "native_audio_ms": timings_ms["native_audio_ms"],
                    "transcription": transcription,
                    "transcription_length": len(transcription or ""),
                    "response_text": response_text,
                    "response_length": len(response_text or ""),
                    "execution_trace": runtime_result.get("execution_trace") or [],
                    "selected_policy": runtime_result.get("selected_policy"),
                    "selected_image_strategy": runtime_result.get(
                        "selected_image_strategy"
                    ),
                    "retrieval_used": runtime_result.get("retrieval_used"),
                    "retrieval_context_items": runtime_result.get(
                        "retrieval_context_items"
                    ),
                    "retrieval_route": runtime_result.get("retrieval_route"),
                    "assistant_used": runtime_result.get("assistant_used"),
                    "economy_mode_activated": runtime_result.get(
                        "economy_mode_activated"
                    ),
                    "degradation_reasons": runtime_result.get("degradation_reasons")
                    or [],
                    "component_snapshot": runtime_result.get("component_snapshot")
                    or [],
                    **insights,
                    "timings_ms": timings_ms,
                    "runtime": self._build_runtime_metadata(operator_agent),
                    **self._voice_contract_payload(connection_id),
                },
            )

        await self._send_json(
            connection_id,
            {"type": "transcription", "text": transcription, "confidence": 1.0},
        )
        await self._send_json(
            connection_id, {"type": "response_text", "text": response_text}
        )
        await self._send_json(connection_id, {"type": "processing", "status": "tts"})

        tts_started_at = time.perf_counter()
        audio_response = await self.audio_engine.speak(response_text)
        timings_ms["tts_ms"] = self._elapsed_ms(tts_started_at)
        timings_ms["total_backend_ms"] = self._elapsed_ms(total_started_at)
        self._update_voice_session_metadata(
            session_dir,
            {
                "timings_ms": timings_ms,
                "runtime": self._build_runtime_metadata(operator_agent),
                "pipeline_id": "multi_runtime_piper",
            },
        )

        if audio_response is not None:
            await self._send_audio(connection_id, audio_response)

        await self._send_json(connection_id, {"type": "complete"})
        return True

    async def _ensure_native_audio_engine_available(self, connection_id: int) -> bool:
        if self.audio_engine:
            return True
        logger.error("AudioEngine nie jest dostępny dla natywnego toru multi_runtime")
        await self._send_json(
            connection_id,
            {
                "type": "error",
                "message": "Audio engine not available for native multi_runtime pipeline",
            },
        )
        return False

    def _base_native_runtime_metadata(
        self,
        *,
        snapshot: dict[str, Any],
        connection_id: int,
        timings_ms: dict[str, float],
        operator_agent,
        decoder_selected: str = "gemma_native",
    ) -> dict[str, Any]:
        return {
            **snapshot,
            "pipeline_id": "multi_runtime_piper",
            "decoder_source": "multi_runtime",
            "decoder_selected": decoder_selected,
            "decoder_effective": "gemma_native",
            "decoder_fallback_reason": "",
            "fallback_reason": "",
            "native_audio_ms": timings_ms.get("native_audio_ms"),
            "timings_ms": timings_ms,
            "runtime": self._build_runtime_metadata(operator_agent),
            **self._voice_contract_payload(connection_id),
        }

    def _persist_native_runtime_failure(
        self,
        *,
        connection_id: int,
        session_dir: Path,
        snapshot: dict[str, Any],
        timings_ms: dict[str, float],
        operator_agent,
        decoder_selected: str = "gemma_native",
    ) -> None:
        payload = {
            **self._base_native_runtime_metadata(
                snapshot=snapshot,
                connection_id=connection_id,
                timings_ms=timings_ms,
                operator_agent=operator_agent,
                decoder_selected=decoder_selected,
            ),
            "audio_input_status": "failed",
            **_build_voice_session_insights_payload(
                transcript="",
                response="",
                voice_mode=self._connection_voice_mode(connection_id),
                pipeline_id="multi_runtime_piper",
                **_multi_runtime_voice_flags(),
                raw_thinking_available=False,
            ),
        }
        self._update_voice_session_metadata(session_dir, payload)

    def _persist_native_runtime_incomplete_result(
        self,
        *,
        connection_id: int,
        session_dir: Path,
        snapshot: dict[str, Any],
        timings_ms: dict[str, float],
        runtime_result: dict[str, Any],
        transcription: str,
        response_text: str,
        operator_agent,
        decoder_selected: str = "gemma_native",
    ) -> None:
        payload = {
            **self._base_native_runtime_metadata(
                snapshot=snapshot,
                connection_id=connection_id,
                timings_ms=timings_ms,
                operator_agent=operator_agent,
                decoder_selected=decoder_selected,
            ),
            "audio_input_status": "failed",
            "transcription": transcription,
            "transcription_length": len(transcription),
            "response_text": response_text,
            "response_length": len(response_text),
            "execution_trace": runtime_result.get("execution_trace") or [],
            "selected_policy": runtime_result.get("selected_policy"),
            "selected_image_strategy": runtime_result.get("selected_image_strategy"),
            "retrieval_used": runtime_result.get("retrieval_used"),
            "retrieval_context_items": runtime_result.get("retrieval_context_items"),
            "retrieval_route": runtime_result.get("retrieval_route"),
            "assistant_used": runtime_result.get("assistant_used"),
            "economy_mode_activated": runtime_result.get("economy_mode_activated"),
            "degradation_reasons": runtime_result.get("degradation_reasons") or [],
            "component_snapshot": runtime_result.get("component_snapshot") or [],
            **_build_voice_session_insights_payload(
                transcript=transcription,
                response=response_text,
                voice_mode=self._connection_voice_mode(connection_id),
                pipeline_id="multi_runtime_piper",
                **_multi_runtime_voice_flags(),
                raw_thinking_available=bool(
                    runtime_result.get("raw_thinking_available", False)
                ),
            ),
        }
        self._update_voice_session_metadata(session_dir, payload)

    async def _process_audio_buffer(
        self,
        connection_id: int,
        audio_buffer: List[np.ndarray],
        operator_agent,
        sample_rate: int = 16000,
    ):
        """
        Przetwarza bufor audio (STT -> Agent -> TTS).

        Args:
            connection_id: ID połączenia
            audio_buffer: Lista fragmentów audio
            operator_agent: Agent do przetwarzania
        """
        assert_runtime_request_allowed(request_kind="voice_chat")
        try:
            total_started_at = time.perf_counter()
            timings_ms: dict[str, float] = {}
            # Wyślij status
            await self._send_json(
                connection_id, {"type": "processing", "status": "stt"}
            )

            # Połącz wszystkie fragmenty
            full_audio = np.concatenate(audio_buffer)
            normalized_audio, audio_stats = self._normalize_recorded_audio(full_audio)
            session_dir = self._persist_voice_session(
                connection_id=connection_id,
                audio=normalized_audio,
                sample_rate=sample_rate,
                audio_stats=audio_stats,
            )
            route_config = self._voice_route_runtime_config()
            decoder_plan = self._resolve_audio_decoder_plan()
            self._update_voice_session_metadata(
                session_dir,
                {
                    "runtime": self._build_runtime_metadata(operator_agent),
                    "voice_pipeline_mode": self._voice_pipeline_mode(),
                    "voice_route_profile": route_config["voice_route_profile"],
                    "audio_decoder_profile": route_config["audio_decoder_profile"],
                    "audio_decoder_chain": route_config["audio_decoder_chain"],
                    "decoder_selected": decoder_plan["selected"],
                },
            )
            logger.info(f"Zapisano sesję audio: {session_dir}")

            if decoder_plan["effective"] == "none":
                self._update_voice_session_metadata(
                    session_dir,
                    {
                        "pipeline_id": "none",
                        "audio_input_status": "failed",
                        "decoder_source": "none",
                        "decoder_effective": "none",
                        "decoder_fallback_reason": decoder_plan["fallback_reason"],
                        "fallback_reason": decoder_plan["fallback_reason"],
                    },
                )
                await self._send_json(
                    connection_id,
                    {"type": "error", "message": decoder_plan["fallback_reason"]},
                )
                return

            if not decoder_plan["should_try_native"]:
                self._update_voice_session_metadata(
                    session_dir,
                    {
                        "pipeline_id": "whisper_llm_piper",
                        "audio_input_status": "fallback",
                        "decoder_source": "faster_whisper",
                        "decoder_effective": decoder_plan["effective"],
                        "decoder_fallback_reason": decoder_plan["fallback_reason"],
                        "fallback_reason": decoder_plan["fallback_reason"],
                    },
                )

            if decoder_plan[
                "should_try_native"
            ] and await self._process_native_multi_runtime_pipeline(
                connection_id,
                session_dir,
                session_dir / VOICE_SESSION_WAV_FILENAME,
                timings_ms,
                total_started_at,
                operator_agent,
                decoder_selected=decoder_plan["selected"],
            ):
                return

            # STT
            if not self.audio_engine:
                logger.warning("AudioEngine nie jest dostępny")
                await self._send_json(
                    connection_id,
                    {
                        "type": "error",
                        "message": "Audio engine not available",
                    },
                )
                return

            stt_started_at = time.perf_counter()
            transcription = await self.audio_engine.listen(
                normalized_audio,
                language="pl",
                sample_rate=sample_rate,
            )
            timings_ms["stt_ms"] = self._elapsed_ms(stt_started_at)
            self._update_voice_session_metadata(
                session_dir,
                {
                    "pipeline_id": "whisper_llm_piper",
                    "transcription": transcription,
                    "transcription_length": len(transcription or ""),
                    "timings_ms": timings_ms,
                    "voice_mode": self._connection_voice_mode(connection_id),
                    "audio_input_status": "verified",
                    "decoder_source": "faster_whisper",
                    "decoder_selected": decoder_plan["selected"],
                    "decoder_effective": "faster_whisper",
                    "decoder_fallback_reason": decoder_plan["fallback_reason"],
                    "runtime_log_path": _coerce_str(
                        _multi_runtime_setting("GEMMA4_AUDIO_LOG_PATH", ""), ""
                    ),
                },
            )

            await self._run_whisper_llm_pipeline(
                connection_id=connection_id,
                session_dir=session_dir,
                transcription=transcription,
                timings_ms=timings_ms,
                total_started_at=total_started_at,
                operator_agent=operator_agent,
                empty_agent_response_log_suffix="",
            )

        except Exception as e:
            logger.error(f"Błąd podczas przetwarzania bufora audio: {e}")
            await self._send_json(connection_id, {"type": "error", "message": str(e)})

    async def _process_encoded_audio_buffer(
        self,
        connection_id: int,
        audio_chunks: List[bytes],
        operator_agent,
        mime_type: str = "",
    ):
        """Przetwarza nagranie z MediaRecorder przez ffmpeg -> WAV -> STT."""
        assert_runtime_request_allowed(request_kind="voice_chat")
        try:
            total_started_at = time.perf_counter()
            timings_ms: dict[str, float] = {}
            await self._send_json(
                connection_id, {"type": "processing", "status": "decode"}
            )
            decode_started_at = time.perf_counter()
            session_dir = await asyncio.to_thread(
                self._persist_encoded_voice_session,
                connection_id,
                audio_chunks,
                mime_type,
            )
            timings_ms["decode_ms"] = self._elapsed_ms(decode_started_at)
            wav_path = session_dir / VOICE_SESSION_WAV_FILENAME
            normalize_started_at = time.perf_counter()
            audio, sample_rate = self._load_wav_int16(wav_path)
            audio, audio_stats = self._normalize_recorded_audio(audio)
            self._write_wav(wav_path, audio, sample_rate)
            timings_ms["normalize_ms"] = self._elapsed_ms(normalize_started_at)
            route_config = self._voice_route_runtime_config()
            decoder_plan = self._resolve_audio_decoder_plan()
            self._update_voice_session_metadata(
                session_dir,
                {
                    **audio_stats,
                    "sample_rate": sample_rate,
                    "samples": int(audio.size),
                    "duration_sec": float(audio.size / sample_rate)
                    if sample_rate
                    else 0.0,
                    "timings_ms": timings_ms,
                    "runtime": self._build_runtime_metadata(operator_agent),
                    "voice_mode": self._connection_voice_mode(connection_id),
                    "voice_pipeline_mode": self._voice_pipeline_mode(),
                    "voice_route_profile": route_config["voice_route_profile"],
                    "audio_decoder_profile": route_config["audio_decoder_profile"],
                    "audio_decoder_chain": route_config["audio_decoder_chain"],
                    "decoder_selected": decoder_plan["selected"],
                },
            )
            logger.info(f"Zapisano sesję audio MediaRecorder: {session_dir}")

            if decoder_plan["effective"] == "none":
                self._update_voice_session_metadata(
                    session_dir,
                    {
                        "pipeline_id": "none",
                        "audio_input_status": "failed",
                        "decoder_source": "none",
                        "decoder_effective": "none",
                        "decoder_fallback_reason": decoder_plan["fallback_reason"],
                        "fallback_reason": decoder_plan["fallback_reason"],
                    },
                )
                await self._send_json(
                    connection_id,
                    {"type": "error", "message": decoder_plan["fallback_reason"]},
                )
                return

            if not decoder_plan["should_try_native"]:
                self._update_voice_session_metadata(
                    session_dir,
                    {
                        "pipeline_id": "whisper_llm_piper",
                        "audio_input_status": "fallback",
                        "decoder_source": "faster_whisper",
                        "decoder_effective": decoder_plan["effective"],
                        "decoder_fallback_reason": decoder_plan["fallback_reason"],
                        "fallback_reason": decoder_plan["fallback_reason"],
                    },
                )

            if decoder_plan[
                "should_try_native"
            ] and await self._process_native_multi_runtime_pipeline(
                connection_id,
                session_dir,
                wav_path,
                timings_ms,
                total_started_at,
                operator_agent,
                decoder_selected=decoder_plan["selected"],
            ):
                return

            if not self.audio_engine:
                logger.warning("AudioEngine nie jest dostępny")
                await self._send_json(
                    connection_id,
                    {"type": "error", "message": "Audio engine not available"},
                )
                return

            await self._send_json(
                connection_id, {"type": "processing", "status": "stt"}
            )
            stt_started_at = time.perf_counter()
            transcription = await asyncio.to_thread(
                self.audio_engine.transcribe_file,
                str(wav_path),
                "pl",
            )
            timings_ms["stt_ms"] = self._elapsed_ms(stt_started_at)
            self._update_voice_session_metadata(
                session_dir,
                {
                    "pipeline_id": "whisper_llm_piper",
                    "transcription": transcription,
                    "transcription_length": len(transcription or ""),
                    "timings_ms": timings_ms,
                    "audio_input_status": "verified",
                    "decoder_source": "faster_whisper",
                    "decoder_selected": decoder_plan["selected"],
                    "decoder_effective": "faster_whisper",
                    "decoder_fallback_reason": decoder_plan["fallback_reason"],
                    "runtime_log_path": _coerce_str(
                        _multi_runtime_setting("GEMMA4_AUDIO_LOG_PATH", ""), ""
                    ),
                },
            )

            await self._run_whisper_llm_pipeline(
                connection_id=connection_id,
                session_dir=session_dir,
                transcription=transcription,
                timings_ms=timings_ms,
                total_started_at=total_started_at,
                operator_agent=operator_agent,
                empty_agent_response_log_suffix=" (encoded)",
            )
        except Exception as e:
            logger.error(f"Błąd podczas przetwarzania encoded audio: {e}")
            await self._send_json(connection_id, {"type": "error", "message": str(e)})

    async def _run_whisper_llm_pipeline(
        self,
        *,
        connection_id: int,
        session_dir: Path,
        transcription: str,
        timings_ms: dict[str, float],
        total_started_at: float,
        operator_agent: object | None,
        empty_agent_response_log_suffix: str = "",
    ) -> None:
        """Run shared whisper->agent->tts pipeline for PCM and encoded audio."""
        if not transcription:
            await self._send_json(
                connection_id,
                {"type": "transcription", "text": "", "confidence": 0.0},
            )
            return

        await self._send_json(
            connection_id,
            {"type": "transcription", "text": transcription, "confidence": 1.0},
        )
        if not operator_agent:
            await self._send_json(connection_id, {"type": "complete"})
            return

        await self._send_json(
            connection_id, {"type": "processing", "status": "thinking"}
        )
        agent_started_at = time.perf_counter()
        voice_context = _build_voice_session_insights_payload(
            transcript=transcription,
            response="",
            voice_mode=self._connection_voice_mode(connection_id),
            pipeline_id="whisper_llm_piper",
            **_multi_runtime_voice_flags(),
            raw_thinking_available=False,
        )
        voice_context.update(
            {
                "execution_context": VOICE_EXECUTION_CONTEXT,
                "history_scope": VOICE_HISTORY_SCOPE,
            }
        )
        runtime_metadata = self._build_runtime_metadata(operator_agent)
        async with runtime_request_guard(
            request_kind="voice_fallback_llm",
            provider=_coerce_str(runtime_metadata.get("llm_provider"), ""),
            model=_coerce_str(runtime_metadata.get("llm_model"), ""),
        ):
            response_text = await _invoke_operator_agent(
                operator_agent,
                transcription,
                mode=self._connection_voice_mode(connection_id),
                voice_context=voice_context,
            )
            timings_ms["llm_ms"] = self._elapsed_ms(agent_started_at)
            self._update_voice_session_metadata(
                session_dir,
                {
                    "pipeline_id": "whisper_llm_piper",
                    "response_text": response_text,
                    "response_length": len(response_text or ""),
                    **_build_voice_session_insights_payload(
                        transcript=transcription,
                        response=response_text,
                        voice_mode=self._connection_voice_mode(connection_id),
                        pipeline_id="whisper_llm_piper",
                        **_multi_runtime_voice_flags(),
                        raw_thinking_available=False,
                    ),
                    "timings_ms": timings_ms,
                    # In fallback whisper->LLM path, this pair must reflect the LLM that
                    # actually generated the response, not the native multi_runtime daemon.
                    "audio_runtime_provider": runtime_metadata.get("llm_provider"),
                    "audio_runtime_model": runtime_metadata.get("llm_model"),
                    "runtime": runtime_metadata,
                    **self._voice_contract_payload(connection_id),
                },
            )
            if not response_text:
                logger.warning(
                    "Agent zwrócił pustą odpowiedź dla connection_id=%s%s",
                    connection_id,
                    empty_agent_response_log_suffix,
                )
                await self._send_json(
                    connection_id,
                    {
                        "type": "error",
                        "message": "Agent returned empty response. Check runtime status.",
                    },
                )
                return

            await self._send_json(
                connection_id, {"type": "response_text", "text": response_text}
            )
            await self._send_json(
                connection_id, {"type": "processing", "status": "tts"}
            )
            audio_engine = self.audio_engine
            if audio_engine is None:
                logger.warning("Brak audio_engine podczas etapu TTS; pomijam speak().")
                await self._send_json(connection_id, {"type": "complete"})
                return
            tts_started_at = time.perf_counter()
            audio_response = await audio_engine.speak(response_text)
            timings_ms["tts_ms"] = self._elapsed_ms(tts_started_at)
            timings_ms["total_backend_ms"] = self._elapsed_ms(total_started_at)
            self._update_voice_session_metadata(
                session_dir,
                {
                    "timings_ms": timings_ms,
                    "runtime": self._build_runtime_metadata(operator_agent),
                },
            )
            if audio_response is not None:
                await self._send_audio(connection_id, audio_response)

            await self._send_json(connection_id, {"type": "complete"})

    def _persist_encoded_voice_session(
        self,
        connection_id: int,
        encoded_audio: bytes | list[bytes],
        mime_type: str = "",
    ) -> Path:
        """Zapisuje oryginalne MediaRecorder audio i dekoduje je do WAV 16 kHz."""
        session_dir = _create_voice_session_dir(connection_id)
        session_id = session_dir.name

        original_suffix = ".webm" if "webm" in mime_type.lower() else ".bin"
        original_path = session_dir / f"original{original_suffix}"
        with open(original_path, "wb") as original_file:
            if isinstance(encoded_audio, (bytes, bytearray, memoryview)):
                original_file.write(bytes(encoded_audio))
            else:
                for chunk in encoded_audio:
                    original_file.write(chunk)
        wav_path = session_dir / VOICE_SESSION_WAV_FILENAME

        command = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-fflags",
            "+genpts",
            "-avoid_negative_ts",
            "make_zero",
            "-i",
            str(original_path),
            "-ac",
            "1",
            "-ar",
            "16000",
            "-af",
            "aresample=async=1:first_pts=0,highpass=f=80,lowpass=f=7600,dynaudnorm=f=150:g=8:p=0.9",
            "-acodec",
            "pcm_s16le",
            str(wav_path),
        ]
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg decode failed: {result.stderr.strip()}")

        audio, sample_rate = self._load_wav_int16(wav_path)
        metadata = {
            "session_id": session_id,
            "connection_id": connection_id,
            "input_format": "mediarecorder",
            "mime_type": mime_type,
            "original_path": str(original_path),
            "sample_rate": sample_rate,
            "samples": int(audio.size),
            "duration_sec": float(audio.size / sample_rate) if sample_rate else 0.0,
            "created_at": datetime.now(UTC).isoformat(),
            "wav_path": str(wav_path),
            "gain_applied": 1.0,
            "peak_before_normalization": 0.0,
            "dc_offset": 0.0,
        }
        self._update_voice_session_metadata(session_dir, metadata)
        return session_dir

    def _persist_voice_session(
        self,
        connection_id: int,
        audio: np.ndarray,
        sample_rate: int,
        audio_stats: dict[str, float] | None = None,
    ) -> Path:
        """Zapisuje surowe nagranie i zwraca katalog sesji."""
        session_dir = _create_voice_session_dir(connection_id)
        session_id = session_dir.name

        audio_int16 = np.asarray(audio)
        if audio_int16.dtype != np.int16:
            if np.issubdtype(audio_int16.dtype, np.floating):
                audio_int16 = np.clip(audio_int16 * 32768.0, -32768, 32767)
            audio_int16 = audio_int16.astype(np.int16, copy=False)

        wav_path = session_dir / VOICE_SESSION_WAV_FILENAME
        with wave.open(str(wav_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(audio_int16.tobytes())

        metadata = {
            "session_id": session_id,
            "connection_id": connection_id,
            "sample_rate": sample_rate,
            "samples": int(audio_int16.size),
            "duration_sec": float(audio_int16.size / sample_rate)
            if sample_rate
            else 0.0,
            "created_at": datetime.now(UTC).isoformat(),
            "wav_path": str(wav_path),
            "gain_applied": 1.0,
            "peak_before_normalization": 0.0,
            "dc_offset": 0.0,
        }
        if audio_stats:
            metadata.update(audio_stats)
        self._update_voice_session_metadata(session_dir, metadata)
        return session_dir

    def _load_wav_int16(self, wav_path: Path) -> tuple[np.ndarray, int]:
        """Wczytuje mono/stereo WAV jako int16 mono."""
        with wave.open(str(wav_path), "rb") as wf:
            channels = wf.getnchannels()
            sample_rate = wf.getframerate()
            audio = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
        if channels > 1 and audio.size:
            audio = audio.reshape(-1, channels).mean(axis=1).astype(np.int16)
        return audio, sample_rate

    def _write_wav(self, wav_path: Path, audio: np.ndarray, sample_rate: int) -> None:
        """Zapisuje PCM int16 mono do WAV."""
        audio_int16 = np.asarray(audio, dtype=np.int16)
        with wave.open(str(wav_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(audio_int16.tobytes())

    def _normalize_recorded_audio(
        self, audio: np.ndarray
    ) -> tuple[np.ndarray, dict[str, float]]:
        """Normalizuje pełne nagranie bez per-chunk artefaktów."""
        audio_int16 = np.asarray(audio, dtype=np.int16)
        if audio_int16.size == 0:
            return audio_int16, {"gain_applied": 1.0, "peak_before_normalization": 0.0}

        float_audio = audio_int16.astype(np.float32) / 32768.0
        dc_offset = float(np.mean(float_audio))
        float_audio = float_audio - dc_offset
        peak_before = float(np.max(np.abs(float_audio))) if float_audio.size else 0.0
        target_peak = 0.6
        gain = 1.0
        if peak_before > 0:
            gain = min(12.0, max(1.0, target_peak / peak_before))
            float_audio = np.clip(float_audio * gain, -1.0, 1.0)

        normalized = np.clip(float_audio * 32767.0, -32768, 32767).astype(np.int16)
        return normalized, {
            "gain_applied": float(gain),
            "peak_before_normalization": float(peak_before),
            "peak_after_normalization": float(np.max(np.abs(float_audio)))
            if float_audio.size
            else 0.0,
            "rms_before_normalization": float(
                np.sqrt(np.mean(np.square(audio_int16.astype(np.float32) / 32768.0)))
            )
            if audio_int16.size
            else 0.0,
            "rms_after_normalization": float(
                np.sqrt(np.mean(np.square(float_audio.astype(np.float32))))
            )
            if float_audio.size
            else 0.0,
            "dc_offset": float(dc_offset),
        }

    def _elapsed_ms(self, started_at: float) -> float:
        """Zwraca czas etapu w milisekundach, zaokrąglony dla metadanych UI."""
        return round((time.perf_counter() - started_at) * 1000.0, 1)

    def _build_runtime_metadata(self, operator_agent=None) -> dict[str, Any]:
        """Buduje snapshot runtime STT/LLM/TTS dla sesji głosowej."""
        audio_engine = self.audio_engine
        whisper = getattr(audio_engine, "whisper", None) if audio_engine else None
        voice = getattr(audio_engine, "voice", None) if audio_engine else None
        service_id = None
        if operator_agent is not None and hasattr(
            operator_agent, "_resolve_chat_service_id"
        ):
            try:
                service_id = operator_agent._resolve_chat_service_id()
            except Exception:
                service_id = None
        runtime_provider = _coerce_str(
            getattr(SETTINGS, "ACTIVE_LLM_SERVER", ""),
            "",
        )
        runtime_model = getattr(SETTINGS, "LLM_MODEL_NAME", None)
        try:
            runtime = get_active_llm_runtime()
            runtime_provider = _coerce_str(
                getattr(runtime, "provider", ""),
                runtime_provider,
            )
            runtime_model = getattr(runtime, "model_name", runtime_model)
        except Exception as exc:
            logger.debug(
                "Nie udało się pobrać live runtime dla metadata audio: %s",
                exc,
            )
        return {
            "stt_model": getattr(whisper, "model_size", None),
            "stt_device": getattr(whisper, "device", None),
            "stt_compute_type": getattr(whisper, "compute_type", None),
            "llm_service_id": service_id,
            "llm_provider": runtime_provider,
            "llm_model": runtime_model,
            "tts_model_path": getattr(voice, "model_path", None),
            "tts_fallback": getattr(voice, "is_fallback_mode", None),
            "tts_sample_rate": self._get_tts_sample_rate(),
            **self._multi_runtime_runtime_snapshot(),
        }

    def _update_voice_session_metadata(
        self, session_dir: Path, payload: dict[str, Any]
    ) -> None:
        """Dopisuje metadane do metadata.json."""
        metadata_path = session_dir / VOICE_SESSION_METADATA_FILENAME
        current: dict[str, Any] = {}
        if metadata_path.exists():
            try:
                current = json.loads(metadata_path.read_text(encoding="utf-8"))
            except Exception:
                current = {}
        current.update(payload)
        metadata_path.write_text(
            json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    async def _send_json(self, connection_id: int, data: dict[str, Any]) -> None:
        """
        Wysyła JSON przez WebSocket.

        Args:
            connection_id: ID połączenia
            data: Dane do wysłania
        """
        import json

        try:
            conn = self.active_connections.get(connection_id)
            if conn:
                await conn["websocket"].send_text(json.dumps(data))
        except Exception as e:
            logger.error(f"Błąd podczas wysyłania JSON: {e}")

    async def _send_audio(self, connection_id: int, audio_data: np.ndarray):
        """
        Wysyła audio przez WebSocket.

        Args:
            connection_id: ID połączenia
            audio_data: Dane audio (numpy array)
        """
        try:
            conn = self.active_connections.get(connection_id)
            if conn:
                # Konwertuj do bytes
                audio_bytes = audio_data.tobytes()

                # Zakoduj jako base64 (dla JSON) lub wyślij bezpośrednio jako bytes
                # Tutaj używamy JSON dla prostoty
                import json

                message = {
                    "type": "audio_response",
                    "audio": base64.b64encode(audio_bytes).decode("utf-8"),
                    "sample_rate": self._get_tts_sample_rate(),
                    "format": "int16",
                    "channels": 1,
                    "bytes": len(audio_bytes),
                }

                await conn["websocket"].send_text(json.dumps(message))

        except Exception as e:
            logger.error(f"Błąd podczas wysyłania audio: {e}")

    def _get_tts_sample_rate(self) -> int:
        """Zwraca sample rate ostatniej syntezy TTS."""
        voice = getattr(self.audio_engine, "voice", None) if self.audio_engine else None
        return int(getattr(voice, "output_sample_rate", 22050) or 22050)


# Singleton instance
audio_stream_handler: Optional[AudioStreamHandler] = None


def get_audio_stream_handler() -> AudioStreamHandler:
    """
    Pobiera globalną instancję AudioStreamHandler.

    Returns:
        AudioStreamHandler instance
    """
    global audio_stream_handler
    if audio_stream_handler is None:
        audio_stream_handler = AudioStreamHandler()
    return audio_stream_handler
