"""Tests for FishSpeechTtsClient HTTP adapter."""

from __future__ import annotations

import io
import wave
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

pytest.importorskip("httpx")

from venom_core.perception.fish_speech_tts_client import (
    FishSpeechTtsClient,
    _wav_bytes_to_ndarray,
)


def _make_wav_bytes(
    samples: np.ndarray,
    sample_rate: int = 24000,
    sample_width: int = 2,
) -> bytes:
    """Build WAV bytes from a float32 numpy array."""
    buf = io.BytesIO()
    int16 = (samples * 32767).clip(-32768, 32767).astype(np.int16)
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        wf.writeframes(int16.tobytes())
    return buf.getvalue()


class TestWavBytesToNdarray:
    def test_round_trip_int16(self) -> None:
        original = np.array([0.0, 0.5, -0.5, 1.0, -1.0], dtype=np.float32)
        wav = _make_wav_bytes(original)
        recovered = _wav_bytes_to_ndarray(wav)
        assert recovered.dtype == np.int16
        assert len(recovered) == len(original)
        np.testing.assert_array_equal(recovered, (original * 32767).astype(np.int16))

    def test_unsupported_sample_width_raises(self) -> None:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(3)
            wf.setframerate(24000)
            wf.writeframes(b"\x00\x00\x00" * 4)
        with pytest.raises(ValueError, match="sample width"):
            _wav_bytes_to_ndarray(buf.getvalue())


class TestFishSpeechTtsClientHealthCheck:
    @pytest.mark.asyncio
    async def test_health_check_returns_true_when_ok(self) -> None:
        client = FishSpeechTtsClient(base_url="http://127.0.0.1:8024")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "ok", "message": "Runtime ready"}

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_resp)
        client._client = mock_http

        result = await client.health_check()
        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_returns_false_when_disabled(self) -> None:
        client = FishSpeechTtsClient(base_url="http://127.0.0.1:8024")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "status": "disabled",
            "message": "Set FISH_SPEECH_ENABLED=true",
        }

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_resp)
        client._client = mock_http

        result = await client.health_check()
        assert result is False

    @pytest.mark.asyncio
    async def test_health_check_returns_false_on_connection_error(self) -> None:
        client = FishSpeechTtsClient(base_url="http://127.0.0.1:8024")
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(side_effect=ConnectionRefusedError("refused"))
        client._client = mock_http

        result = await client.health_check()
        assert result is False


class TestFishSpeechTtsClientSpeak:
    @pytest.mark.asyncio
    async def test_speak_returns_ndarray_on_success(self) -> None:
        audio = np.zeros(100, dtype=np.float32)
        wav_bytes = _make_wav_bytes(audio)

        client = FishSpeechTtsClient(base_url="http://127.0.0.1:8024")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = wav_bytes

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        client._client = mock_http

        result = await client.speak("hello world", language="en")
        assert isinstance(result, np.ndarray)
        assert len(result) == 100

    @pytest.mark.asyncio
    async def test_speak_returns_none_on_503(self) -> None:
        client = FishSpeechTtsClient(base_url="http://127.0.0.1:8024")
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        mock_resp.text = "disabled"

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        client._client = mock_http

        result = await client.speak("test")
        assert result is None

    @pytest.mark.asyncio
    async def test_speak_returns_none_on_network_error(self) -> None:
        client = FishSpeechTtsClient(base_url="http://127.0.0.1:8024")
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(side_effect=OSError("connection reset"))
        client._client = mock_http

        result = await client.speak("test")
        assert result is None

    @pytest.mark.asyncio
    async def test_speak_posts_to_correct_endpoint(self) -> None:
        audio = np.zeros(50, dtype=np.float32)
        wav_bytes = _make_wav_bytes(audio)

        client = FishSpeechTtsClient(base_url="http://127.0.0.1:8024")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = wav_bytes

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        client._client = mock_http

        await client.speak("test text", language="pl", sample_rate=22050)

        mock_http.post.assert_called_once()
        call_kwargs = mock_http.post.call_args
        assert call_kwargs[0][0].endswith("/v1/tts")
        json_body = call_kwargs[1]["json"]
        assert json_body["text"] == "test text"
        assert json_body["language"] == "pl"
        assert json_body["sample_rate"] == 22050
