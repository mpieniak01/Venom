"""Assistant postprocess stage placeholder."""

from __future__ import annotations

from time import perf_counter
from typing import Any

from .base import StageContext


class AssistantPostprocessStage:
    name = "assistant_postprocess"

    def __init__(self, daemon: Any | None = None):
        self._daemon = daemon

    def run(self, context: StageContext) -> None:
        started = perf_counter()
        mode = str(context.state["policy"].assistant_mode)
        if mode == "off":
            context.diagnostics.assistant_used = False
            context.diagnostics.push_trace(self.name, started, outcome="skipped")
            return

        assistant_model = context.daemon_status.get("assistant_model")
        assistant_loaded = bool(context.daemon_status.get("assistant_loaded"))
        if not assistant_model or not assistant_loaded or self._daemon is None:
            context.diagnostics.assistant_used = False
            context.diagnostics.add_degradation(
                "assistant policy active but assistant model unavailable"
            )
            context.diagnostics.push_trace(self.name, started, outcome="degraded")
            return

        if (
            mode == "conditional"
            and not context.diagnostics.retrieval_used
            and not bool(context.images)
        ):
            context.diagnostics.assistant_used = False
            context.diagnostics.push_trace(self.name, started, outcome="skipped")
            return

        if context.state["policy"].economy_mode == "auto" and mode == "conditional":
            context.diagnostics.assistant_used = False
            context.diagnostics.economy_mode_activated = True
            context.diagnostics.add_degradation(
                "economy_mode skipped conditional assistant postprocess"
            )
            context.diagnostics.push_trace(self.name, started, outcome="degraded")
            return

        generated_text = str(context.state.get("generated_text", "")).strip()
        if not generated_text:
            context.diagnostics.assistant_used = False
            context.diagnostics.push_trace(self.name, started, outcome="skipped")
            return

        try:
            revised_text, _duration = self._daemon.respond_with_assistant(
                prompt=generated_text,
                system_prompt=(
                    "Review the draft answer. Return the same answer if it is already "
                    "clear and concise. Otherwise return a minimally improved version."
                ),
                max_new_tokens=min(192, max(64, len(generated_text.split()) * 8)),
            )
        except Exception as exc:
            context.diagnostics.assistant_used = False
            context.diagnostics.add_degradation(
                f"assistant postprocess failed: {type(exc).__name__}"
            )
            context.diagnostics.push_trace(self.name, started, outcome="fallback")
            return

        revised_text = str(revised_text or "").strip()
        if revised_text:
            context.state["generated_text"] = revised_text
        context.diagnostics.assistant_used = True
        context.diagnostics.push_trace(self.name, started, outcome="ok")
