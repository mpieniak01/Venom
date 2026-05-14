"""Input router stage for multimodal routing decisions."""

from __future__ import annotations

from time import perf_counter

from ..router import route_inputs
from .base import StageContext


class InputRouterStage:
    name = "input_router"

    def run(self, context: StageContext) -> None:
        started = perf_counter()
        route = route_inputs(
            text_content=context.text_content,
            has_audio=context.audio_array is not None,
            image_count=len(context.images),
            image_strategy=context.state["policy"].image_strategy,
        )
        context.state["route"] = route
        context.diagnostics.selected_image_strategy = route.image_strategy
        context.diagnostics.push_trace(self.name, started)
