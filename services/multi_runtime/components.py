"""Component registry for multi_runtime runtime diagnostics."""

from __future__ import annotations

from dataclasses import asdict, dataclass
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


def build_component_snapshot(daemon_status: dict[str, Any]) -> list[dict[str, object]]:
    vram_backend = str(daemon_status.get("vram", {}).get("backend", "cpu"))
    target_loaded = bool(daemon_status.get("target_loaded", False))
    assistant_loaded = bool(daemon_status.get("assistant_loaded", False))
    supports_image_input = bool(daemon_status.get("supports_image_input", True))

    components = [
        RuntimeComponent(
            component_id="main_model",
            component_type="model",
            enabled=True,
            available=target_loaded,
            backend=vram_backend,
            model_id=daemon_status.get("target_model"),
            device_target=vram_backend,
            health=_component_health(True, target_loaded),
        ),
        RuntimeComponent(
            component_id="assistant_model",
            component_type="model",
            enabled=bool(daemon_status.get("assistant_model")),
            available=assistant_loaded,
            backend=vram_backend,
            model_id=daemon_status.get("assistant_model"),
            device_target=vram_backend,
            health=_component_health(
                bool(daemon_status.get("assistant_model")), assistant_loaded
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
            enabled=False,
            available=False,
            backend="stub",
            model_id=None,
            device_target="cpu",
            health="disabled",
        ),
        RuntimeComponent(
            component_id="embedding_component",
            component_type="retrieval",
            enabled=False,
            available=False,
            backend="stub",
            model_id=None,
            device_target="cpu",
            health="disabled",
        ),
        RuntimeComponent(
            component_id="retrieval_component",
            component_type="retrieval",
            enabled=False,
            available=False,
            backend="stub",
            model_id=None,
            device_target="cpu",
            health="disabled",
        ),
    ]
    return [asdict(component) for component in components]
