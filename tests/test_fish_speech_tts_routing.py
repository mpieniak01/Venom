"""Tests for TTS engine routing in AudioEngine."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest


def _make_audio_engine(tts_engine: str = "piper_local") -> object:
    """Build an AudioEngine with mocked sub-components."""
    with (
        patch("venom_core.perception.audio_engine.WhisperSkill"),
        patch("venom_core.perception.audio_engine.VoiceSkill"),
    ):
        from venom_core.perception.audio_engine import AudioEngine

        engine = AudioEngine(tts_engine=tts_engine)
    return engine


class TestAudioEngineTtsEngineParam:
    def test_default_tts_engine_is_piper_local(self) -> None:
        with (
            patch("venom_core.perception.audio_engine.WhisperSkill"),
            patch("venom_core.perception.audio_engine.VoiceSkill"),
        ):
            from venom_core.perception.audio_engine import AudioEngine

            engine = AudioEngine()
        assert engine.tts_engine == "piper_local"

    def test_fish_speech_engine_sets_client(self) -> None:
        with (
            patch("venom_core.perception.audio_engine.WhisperSkill"),
            patch("venom_core.perception.audio_engine.VoiceSkill"),
            patch(
                "venom_core.perception.audio_engine.FishSpeechTtsClient"
                if False
                else "venom_core.perception.fish_speech_tts_client.FishSpeechTtsClient"
            ),
        ):
            from venom_core.perception.audio_engine import AudioEngine

            engine = AudioEngine(tts_engine="fish_speech")
        assert engine.tts_engine == "fish_speech"
        assert engine._fish_client is not None

    def test_piper_engine_does_not_create_fish_client(self) -> None:
        with (
            patch("venom_core.perception.audio_engine.WhisperSkill"),
            patch("venom_core.perception.audio_engine.VoiceSkill"),
        ):
            from venom_core.perception.audio_engine import AudioEngine

            engine = AudioEngine(tts_engine="piper_local")
        assert engine._fish_client is None


class TestAudioEngineSpeakRouting:
    @pytest.mark.asyncio
    async def test_piper_speak_delegates_to_voice_skill(self) -> None:
        expected = np.zeros(100, dtype=np.float32)
        with (
            patch("venom_core.perception.audio_engine.WhisperSkill"),
            patch("venom_core.perception.audio_engine.VoiceSkill") as mock_voice_cls,
        ):
            from venom_core.perception.audio_engine import AudioEngine

            mock_voice = MagicMock()
            mock_voice.speak = AsyncMock(return_value=expected)
            mock_voice_cls.return_value = mock_voice

            engine = AudioEngine(tts_engine="piper_local")
            result = await engine.speak("hello")

        assert result is expected

    @pytest.mark.asyncio
    async def test_fish_speech_speak_uses_fish_client(self) -> None:
        expected = np.ones(200, dtype=np.float32) * 0.5
        with (
            patch("venom_core.perception.audio_engine.WhisperSkill"),
            patch("venom_core.perception.audio_engine.VoiceSkill"),
        ):
            from venom_core.perception.audio_engine import AudioEngine
            from venom_core.perception.fish_speech_tts_client import FishSpeechTtsClient

            engine = AudioEngine(tts_engine="fish_speech")
            mock_client = AsyncMock(spec=FishSpeechTtsClient)
            mock_client.speak = AsyncMock(return_value=expected)
            engine._fish_client = mock_client

            result = await engine.speak("bonjour")

        assert result is expected
        mock_client.speak.assert_called_once_with("bonjour")

    @pytest.mark.asyncio
    async def test_fish_speech_falls_back_to_piper_on_none(self) -> None:
        fallback_audio = np.zeros(50, dtype=np.float32)
        with (
            patch("venom_core.perception.audio_engine.WhisperSkill"),
            patch("venom_core.perception.audio_engine.VoiceSkill") as mock_voice_cls,
        ):
            from venom_core.perception.audio_engine import AudioEngine
            from venom_core.perception.fish_speech_tts_client import FishSpeechTtsClient

            mock_voice = MagicMock()
            mock_voice.speak = AsyncMock(return_value=fallback_audio)
            mock_voice_cls.return_value = mock_voice

            engine = AudioEngine(tts_engine="fish_speech")
            mock_client = AsyncMock(spec=FishSpeechTtsClient)
            mock_client.speak = AsyncMock(return_value=None)
            engine._fish_client = mock_client

            result = await engine.speak("fallback test")

        assert result is fallback_audio
        mock_voice.speak.assert_called_once_with("fallback test")


class TestAudioEngineWarmupRouting:
    @pytest.mark.asyncio
    async def test_warmup_fish_speech_checks_health(self) -> None:
        with (
            patch(
                "venom_core.perception.audio_engine.WhisperSkill"
            ) as mock_whisper_cls,
            patch("venom_core.perception.audio_engine.VoiceSkill"),
        ):
            from venom_core.perception.audio_engine import AudioEngine
            from venom_core.perception.fish_speech_tts_client import FishSpeechTtsClient

            mock_whisper = MagicMock()
            mock_whisper.model = MagicMock()
            mock_whisper._load_model = MagicMock()
            mock_whisper_cls.return_value = mock_whisper

            engine = AudioEngine(tts_engine="fish_speech")
            mock_client = AsyncMock(spec=FishSpeechTtsClient)
            mock_client.health_check = AsyncMock(return_value=True)
            engine._fish_client = mock_client

            state = await engine.warmup()

        assert state["tts_loaded"] is True
        mock_client.health_check.assert_called_once()

    @pytest.mark.asyncio
    async def test_warmup_fish_speech_tts_loaded_false_when_daemon_down(self) -> None:
        with (
            patch(
                "venom_core.perception.audio_engine.WhisperSkill"
            ) as mock_whisper_cls,
            patch("venom_core.perception.audio_engine.VoiceSkill"),
        ):
            from venom_core.perception.audio_engine import AudioEngine
            from venom_core.perception.fish_speech_tts_client import FishSpeechTtsClient

            mock_whisper = MagicMock()
            mock_whisper.model = None
            mock_whisper._load_model = MagicMock()
            mock_whisper_cls.return_value = mock_whisper

            engine = AudioEngine(tts_engine="fish_speech")
            mock_client = AsyncMock(spec=FishSpeechTtsClient)
            mock_client.health_check = AsyncMock(return_value=False)
            engine._fish_client = mock_client

            state = await engine.warmup()

        assert state["tts_loaded"] is False
