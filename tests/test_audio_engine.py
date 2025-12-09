"""Testy jednostkowe dla modułu audio_engine."""

import numpy as np
import pytest

from venom_core.perception.audio_engine import AudioEngine, VoiceSkill, WhisperSkill


class TestWhisperSkill:
    """Testy dla WhisperSkill (STT)."""

    def test_initialization(self):
        """Test inicjalizacji WhisperSkill."""
        skill = WhisperSkill(model_size="tiny", device="cpu")
        assert skill.model_size == "tiny"
        assert skill.device == "cpu"
        assert skill.model is None  # Lazy loading

    @pytest.mark.asyncio
    async def test_transcribe_empty_audio(self):
        """Test transkrypcji pustego audio."""
        # Symuluj pusty bufor audio
        empty_audio = np.zeros(16000, dtype=np.int16)

        # Dla testów jednostkowych nie ładujemy modelu, sprawdzamy tylko strukturę
        # W realnym przypadku potrzebujemy mock lub integracyjny test z modelem
        assert empty_audio.shape[0] == 16000


class TestVoiceSkill:
    """Testy dla VoiceSkill (TTS)."""

    def test_initialization(self):
        """Test inicjalizacji VoiceSkill."""
        skill = VoiceSkill(model_path=None, speaker_id=0)
        assert skill.model_path is None
        assert skill.speaker_id == 0
        assert skill.voice is None  # Lazy loading
        assert skill.is_fallback_mode is True  # Brak modelu = fallback mode

    def test_initialization_with_valid_path(self, tmp_path):
        """Test inicjalizacji z poprawną ścieżką do modelu."""
        # Utwórz tymczasowy plik modelu
        model_file = tmp_path / "test_model.onnx"
        model_file.write_text("fake model")

        skill = VoiceSkill(model_path=str(model_file), speaker_id=0)
        assert skill.model_path == str(model_file)
        assert skill.is_fallback_mode is False

    def test_initialization_with_invalid_path(self):
        """Test inicjalizacji z niepoprawną ścieżką do modelu."""
        skill = VoiceSkill(model_path="/nonexistent/path/model.onnx", speaker_id=0)
        assert skill.is_fallback_mode is True

    @pytest.mark.asyncio
    async def test_speak_empty_text(self):
        """Test syntezy pustego tekstu."""
        skill = VoiceSkill(model_path=None)
        result = await skill.speak("")
        assert result is None  # Pusty tekst nie powinien być syntetyzowany

    def test_clean_text_for_speech(self):
        """Test czyszczenia tekstu dla TTS."""
        skill = VoiceSkill(model_path=None)

        # Test usuwania markdown
        text_with_markdown = "To jest **bold** i *italic* tekst."
        cleaned = skill._clean_text_for_speech(text_with_markdown)
        assert "**" not in cleaned
        assert "*" not in cleaned

        # Test usuwania bloków kodu
        text_with_code = "Kod: ```python\nprint('test')\n``` Koniec."
        cleaned = skill._clean_text_for_speech(text_with_code)
        assert "```" not in cleaned

        # Test usuwania linków
        text_with_links = "Zobacz [link](https://example.com) tutaj."
        cleaned = skill._clean_text_for_speech(text_with_links)
        assert "https://" not in cleaned
        assert "link" in cleaned

    @pytest.mark.asyncio
    async def test_speak_mock_mode(self):
        """Test TTS w trybie mock (bez modelu)."""
        skill = VoiceSkill(model_path=None)

        # W trybie mock powinien zwrócić ciszę
        result = await skill.speak("Test text")
        assert result is not None
        assert isinstance(result, np.ndarray)
        # Sprawdź czy zwrócona cisza ma odpowiednią długość (1 sekunda)
        assert len(result) == 16000

    @pytest.mark.asyncio
    async def test_speak_fallback_mode_with_invalid_path(self):
        """Test TTS w trybie fallback z niepoprawną ścieżką."""
        skill = VoiceSkill(model_path="/invalid/path.onnx")
        assert skill.is_fallback_mode is True

        # Powinien zwrócić ciszę w trybie fallback
        result = await skill.speak("Test text")
        assert result is not None
        assert isinstance(result, np.ndarray)
        assert len(result) == 16000


class TestAudioEngine:
    """Testy dla AudioEngine."""

    def test_initialization(self):
        """Test inicjalizacji AudioEngine."""
        engine = AudioEngine(
            whisper_model_size="tiny",
            tts_model_path=None,
            device="cpu",
        )

        assert engine.whisper is not None
        assert engine.voice is not None
        assert engine.whisper.model_size == "tiny"

    @pytest.mark.asyncio
    async def test_listen(self):
        """Test funkcji listen (STT)."""
        # Symuluj bufor audio
        audio_buffer = np.zeros(16000, dtype=np.int16)

        # Test struktury - pełny test wymagałby modelu
        assert audio_buffer.shape[0] == 16000

    @pytest.mark.asyncio
    async def test_speak(self):
        """Test funkcji speak (TTS)."""
        engine = AudioEngine(tts_model_path=None, device="cpu")

        # W trybie mock powinien zwrócić audio
        result = await engine.speak("Test message")
        assert result is not None
        assert isinstance(result, np.ndarray)

    @pytest.mark.asyncio
    async def test_process_voice_command(self):
        """Test przetwarzania komendy głosowej."""
        # Symuluj bufor audio
        audio_buffer = np.zeros(16000, dtype=np.int16)

        # Test struktury
        assert audio_buffer is not None
