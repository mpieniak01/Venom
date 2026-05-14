"""Assistant postprocess stage placeholder."""

from __future__ import annotations

from time import perf_counter

from .base import StageContext


class AssistantPostprocessStage:
    name = "assistant_postprocess"

    def run(self, context: StageContext) -> None:
        started = perf_counter()
        mode = str(context.state["policy"].assistant_mode)
        context.diagnostics.assistant_used = mode != "off"
        context.diagnostics.push_trace(
            self.name,
            started,
            outcome="stub" if mode != "off" else "skipped",
        )
