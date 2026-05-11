"""Fish Speech inference engine with lazy model loading."""

from __future__ import annotations

import io
import logging
import os
import sys
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
                    from natsort import natsorted

                    return natsorted(children, reverse=True)[0]
    return None


def _resolve_source_root() -> Path:
    """Resolve the official Fish Speech source checkout used for inference."""
    source_dir = os.getenv("FISH_SPEECH_SOURCE_DIR", "").strip()
    if source_dir:
        return Path(source_dir).expanduser().resolve()

    # Local developer default: sibling checkout next to the Venom repository.
    return Path(__file__).resolve().parents[3] / "fish-speech-src"


def _prepend_source_root() -> Path:
    """Ensure the Fish Speech source checkout is importable."""
    source_root = _resolve_source_root()
    if not source_root.exists():
        raise RuntimeError(
            "Fish Speech source checkout was not found. "
            "Set FISH_SPEECH_SOURCE_DIR to the cloned fish-speech repository."
        )
    source_root_str = str(source_root)
    if source_root_str not in sys.path:
        sys.path.insert(0, source_root_str)
    return source_root


def _clear_fish_speech_import_cache() -> None:
    """Drop cached Fish Speech modules so the source checkout wins imports."""
    for module_name in list(sys.modules):
        if module_name == "tools" or module_name.startswith("tools."):
            sys.modules.pop(module_name, None)


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

        self._loaded = False
        self._load_error: str | None = None
        self._model_manager: Any = None
        self._tts_inference_engine: Any = None
        self._sample_rate: int | None = None

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

    def _resolve_checkpoint_dir(self) -> tuple[Path, Path]:
        snapshot = _model_snapshot_dir(self.model_id, self.cache_dir)
        if snapshot is None:
            raise FileNotFoundError(
                f"Model weights not found for {self.model_id} in {self.cache_dir}. "
                f"Download via: huggingface-cli download {self.model_id}"
            )

        decoder_checkpoint_path = (
            snapshot / "firefly-gan-vq-fsq-8x1024-21hz-generator.pth"
        )
        llama_checkpoint_path = snapshot
        if not (llama_checkpoint_path / "model.pth").exists():
            raise FileNotFoundError(
                f"Missing Fish Speech llama checkpoint: {llama_checkpoint_path / 'model.pth'}"
            )
        if not (llama_checkpoint_path / "tokenizer.tiktoken").exists():
            raise FileNotFoundError(
                f"Missing Fish Speech tokenizer: {llama_checkpoint_path / 'tokenizer.tiktoken'}"
            )
        if not decoder_checkpoint_path.exists():
            raise FileNotFoundError(
                f"Missing Fish Speech decoder checkpoint: {decoder_checkpoint_path}"
            )
        return llama_checkpoint_path, decoder_checkpoint_path

    def load(self) -> bool:
        """Load the Fish Speech models. Returns True on success."""
        if self._loaded:
            return True

        try:
            _prepend_source_root()
            _clear_fish_speech_import_cache()
        except Exception as exc:
            self._load_error = str(exc)
            logger.warning(self._load_error)
            return False

        try:
            from tools.server.model_manager import ModelManager

            llama_checkpoint_path, decoder_checkpoint_path = (
                self._resolve_checkpoint_dir()
            )
            resolved_device = self._resolve_device()
            effective_half = self.half and resolved_device != "cpu"

            self._model_manager = ModelManager(
                mode="tts",
                device=resolved_device,
                half=effective_half,
                compile=self.compile_model,
                asr_enabled=False,
                llama_checkpoint_path=str(llama_checkpoint_path),
                decoder_checkpoint_path=str(decoder_checkpoint_path),
                decoder_config_name="firefly_gan_vq",
            )
            self._tts_inference_engine = self._model_manager.tts_inference_engine
            self._sample_rate = int(
                self._tts_inference_engine.decoder_model.spec_transform.sample_rate
            )
            self._loaded = True
            self._load_error = None
            logger.info(
                "Fish Speech engine loaded from %s (device=%s, half=%s, sample_rate=%s)",
                llama_checkpoint_path.parent,
                resolved_device,
                effective_half,
                self._sample_rate,
            )
            return True
        except Exception as exc:
            self._load_error = f"Failed to load Fish Speech model: {exc}"
            logger.exception(self._load_error)
            return False

    def synthesize(
        self,
        text: str,
        language: str = "pl",
        sample_rate: int = 24000,
    ) -> bytes:
        """Synthesize speech from text. Returns WAV bytes."""
        if not self._loaded or self._tts_inference_engine is None:
            raise RuntimeError(
                self._load_error or "Engine not loaded. Call load() first."
            )

        # The official Fish Speech TTS server speaks from text and references.
        # Our Venom API keeps a language parameter for compatibility, but Fish Speech
        # v1.5 inference does not require it directly.
        del language
        if self._sample_rate is None:
            self._sample_rate = sample_rate

        try:
            _prepend_source_root()
            _clear_fish_speech_import_cache()
            from tools.schema import ServeTTSRequest
            from tools.server.inference import inference_wrapper

            request = ServeTTSRequest(
                text=text,
                chunk_length=200,
                format="wav",
                references=[],
                reference_id=None,
                seed=None,
                use_memory_cache="off",
                normalize=True,
                streaming=False,
                max_new_tokens=1024,
                top_p=0.7,
                repetition_penalty=1.2,
                temperature=0.7,
            )
            audio = next(inference_wrapper(request, self._tts_inference_engine))
        except Exception as exc:
            raise RuntimeError(f"Fish Speech synthesis failed: {exc}") from exc

        if isinstance(audio, (bytes, bytearray)):
            return bytes(audio)
        if isinstance(audio, np.ndarray):
            return _ndarray_to_wav_bytes(audio, sample_rate=self._sample_rate)
        raise RuntimeError(f"Unexpected Fish Speech output type: {type(audio)!r}")


def _ndarray_to_wav_bytes(audio: np.ndarray, sample_rate: int) -> bytes:
    """Convert a float32 numpy array to WAV bytes."""
    import wave

    audio = np.asarray(audio, dtype=np.float32)
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
