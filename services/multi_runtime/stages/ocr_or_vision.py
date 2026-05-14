"""Select OCR or direct vision path based on policy and availability."""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass, field
from time import perf_counter

from PIL import Image

from .base import StageContext


@dataclass(slots=True)
class OCRToken:
    text: str
    confidence: float | None = None
    bbox: tuple[int, int, int, int] | None = None
    page: int | None = None
    block: int | None = None
    par: int | None = None
    line: int | None = None
    word: int | None = None


@dataclass(slots=True)
class OCRResult:
    backend: str
    available: bool
    execution_path: str
    text: str
    lines: list[str] = field(default_factory=list)
    tokens: list[OCRToken] = field(default_factory=list)
    error: str | None = None

    def prompt_block(self, limit: int = 12) -> str:
        if not (self.lines or self.text or self.tokens or self.error):
            return ""
        parts: list[str] = [
            f"[ocr_context backend={self.backend} path={self.execution_path} available={self.available}]"
        ]
        if self.lines:
            for index, line in enumerate(self.lines[:limit], start=1):
                parts.append(f"{index}. {line}")
        elif self.text:
            parts.append(self.text[:2000])
        token_preview = ", ".join(
            token.text for token in self.tokens[:24] if token.text.strip()
        )
        if token_preview:
            parts.append(f"[tokens] {token_preview}")
        if self.error:
            parts.append(f"[ocr_error] {self.error}")
        return "\n".join(parts).strip()


class OcrOrVisionStage:
    name = "ocr_or_vision"

    @staticmethod
    def _ocr_available() -> bool:
        return importlib.util.find_spec("pytesseract") is not None

    @staticmethod
    def _extract_ocr_result(
        images: list[Image.Image], execution_path: str
    ) -> OCRResult:
        import pytesseract  # type: ignore[import-not-found]

        chunks: list[str] = []
        lines: list[str] = []
        tokens: list[OCRToken] = []

        def _normalize_confidence(value: object) -> float | None:
            try:
                conf = float(value)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                return None
            return conf if conf >= 0 else None

        for image in images:
            text = str(pytesseract.image_to_string(image) or "").strip()
            if text:
                chunks.append(text)
            try:
                data = pytesseract.image_to_data(
                    image, output_type=pytesseract.Output.DICT
                )
            except Exception:
                data = None
            if not data:
                if text:
                    lines.extend(line for line in text.splitlines() if line.strip())
                continue

            group_order: list[tuple[int, int, int, int]] = []
            group_tokens: dict[tuple[int, int, int, int], list[OCRToken]] = {}
            page_numbers = data.get("page_num", [])
            block_numbers = data.get("block_num", [])
            par_numbers = data.get("par_num", [])
            line_numbers = data.get("line_num", [])
            word_numbers = data.get("word_num", [])
            left_values = data.get("left", [])
            top_values = data.get("top", [])
            width_values = data.get("width", [])
            height_values = data.get("height", [])
            confidence_values = data.get("conf", [])
            text_values = data.get("text", [])

            for index, raw_token in enumerate(text_values):
                token_text = str(raw_token or "").strip()
                if not token_text:
                    continue
                group_key = (
                    int(page_numbers[index] or 0),
                    int(block_numbers[index] or 0),
                    int(par_numbers[index] or 0),
                    int(line_numbers[index] or 0),
                )
                token = OCRToken(
                    text=token_text,
                    confidence=_normalize_confidence(
                        confidence_values[index]
                        if index < len(confidence_values)
                        else None
                    ),
                    bbox=(
                        int(left_values[index] or 0),
                        int(top_values[index] or 0),
                        int(width_values[index] or 0),
                        int(height_values[index] or 0),
                    ),
                    page=int(page_numbers[index] or 0),
                    block=int(block_numbers[index] or 0),
                    par=int(par_numbers[index] or 0),
                    line=int(line_numbers[index] or 0),
                    word=int(word_numbers[index] or 0),
                )
                tokens.append(token)
                if group_key not in group_tokens:
                    group_order.append(group_key)
                    group_tokens[group_key] = []
                group_tokens[group_key].append(token)

            for group_key in group_order:
                grouped_tokens = group_tokens.get(group_key, [])
                line_text = " ".join(
                    token.text for token in grouped_tokens if token.text.strip()
                ).strip()
                if line_text:
                    lines.append(line_text)

        return OCRResult(
            backend="pytesseract",
            available=True,
            execution_path=execution_path,
            text="\n\n".join(chunk for chunk in chunks if chunk).strip(),
            lines=lines,
            tokens=tokens,
        )

    def run(self, context: StageContext) -> None:
        started = perf_counter()
        images = context.state.get("preprocessed_images", [])
        if not images:
            context.state["image_execution_path"] = "none"
            context.state["ocr_result"] = OCRResult(
                backend="pytesseract",
                available=False,
                execution_path="none",
                text="",
            )
            context.state["ocr_text"] = ""
            context.diagnostics.push_trace(self.name, started, outcome="skipped")
            return

        strategy = str(context.state["policy"].image_strategy)
        ocr_available = self._ocr_available()
        selected = strategy
        ocr_result = OCRResult(
            backend="pytesseract",
            available=ocr_available,
            execution_path=strategy,
            text="",
        )

        if strategy == "ocr_first" and not ocr_available:
            selected = "vlm_only"
            ocr_result.execution_path = selected
            context.diagnostics.add_degradation(
                "ocr_first requested but OCR backend unavailable; falling back to vlm_only"
            )
        elif strategy == "hybrid" and not ocr_available:
            selected = "vlm_only"
            ocr_result.execution_path = selected
            context.diagnostics.add_degradation(
                "hybrid requested but OCR backend unavailable; falling back to vlm_only"
            )
        elif context.state["policy"].economy_mode == "auto" and strategy == "hybrid":
            selected = "vlm_only"
            ocr_result.execution_path = selected
            context.diagnostics.economy_mode_activated = True
            context.diagnostics.add_degradation(
                "economy_mode simplified hybrid image path to vlm_only"
            )
        elif strategy in {"ocr_first", "hybrid"} and ocr_available:
            try:
                ocr_result = self._extract_ocr_result(images, execution_path=strategy)
            except Exception as exc:
                selected = "vlm_only" if strategy == "ocr_first" else selected
                ocr_result = OCRResult(
                    backend="pytesseract",
                    available=True,
                    execution_path=selected,
                    text="",
                    error=f"{type(exc).__name__}: {exc}",
                )
                context.diagnostics.add_degradation(
                    f"OCR extraction failed: {type(exc).__name__}"
                )
                if strategy == "ocr_first":
                    context.diagnostics.add_degradation(
                        "ocr_first fell back to vlm_only after OCR failure"
                    )

        context.state["image_execution_path"] = selected
        context.state["ocr_result"] = ocr_result
        context.state["ocr_text"] = ocr_result.text
        context.diagnostics.selected_image_strategy = selected
        outcome = "ok" if selected == strategy else "degraded"
        context.diagnostics.push_trace(self.name, started, outcome=outcome)
