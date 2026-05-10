from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import scripts.dev.audio_smoke as audio_smoke


def test_parse_args_supports_tts_model_path(monkeypatch):
    monkeypatch.setattr(
        "sys.argv",
        [
            "audio_smoke.py",
            "--base-url",
            "http://localhost:8000",
            "--file",
            "sample.wav",
            "--tts-model-path",
            "voice.onnx",
        ],
    )

    args = audio_smoke._parse_args()

    assert args.base_url == "http://localhost:8000"
    assert args.file == Path("sample.wav")
    assert args.tts_model_path == Path("voice.onnx")


def test_run_local_transcribe_uses_override_path(monkeypatch, tmp_path):
    model_path = tmp_path / "voice.onnx"
    model_path.write_text("fake")
    audio_file = tmp_path / "sample.wav"
    audio_file.write_bytes(b"RIFFTEST")

    fake_engine = SimpleNamespace(
        whisper=SimpleNamespace(model_size="base"),
        voice=SimpleNamespace(model_path=str(model_path), is_fallback_mode=False),
        warmup=AsyncMock(return_value={"whisper_loaded": True, "tts_loaded": True}),
        transcribe_file=Mock(return_value="to jest test"),
    )

    engine_cls = Mock(return_value=fake_engine)
    monkeypatch.setattr(audio_smoke, "AudioEngine", engine_cls)
    monkeypatch.setattr(audio_smoke.SETTINGS, "WHISPER_MODEL_SIZE", "base")
    monkeypatch.setattr(audio_smoke.SETTINGS, "TTS_MODEL_PATH", "")
    monkeypatch.setattr(audio_smoke.SETTINGS, "AUDIO_DEVICE", "cpu")
    monkeypatch.setattr(audio_smoke, "httpx", SimpleNamespace(get=Mock()))

    payload = audio_smoke._run_local_transcribe(audio_file, model_path)

    engine_cls.assert_called_once_with(
        whisper_model_size="base",
        tts_model_path=str(model_path),
        device="cpu",
    )
    fake_engine.warmup.assert_awaited_once()
    fake_engine.transcribe_file.assert_called_once_with(str(audio_file), language="pl")
    assert payload["text"] == "to jest test"
    assert payload["tts_fallback"] is False
    assert payload["tts_model_path"] == str(model_path)
