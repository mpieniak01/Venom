"""Tests for the Fish Speech runtime service daemon."""

from __future__ import annotations

import io
import os
import wave
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


class TestUptimeEndpoint:
    def test_uptime_returns_float(self) -> None:
        data = _client.get("/uptime").json()
        assert "uptime_seconds" in data
        assert isinstance(data["uptime_seconds"], float)
