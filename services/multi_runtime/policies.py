"""Execution policy resolution for multi_runtime pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

ExecutionMode = Literal["balanced", "vision_priority", "voice_priority"]
ImageStrategy = Literal["vlm_only", "ocr_first", "hybrid"]
RetrievalMode = Literal["off", "auto", "always"]
AudioOutputMode = Literal["off", "text_first", "voice_first"]
AssistantMode = Literal["off", "attached", "conditional"]
EconomyMode = Literal["off", "auto"]


@dataclass(slots=True)
class ExecutionPolicy:
    execution_mode: ExecutionMode = "balanced"
    image_strategy: ImageStrategy = "vlm_only"
    retrieval_mode: RetrievalMode = "off"
    audio_output_mode: AudioOutputMode = "off"
    assistant_mode: AssistantMode = "off"
    economy_mode: EconomyMode = "off"

    def policy_name(self) -> str:
        return (
            f"{self.execution_mode}|{self.image_strategy}|{self.retrieval_mode}|"
            f"{self.audio_output_mode}|{self.assistant_mode}|{self.economy_mode}"
        )


class RuntimePolicyResolver:
    """Resolve runtime policy from daemon state and request modalities.

    Current implementation preserves existing behavior and defaults to a safe,
    lightweight policy. It is intentionally minimal for phase 1.
    """

    def resolve(
        self,
        *,
        daemon_status: dict[str, Any],
        has_images: bool,
        has_audio: bool,
    ) -> ExecutionPolicy:
        params = daemon_status.get("params", {})
        vram_backend = str(daemon_status.get("vram", {}).get("backend", "cpu"))
        assistant_attached = bool(daemon_status.get("assistant_model"))

        profile_execution_mode = params.get("execution_mode")
        if profile_execution_mode in {
            "balanced",
            "vision_priority",
            "voice_priority",
        }:
            execution_mode: ExecutionMode = profile_execution_mode
        elif has_images and not has_audio:
            execution_mode: ExecutionMode = "vision_priority"
        elif has_audio and not has_images:
            execution_mode = "voice_priority"
        else:
            execution_mode = "balanced"

        profile_image_strategy = params.get("image_strategy")
        image_strategy: ImageStrategy = (
            profile_image_strategy
            if profile_image_strategy in {"vlm_only", "ocr_first", "hybrid"}
            else "vlm_only"
        )

        profile_retrieval_mode = params.get("retrieval_mode")
        retrieval_mode: RetrievalMode = (
            profile_retrieval_mode
            if profile_retrieval_mode in {"off", "auto", "always"}
            else "off"
        )

        profile_audio_output_mode = params.get("audio_output_mode")
        audio_output_mode: AudioOutputMode = (
            profile_audio_output_mode
            if profile_audio_output_mode in {"off", "text_first", "voice_first"}
            else "off"
        )

        profile_assistant_mode = params.get("assistant_mode")
        if profile_assistant_mode in {"off", "attached", "conditional"}:
            assistant_mode: AssistantMode = profile_assistant_mode
        else:
            assistant_mode = "attached" if assistant_attached else "off"

        profile_economy_mode = params.get("economy_mode")
        if profile_economy_mode in {"off", "auto"}:
            economy_mode: EconomyMode = profile_economy_mode
        else:
            economy_mode = "auto" if vram_backend != "cuda" else "off"

        return ExecutionPolicy(
            execution_mode=execution_mode,
            image_strategy=image_strategy,
            retrieval_mode=retrieval_mode,
            audio_output_mode=audio_output_mode,
            assistant_mode=assistant_mode,
            economy_mode=economy_mode,
        )
