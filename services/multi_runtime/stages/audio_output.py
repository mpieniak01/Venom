"""Audio output stage — Piper TTS synthesis for multi_runtime pipeline."""

from __future__ import annotations

import base64
import io
import re
import wave
from pathlib import Path
from time import perf_counter
from typing import Any

from services.multi_runtime.runtime_config import read_config_str

from .base import StageContext

_DEFAULT_SAMPLE_RATE = 22050
_TTS_MAX_CHARS = 2000
_PIPER_VOICE_CACHE: dict[str, Any] = {}


def _find_tts_model_path() -> Path | None:
    configured = read_config_str("TTS_MODEL_PATH", "")
    if configured:
        p = Path(configured)
        return p if p.exists() else None
    default_dir = Path("data/models/piper")
    if default_dir.exists():
        candidates = sorted(default_dir.glob("*.onnx"))
        return candidates[0] if candidates else None
    return None


def _clean_text(text: str) -> str:
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`[^`]+`", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    text = re.sub(r"[*_~#]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _pcm_to_wav_bytes(pcm_int16: Any, sample_rate: int) -> bytes:
    import numpy as np

    buf = io.BytesIO()
    arr = np.asarray(pcm_int16, dtype=np.int16)
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(arr.tobytes())
    return buf.getvalue()


def _synthesize(text: str, model_path: Path) -> tuple[bytes, int]:
    """Synthesize text via Piper and return (wav_bytes, sample_rate)."""
    import numpy as np

    piper = __import__("piper")
    path_key = str(model_path)
    if path_key not in _PIPER_VOICE_CACHE:
        _PIPER_VOICE_CACHE[path_key] = piper.PiperVoice.load(path_key)
    voice = _PIPER_VOICE_CACHE[path_key]
    sample_rate = _DEFAULT_SAMPLE_RATE

    try:
        from piper.config import SynthesisConfig

        syn_config = SynthesisConfig(speaker_id=0)
    except Exception:
        syn_config = None

    chunks = list(voice.synthesize(text, syn_config=syn_config))
    if not chunks:
        return b"", sample_rate

    sample_rate = int(
        getattr(chunks[0], "sample_rate", _DEFAULT_SAMPLE_RATE) or _DEFAULT_SAMPLE_RATE
    )
    arrays = [np.asarray(c.audio_int16_array, dtype=np.int16) for c in chunks]
    combined = np.concatenate(arrays) if arrays else np.zeros(0, dtype=np.int16)
    return _pcm_to_wav_bytes(combined, sample_rate), sample_rate


class AudioOutputStage:
    name = "audio_output"

    def run(self, context: StageContext) -> None:
        started = perf_counter()
        mode = str(context.state["policy"].audio_output_mode)
        context.state["audio_output_mode"] = mode

        if mode == "off":
            context.diagnostics.push_trace(self.name, started, outcome="skipped")
            return

        components = context.diagnostics.component_snapshot
        tts_component = next(
            (
                c
                for c in components
                if str(c.get("component_id", "")) == "tts_component"
            ),
            None,
        )
        tts_available = bool(tts_component and tts_component.get("available"))

        if not tts_available:
            context.diagnostics.add_degradation(
                "audio output requested but TTS backend unavailable"
            )
            context.diagnostics.push_trace(self.name, started, outcome="degraded")
            return

        generated_text = str(context.state.get("generated_text", "")).strip()
        if not generated_text:
            context.diagnostics.push_trace(self.name, started, outcome="skipped")
            return

        model_path = _find_tts_model_path()
        if model_path is None:
            context.diagnostics.add_degradation(
                "audio output: TTS model file not found on disk"
            )
            context.diagnostics.push_trace(self.name, started, outcome="degraded")
            return

        clean_text = _clean_text(generated_text)[:_TTS_MAX_CHARS]

        try:
            wav_bytes, sample_rate = _synthesize(clean_text, model_path)
        except ImportError:
            context.diagnostics.add_degradation(
                "audio output: piper-tts package not installed"
            )
            context.diagnostics.push_trace(self.name, started, outcome="degraded")
            return
        except Exception as exc:
            context.diagnostics.add_degradation(
                f"audio output: synthesis failed: {type(exc).__name__}"
            )
            context.diagnostics.push_trace(self.name, started, outcome="fallback")
            return

        if not wav_bytes:
            context.diagnostics.push_trace(self.name, started, outcome="empty")
            return

        context.state["audio_bytes"] = base64.b64encode(wav_bytes).decode("ascii")
        context.state["audio_sample_rate"] = sample_rate
        context.diagnostics.push_trace(self.name, started, outcome="ok")
