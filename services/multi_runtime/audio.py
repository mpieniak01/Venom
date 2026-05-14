"""Audio normalization and processing utilities."""

from __future__ import annotations

import io
import math
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Tuple

import numpy as np

TARGET_SAMPLE_RATE = 16_000


class AudioNormalizationError(Exception):
    """Raised when audio normalization fails."""

    pass


def read_audio_file(path: Path) -> Tuple[np.ndarray, int]:
    """Read audio file using soundfile with ffmpeg fallback."""
    import soundfile as sf

    try:
        audio, sample_rate = sf.read(str(path), always_2d=True, dtype="float32")
        return audio, int(sample_rate)
    except Exception as e:
        # Fallback to ffmpeg
        try:
            with tempfile.TemporaryDirectory(prefix="multi_runtime_ffmpeg_") as tmpdir:
                tmp_path = Path(tmpdir) / "decoded.wav"
                cmd = [
                    "ffmpeg",
                    "-nostdin",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-i",
                    str(path),
                    "-ac",
                    "1",
                    "-ar",
                    str(TARGET_SAMPLE_RATE),
                    "-c:a",
                    "pcm_f32le",
                    str(tmp_path),
                ]
                subprocess.run(cmd, check=True, capture_output=True, timeout=30)
                audio, sample_rate = sf.read(
                    str(tmp_path), always_2d=True, dtype="float32"
                )
                return audio, int(sample_rate)
        except Exception as ffmpeg_err:
            raise AudioNormalizationError(
                f"Failed to read audio with soundfile ({e}) and ffmpeg ({ffmpeg_err})"
            ) from e


def read_audio_bytes(
    file_bytes: bytes, sample_rate_hint: Optional[int] = None
) -> Tuple[np.ndarray, int]:
    """Read audio from bytes using soundfile with ffmpeg fallback."""
    import soundfile as sf

    try:
        with io.BytesIO(file_bytes) as buf:
            audio, sample_rate = sf.read(buf, always_2d=True, dtype="float32")
        return audio, int(sample_rate)
    except Exception as e:
        # Fallback to ffmpeg
        try:
            with tempfile.TemporaryDirectory(prefix="multi_runtime_ffmpeg_") as tmpdir:
                input_path = Path(tmpdir) / "input.audio"
                output_path = Path(tmpdir) / "decoded.wav"

                input_path.write_bytes(file_bytes)

                cmd = [
                    "ffmpeg",
                    "-nostdin",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-i",
                    str(input_path),
                    "-ac",
                    "1",
                    "-ar",
                    str(TARGET_SAMPLE_RATE),
                    "-c:a",
                    "pcm_f32le",
                    str(output_path),
                ]
                subprocess.run(cmd, check=True, capture_output=True, timeout=30)
                audio, sample_rate = sf.read(
                    str(output_path), always_2d=True, dtype="float32"
                )
                return audio, int(sample_rate)
        except Exception as ffmpeg_err:
            raise AudioNormalizationError(
                f"Failed to read audio from bytes with soundfile ({e}) "
                f"and ffmpeg ({ffmpeg_err})"
            ) from e


def normalize_audio(
    audio: np.ndarray, sample_rate: int, target_sr: int = TARGET_SAMPLE_RATE
) -> Tuple[np.ndarray, int]:
    """Normalize audio to mono float32 at target sample rate.

    Args:
        audio: Audio array (can be multi-channel)
        sample_rate: Current sample rate
        target_sr: Target sample rate (default 16000 Hz)

    Returns:
        Tuple of (normalized_audio, target_sample_rate)

    Raises:
        AudioNormalizationError: If normalization fails
    """
    try:
        # Convert to mono
        if audio.ndim > 1:
            mono = audio.mean(axis=1)
        else:
            mono = audio

        mono = np.asarray(mono, dtype=np.float32)

        # Resample if needed
        if sample_rate != target_sr:
            from scipy.signal import resample_poly

            gcd = math.gcd(sample_rate, target_sr)
            up = target_sr // gcd
            down = sample_rate // gcd
            mono = resample_poly(mono, up, down).astype(np.float32, copy=False)
            sample_rate = target_sr

        # Clip to [-1.0, 1.0] range
        mono = np.clip(mono, -1.0, 1.0).astype(np.float32, copy=False)

        return mono, sample_rate
    except Exception as e:
        raise AudioNormalizationError(f"Failed to normalize audio: {e}") from e


def audio_from_file(path: Path) -> Tuple[np.ndarray, int]:
    """Load and normalize audio from file path.

    Args:
        path: Path to audio file

    Returns:
        Tuple of (normalized_audio_array, sample_rate)

    Raises:
        AudioNormalizationError: If file reading or normalization fails
    """
    audio, sample_rate = read_audio_file(path)
    normalized, sr = normalize_audio(audio, sample_rate)
    return normalized, sr


def audio_from_bytes(file_bytes: bytes) -> Tuple[np.ndarray, int]:
    """Load and normalize audio from bytes.

    Args:
        file_bytes: Audio file content as bytes

    Returns:
        Tuple of (normalized_audio_array, sample_rate)

    Raises:
        AudioNormalizationError: If file reading or normalization fails
    """
    audio, sample_rate = read_audio_bytes(file_bytes)
    normalized, sr = normalize_audio(audio, sample_rate)
    return normalized, sr


def get_audio_duration(audio: np.ndarray, sample_rate: int) -> float:
    """Get audio duration in seconds."""
    if sample_rate <= 0:
        return 0.0
    return float(len(audio)) / float(sample_rate)
