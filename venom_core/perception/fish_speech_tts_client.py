"""Async HTTP client for the Fish Speech TTS daemon."""

from __future__ import annotations

import io
import logging
import wave
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

_CONNECT_TIMEOUT = 3.0
_READ_TIMEOUT = 180.0


class FishSpeechTtsClient:
    """Thin async wrapper around the Fish Speech daemon /v1/tts endpoint."""

    def __init__(self, base_url: str = "http://127.0.0.1:8024") -> None:
        self.base_url = base_url.rstrip("/")
        self._client: Optional[object] = None
        self.last_sample_rate: int = 24000

    def _get_client(self) -> object:
        try:
            import httpx  # type: ignore[import]
        except ImportError as exc:
            raise RuntimeError(
                "httpx is required for FishSpeechTtsClient. "
                "Install it via: pip install httpx"
            ) from exc
        if self._client is None:
            import httpx  # type: ignore[import]

            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(_READ_TIMEOUT, connect=_CONNECT_TIMEOUT)
            )
        return self._client

    async def health_check(self) -> bool:
        """Return True only when daemon reports fully ready status."""
        try:
            client = self._get_client()
            resp = await client.get(f"{self.base_url}/health")  # type: ignore[attr-defined]
            data = resp.json()
            return resp.status_code == 200 and data.get("status") == "ok"
        except Exception as exc:
            logger.debug(f"Fish Speech health check failed: {exc}")
            return False

    async def speak(
        self,
        text: str,
        language: str = "pl",
        sample_rate: int = 24000,
    ) -> Optional[np.ndarray]:
        """
        Synthesize speech via the Fish Speech daemon.

        Returns float32 numpy array on success, None on any failure.
        Failures are logged as warnings — callers should fall back to Piper.
        """
        try:
            self.last_sample_rate = int(sample_rate or 24000)
            client = self._get_client()
            resp = await client.post(  # type: ignore[attr-defined]
                f"{self.base_url}/v1/tts",
                json={"text": text, "language": language, "sample_rate": sample_rate},
            )
            if resp.status_code != 200:
                logger.warning(
                    f"Fish Speech daemon returned {resp.status_code}: {resp.text[:200]}"
                )
                return None
            return _wav_bytes_to_ndarray(resp.content)
        except Exception as exc:
            logger.warning(f"Fish Speech speak() failed: {exc}")
            return None

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()  # type: ignore[attr-defined]
            self._client = None


def _wav_bytes_to_ndarray(wav_bytes: bytes) -> np.ndarray:
    """Convert WAV bytes to int16 numpy array."""
    buf = io.BytesIO(wav_bytes)
    with wave.open(buf, "rb") as wf:
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)
        sample_width = wf.getsampwidth()

    if sample_width == 2:
        audio = np.frombuffer(raw, dtype=np.int16)
    elif sample_width == 4:
        audio = np.clip(np.frombuffer(raw, dtype=np.int32) >> 16, -32768, 32767).astype(
            np.int16
        )
    else:
        raise ValueError(f"Unsupported WAV sample width: {sample_width}")

    return audio
