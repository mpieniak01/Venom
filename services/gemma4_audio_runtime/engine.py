"""Gemma 4 model engine, inference logic, and daemon orchestration."""

from __future__ import annotations

import gc
import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

import numpy as np
import transformers

from .audio import get_audio_duration, normalize_audio

logger = logging.getLogger(__name__)


class ModelLoadError(Exception):
    """Raised when model fails to load."""


class InferenceError(Exception):
    """Raised when inference fails."""


class RuntimeMode(str, Enum):
    TARGET_ONLY = "target_only"
    TARGET_WITH_ASSISTANT = "target_with_assistant"


class ReloadSignal(str, Enum):
    NONE = "none"
    SOFT_RELOAD = "soft_reload"
    HARD_RESTART = "hard_restart"


@dataclass
class DaemonParams:
    max_new_tokens: int = 128
    enable_thinking: bool = False
    cache_implementation: Optional[str] = None


@dataclass
class VRAMInfo:
    backend: str = "cpu"
    allocated_mb: float = 0.0
    reserved_mb: float = 0.0
    total_mb: float = 0.0
    free_mb: float = 0.0


def _free_vram() -> None:
    """Release Python references and flush CUDA cache."""
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass


def _get_vram_info() -> VRAMInfo:
    """Return current VRAM usage snapshot."""
    try:
        import torch

        if torch.cuda.is_available():
            allocated = torch.cuda.memory_allocated(0)
            reserved = torch.cuda.memory_reserved(0)
            total = torch.cuda.get_device_properties(0).total_memory
            return VRAMInfo(
                backend="cuda",
                allocated_mb=round(allocated / 1024**2, 1),
                reserved_mb=round(reserved / 1024**2, 1),
                total_mb=round(total / 1024**2, 1),
                free_mb=round((total - allocated) / 1024**2, 1),
            )
    except (ImportError, AttributeError, RuntimeError):
        pass
    return VRAMInfo()


class Gemma4AudioEngine:
    """Engine for Gemma 4 audio inference using processor_model approach."""

    def __init__(
        self,
        model_id: str,
        cache_dir: str,
        device: str = "auto",
        max_new_tokens: int = 128,
    ):
        self.model_id = model_id
        self.cache_dir = cache_dir
        self.device = device
        self.default_max_new_tokens = max_new_tokens

        self.model: Optional[Any] = None
        self.processor: Optional[Any] = None
        self.model_class_name: Optional[str] = None

    # Model classes tried in order — multimodal first, causal-LM last (for
    # assistant/drafter models like Gemma4AssistantConfig used in spec. decoding).
    _MODEL_CLASS_CANDIDATES = (
        "AutoModelForMultimodalLM",
        "AutoModelForImageTextToText",
        "AutoModelForCausalLM",
    )

    def load(self) -> None:
        """Load model and processor, trying multimodal then causal-LM classes."""
        try:
            self.processor = transformers.AutoProcessor.from_pretrained(
                self.model_id,
                cache_dir=self.cache_dir,
                local_files_only=True,
            )
        except Exception as e:
            raise ModelLoadError(
                f"Failed to load processor for {self.model_id}: {e}"
            ) from e

        last_error: Optional[Exception] = None
        for cls_name in self._MODEL_CLASS_CANDIDATES:
            model_cls = getattr(transformers, cls_name, None)
            if model_cls is None:
                continue
            try:
                self.model = model_cls.from_pretrained(
                    self.model_id,
                    dtype="auto",
                    device_map=self.device,
                    cache_dir=self.cache_dir,
                    local_files_only=True,
                )
                self.model_class_name = cls_name
                logger.debug("Loaded %s with %s", self.model_id, cls_name)
                return
            except Exception as e:
                last_error = e
                continue

        raise ModelLoadError(
            f"Failed to load model {self.model_id} with any candidate class: {last_error}"
        ) from last_error

    def unload(self) -> None:
        """Unload model and free references."""
        self.model = None
        self.processor = None

    def is_loaded(self) -> bool:
        return self.model is not None and self.processor is not None

    def _build_prompt_for_task(
        self, task: Optional[str], question: Optional[str], default_prompt: str
    ) -> str:
        if task == "math-5x5":
            return (
                "Listen to the audio and answer the question using only the audio as evidence. "
                "Return only the answer, no explanation, no extra words.\n"
                "Question: Ile to jest 5 razy 5?"
            )
        if task == "transcribe":
            return (
                "Transcribe the speech in the audio. "
                "Return only the transcription, with no bullets and no extra commentary."
            )
        if question and question.strip():
            return (
                "Listen to the audio and answer the question using only the audio as evidence. "
                "If the answer is not clear from the audio, say so briefly.\n"
                f"Question: {question.strip()}"
            )
        return default_prompt

    def respond(
        self,
        audio_array: np.ndarray,
        sample_rate: int,
        prompt: str = "Transcribe the speech in the audio.",
        task: Optional[str] = None,
        question: Optional[str] = None,
        system_prompt: Optional[str] = None,
        max_new_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        do_sample: Optional[bool] = None,
        enable_thinking: bool = False,
        cache_implementation: Optional[str] = None,
    ) -> tuple[str, float]:
        """Run inference on audio with optional text.

        Returns:
            Tuple of (generated_text, duration_sec)
        """
        if not self.is_loaded():
            raise InferenceError("Model is not loaded. Call load() first.")

        try:
            audio_normalized, sr = normalize_audio(audio_array, sample_rate)
        except Exception as e:
            raise InferenceError(f"Failed to normalize audio: {e}") from e

        effective_prompt = self._build_prompt_for_task(task, question, prompt)

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "audio", "array": audio_normalized, "sample_rate": sr},
                    {"type": "text", "text": effective_prompt},
                ],
            }
        ]

        if system_prompt:
            messages.insert(
                0,
                {
                    "role": "system",
                    "content": [{"type": "text", "text": system_prompt}],
                },
            )

        try:
            apply_template_kwargs: dict[str, Any] = {
                "add_generation_prompt": True,
                "tokenize": True,
                "return_dict": True,
                "return_tensors": "pt",
            }
            if enable_thinking:
                apply_template_kwargs["enable_thinking"] = True

            try:
                inputs = self.processor.apply_chat_template(
                    messages,
                    **apply_template_kwargs,
                )
            except TypeError:
                apply_template_kwargs.pop("enable_thinking", None)
                inputs = self.processor.apply_chat_template(
                    messages,
                    **apply_template_kwargs,
                )

            if hasattr(inputs, "to"):
                inputs = inputs.to(self.model.device)

            generate_kwargs: dict[str, Any] = {
                "max_new_tokens": max_new_tokens or self.default_max_new_tokens,
                "temperature": temperature,
                "top_p": top_p,
                "do_sample": do_sample if do_sample is not None else False,
            }
            if cache_implementation is not None:
                generate_kwargs["cache_implementation"] = cache_implementation

            try:
                outputs = self.model.generate(**inputs, **generate_kwargs)
            except TypeError:
                generate_kwargs.pop("cache_implementation", None)
                outputs = self.model.generate(**inputs, **generate_kwargs)

            input_len = 0
            if hasattr(inputs, "input_ids"):
                try:
                    input_len = int(inputs.input_ids.shape[-1])
                except Exception:
                    pass

            if hasattr(outputs, "__getitem__") and len(outputs) > 0 and input_len > 0:
                output_ids = outputs[0][input_len:]
            else:
                output_ids = (
                    outputs[0]
                    if hasattr(outputs, "__getitem__") and len(outputs) > 0
                    else outputs
                )

            generated_text = self.processor.decode(
                output_ids,
                skip_special_tokens=False,
                clean_up_tokenization_spaces=False,
            )

            generated_text = self._clean_generated_text(generated_text)
            duration_sec = get_audio_duration(audio_normalized, sr)

            return generated_text, duration_sec

        except Exception as e:
            raise InferenceError(f"Inference failed: {e}") from e

    @staticmethod
    def _clean_generated_text(text: str) -> str:
        cleaned = (
            text.replace("<bos>", "").replace("<turn|>", "").replace("<|turn>", "")
        )
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    def transcribe(
        self,
        audio_array: np.ndarray,
        sample_rate: int,
        max_new_tokens: int = 256,
    ) -> str:
        text, _ = self.respond(
            audio_array,
            sample_rate,
            prompt="Transcribe the speech in the audio. Return only the transcription.",
            task="transcribe",
            max_new_tokens=max_new_tokens,
        )
        return text


class Gemma4Daemon:
    """Steerable daemon wrapping a target Gemma 4 model with optional assistant.

    Responsibilities:
    - Holds exactly one target model as the base.
    - Optionally loads an assistant/drafter model.
    - Provides live parameter updates when no reload is needed.
    - Signals when soft reload or hard restart is required.
    - Guarantees VRAM is clean after every switch or reload.
    """

    DEFAULT_TARGET = "google/gemma-4-E2B-it"

    def __init__(
        self,
        cache_dir: str,
        device: str = "auto",
        model_id: Optional[str] = None,
        max_new_tokens: int = 128,
    ):
        self._target_id: str = model_id or self.DEFAULT_TARGET
        self._assistant_id: Optional[str] = None
        self._target_engine: Optional[Gemma4AudioEngine] = None
        self._assistant_engine: Optional[Gemma4AudioEngine] = None
        self._params: DaemonParams = DaemonParams(max_new_tokens=max_new_tokens)
        self._cache_dir = cache_dir
        self._device = device
        self._reload_reason: Optional[str] = None
        self._mode: RuntimeMode = RuntimeMode.TARGET_ONLY

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def load_target(self) -> None:
        """Load target model. Cleans VRAM first to prevent orphaned models."""
        self._ensure_vram_clean()
        self._target_engine = Gemma4AudioEngine(
            model_id=self._target_id,
            cache_dir=self._cache_dir,
            device=self._device,
            max_new_tokens=self._params.max_new_tokens,
        )
        self._target_engine.load()
        logger.info("Target model loaded: %s", self._target_id)

    def soft_reload(self) -> str:
        """Free VRAM and reload the target model. Returns the reload reason."""
        reason = self._reload_reason or "manual_reload"
        self._reload_reason = None
        # Soft reload drops the assistant — caller must re-attach explicitly.
        assistant_was = self._assistant_id
        self._ensure_vram_clean()
        self._assistant_id = None
        self._mode = RuntimeMode.TARGET_ONLY
        self.load_target()
        if assistant_was:
            logger.info(
                "Soft reload completed; assistant '%s' was dropped. Re-attach manually.",
                assistant_was,
            )
        logger.info("Soft reload done. Reason: %s", reason)
        return reason

    def unload_all(self) -> None:
        """Unload every model and free VRAM. Used before hard restart."""
        self._ensure_vram_clean()
        self._assistant_id = None
        self._mode = RuntimeMode.TARGET_ONLY
        logger.info("All models unloaded (pre-restart)")

    # ------------------------------------------------------------------
    # Assistant management
    # ------------------------------------------------------------------

    def attach_assistant(self, model_id: str) -> None:
        """Attach an assistant model. Replaces any existing assistant."""
        if self._assistant_engine is not None:
            self._drop_assistant()
        self._assistant_id = model_id
        try:
            engine = Gemma4AudioEngine(
                model_id=model_id,
                cache_dir=self._cache_dir,
                device=self._device,
                max_new_tokens=self._params.max_new_tokens,
            )
            engine.load()
            self._assistant_engine = engine
            self._mode = RuntimeMode.TARGET_WITH_ASSISTANT
            logger.info("Assistant model attached: %s", model_id)
        except Exception as exc:
            self._assistant_engine = None
            self._assistant_id = None
            _free_vram()
            raise ModelLoadError(
                f"Failed to attach assistant '{model_id}': {exc}"
            ) from exc

    def detach_assistant(self) -> None:
        """Detach and unload the current assistant model."""
        self._drop_assistant()

    def _drop_assistant(self) -> None:
        if self._assistant_engine is not None:
            self._assistant_engine.unload()
            self._assistant_engine = None
            _free_vram()
        self._assistant_id = None
        self._mode = RuntimeMode.TARGET_ONLY
        logger.info("Assistant model detached")

    # ------------------------------------------------------------------
    # Parameter control
    # ------------------------------------------------------------------

    def update_params(
        self,
        max_new_tokens: Optional[int] = None,
        enable_thinking: Optional[bool] = None,
        cache_implementation: Optional[str] = None,
    ) -> ReloadSignal:
        """Apply parameter changes. Returns the minimum reload action required."""
        reload_signal = ReloadSignal.NONE

        if max_new_tokens is not None:
            self._params.max_new_tokens = max_new_tokens
            if self._target_engine:
                self._target_engine.default_max_new_tokens = max_new_tokens
            if self._assistant_engine:
                self._assistant_engine.default_max_new_tokens = max_new_tokens

        if enable_thinking is not None:
            self._params.enable_thinking = enable_thinking

        if (
            cache_implementation is not None
            and cache_implementation != self._params.cache_implementation
        ):
            self._params.cache_implementation = cache_implementation
            self._reload_reason = (
                f"cache_implementation changed to '{cache_implementation}'"
            )
            reload_signal = ReloadSignal.SOFT_RELOAD

        return reload_signal

    def fallback(self) -> ReloadSignal:
        """Reset to safe defaults (target only, default params).

        Returns the reload signal needed to complete the fallback.
        Caller should execute the reload after receiving the signal.
        """
        self._drop_assistant()
        prev_target = self._target_id
        prev_cache = self._params.cache_implementation
        self._params = DaemonParams()

        if prev_target != self.DEFAULT_TARGET:
            self._target_id = self.DEFAULT_TARGET
            self._reload_reason = f"fallback: target changed from '{prev_target}' to '{self.DEFAULT_TARGET}'"
            return ReloadSignal.HARD_RESTART

        if prev_cache is not None:
            self._reload_reason = "fallback: cache_implementation reset to default"
            return ReloadSignal.SOFT_RELOAD

        self._reload_reason = "fallback: clean reload"
        return ReloadSignal.SOFT_RELOAD

    # ------------------------------------------------------------------
    # Status and routing
    # ------------------------------------------------------------------

    def is_ready(self) -> bool:
        return self._target_engine is not None and self._target_engine.is_loaded()

    def active_engine(self) -> Gemma4AudioEngine:
        """Return the engine to use for inference (always the target)."""
        if not self.is_ready():
            raise RuntimeError("Daemon target model is not loaded")
        assert self._target_engine is not None
        return self._target_engine

    def status(self) -> dict[str, Any]:
        return {
            "target_model": self._target_id,
            "assistant_model": self._assistant_id,
            "mode": self._mode.value,
            "target_loaded": self.is_ready(),
            "assistant_loaded": (
                self._assistant_engine is not None
                and self._assistant_engine.is_loaded()
            ),
            "params": {
                "max_new_tokens": self._params.max_new_tokens,
                "enable_thinking": self._params.enable_thinking,
                "cache_implementation": self._params.cache_implementation,
            },
            "vram": _get_vram_info().__dict__,
            "pending_reload": self._reload_reason is not None,
            "reload_reason": self._reload_reason,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_vram_clean(self) -> None:
        """Unload all models and flush VRAM. No orphaned tensors left behind."""
        if self._target_engine is not None:
            self._target_engine.unload()
            self._target_engine = None
        if self._assistant_engine is not None:
            self._assistant_engine.unload()
            self._assistant_engine = None
        _free_vram()
