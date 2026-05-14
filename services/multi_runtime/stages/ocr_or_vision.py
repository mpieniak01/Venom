"""Select OCR or direct vision path based on policy and availability."""

from __future__ import annotations

import importlib.util
from time import perf_counter

from .base import StageContext


class OcrOrVisionStage:
    name = "ocr_or_vision"

    @staticmethod
    def _ocr_available() -> bool:
        return importlib.util.find_spec("pytesseract") is not None

    def run(self, context: StageContext) -> None:
        started = perf_counter()
        images = context.state.get("preprocessed_images", [])
        if not images:
            context.state["image_execution_path"] = "none"
            context.diagnostics.push_trace(self.name, started, outcome="skipped")
            return

        strategy = str(context.state["policy"].image_strategy)
        ocr_available = self._ocr_available()
        selected = strategy

        if strategy == "ocr_first" and not ocr_available:
            selected = "vlm_only"
            context.diagnostics.add_degradation(
                "ocr_first requested but OCR backend unavailable; falling back to vlm_only"
            )
        elif strategy == "hybrid" and not ocr_available:
            selected = "vlm_only"
            context.diagnostics.add_degradation(
                "hybrid requested but OCR backend unavailable; falling back to vlm_only"
            )
        elif context.state["policy"].economy_mode == "auto" and strategy == "hybrid":
            selected = "vlm_only"
            context.diagnostics.economy_mode_activated = True
            context.diagnostics.add_degradation(
                "economy_mode simplified hybrid image path to vlm_only"
            )

        context.state["image_execution_path"] = selected
        context.diagnostics.selected_image_strategy = selected
        outcome = "ok" if selected == strategy else "degraded"
        context.diagnostics.push_trace(self.name, started, outcome=outcome)
