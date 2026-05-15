"""Component registry for multi_runtime runtime diagnostics."""

from __future__ import annotations

import importlib.util
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class RuntimeComponent:
    component_id: str
    component_type: str
    enabled: bool
    available: bool
    backend: str
    model_id: str | None
    device_target: str
    health: str
    last_error: str | None = None


def _component_health(enabled: bool, available: bool) -> str:
    if enabled and available:
        return "ok"
    if enabled and not available:
        return "degraded"
    return "disabled"


def _module_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def _resolve_tts_status() -> tuple[bool, str, str | None]:
    configured_path = str(os.getenv("TTS_MODEL_PATH", "")).strip()
    if configured_path:
        path = Path(configured_path)
        if path.exists():
            return True, "piper", None
        return False, "piper", f"TTS model path missing: {path}"

    default_dir = Path("data/models/piper")
    if default_dir.exists() and any(default_dir.glob("*.onnx")):
        return True, "piper", None
    return False, "piper", "No Piper voice model detected"


def _resolve_embedding_status() -> tuple[bool, str, str | None]:
    if _module_available("sentence_transformers"):
        return True, "sentence_transformers", None
    return (
        True,
        "fallback",
        "sentence-transformers unavailable; deterministic fallback active",
    )


def _resolve_retrieval_status() -> tuple[bool, str, str | None]:
    if not _module_available("lancedb"):
        return False, "lancedb", "lancedb package unavailable"

    memory_root = Path("data/memory")
    if not memory_root.exists():
        return False, "lancedb", "data/memory directory not found"

    return True, "lancedb", None


def _resolve_ocr_status() -> tuple[bool, str, str | None]:
    if _module_available("pytesseract"):
        return True, "pytesseract", None
    return False, "pytesseract", "pytesseract package unavailable"


def build_component_snapshot(
    daemon_status: dict[str, Any],
    *,
    request_overrides: dict[str, Any] | None = None,
) -> list[dict[str, object]]:
    vram_backend = str(daemon_status.get("vram", {}).get("backend", "cpu"))
    target_loaded = bool(daemon_status.get("target_loaded", False))
    assistant_loaded = bool(daemon_status.get("assistant_loaded", False))
    supports_image_input = bool(daemon_status.get("supports_image_input", True))
    params = daemon_status.get("params", {})
    overrides = request_overrides or {}
    precision = str(params.get("precision", "auto")).strip().lower()
    quantization_backend = str(params.get("quantization_backend", "")).strip().lower()
    retrieval_mode = str(
        overrides.get("retrieval_mode", params.get("retrieval_mode", "off"))
    )
    audio_output_mode = str(
        overrides.get("audio_output_mode", params.get("audio_output_mode", "off"))
    )
    assistant_mode = str(
        overrides.get("assistant_mode", params.get("assistant_mode", "off"))
    )
    image_strategy = str(
        overrides.get("image_strategy", params.get("image_strategy", "vlm_only"))
    )

    tts_available, tts_backend, tts_error = _resolve_tts_status()
    embedding_available, embedding_backend, embedding_error = (
        _resolve_embedding_status()
    )
    retrieval_available, retrieval_backend, retrieval_error = (
        _resolve_retrieval_status()
    )
    ocr_available, ocr_backend, ocr_error = _resolve_ocr_status()
    assistant_enabled = assistant_mode != "off" and bool(
        daemon_status.get("assistant_model")
    )
    image_last_error = (
        "OCR-first strategy requested but OCR backend unavailable"
        if image_strategy in {"ocr_first", "hybrid"} and not ocr_available
        else None
    )

    components = [
        RuntimeComponent(
            component_id="main_model",
            component_type="model",
            enabled=True,
            available=target_loaded,
            backend=(
                "bitsandbytes"
                if quantization_backend == "bitsandbytes"
                and precision in {"int4", "int8"}
                else vram_backend
            ),
            model_id=daemon_status.get("target_model"),
            device_target=vram_backend,
            health=_component_health(True, target_loaded),
        ),
        RuntimeComponent(
            component_id="assistant_model",
            component_type="model",
            enabled=assistant_enabled,
            available=assistant_loaded,
            backend=vram_backend,
            model_id=daemon_status.get("assistant_model"),
            device_target=vram_backend,
            health=_component_health(assistant_enabled, assistant_loaded),
            last_error=(
                "Assistant policy requires an attached model"
                if assistant_mode != "off" and not daemon_status.get("assistant_model")
                else None
            ),
        ),
        RuntimeComponent(
            component_id="image_input",
            component_type="vision",
            enabled=True,
            available=supports_image_input,
            backend="builtin",
            model_id=None,
            device_target="cpu",
            health=_component_health(True, supports_image_input),
            last_error=image_last_error,
        ),
        RuntimeComponent(
            component_id="ocr_component",
            component_type="vision",
            enabled=image_strategy in {"ocr_first", "hybrid"},
            available=ocr_available,
            backend=ocr_backend,
            model_id=None,
            device_target="cpu",
            health=_component_health(
                image_strategy in {"ocr_first", "hybrid"}, ocr_available
            ),
            last_error=ocr_error if image_strategy in {"ocr_first", "hybrid"} else None,
        ),
        RuntimeComponent(
            component_id="stt_component",
            component_type="audio",
            enabled=True,
            available=target_loaded,
            backend="builtin",
            model_id=None,
            device_target="cpu",
            health=_component_health(True, target_loaded),
        ),
        RuntimeComponent(
            component_id="tts_component",
            component_type="audio",
            enabled=audio_output_mode == "voice_first",
            available=tts_available,
            backend=tts_backend,
            model_id=None,
            device_target="cpu",
            health=_component_health(audio_output_mode == "voice_first", tts_available),
            last_error=tts_error,
        ),
        RuntimeComponent(
            component_id="embedding_component",
            component_type="retrieval",
            enabled=retrieval_mode != "off",
            available=embedding_available,
            backend=embedding_backend,
            model_id=None,
            device_target="cpu",
            health=_component_health(retrieval_mode != "off", embedding_available),
            last_error=embedding_error,
        ),
        RuntimeComponent(
            component_id="retrieval_component",
            component_type="retrieval",
            enabled=retrieval_mode != "off",
            available=retrieval_available,
            backend=retrieval_backend,
            model_id=None,
            device_target="cpu",
            health=_component_health(retrieval_mode != "off", retrieval_available),
            last_error=retrieval_error,
        ),
    ]
    return [asdict(component) for component in components]
