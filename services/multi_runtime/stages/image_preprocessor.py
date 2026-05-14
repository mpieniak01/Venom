"""Image preprocessing stage for multimodal pipeline."""

from __future__ import annotations

from time import perf_counter

from .base import StageContext


class ImagePreprocessorStage:
    name = "image_preprocessor"

    def run(self, context: StageContext) -> None:
        started = perf_counter()
        if not context.images:
            context.state["preprocessed_images"] = []
            context.diagnostics.push_trace(self.name, started, outcome="skipped")
            return

        context.state["preprocessed_images"] = context.images
        context.diagnostics.push_trace(self.name, started)
