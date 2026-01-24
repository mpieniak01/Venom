"""Moduł: audio_engine - silnik audio dla STT i TTS."""

import asyncio
import queue
import threading
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
                from faster_whisper import WhisperModel  # type: ignore[import-untyped]

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

    async def transcribe(self, audio_buffer: np.ndarray, language: str = "pl") -> str:
        """
        Transkrybuje audio na tekst.

        Args:
            audio_buffer: Bufor audio (numpy array, 16kHz, mono)
            language: Język transkrypcji ('pl', 'en', etc.)

        Returns:
            Transkrybowany tekst
        """
        self._load_model()

        try:
            # Wykonaj transkrypcję w osobnym wątku aby nie blokować event loop
            loop = asyncio.get_event_loop()
            model = self.model
            if model is None:
                raise RuntimeError("Model Whisper nie został zainicjalizowany.")
            segments, info = await loop.run_in_executor(
                None,
                lambda: model.transcribe(
                    audio_buffer,
                    language=language,
                    beam_size=5,
                    vad_filter=True,  # Voice Activity Detection
                ),
            )

            # Zbierz wszystkie segmenty
            transcription = " ".join([segment.text for segment in segments])
            logger.info(f"Transkrypcja: {transcription}")
            return transcription.strip()

        except Exception as e:
            logger.error(f"Błąd podczas transkrypcji: {e}")
            return ""


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

            # Wykonaj syntezę w osobnym wątku
            loop = asyncio.get_event_loop()
            audio_stream = await loop.run_in_executor(
                None,
                lambda: voice.synthesize(text, speaker_id=self.speaker_id),
            )

            logger.info(f"Syntetyzowano mowę: {text[:50]}...")
            return audio_stream

        except Exception as e:
            logger.error(f"Błąd podczas syntezy mowy: {e}")
            return None

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
            logger.info("Wątek odtwarzania audio uruchomiony")

    def _playback_worker(self):
        """Worker do odtwarzania audio z kolejki."""
        try:
            import sounddevice as sd  # type: ignore[import-untyped]

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
            self._playback_thread.join(timeout=2.0)
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

    async def listen(self, audio_buffer: np.ndarray, language: str = "pl") -> str:
        """
        Transkrybuje audio na tekst.

        Args:
            audio_buffer: Bufor audio
            language: Język transkrypcji

        Returns:
            Transkrybowany tekst
        """
        return await self.whisper.transcribe(audio_buffer, language=language)

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
        self, audio_buffer: np.ndarray, language: str = "pl"
    ) -> str:
        """
        Przetwarza komendę głosową (STT).

        Args:
            audio_buffer: Bufor audio z mikrofonem
            language: Język

        Returns:
            Transkrybowany tekst komendy
        """
        text = await self.listen(audio_buffer, language=language)
        logger.info(f"Komenda głosowa: {text}")
        return text
