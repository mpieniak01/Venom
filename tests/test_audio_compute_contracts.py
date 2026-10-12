"""Strict speech results and singleton reuse for optional device modules."""

from types import SimpleNamespace

import numpy as np
import pytest

from venom_core.perception.audio_engine import AudioEngine, WhisperSkill


@pytest.mark.asyncio
async def test_checked_stt_propagates_inference_error_but_legacy_remains_empty():
    skill = WhisperSkill()

    def fail(*_args, **_kwargs):
        raise RuntimeError("inference failure")

    skill.model = SimpleNamespace(transcribe=fail)
    samples = np.zeros(1600, dtype=np.int16)
    with pytest.raises(RuntimeError, match="inference failure"):
        await skill.transcribe_checked(samples)
    assert await skill.transcribe(samples) == ""


@pytest.mark.asyncio
async def test_checked_stt_successful_silence_is_not_an_error():
    skill = WhisperSkill()
    skill.model = SimpleNamespace(transcribe=lambda *_a, **_k: ([], None))
    assert await skill.transcribe_checked(np.zeros(1600, dtype=np.int16)) == ""


@pytest.mark.asyncio
async def test_audio_engine_checked_reuses_one_whisper_and_preserves_language_rate():
    engine = AudioEngine()
    calls = []

    async def checked(samples, language, sample_rate):
        calls.append((samples, language, sample_rate))
        return "transcript"

    engine.whisper.transcribe_checked = checked
    samples = np.zeros(1600, dtype=np.int16)
    assert await engine.transcribe_checked(samples, "de", 22050) == "transcript"
    assert calls[0][0] is samples and calls[0][1:] == ("de", 22050)


@pytest.mark.asyncio
async def test_optional_module_receives_host_audio_instance(monkeypatch):
    from venom_core import main

    shared = object()
    monkeypatch.setattr(main.app.state, "audio_engine", None, raising=False)
    monkeypatch.setattr(main, "_initialize_audio_engine_if_enabled", lambda: shared)

    async def no_hardware():
        return None

    monkeypatch.setattr(main, "_initialize_hardware_bridge_if_enabled", no_hardware)
    monkeypatch.setattr(main, "_initialize_operator_agent_if_possible", lambda *_: None)
    monkeypatch.setattr(
        main, "_initialize_audio_stream_handler_if_possible", lambda *_: None
    )
    for name in (
        "audio_engine",
        "hardware_bridge",
        "operator_agent",
        "audio_stream_handler",
    ):
        monkeypatch.setattr(main, name, None)
    await main._initialize_avatar_stack()
    assert main.app.state.audio_engine is shared and main.audio_engine is shared
