"""Compatibility shim — implementation moved to services.multi_runtime.audio."""

from __future__ import annotations

from services.multi_runtime.audio import (
    audio_from_bytes,
    audio_from_file,
    get_audio_duration,
    normalize_audio,
)

__all__ = [
    "audio_from_bytes",
    "audio_from_file",
    "get_audio_duration",
    "normalize_audio",
]
