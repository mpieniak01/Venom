"""Retrieval hook stage for multi_runtime pipeline."""

from __future__ import annotations

from time import perf_counter

from .base import StageContext


class RetrievalStage:
    name = "retrieval"

    def run(self, context: StageContext) -> None:
        started = perf_counter()
        mode = str(context.state["policy"].retrieval_mode)

        if mode == "off":
            context.state["retrieval_context"] = ""
            context.diagnostics.retrieval_used = False
            context.diagnostics.push_trace(self.name, started, outcome="skipped")
            return

        text = str(context.text_content or "").strip()
        should_use = mode == "always" or (mode == "auto" and bool(text))
        if not should_use:
            context.state["retrieval_context"] = ""
            context.diagnostics.retrieval_used = False
            context.diagnostics.push_trace(self.name, started, outcome="skipped")
            return

        context.state["retrieval_context"] = ""
        context.diagnostics.retrieval_used = True
        context.diagnostics.push_trace(self.name, started, outcome="stub")
