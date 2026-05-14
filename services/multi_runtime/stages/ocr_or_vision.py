"""Select OCR or direct vision path based on policy and availability."""

from __future__ import annotations

from time import perf_counter

from .base import StageContext


class OcrOrVisionStage:
    name = "ocr_or_vision"

    def run(self, context: StageContext) -> None:
        started = perf_counter()
        images = context.state.get("preprocessed_images", [])
        if not images:
            context.state["image_execution_path"] = "none"
            context.diagnostics.push_trace(self.name, started, outcome="skipped")
            return

        strategy = str(context.state["policy"].image_strategy)
        ocr_available = False
        selected = strategy

        if strategy == "ocr_first" and not ocr_available:
            selected = "vlm_only"
        elif strategy == "hybrid" and not ocr_available:
            selected = "vlm_only"

        context.state["image_execution_path"] = selected
        context.diagnostics.selected_image_strategy = selected
        context.diagnostics.push_trace(self.name, started)
