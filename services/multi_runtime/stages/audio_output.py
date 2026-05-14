"""Audio output stage placeholder."""

from __future__ import annotations

from time import perf_counter

from .base import StageContext


class AudioOutputStage:
    name = "audio_output"

    def run(self, context: StageContext) -> None:
        started = perf_counter()
        mode = str(context.state["policy"].audio_output_mode)
        context.state["audio_output_mode"] = mode
        context.diagnostics.push_trace(
            self.name,
            started,
            outcome="stub" if mode != "off" else "skipped",
        )
