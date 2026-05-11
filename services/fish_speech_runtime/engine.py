"""Fish Speech inference engine with lazy model loading."""

from __future__ import annotations

import io
import logging
import os
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

_engine_instance: FishSpeechEngine | None = None


def _model_snapshot_dir(model_id: str, cache_dir: Path) -> Path | None:
    """Return the snapshots dir for a cached HF model, or None if not found."""
    model_slug = model_id.replace("/", "--")
    prefix = f"models--{model_slug}"
    if not cache_dir.exists():
        return None
    for entry in cache_dir.iterdir():
        if entry.name.startswith(prefix) and entry.is_dir():
            snapshots = entry / "snapshots"
            if snapshots.exists():
                children = list(snapshots.iterdir())
                if children:
                    return children[0]
    return None


class FishSpeechEngine:
    """Lazy-loading Fish Speech TTS inference engine."""

    def __init__(
        self,
        model_id: str,
        cache_dir: str,
        device: str = "auto",
        half: bool = True,
        compile_model: bool = False,
    ) -> None:
        self.model_id = model_id
        self.cache_dir = Path(cache_dir)
        self.device = device
        self.half = half
        self.compile_model = compile_model

        self._model: Any = None
        self._decoder: Any = None
        self._tokenizer: Any = None
        self._loaded = False
        self._load_error: str | None = None

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def load_error(self) -> str | None:
        return self._load_error

    def _resolve_device(self) -> str:
        if self.device != "auto":
            return self.device
        try:
            import torch  # type: ignore[import]

            return "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            return "cpu"

    def load(self) -> bool:
        """Load the Fish Speech model. Returns True on success."""
        if self._loaded:
            return True

        try:
            import fish_speech  # noqa: F401 — check package available
        except ImportError:
            self._load_error = (
                "fish_speech package not installed. "
                "Install it via: pip install fish-speech"
            )
            logger.warning(self._load_error)
            return False

        snapshot = _model_snapshot_dir(self.model_id, self.cache_dir)
        if snapshot is None:
            self._load_error = (
                f"Model weights not found for {self.model_id} in {self.cache_dir}. "
                "Download via: huggingface-cli download fishaudio/fish-speech-1.5"
            )
            logger.warning(self._load_error)
            return False

        try:
            self._load_from_snapshot(snapshot)
            self._loaded = True
            self._load_error = None
            logger.info(f"Fish Speech engine loaded from {snapshot}")
            return True
        except Exception as exc:
            self._load_error = f"Failed to load Fish Speech model: {exc}"
            logger.error(self._load_error)
            return False

    def _load_from_snapshot(self, snapshot: Path) -> None:
        """Internal: load model components from snapshot directory."""
        import torch  # type: ignore[import]
        from fish_speech.models.text2semantic.inference import (
            load_model as load_semantic_model,  # type: ignore[import]
        )
        from fish_speech.models.vqgan.inference import (
            load_model as load_decoder_model,  # type: ignore[import]
        )

        resolved_device = self._resolve_device()
        dtype = torch.half if (self.half and resolved_device == "cuda") else torch.float

        semantic_path = snapshot / "model.pth"
        decoder_path = snapshot / "firefly-gan-vq-fsq-8x1024-21hz-generator.pth"

        self._model = load_semantic_model(
            config_name="dual_ar_2_codebook_large",
            checkpoint_path=str(semantic_path),
            device=resolved_device,
            dtype=dtype,
            compile=self.compile_model,
        )
        self._decoder = load_decoder_model(
            config_name="firefly_gan_vq",
            checkpoint_path=str(decoder_path),
            device=resolved_device,
        )

    def synthesize(
        self,
        text: str,
        language: str = "pl",
        sample_rate: int = 24000,
    ) -> bytes:
        """Synthesize speech from text. Returns WAV bytes."""
        if not self._loaded:
            raise RuntimeError(
                self._load_error or "Engine not loaded. Call load() first."
            )

        import torch  # type: ignore[import]

        resolved_device = self._resolve_device()

        from fish_speech.models.text2semantic.inference import (  # type: ignore[import]
            generate_long,
        )

        audio_chunks: list[np.ndarray] = []

        with torch.inference_mode():
            for chunk in generate_long(
                model=self._model,
                decoder_model=self._decoder,
                text=text,
                num_samples=1,
                max_new_tokens=0,
                top_p=0.7,
                repetition_penalty=1.2,
                temperature=0.7,
                device=resolved_device,
                compile=self.compile_model,
            ):
                if isinstance(chunk, np.ndarray):
                    audio_chunks.append(chunk)

        if not audio_chunks:
            raise RuntimeError("Fish Speech inference produced no audio output")

        audio = np.concatenate(audio_chunks, axis=-1)
        return _ndarray_to_wav_bytes(audio, sample_rate=sample_rate)


def _ndarray_to_wav_bytes(audio: np.ndarray, sample_rate: int) -> bytes:
    """Convert a float32 numpy array to WAV bytes."""
    import wave

    audio_int16 = (audio * 32767).clip(-32768, 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_int16.tobytes())
    return buf.getvalue()


def get_engine() -> FishSpeechEngine:
    """Return (creating if needed) the singleton engine instance."""
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = FishSpeechEngine(
            model_id=os.getenv("FISH_SPEECH_MODEL_ID", "fishaudio/fish-speech-1.5"),
            cache_dir=os.getenv("FISH_SPEECH_CACHE_DIR", "models_cache/hf"),
            device=os.getenv("FISH_SPEECH_DEVICE", "auto"),
            half=os.getenv("FISH_SPEECH_HALF", "true").lower() == "true",
            compile_model=os.getenv("FISH_SPEECH_COMPILE", "false").lower() == "true",
        )
    return _engine_instance
