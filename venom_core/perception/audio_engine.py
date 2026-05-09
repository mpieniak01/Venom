"""Moduł: audio_engine - silnik audio dla STT i TTS."""

import asyncio
import queue
import subprocess
import threading
import wave
from pathlib import Path
from typing import Any, Optional

import numpy as np

from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class WhisperSkill:
    """
    Skill do transkrypcji mowy na tekst (STT) przy użyciu faster-whisper.
    Działa lokalnie na CPU/GPU bez wymagania połączenia internetowego.
    """

    def __init__(
        self,
        model_size: str = "base",
        device: str = "cpu",
        compute_type: str = "int8",
    ):
        """
        Inicjalizacja Whisper STT.

        Args:
            model_size: Rozmiar modelu ('tiny', 'base', 'small', 'medium', 'large')
            device: Urządzenie ('cpu', 'cuda')
            compute_type: Typ obliczeń ('int8', 'float16', 'float32')
        """
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.model: Optional[Any] = None
        logger.info(f"Inicjalizacja WhisperSkill: model={model_size}, device={device}")

    def _load_model(self):
        """Lazy loading modelu (tylko gdy potrzebny)."""
        if self.model is None:
            try:
                from faster_whisper import WhisperModel

                self.model = WhisperModel(
                    self.model_size,
                    device=self.device,
                    compute_type=self.compute_type,
                )
                logger.info("Model Whisper załadowany pomyślnie")
            except ImportError:
                logger.error(
                    "faster-whisper nie jest zainstalowany. Użyj: pip install faster-whisper"
                )
                raise
            except Exception as e:
                logger.error(f"Błąd podczas ładowania modelu Whisper: {e}")
                raise

    def _transcribe_buffer_sync(
        self, audio_buffer: np.ndarray, language: str = "pl", sample_rate: int = 16000
    ) -> str:
        """Synchronously transcribe a preloaded audio buffer."""
        self._load_model()

        try:
            model = self.model
            if model is None:
                raise RuntimeError("Model Whisper nie został zainicjalizowany.")

            audio_buffer = self._prepare_audio_buffer(
                audio_buffer, sample_rate=sample_rate
            )
            audio_buffer = self._trim_silence(audio_buffer)
            if audio_buffer.size:
                rms = float(np.sqrt(np.mean(np.square(audio_buffer, dtype=np.float32))))
                peak = float(np.max(np.abs(audio_buffer)))
                logger.info(
                    f"Audio STT stats: samples={audio_buffer.size}, sample_rate={sample_rate}, rms={rms:.6f}, peak={peak:.6f}"
                )
            segments, _ = model.transcribe(
                audio_buffer,
                language=language,
                beam_size=5,
                vad_filter=False,
            )
            transcription = " ".join(segment.text for segment in segments)
            logger.info(f"Transkrypcja: {transcription}")
            return transcription.strip()
        except Exception as e:
            logger.error(f"Błąd podczas transkrypcji: {e}")
            return ""

    def _prepare_audio_buffer(
        self, audio_buffer: np.ndarray, sample_rate: int = 16000
    ) -> np.ndarray:
        """Normalize audio to mono float32 and resample to 16 kHz."""
        audio = np.asarray(audio_buffer)
        if audio.size == 0:
            return np.zeros(0, dtype=np.float32)

        if audio.ndim > 1:
            audio = audio.reshape(-1)

        if audio.dtype == np.int16:
            audio = audio.astype(np.float32) / 32768.0
        elif audio.dtype == np.int32:
            audio = audio.astype(np.float32) / 2147483648.0
        elif audio.dtype == np.uint8:
            audio = (audio.astype(np.float32) - 128.0) / 128.0
        else:
            audio = audio.astype(np.float32, copy=False)

        audio = np.clip(audio, -1.0, 1.0)
        if sample_rate and sample_rate != 16000 and audio.size > 1:
            target_len = max(1, int(round(len(audio) * 16000 / sample_rate)))
            src_idx = np.linspace(0.0, 1.0, num=len(audio), endpoint=True)
            dst_idx = np.linspace(0.0, 1.0, num=target_len, endpoint=True)
            audio = np.interp(dst_idx, src_idx, audio.astype(np.float64)).astype(
                np.float32
            )

        peak = float(np.max(np.abs(audio))) if audio.size else 0.0
        if 0.0 < peak < 0.1:
            audio = audio * (0.9 / peak)
            audio = np.clip(audio, -1.0, 1.0)

        return np.ascontiguousarray(audio, dtype=np.float32)

    def _trim_silence(
        self, audio: np.ndarray, threshold: float = 0.015, pad_samples: int = 1600
    ) -> np.ndarray:
        """Wytnij ciszę z początku i końca przed transkrypcją."""
        if audio.size == 0:
            return audio

        magnitude = np.abs(audio)
        active = np.flatnonzero(magnitude >= threshold)
        if active.size == 0:
            return audio

        start = max(0, int(active[0]) - pad_samples)
        end = min(audio.size, int(active[-1]) + pad_samples + 1)
        return audio[start:end]

    def _load_audio_file(self, file_path: str) -> tuple[np.ndarray, int]:
        """Load audio from file and return raw mono samples plus sample rate."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Plik audio nie istnieje: {file_path}")

        try:
            with wave.open(str(path), "rb") as wf:
                sample_rate = wf.getframerate()
                channels = wf.getnchannels()
                sampwidth = wf.getsampwidth()
                frames = wf.readframes(wf.getnframes())

            if sampwidth == 1:
                audio = np.frombuffer(frames, dtype=np.uint8).astype(np.int16)
                audio = (audio - 128) << 8
            elif sampwidth == 2:
                audio = np.frombuffer(frames, dtype=np.int16)
            elif sampwidth == 4:
                audio = (np.frombuffer(frames, dtype=np.int32) >> 16).astype(np.int16)
            else:
                raise ValueError(f"Nieobsługiwana głębia bitowa WAV: {sampwidth}")

            if channels > 1:
                audio = audio.reshape(-1, channels).mean(axis=1)

            return np.ascontiguousarray(audio, dtype=np.int16), sample_rate
        except Exception:
            # Fallback do ffmpeg, który obsługuje także mp3/ogg/flac/m4a.
            result = subprocess.run(
                [
                    "ffmpeg",
                    "-nostdin",
                    "-i",
                    str(path),
                    "-ac",
                    "1",
                    "-ar",
                    "16000",
                    "-f",
                    "s16le",
                    "pipe:1",
                ],
                check=True,
                capture_output=True,
            )
            audio = np.frombuffer(result.stdout, dtype=np.int16)
            return np.ascontiguousarray(audio, dtype=np.int16), 16000

    async def transcribe(
        self, audio_buffer: np.ndarray, language: str = "pl", sample_rate: int = 16000
    ) -> str:
        """
        Transkrybuje audio na tekst.

        Args:
            audio_buffer: Bufor audio (numpy array, 16kHz, mono)
            language: Język transkrypcji ('pl', 'en', etc.)

        Returns:
            Transkrybowany tekst
        """
        return await asyncio.to_thread(
            self._transcribe_buffer_sync, audio_buffer, language, sample_rate
        )

    def transcribe_file(self, file_path: str, language: str = "pl") -> str:
        """Transcribe an audio file from disk."""
        audio_buffer, sample_rate = self._load_audio_file(file_path)
        return self._transcribe_buffer_sync(
            audio_buffer, language=language, sample_rate=sample_rate
        )


class VoiceSkill:
    """
    Skill do syntezy mowy (TTS) przy użyciu piper-tts.
    Bardzo szybki, działa na ONNX lokalnie.
    """

    def __init__(
        self,
        model_path: Optional[str] = None,
        speaker_id: int = 0,
    ):
        """
        Inicjalizacja Piper TTS.

        Args:
            model_path: Ścieżka do modelu ONNX (np. 'en_US-lessac-medium.onnx')
            speaker_id: ID głosu (dla modeli multi-speaker)
        """
        self.model_path = model_path
        self.speaker_id = speaker_id
        self.voice: Optional[Any] = None
        self.output_sample_rate = 22050
        self.audio_queue: queue.Queue[Optional[np.ndarray]] = queue.Queue()
        self._playback_thread: Optional[threading.Thread] = None
        self._stop_playback = threading.Event()

        # Walidacja modelu i ustawienie trybu fallback
        self.is_fallback_mode = self._validate_model_path()

    def _validate_model_path(self) -> bool:
        """
        Waliduje ścieżkę do modelu i określa czy należy użyć trybu fallback.

        Returns:
            True jeśli tryb fallback jest wymagany, False w przeciwnym razie
        """
        if not self.model_path:
            logger.warning(
                "Brak ścieżki do modelu TTS. VoiceSkill będzie działał w trybie mock."
            )
            return True

        model_file = Path(self.model_path)
        if not model_file.exists():
            logger.warning(
                f"Model TTS nie istnieje: {self.model_path}. VoiceSkill będzie działał w trybie mock."
            )
            return True

        logger.info(f"Inicjalizacja VoiceSkill: model_path={self.model_path}")
        return False

    def _load_model(self):
        """Lazy loading modelu TTS."""
        if self.voice is None and not self.is_fallback_mode:
            try:
                import piper

                self.voice = piper.PiperVoice.load(self.model_path)
                logger.info("Model Piper TTS załadowany pomyślnie")
            except ImportError:
                logger.warning(
                    "piper-tts nie jest zainstalowany. VoiceSkill działa w trybie mock."
                )
                self.is_fallback_mode = True
            except Exception as e:
                logger.error(f"Błąd podczas ładowania modelu TTS: {e}")
                self.is_fallback_mode = True

    async def speak(self, text: str) -> Optional[np.ndarray]:
        """
        Syntetyzuje mowę z tekstu.

        Args:
            text: Tekst do wypowiedzenia

        Returns:
            Audio stream (numpy array) lub None w przypadku błędu
        """
        if not text.strip():
            return None

        # Usuń markdown i formatowanie (nie nadaje się do TTS)
        text = self._clean_text_for_speech(text)

        try:
            self._load_model()

            voice = self.voice
            if voice is None or self.is_fallback_mode:
                # Mock mode - zwróć ciszę
                logger.warning("TTS w trybie mock (fallback) - zwracam ciszę")
                return np.zeros(16000, dtype=np.int16)  # 1 sekunda ciszy

            audio_stream = await asyncio.to_thread(self._synthesize_with_piper, text)

            if isinstance(audio_stream, (bytes, bytearray, memoryview)):
                audio_stream = np.frombuffer(audio_stream, dtype=np.int16)
            else:
                audio_stream = np.asarray(audio_stream)
            if audio_stream.dtype != np.int16:
                if np.issubdtype(audio_stream.dtype, np.floating):
                    audio_stream = np.clip(audio_stream * 32768.0, -32768, 32767)
                audio_stream = audio_stream.astype(np.int16, copy=False)

            logger.info(f"Syntetyzowano mowę: {text[:50]}...")
            return audio_stream

        except Exception as e:
            logger.error(f"Błąd podczas syntezy mowy: {e}")
            return None

    def _synthesize_with_piper(self, text: str) -> np.ndarray:
        """Dostosowuje aktualne API piper-tts do kontraktu PCM int16."""
        voice = self.voice
        if voice is None:
            return np.zeros(0, dtype=np.int16)

        try:
            from piper.config import SynthesisConfig

            syn_config = SynthesisConfig(speaker_id=self.speaker_id)
        except Exception:
            syn_config = None

        chunks = list(voice.synthesize(text, syn_config=syn_config))
        if not chunks:
            return np.zeros(0, dtype=np.int16)

        first_chunk = chunks[0]
        self.output_sample_rate = int(
            getattr(first_chunk, "sample_rate", 22050) or 22050
        )
        arrays = [
            np.asarray(chunk.audio_int16_array, dtype=np.int16) for chunk in chunks
        ]
        return np.concatenate(arrays) if arrays else np.zeros(0, dtype=np.int16)

    def _clean_text_for_speech(self, text: str) -> str:
        """
        Czyści tekst z markdown i formatowania.

        Args:
            text: Surowy tekst

        Returns:
            Oczyszczony tekst gotowy do TTS
        """
        import re

        # Usuń bloki kodu
        text = re.sub(r"```[\s\S]*?```", "", text)
        text = re.sub(r"`[^`]+`", "", text)

        # Usuń markdown formatting
        text = re.sub(r"[*_~#]", "", text)

        # Usuń linki markdown
        text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)

        # Zamień wielokrotne spacje na pojedyncze
        text = re.sub(r"\s+", " ", text)

        return text.strip()

    async def start_playback_queue(self):
        """Uruchamia wątek do odtwarzania kolejki audio."""
        if self._playback_thread is None or not self._playback_thread.is_alive():
            self._stop_playback.clear()
            self._playback_thread = threading.Thread(
                target=self._playback_worker, daemon=True
            )
            self._playback_thread.start()
            await asyncio.sleep(0)
            logger.info("Wątek odtwarzania audio uruchomiony")

    def _playback_worker(self):
        """Worker do odtwarzania audio z kolejki."""
        try:
            import sounddevice as sd

            while not self._stop_playback.is_set():
                try:
                    audio_data = self.audio_queue.get(timeout=1.0)
                    if audio_data is not None:
                        # Odtwórz audio
                        sd.play(audio_data, samplerate=22050)
                        sd.wait()
                except queue.Empty:
                    continue
                except Exception as e:
                    logger.error(f"Błąd podczas odtwarzania audio: {e}")

        except ImportError:
            logger.error(
                "sounddevice nie jest zainstalowany. Użyj: pip install sounddevice"
            )

    async def stop_playback_queue(self):
        """Zatrzymuje wątek odtwarzania."""
        self._stop_playback.set()
        if self._playback_thread:
            await asyncio.to_thread(self._playback_thread.join, 2.0)
            logger.info("Wątek odtwarzania audio zatrzymany")


class AudioEngine:
    """
    Główny silnik audio łączący STT i TTS.
    Zapewnia interfejs wysokiego poziomu dla agentów.
    """

    def __init__(
        self,
        whisper_model_size: str = "base",
        tts_model_path: Optional[str] = None,
        device: str = "cpu",
    ):
        """
        Inicjalizacja silnika audio.

        Args:
            whisper_model_size: Rozmiar modelu Whisper
            tts_model_path: Ścieżka do modelu TTS
            device: Urządzenie ('cpu', 'cuda')
        """
        self.whisper = WhisperSkill(
            model_size=whisper_model_size,
            device=device,
        )
        self.voice = VoiceSkill(model_path=tts_model_path)
        logger.info("AudioEngine zainicjalizowany")

    async def listen(
        self, audio_buffer: np.ndarray, language: str = "pl", sample_rate: int = 16000
    ) -> str:
        """
        Transkrybuje audio na tekst.

        Args:
            audio_buffer: Bufor audio
            language: Język transkrypcji

        Returns:
            Transkrybowany tekst
        """
        return await self.whisper.transcribe(
            audio_buffer, language=language, sample_rate=sample_rate
        )

    def transcribe_file(self, file_path: str, language: str = "pl") -> str:
        """Synchronously transcribe an audio file from disk."""
        return self.whisper.transcribe_file(file_path, language=language)

    async def warmup(self) -> dict[str, bool]:
        """Preload STT/TTS models so first user-facing request is faster."""
        warmup_state = {"whisper_loaded": False, "tts_loaded": False}

        try:
            await asyncio.to_thread(self.whisper._load_model)
            warmup_state["whisper_loaded"] = self.whisper.model is not None
        except Exception as exc:
            logger.warning(f"Nie udało się podgrzać Whisper: {exc}")

        try:
            if not self.voice.is_fallback_mode:
                await asyncio.to_thread(self.voice._load_model)
                warmup_state["tts_loaded"] = self.voice.voice is not None
            else:
                warmup_state["tts_loaded"] = False
        except Exception as exc:
            logger.warning(f"Nie udało się podgrzać Piper: {exc}")

        return warmup_state

    async def speak(self, text: str) -> Optional[np.ndarray]:
        """
        Syntetyzuje mowę z tekstu.

        Args:
            text: Tekst do wypowiedzenia

        Returns:
            Audio stream
        """
        return await self.voice.speak(text)

    async def process_voice_command(
        self, audio_buffer: np.ndarray, language: str = "pl", sample_rate: int = 16000
    ) -> str:
        """
        Przetwarza komendę głosową (STT).

        Args:
            audio_buffer: Bufor audio z mikrofonem
            language: Język

        Returns:
            Transkrybowany tekst komendy
        """
        text = await self.listen(
            audio_buffer, language=language, sample_rate=sample_rate
        )
        logger.info(f"Komenda głosowa: {text}")
        return text
