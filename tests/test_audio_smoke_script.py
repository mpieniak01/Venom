from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

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


@pytest.mark.parametrize("tts_use_cuda", [False, True])
def test_run_local_transcribe_uses_override_path(monkeypatch, tmp_path, tts_use_cuda):
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
    monkeypatch.setattr(audio_smoke.SETTINGS, "TTS_USE_CUDA", tts_use_cuda)
    monkeypatch.setattr(audio_smoke, "httpx", SimpleNamespace(get=Mock()))

    payload = audio_smoke._run_local_transcribe(audio_file, model_path)

    engine_cls.assert_called_once_with(
        whisper_model_size="base",
        tts_model_path=str(model_path),
        device="cpu",
        tts_use_cuda=tts_use_cuda,
    )
    fake_engine.warmup.assert_awaited_once()
    fake_engine.transcribe_file.assert_called_once_with(str(audio_file), language="pl")
    assert payload["text"] == "to jest test"
    assert payload["tts_fallback"] is False
    assert payload["tts_model_path"] == str(model_path)


@pytest.mark.parametrize("prepared", [False, True])
def test_cli_prepares_gpu_libraries_once(monkeypatch, tmp_path, prepared):
    """The shared wrapper runs once, preserving CLI arguments without models."""
    libraries = tmp_path / "lib/python3.14/site-packages/nvidia/cu13/lib"
    libraries.mkdir(parents=True)
    monkeypatch.setattr(audio_smoke.sys, "prefix", str(tmp_path))
    inherited = "/operator/lib"
    expected = audio_smoke.library_path(tmp_path, inherited)
    monkeypatch.setenv("LD_LIBRARY_PATH", expected if prepared else inherited)
    arguments = ["audio_smoke.py", "--file", "sample name.wav", "--json"]
    monkeypatch.setattr(audio_smoke.sys, "argv", arguments)
    execute = Mock()
    monkeypatch.setattr(audio_smoke.os, "execv", execute)

    audio_smoke._prepare_gpu_libraries()

    if prepared:
        execute.assert_not_called()
    else:
        execute.assert_called_once_with(
            audio_smoke.sys.executable,
            [
                audio_smoke.sys.executable,
                str(audio_smoke.ROOT_DIR / "scripts/llm/with_gpu_libraries.py"),
                audio_smoke.sys.executable,
                str(Path(audio_smoke.__file__).resolve()),
                *arguments[1:],
            ],
        )
