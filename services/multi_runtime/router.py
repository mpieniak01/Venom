"""Input routing for multi_runtime pipeline."""

from __future__ import annotations

from dataclasses import dataclass

from .policies import ImageStrategy


@dataclass(slots=True)
class InputRoute:
    has_text: bool
    has_audio: bool
    has_images: bool
    primary_modality: str
    image_strategy: ImageStrategy


def route_inputs(
    *,
    text_content: str | None,
    has_audio: bool,
    image_count: int,
    image_strategy: ImageStrategy,
) -> InputRoute:
    has_text = bool((text_content or "").strip())
    has_images = image_count > 0

    if has_audio:
        primary_modality = "audio"
    elif has_images and has_text:
        primary_modality = "image_text"
    elif has_images:
        primary_modality = "image"
    else:
        primary_modality = "text"

    return InputRoute(
        has_text=has_text,
        has_audio=has_audio,
        has_images=has_images,
        primary_modality=primary_modality,
        image_strategy=image_strategy,
    )
