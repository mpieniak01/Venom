"""Moduł: audio_stream - WebSocket endpoint dla streamingu audio."""

import asyncio
import base64
import importlib.util
import json
import shutil
import subprocess
import time
import wave
from datetime import UTC, datetime
from pathlib import Path
from typing import Dict, List, Optional, TypedDict

import numpy as np
from fastapi import WebSocket, WebSocketDisconnect

from venom_core.config import SETTINGS
from venom_core.perception.audio_engine import AudioEngine
from venom_core.utils.logger import get_logger

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


def collect_latest_voice_session_record(
    session_root: Path = VOICE_SESSION_ROOT,
) -> dict[str, object] | None:
    """Zwraca najnowszą sesję voice z katalogu sesji."""
    if not session_root.exists():
        return None

    candidates: list[tuple[float, Path, dict[str, object]]] = []
    for session_dir in session_root.iterdir():
        if not session_dir.is_dir():
            continue
        wav_path = session_dir / "recording.wav"
        if not wav_path.exists():
            continue

        metadata_path = session_dir / "metadata.json"
        stat_source = metadata_path if metadata_path.exists() else wav_path
        try:
            mtime = stat_source.stat().st_mtime
        except OSError:
            continue

        metadata: dict[str, object] = {}
        if metadata_path.exists():
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except Exception:
                metadata = {}
        candidates.append((mtime, session_dir, metadata))

    for _mtime, latest_dir, metadata in sorted(
        candidates, key=lambda item: item[0], reverse=True
    ):
        duration_sec = metadata.get("duration_sec")
        samples = metadata.get("samples")
        try:
            if (
                duration_sec is not None
                and float(duration_sec) < MIN_VOICE_SESSION_DURATION_SEC
            ):
                continue
        except Exception:
            pass
        try:
            if samples is not None and int(samples) < 4096:
                continue
        except Exception:
            pass

        metadata_path = latest_dir / "metadata.json"
        wav_path = latest_dir / "recording.wav"
        return {
            "session_id": latest_dir.name,
            "created_at": metadata.get("created_at"),
            "duration_sec": duration_sec,
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
            "wav_path": str(wav_path),
            "metadata_path": str(metadata_path) if metadata_path.exists() else None,
            "transcription": metadata.get("transcription") or "",
            "response_text": metadata.get("response_text") or "",
        }

    return None


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
                    await self._handle_audio_data(
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
    ):
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
            command = data.get("command")

            if command == "start_recording":
                # Rozpocznij nagrywanie
                conn = self.active_connections[connection_id]
                conn["audio_buffer"] = []
                conn["audio_bytes_buffer"] = []
                conn["is_speaking"] = True
                self._cancel_silence_finalize_task(conn)
                audio_config = conn.get("audio_config") or {}
                conn["sample_rate"] = int(
                    data.get("sample_rate") or audio_config.get("sample_rate") or 16000
                )
                conn["speech_detected"] = False
                conn["recording_format"] = str(
                    data.get("format") or audio_config.get("format") or "pcm16"
                )
                conn["mime_type"] = str(
                    data.get("mime_type") or audio_config.get("mime_type") or ""
                )
                conn["channels"] = int(
                    data.get("channels") or audio_config.get("channels") or 1
                )
                conn["audio_config"] = {
                    "sample_rate": conn["sample_rate"],
                    "channels": conn["channels"],
                    "format": conn["recording_format"],
                    "mime_type": conn["mime_type"],
                }
                logger.info(
                    "Rozpoczęto nagrywanie: "
                    f"{connection_id} config={conn['audio_config']}"
                )

                # Wyślij potwierdzenie
                await self._send_json(
                    connection_id, {"type": "recording_started", "status": "ok"}
                )

            elif command == "audio_config":
                conn = self.active_connections[connection_id]
                conn["audio_config"] = {
                    "sample_rate": int(data.get("sample_rate") or 16000),
                    "channels": int(data.get("channels") or 1),
                    "format": str(data.get("format") or "pcm16"),
                    "mime_type": str(data.get("mime_type") or ""),
                }
                if data.get("sample_rate"):
                    conn["sample_rate"] = int(data.get("sample_rate"))
                if data.get("format"):
                    conn["recording_format"] = str(data.get("format"))
                if data.get("mime_type"):
                    conn["mime_type"] = str(data.get("mime_type"))
                logger.info(
                    f"Ustawiono audio_config dla {connection_id}: {conn['audio_config']}"
                )
                await self._send_json(
                    connection_id,
                    {
                        "type": "audio_config",
                        "status": "ok",
                        "config": conn["audio_config"],
                    },
                )

            elif command == "voice_mode":
                conn = self.active_connections[connection_id]
                voice_mode = str(data.get("mode") or "standard").strip() or "standard"
                conn["voice_mode"] = voice_mode
                logger.info(f"Ustawiono voice_mode dla {connection_id}: {voice_mode}")
                await self._send_json(
                    connection_id,
                    {
                        "type": "voice_mode",
                        "status": "ok",
                        "mode": voice_mode,
                    },
                )

            elif command == "stop_recording":
                # Zakończ nagrywanie i przetwórz
                conn = self.active_connections[connection_id]
                conn["is_speaking"] = False
                self._cancel_silence_finalize_task(conn)
                logger.info(
                    "Zakończono nagrywanie: "
                    f"{connection_id} (pcm_chunks={len(conn['audio_buffer'])}, "
                    f"encoded_chunks={len(conn['audio_bytes_buffer'])}, "
                    f"format={conn['recording_format']})"
                )

                # Przetwórz audio
                if conn["audio_bytes_buffer"] and conn["recording_format"] != "pcm16":
                    await self._process_encoded_audio_buffer(
                        connection_id,
                        conn["audio_bytes_buffer"],
                        operator_agent,
                        mime_type=conn.get("mime_type", ""),
                    )
                    conn["audio_bytes_buffer"] = []
                elif conn["audio_buffer"]:
                    await self._process_audio_buffer(
                        connection_id,
                        conn["audio_buffer"],
                        operator_agent,
                        sample_rate=conn.get("sample_rate", 16000),
                    )
                    conn["audio_buffer"] = []

            elif command == "ping":
                # Keep-alive
                await self._send_json(connection_id, {"type": "pong"})

        except json.JSONDecodeError:
            logger.error(f"Nieprawidłowy JSON: {message}")
        except Exception as e:
            logger.error(f"Błąd podczas obsługi wiadomości sterującej: {e}")

    async def _handle_audio_data(
        self, connection_id: int, audio_bytes: bytes, operator_agent
    ):
        """
        Obsługuje dane audio (blob).

        Args:
            connection_id: ID połączenia
            audio_bytes: Surowe dane audio
            operator_agent: Agent operatora
        """
        try:
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
                    sample_rate=int(conn.get("sample_rate", 16000)),
                )

        except Exception as e:
            logger.error(f"Błąd podczas obsługi audio data: {e}")

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

    def _cancel_silence_finalize_task(self, conn: dict[str, object] | None) -> None:
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
            except asyncio.CancelledError:
                return
            finally:
                current = self.active_connections.get(connection_id)
                if current and current.get("silence_finalize_task") is task:
                    current["silence_finalize_task"] = None

        task = asyncio.create_task(finalize_after_silence())
        conn["silence_finalize_task"] = task

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
            self._update_voice_session_metadata(
                session_dir,
                {"runtime": self._build_runtime_metadata(operator_agent)},
            )
            logger.info(f"Zapisano sesję audio: {session_dir}")

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
                    "transcription": transcription,
                    "transcription_length": len(transcription or ""),
                    "timings_ms": timings_ms,
                    "voice_mode": self.active_connections.get(connection_id, {}).get(
                        "voice_mode", "standard"
                    ),
                },
            )

            if not transcription:
                await self._send_json(
                    connection_id,
                    {"type": "transcription", "text": "", "confidence": 0.0},
                )
                return

            # Wyślij transkrypcję do klienta
            await self._send_json(
                connection_id,
                {"type": "transcription", "text": transcription, "confidence": 1.0},
            )

            # Przetwórz komendę przez agenta
            if operator_agent:
                await self._send_json(
                    connection_id, {"type": "processing", "status": "thinking"}
                )

                agent_started_at = time.perf_counter()
                response_text = await operator_agent.process(
                    transcription,
                    mode=str(
                        self.active_connections.get(connection_id, {}).get(
                            "voice_mode", "standard"
                        )
                    ),
                )
                timings_ms["llm_ms"] = self._elapsed_ms(agent_started_at)
                self._update_voice_session_metadata(
                    session_dir,
                    {
                        "response_text": response_text,
                        "response_length": len(response_text or ""),
                        "timings_ms": timings_ms,
                    },
                )

                # Wyślij tekst odpowiedzi
                await self._send_json(
                    connection_id, {"type": "response_text", "text": response_text}
                )

                # TTS
                await self._send_json(
                    connection_id, {"type": "processing", "status": "tts"}
                )

                tts_started_at = time.perf_counter()
                audio_response = await self.audio_engine.speak(response_text)
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
                    # Wyślij audio do odtworzenia
                    await self._send_audio(connection_id, audio_response)

            # Gotowe
            await self._send_json(connection_id, {"type": "complete"})

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
            wav_path = session_dir / "recording.wav"
            normalize_started_at = time.perf_counter()
            audio, sample_rate = self._load_wav_int16(wav_path)
            audio, audio_stats = self._normalize_recorded_audio(audio)
            self._write_wav(wav_path, audio, sample_rate)
            timings_ms["normalize_ms"] = self._elapsed_ms(normalize_started_at)
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
                    "voice_mode": self.active_connections.get(connection_id, {}).get(
                        "voice_mode", "standard"
                    ),
                },
            )
            logger.info(f"Zapisano sesję audio MediaRecorder: {session_dir}")

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
                    "transcription": transcription,
                    "transcription_length": len(transcription or ""),
                    "timings_ms": timings_ms,
                },
            )

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

            if operator_agent:
                await self._send_json(
                    connection_id, {"type": "processing", "status": "thinking"}
                )
                agent_started_at = time.perf_counter()
                response_text = await operator_agent.process(
                    transcription,
                    mode=str(
                        self.active_connections.get(connection_id, {}).get(
                            "voice_mode", "standard"
                        )
                    ),
                )
                timings_ms["llm_ms"] = self._elapsed_ms(agent_started_at)
                self._update_voice_session_metadata(
                    session_dir,
                    {
                        "response_text": response_text,
                        "response_length": len(response_text or ""),
                        "timings_ms": timings_ms,
                    },
                )
                await self._send_json(
                    connection_id, {"type": "response_text", "text": response_text}
                )
                await self._send_json(
                    connection_id, {"type": "processing", "status": "tts"}
                )
                tts_started_at = time.perf_counter()
                audio_response = await self.audio_engine.speak(response_text)
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
        except Exception as e:
            logger.error(f"Błąd podczas przetwarzania encoded audio: {e}")
            await self._send_json(connection_id, {"type": "error", "message": str(e)})

    def _persist_encoded_voice_session(
        self,
        connection_id: int,
        encoded_audio: bytes | list[bytes],
        mime_type: str = "",
    ) -> Path:
        """Zapisuje oryginalne MediaRecorder audio i dekoduje je do WAV 16 kHz."""
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        session_dir = VOICE_SESSION_ROOT / f"{timestamp}_{connection_id}"
        session_dir.mkdir(parents=True, exist_ok=True)
        session_id = session_dir.name

        original_suffix = ".webm" if "webm" in mime_type.lower() else ".bin"
        original_path = session_dir / f"original{original_suffix}"
        with open(original_path, "wb") as original_file:
            if isinstance(encoded_audio, (bytes, bytearray, memoryview)):
                original_file.write(bytes(encoded_audio))
            else:
                for chunk in encoded_audio:
                    original_file.write(chunk)
        wav_path = session_dir / "recording.wav"

        command = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(original_path),
            "-ac",
            "1",
            "-ar",
            "16000",
            "-af",
            "highpass=f=80,lowpass=f=7600,dynaudnorm=f=150:g=8:p=0.9",
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
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        session_dir = VOICE_SESSION_ROOT / f"{timestamp}_{connection_id}"
        session_dir.mkdir(parents=True, exist_ok=True)
        session_id = session_dir.name

        audio_int16 = np.asarray(audio)
        if audio_int16.dtype != np.int16:
            if np.issubdtype(audio_int16.dtype, np.floating):
                audio_int16 = np.clip(audio_int16 * 32768.0, -32768, 32767)
            audio_int16 = audio_int16.astype(np.int16, copy=False)

        wav_path = session_dir / "recording.wav"
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

    def _build_runtime_metadata(self, operator_agent=None) -> dict[str, object]:
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
        return {
            "stt_model": getattr(whisper, "model_size", None),
            "stt_device": getattr(whisper, "device", None),
            "stt_compute_type": getattr(whisper, "compute_type", None),
            "llm_service_id": service_id,
            "llm_model": getattr(SETTINGS, "LLM_MODEL_NAME", None),
            "tts_model_path": getattr(voice, "model_path", None),
            "tts_fallback": getattr(voice, "is_fallback_mode", None),
            "tts_sample_rate": self._get_tts_sample_rate(),
        }

    def _update_voice_session_metadata(self, session_dir: Path, payload: dict) -> None:
        """Dopisuje metadane do session.json."""
        metadata_path = session_dir / "metadata.json"
        current: dict = {}
        if metadata_path.exists():
            try:
                current = json.loads(metadata_path.read_text(encoding="utf-8"))
            except Exception:
                current = {}
        current.update(payload)
        metadata_path.write_text(
            json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    async def _send_json(self, connection_id: int, data: dict):
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
