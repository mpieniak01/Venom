"""Tests for the Fish Speech runtime service daemon."""

from __future__ import annotations

import io
import os
import sys
import textwrap
import wave
from pathlib import Path
from unittest.mock import patch

import numpy as np
from fastapi.testclient import TestClient

from services.fish_speech_runtime.main import app

_client = TestClient(app)


class TestHealthEndpoint:
    def test_health_returns_200_always(self) -> None:
        with patch.dict(os.environ, {"FISH_SPEECH_ENABLED": "false"}):
            resp = _client.get("/health")
        assert resp.status_code == 200

    def test_health_disabled_status_when_not_enabled(self) -> None:
        with patch.dict(os.environ, {"FISH_SPEECH_ENABLED": "false"}):
            data = _client.get("/health").json()
        assert data["status"] == "disabled"

    def test_health_warming_when_cache_missing(self, tmp_path: object) -> None:
        env = {
            "FISH_SPEECH_ENABLED": "true",
            "FISH_SPEECH_CACHE_DIR": str(tmp_path),
        }
        with patch.dict(os.environ, env):
            data = _client.get("/health").json()
        assert data["status"] == "warming"


class TestStatusEndpoint:
    def test_status_returns_200_always(self) -> None:
        with patch.dict(os.environ, {"FISH_SPEECH_ENABLED": "false"}):
            resp = _client.get("/status")
        assert resp.status_code == 200

    def test_status_model_loaded_false_when_disabled(self) -> None:
        with patch.dict(os.environ, {"FISH_SPEECH_ENABLED": "false"}):
            data = _client.get("/status").json()
        assert data["model_loaded"] is False
        assert data["service"] == "fish_speech"

    def test_status_contains_model_id_and_device(self) -> None:
        env = {
            "FISH_SPEECH_ENABLED": "false",
            "FISH_SPEECH_MODEL_ID": "fishaudio/fish-speech-1.5",
            "FISH_SPEECH_DEVICE": "cpu",
        }
        with patch.dict(os.environ, env):
            data = _client.get("/status").json()
        assert data["model_id"] == "fishaudio/fish-speech-1.5"
        assert data["device"] == "cpu"


class TestTtsEndpoint:
    def test_tts_returns_503_when_disabled(self) -> None:
        with patch.dict(os.environ, {"FISH_SPEECH_ENABLED": "false"}):
            resp = _client.post("/v1/tts", json={"text": "hello"})
        assert resp.status_code == 503

    def test_tts_returns_503_when_cache_missing(self, tmp_path: object) -> None:
        env = {
            "FISH_SPEECH_ENABLED": "true",
            "FISH_SPEECH_CACHE_DIR": str(tmp_path),
        }
        with patch.dict(os.environ, env):
            resp = _client.post("/v1/tts", json={"text": "hello"})
        assert resp.status_code == 503

    def test_tts_returns_wav_when_engine_loaded(self, tmp_path: object) -> None:
        audio = np.zeros(100, dtype=np.float32)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(24000)
            wf.writeframes((audio * 32767).astype("int16").tobytes())
        wav_bytes = buf.getvalue()

        model_slug = "models--fishaudio--fish-speech-1.5"
        snapshot_dir = tmp_path / model_slug / "snapshots" / "abc123"
        snapshot_dir.mkdir(parents=True)
        (snapshot_dir / "model.pth").write_bytes(b"")

        env = {
            "FISH_SPEECH_ENABLED": "true",
            "FISH_SPEECH_CACHE_DIR": str(tmp_path),
        }
        with (
            patch.dict(os.environ, env),
            patch(
                "services.fish_speech_runtime.engine.FishSpeechEngine.synthesize",
                return_value=wav_bytes,
            ),
            patch(
                "services.fish_speech_runtime.engine.FishSpeechEngine.is_loaded",
                new_callable=lambda: property(lambda self: True),
            ),
        ):
            resp = _client.post("/v1/tts", json={"text": "test synthesis"})

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "audio/wav"

    def test_tts_validates_empty_text(self) -> None:
        with patch.dict(os.environ, {"FISH_SPEECH_ENABLED": "false"}):
            resp = _client.post("/v1/tts", json={"text": ""})
        assert resp.status_code == 422


class TestEngineIntegration:
    def test_engine_loads_from_source_checkout_and_snapshot(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        for module_name in list(sys.modules):
            if module_name == "tools" or module_name.startswith("tools."):
                sys.modules.pop(module_name, None)

        source_root = tmp_path / "fish-speech-src"
        (source_root / "tools" / "server").mkdir(parents=True)
        (source_root / "tools" / "__init__.py").write_text("")
        (source_root / "tools" / "server" / "__init__.py").write_text("")
        (source_root / "tools" / "server" / "model_manager.py").write_text(
            textwrap.dedent(
                """
                class _DummyDecoder:
                    class spec_transform:
                        sample_rate = 24000


                class ModelManager:
                    def __init__(self, **kwargs):
                        self.kwargs = kwargs
                        self.tts_inference_engine = type(
                            "DummyEngine",
                            (),
                            {"decoder_model": _DummyDecoder()},
                        )()
                """
            )
        )

        cache_dir = tmp_path / "cache"
        snapshot_dir = (
            cache_dir / "models--fishaudio--fish-speech-1.5" / "snapshots" / "abc123"
        )
        snapshot_dir.mkdir(parents=True)
        (snapshot_dir / "model.pth").write_bytes(b"model")
        (snapshot_dir / "tokenizer.tiktoken").write_text("tokenizer")
        (snapshot_dir / "firefly-gan-vq-fsq-8x1024-21hz-generator.pth").write_bytes(
            b"decoder"
        )

        monkeypatch.setenv("FISH_SPEECH_SOURCE_DIR", str(source_root))
        monkeypatch.setenv("FISH_SPEECH_MODEL_ID", "fishaudio/fish-speech-1.5")
        monkeypatch.setenv("FISH_SPEECH_CACHE_DIR", str(cache_dir))
        monkeypatch.setenv("FISH_SPEECH_DEVICE", "cpu")

        from services.fish_speech_runtime.engine import FishSpeechEngine

        engine = FishSpeechEngine(
            model_id="fishaudio/fish-speech-1.5",
            cache_dir=str(cache_dir),
            device="cpu",
        )

        assert engine.load() is True
        assert engine.is_loaded is True
        assert engine._model_manager.kwargs["llama_checkpoint_path"] == str(
            snapshot_dir
        )
        assert engine._model_manager.kwargs["decoder_checkpoint_path"] == str(
            snapshot_dir / "firefly-gan-vq-fsq-8x1024-21hz-generator.pth"
        )
        assert engine._sample_rate == 24000

    def test_engine_synthesize_uses_source_inference_wrapper(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        for module_name in list(sys.modules):
            if module_name == "tools" or module_name.startswith("tools."):
                sys.modules.pop(module_name, None)

        source_root = tmp_path / "fish-speech-src"
        (source_root / "tools" / "server").mkdir(parents=True)
        (source_root / "tools" / "__init__.py").write_text("")
        (source_root / "tools" / "server" / "__init__.py").write_text("")
        (source_root / "tools" / "server" / "model_manager.py").write_text(
            textwrap.dedent(
                """
                class _DummyDecoder:
                    class spec_transform:
                        sample_rate = 24000


                class ModelManager:
                    def __init__(self, **kwargs):
                        self.kwargs = kwargs
                        self.tts_inference_engine = type(
                            "DummyEngine",
                            (),
                            {"decoder_model": _DummyDecoder()},
                        )()
                """
            )
        )
        (source_root / "tools" / "schema.py").write_text(
            textwrap.dedent(
                """
                class ServeTTSRequest:
                    def __init__(self, **kwargs):
                        self.__dict__.update(kwargs)
                """
            )
        )
        (source_root / "tools" / "server" / "inference.py").write_text(
            textwrap.dedent(
                """
                import numpy as np


                def inference_wrapper(req, engine):
                    del req, engine
                    yield np.zeros(240, dtype=np.float32)
                """
            )
        )

        cache_dir = tmp_path / "cache"
        snapshot_dir = (
            cache_dir / "models--fishaudio--fish-speech-1.5" / "snapshots" / "abc123"
        )
        snapshot_dir.mkdir(parents=True)
        (snapshot_dir / "model.pth").write_bytes(b"model")
        (snapshot_dir / "tokenizer.tiktoken").write_text("tokenizer")
        (snapshot_dir / "firefly-gan-vq-fsq-8x1024-21hz-generator.pth").write_bytes(
            b"decoder"
        )

        monkeypatch.setenv("FISH_SPEECH_SOURCE_DIR", str(source_root))
        monkeypatch.setenv("FISH_SPEECH_MODEL_ID", "fishaudio/fish-speech-1.5")
        monkeypatch.setenv("FISH_SPEECH_CACHE_DIR", str(cache_dir))
        monkeypatch.setenv("FISH_SPEECH_DEVICE", "cpu")

        from services.fish_speech_runtime.engine import FishSpeechEngine

        engine = FishSpeechEngine(
            model_id="fishaudio/fish-speech-1.5",
            cache_dir=str(cache_dir),
            device="cpu",
        )
        assert engine.load() is True

        wav_bytes = engine.synthesize("hello")
        assert wav_bytes[:4] == b"RIFF"
        assert len(wav_bytes) > 44


class TestUptimeEndpoint:
    def test_uptime_returns_float(self) -> None:
        data = _client.get("/uptime").json()
        assert "uptime_seconds" in data
        assert isinstance(data["uptime_seconds"], float)
