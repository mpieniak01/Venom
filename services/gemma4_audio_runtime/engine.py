"""Gemma 4 model engine and inference logic."""

from __future__ import annotations

import re
from typing import Any, Optional

import numpy as np
import transformers

from .audio import get_audio_duration, normalize_audio


class ModelLoadError(Exception):
    """Raised when model fails to load."""

    pass


class InferenceError(Exception):
    """Raised when inference fails."""

    pass


class Gemma4AudioEngine:
    """Engine for Gemma 4 audio inference using processor_model approach."""

    def __init__(
        self,
        model_id: str,
        cache_dir: str,
        device: str = "auto",
        max_new_tokens: int = 128,
    ):
        """Initialize the engine.

        Args:
            model_id: Hugging Face model ID (e.g., 'google/gemma-4-E2B-it')
            cache_dir: Cache directory for model download
            device: Device to load model on ('auto', 'cuda', 'cpu')
            max_new_tokens: Default max new tokens for generation
        """
        self.model_id = model_id
        self.cache_dir = cache_dir
        self.device = device
        self.default_max_new_tokens = max_new_tokens

        self.model: Optional[Any] = None
        self.processor: Optional[Any] = None
        self.model_class_name: Optional[str] = None

    def load(self) -> None:
        """Load model and processor from Hugging Face."""
        try:
            self.processor = transformers.AutoProcessor.from_pretrained(
                self.model_id,
                cache_dir=self.cache_dir,
                local_files_only=True,
            )

            model_class = self._resolve_model_class()
            self.model = model_class.from_pretrained(
                self.model_id,
                dtype="auto",
                device_map=self.device,
                cache_dir=self.cache_dir,
                local_files_only=True,
            )
            self.model_class_name = model_class.__name__

        except Exception as e:
            raise ModelLoadError(f"Failed to load model {self.model_id}: {e}") from e

    def unload(self) -> None:
        """Unload model and free resources."""
        self.model = None
        self.processor = None

    def is_loaded(self) -> bool:
        """Check if model is currently loaded."""
        return self.model is not None and self.processor is not None

    @staticmethod
    def _resolve_model_class() -> type[Any]:
        """Resolve the correct multimodal model class from transformers."""
        model_cls = getattr(transformers, "AutoModelForMultimodalLM", None)
        if model_cls is not None:
            return model_cls

        model_cls = getattr(transformers, "AutoModelForImageTextToText", None)
        if model_cls is not None:
            return model_cls

        raise ModelLoadError(
            "No compatible multimodal model class found in installed transformers. "
            "Ensure transformers >= 5.0 is installed."
        )

    def _build_prompt_for_task(
        self, task: Optional[str], question: Optional[str], default_prompt: str
    ) -> str:
        """Build the prompt instruction based on task or question."""
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
    ) -> tuple[str, float]:
        """Run inference on audio with optional text.

        Args:
            audio_array: Audio array (should be normalized to 16kHz mono float32)
            sample_rate: Sample rate of audio
            prompt: Default prompt if task/question not set
            task: Preset task ('transcribe', 'question', 'math-5x5')
            question: Question to answer about audio
            system_prompt: System message override
            max_new_tokens: Generation budget (uses default if None)
            temperature: Sampling temperature
            top_p: Top-p sampling parameter
            do_sample: Whether to use sampling

        Returns:
            Tuple of (generated_text, duration_sec)

        Raises:
            InferenceError: If inference fails
        """
        if not self.is_loaded():
            raise InferenceError("Model is not loaded. Call load() first.")

        # Normalize audio once more to ensure consistency
        try:
            audio_normalized, sr = normalize_audio(audio_array, sample_rate)
        except Exception as e:
            raise InferenceError(f"Failed to normalize audio: {e}") from e

        # Build the effective prompt
        effective_prompt = self._build_prompt_for_task(task, question, prompt)

        # Build messages in the format expected by Gemma processor
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
            # Apply chat template and tokenize
            inputs = self.processor.apply_chat_template(
                messages,
                add_generation_prompt=True,
                tokenize=True,
                return_dict=True,
                return_tensors="pt",
            )

            # Move inputs to model device if necessary
            if hasattr(inputs, "to"):
                inputs = inputs.to(self.model.device)

            # Generate
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens or self.default_max_new_tokens,
                temperature=temperature,
                top_p=top_p,
                do_sample=do_sample if do_sample is not None else False,
            )

            # Decode output
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

            # Clean up special tokens
            generated_text = self._clean_generated_text(generated_text)

            duration_sec = get_audio_duration(audio_normalized, sr)

            return generated_text, duration_sec

        except Exception as e:
            raise InferenceError(f"Inference failed: {e}") from e

    @staticmethod
    def _clean_generated_text(text: str) -> str:
        """Clean generated text by removing special tokens."""
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
        """Transcribe audio to text.

        Args:
            audio_array: Audio array
            sample_rate: Sample rate
            max_new_tokens: Generation budget

        Returns:
            Transcribed text
        """
        text, _ = self.respond(
            audio_array,
            sample_rate,
            prompt="Transcribe the speech in the audio. Return only the transcription.",
            task="transcribe",
            max_new_tokens=max_new_tokens,
        )
        return text
