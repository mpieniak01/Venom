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
        if mode == "off":
            context.diagnostics.push_trace(self.name, started, outcome="skipped")
            return

        components = context.diagnostics.component_snapshot
        tts_component = next(
            (
                item
                for item in components
                if str(item.get("component_id", "")) == "tts_component"
            ),
            None,
        )
        tts_available = bool(tts_component and tts_component.get("available"))
        if not tts_available:
            context.diagnostics.add_degradation(
                "audio output requested but TTS backend unavailable"
            )
            context.diagnostics.push_trace(self.name, started, outcome="degraded")
            return

        context.diagnostics.push_trace(
            self.name,
            started,
            outcome="stub",
        )
