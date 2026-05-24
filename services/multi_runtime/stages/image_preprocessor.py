"""Image preprocessing stage for multimodal pipeline."""

from __future__ import annotations

from time import perf_counter

from PIL import Image, ImageOps

from services.multi_runtime.runtime_config import read_config_int

from .base import StageContext

_MAX_DIM_DEFAULT = 1024


def _max_image_dim() -> int:
    return read_config_int("MULTI_RUNTIME_IMAGE_MAX_DIM", _MAX_DIM_DEFAULT)


def _normalize_image(img: Image.Image, max_dim: int) -> tuple[Image.Image, str]:
    """Return (normalized_image, summary) applying EXIF rotation, RGB conversion, resize."""
    original_size = img.size

    # Apply EXIF orientation before any other transform
    img = ImageOps.exif_transpose(img)

    # Convert to RGB — drops alpha, palette, grayscale
    if img.mode != "RGB":
        img = img.convert("RGB")

    # Resize to fit max_dim on the longest edge (preserve aspect ratio)
    w, h = img.size
    if max(w, h) > max_dim:
        scale = max_dim / max(w, h)
        new_w = max(1, int(w * scale))
        new_h = max(1, int(h * scale))
        img = img.resize((new_w, new_h), Image.LANCZOS)

    summary = f"{original_size[0]}x{original_size[1]}->{img.size[0]}x{img.size[1]}"
    return img, summary


class ImagePreprocessorStage:
    name = "image_preprocessor"

    def run(self, context: StageContext) -> None:
        started = perf_counter()
        if not context.images:
            context.state["preprocessed_images"] = []
            context.diagnostics.push_trace(self.name, started, outcome="skipped")
            return

        max_dim = _max_image_dim()
        processed: list[Image.Image] = []
        summaries: list[str] = []

        for img in context.images:
            try:
                normalized, summary = _normalize_image(img, max_dim)
                processed.append(normalized)
                summaries.append(summary)
            except Exception as exc:
                context.diagnostics.add_degradation(
                    f"image_preprocessor: {type(exc).__name__}: {exc}"
                )

        context.state["preprocessed_images"] = processed
        context.state["image_preprocessing_summaries"] = summaries
        outcome = "ok" if processed else "degraded"
        context.diagnostics.push_trace(self.name, started, outcome=outcome)
