"""Pipeline orchestration for multi_runtime execution."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any

from .components import build_component_snapshot
from .diagnostics import ExecutionDiagnostics
from .policies import RuntimePolicyResolver
from .stages import (
    AssistantPostprocessStage,
    AudioOutputStage,
    ImagePreprocessorStage,
    InputRouterStage,
    MainGenerationStage,
    OcrOrVisionStage,
    RetrievalStage,
    StageContext,
)


@dataclass(slots=True)
class PipelineRequestData:
    request_payload: Any
    text_content: str | None
    audio_array: Any
    sample_rate: int
    images: list[Any]


@dataclass(slots=True)
class PipelineResult:
    generated_text: str
    audio_duration_sec: float
    total_duration_ms: int
    input_modalities: list[str]
    diagnostics: ExecutionDiagnostics


class MultiRuntimePipeline:
    """Runtime pipeline preserving current behavior while exposing clear stages."""

    def __init__(self, engine: Any, daemon: Any | None = None):
        self._engine = engine
        self._daemon = daemon
        self._policy_resolver = RuntimePolicyResolver()

    def execute(
        self,
        *,
        daemon_status: dict[str, Any],
        request: PipelineRequestData,
    ) -> PipelineResult:
        started = perf_counter()
        diagnostics = ExecutionDiagnostics()

        policy = self._policy_resolver.resolve(
            daemon_status=daemon_status,
            has_images=bool(request.images),
            has_audio=request.audio_array is not None,
        )
        diagnostics.component_snapshot = build_component_snapshot(
            daemon_status,
            request_overrides={
                "retrieval_mode": policy.retrieval_mode,
                "audio_output_mode": policy.audio_output_mode,
                "assistant_mode": policy.assistant_mode,
                "image_strategy": policy.image_strategy,
            },
        )
        diagnostics.selected_policy = policy.policy_name()
        diagnostics.selected_image_strategy = policy.image_strategy
        diagnostics.retrieval_used = False
        diagnostics.assistant_used = False
        diagnostics.economy_mode_activated = False

        context = StageContext(
            request_payload=request.request_payload,
            daemon_status=daemon_status,
            text_content=request.text_content,
            audio_array=request.audio_array,
            sample_rate=request.sample_rate,
            images=request.images,
            diagnostics=diagnostics,
            state={"policy": policy},
        )

        InputRouterStage().run(context)
        ImagePreprocessorStage().run(context)
        OcrOrVisionStage().run(context)
        RetrievalStage().run(context)
        MainGenerationStage(self._engine).run(context)
        AssistantPostprocessStage(self._daemon).run(context)
        AudioOutputStage().run(context)

        audio_present = request.audio_array is not None
        image_present = bool(request.images)

        if audio_present and image_present:
            modalities = ["text", "audio", "image"]
        elif audio_present:
            modalities = ["text", "audio"]
        elif image_present:
            modalities = ["text", "image"]
        else:
            modalities = ["text"]

        return PipelineResult(
            generated_text=str(context.state.get("generated_text", "")),
            audio_duration_sec=float(context.state.get("audio_duration_sec", 0.0)),
            total_duration_ms=int((perf_counter() - started) * 1000),
            input_modalities=modalities,
            diagnostics=diagnostics,
        )
