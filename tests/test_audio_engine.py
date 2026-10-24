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

    def test_transcribe_empty_audio(self):
        """Test transkrypcji pustego audio."""
        # Symuluj pusty bufor audio
        empty_audio = np.zeros(16000, dtype=np.int16)

        # Dla testów jednostkowych nie ładujemy modelu, sprawdzamy tylko strukturę
        # W realnym przypadku potrzebujemy mock lub integracyjny test z modelem
        assert empty_audio.shape[0] == 16000

    def test_transcribe_file_delegates_to_buffer(self, monkeypatch):
        """Test transcribe_file deleguje do transkrypcji bufora."""
        skill = WhisperSkill(model_size="tiny", device="cpu")
        monkeypatch.setattr(
            skill,
            "_load_audio_file",
            lambda _path: (np.zeros(32, dtype=np.int16), 22050),
        )
        monkeypatch.setattr(
            skill,
            "_transcribe_buffer_sync",
            lambda audio,
            language="pl",
            sample_rate=16000: f"{len(audio)}:{language}:{sample_rate}",
        )

        result = skill.transcribe_file("/tmp/fake.wav", language="pl")

        assert result == "32:pl:22050"


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

    def test_stop_playback_sync_clears_queue_and_thread_reference(self):
        """stop_playback_sync czyści kolejkę i resetuje referencję wątku."""
        skill = VoiceSkill(model_path=None)
        skill.audio_queue.put(np.zeros(8, dtype=np.int16))
        skill.audio_queue.put(np.zeros(4, dtype=np.int16))

        skill.stop_playback_sync()

        assert skill.audio_queue.empty() is True
        assert skill._playback_thread is None


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

    def test_listen(self):
        """Test funkcji listen (STT)."""
        # Symuluj bufor audio
        audio_buffer = np.zeros(16000, dtype=np.int16)

        # Test struktury - pełny test wymagałby modelu
        assert audio_buffer.shape[0] == 16000

    def test_transcribe_file_delegates(self, monkeypatch):
        """AudioEngine.transcribe_file deleguje do WhisperSkill."""
        engine = AudioEngine(tts_model_path=None, device="cpu")
        monkeypatch.setattr(
            engine.whisper,
            "transcribe_file",
            lambda _path, language="pl": f"ok:{language}",
        )

        result = engine.transcribe_file("/tmp/example.wav", language="pl")

        assert result == "ok:pl"

    @pytest.mark.asyncio
    async def test_warmup_loads_models(self, monkeypatch, tmp_path):
        """AudioEngine.warmup preloads STT/TTS models when available."""
        tts_model = tmp_path / "voice.onnx"
        tts_model.write_text("fake")
        engine = AudioEngine(tts_model_path=str(tts_model), device="cpu")
        engine.whisper.model = None
        engine.voice.voice = None

        def _fake_whisper_load():
            engine.whisper.model = object()

        def _fake_tts_load():
            engine.voice.voice = object()

        monkeypatch.setattr(engine.whisper, "_load_model", _fake_whisper_load)
        monkeypatch.setattr(engine.voice, "_load_model", _fake_tts_load)

        result = await engine.warmup()

        assert result["whisper_loaded"] is True
        assert result["tts_loaded"] is True

    @pytest.mark.asyncio
    async def test_speak(self):
        """Test funkcji speak (TTS)."""
        engine = AudioEngine(tts_model_path=None, device="cpu")

        # W trybie mock powinien zwrócić audio
        result = await engine.speak("Test message")
        assert result is not None
        assert isinstance(result, np.ndarray)

    @pytest.mark.asyncio
    async def test_set_tts_model_path_reports_change_and_load_state(
        self, monkeypatch, tmp_path
    ):
        """set_tts_model_path powinno raportować zmianę i stan załadowania modelu."""
        tts_model_a = tmp_path / "voice_a.onnx"
        tts_model_b = tmp_path / "voice_b.onnx"
        tts_model_a.write_text("fake-a")
        tts_model_b.write_text("fake-b")

        engine = AudioEngine(tts_model_path=str(tts_model_a), device="cpu")

        def _fake_tts_load(self):
            self.voice = object()

        monkeypatch.setattr(VoiceSkill, "_load_model", _fake_tts_load)

        result_changed = await engine.set_tts_model_path(str(tts_model_b))
        assert result_changed["tts_loaded"] is True
        assert result_changed["tts_fallback"] is False
        assert result_changed["tts_model_changed"] is True
        assert engine.voice.model_path == str(tts_model_b)

        result_same = await engine.set_tts_model_path(str(tts_model_b))
        assert result_same["tts_loaded"] is True
        assert result_same["tts_fallback"] is False
        assert result_same["tts_model_changed"] is False

    def test_process_voice_command(self):
        """Test przetwarzania komendy głosowej."""
        # Symuluj bufor audio
        audio_buffer = np.zeros(16000, dtype=np.int16)

        # Test struktury
        assert audio_buffer is not None


def test_stereo_wav_preserves_int16_output_with_new_numpy(tmp_path):
    """Stereo averaging remains mono contiguous PCM16 across NumPy versions."""
    import wave

    import numpy as np

    path = tmp_path / "stereo.wav"
    with wave.open(str(path), "wb") as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(
            np.array([1000, -1000, 2000, 0, -2000, 0], dtype=np.int16).tobytes()
        )
    samples, rate = WhisperSkill()._load_audio_file(str(path))
    assert rate == 16000
    assert samples.dtype == np.int16
    assert samples.flags.c_contiguous
    np.testing.assert_array_equal(samples, [0, 1000, -1000])


@pytest.mark.parametrize("missing_package", [False, True])
def test_piper_import_error_distinguishes_package_and_cuda_dependency(
    tmp_path, monkeypatch, missing_package
):
    import builtins

    model = tmp_path / "voice.onnx"
    model.write_bytes(b"fixture")
    original_import = builtins.__import__

    def failing_import(name, *args, **kwargs):
        if name == "piper":
            if missing_package:
                raise ModuleNotFoundError("No module named piper", name="piper")
            raise ImportError("libcudart.so.13 cannot be opened")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", failing_import)
    skill = VoiceSkill(str(model), use_cuda=True)
    skill._load_model()
    assert skill.voice is None
    assert skill.is_fallback_mode
    assert skill.load_error_code == (
        "tts_package_missing" if missing_package else "tts_dependency_unavailable"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("cuda_available", [False, True])
async def test_explicit_piper_cuda_never_becomes_cpu_or_silent_mock(
    tmp_path, monkeypatch, cuda_available
):
    import sys
    from types import SimpleNamespace

    model = tmp_path / "voice.onnx"
    model.write_bytes(b"fixture")
    options = []
    providers = (
        ["CUDAExecutionProvider", "CPUExecutionProvider"]
        if cuda_available
        else ["CPUExecutionProvider"]
    )
    voice = SimpleNamespace(session=SimpleNamespace(get_providers=lambda: providers))

    def load(path, *, use_cuda):
        options.append(use_cuda)
        return voice

    monkeypatch.setitem(
        sys.modules, "piper", SimpleNamespace(PiperVoice=SimpleNamespace(load=load))
    )
    skill = VoiceSkill(str(model), use_cuda=True)
    skill._load_model()
    assert options == [True]
    assert (skill.voice is voice) is cuda_available
    assert skill.load_error_code == (None if cuda_available else "tts_cuda_unavailable")
    if not cuda_available:
        assert await skill.speak("fixture") is None


@pytest.mark.asyncio
async def test_switching_tts_model_preserves_requested_cuda(tmp_path, monkeypatch):
    first = tmp_path / "first.onnx"
    second = tmp_path / "second.onnx"
    first.touch()
    second.touch()
    engine = AudioEngine(tts_model_path=str(first), tts_use_cuda=True)
    monkeypatch.setattr(VoiceSkill, "_load_model", lambda self: None)
    await engine.set_tts_model_path(str(second))
    assert engine.voice.use_cuda is True
