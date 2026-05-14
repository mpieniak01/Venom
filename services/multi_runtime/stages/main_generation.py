"""Main generation stage for the target model inference."""

from __future__ import annotations

from time import perf_counter
from typing import Any

from .base import StageContext


class MainGenerationStage:
    name = "main_generation"

    def __init__(self, engine: Any):
        self._engine = engine

    def run(self, context: StageContext) -> None:
        started = perf_counter()
        daemon_params = context.daemon_status["params"]
        request_payload = context.request_payload

        prompt = (
            context.text_content
            or request_payload.system_prompt
            or "Respond to the audio"
        )
        ocr_text = str(context.state.get("ocr_text", "")).strip()
        image_execution_path = str(
            context.state.get("image_execution_path", "")
        ).strip()
        if ocr_text:
            prompt = f"{prompt}\n\n[ocr_context path={image_execution_path or 'ocr'}]\n{ocr_text[:2000]}"
        retrieval_context = str(context.state.get("retrieval_context", "")).strip()
        if retrieval_context:
            prompt = f"{prompt}\n\n[retrieval_context]\n{retrieval_context}"

        generated_text, duration = self._engine.respond(
            context.audio_array,
            sample_rate=context.sample_rate,
            prompt=prompt,
            images=context.images or None,
            task=request_payload.task,
            question=request_payload.question,
            system_prompt=request_payload.system_prompt,
            max_new_tokens=request_payload.max_new_tokens,
            temperature=request_payload.temperature,
            top_p=request_payload.top_p,
            do_sample=request_payload.do_sample,
            enable_thinking=bool(daemon_params["enable_thinking"]),
            cache_implementation=daemon_params["cache_implementation"],
        )

        context.state["generated_text"] = generated_text
        context.state["audio_duration_sec"] = duration
        context.diagnostics.push_trace(self.name, started)
