"""Normalizacja runtime capabilities dla modeli Ollama."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

_LEGACY_TEXT_ONLY = "legacy_text_only"
_TEXT_THINKING = "text_thinking"
_TEXT_TOOLS = "text_tools"
_VISION_TEXT = "vision_text"
_MULTIMODAL_AUDIO = "multimodal_audio"


@dataclass(slots=True)
class OllamaRuntimeCapabilities:
    """Znormalizowany snapshot capabilities modelu Ollama."""

    runtime_id: str
    endpoint: str
    model_name: str
    probe_status: str
    ollama_version: str | None = None
    metadata_source: str = "api_show"
    compatibility_profile: str = _LEGACY_TEXT_ONLY
    context_length: int | None = None
    parameter_size: str | None = None
    quantization: str | None = None
    capabilities: dict[str, bool] = field(default_factory=dict)
    raw_capabilities: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
    model_info: dict[str, Any] = field(default_factory=dict)
    probes: dict[str, dict[str, Any]] = field(default_factory=dict)
    fallbacks: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_id": self.runtime_id,
            "endpoint": self.endpoint,
            "model_name": self.model_name,
            "probe_status": self.probe_status,
            "ollama_version": self.ollama_version,
            "metadata_source": self.metadata_source,
            "compatibility_profile": self.compatibility_profile,
            "context_length": self.context_length,
            "parameter_size": self.parameter_size,
            "quantization": self.quantization,
            "capabilities": self.capabilities,
            "raw_capabilities": self.raw_capabilities,
            "details": self.details,
            "model_info": self.model_info,
            "probes": self.probes,
            "fallbacks": self.fallbacks,
        }


def _resolve_compatibility_profile(capabilities: set[str]) -> str:
    if "audio" in capabilities:
        return _MULTIMODAL_AUDIO
    if "vision" in capabilities:
        return _VISION_TEXT
    if "tools" in capabilities:
        return _TEXT_TOOLS
    if "thinking" in capabilities:
        return _TEXT_THINKING
    return _LEGACY_TEXT_ONLY


def normalize_ollama_show_payload(
    *,
    model_name: str,
    payload: dict[str, Any] | None,
    endpoint: str,
    ollama_version: str | None = None,
    probe_status: str = "metadata_only",
) -> OllamaRuntimeCapabilities:
    """Mapuje odpowiedź /api/show na kontrakt runtime Venom."""

    payload = payload or {}
    raw_capabilities = payload.get("capabilities") or []
    capability_set = {str(cap).strip().lower() for cap in raw_capabilities if cap}
    details = payload.get("details") or {}
    model_info = payload.get("model_info") or {}

    context_length = (
        _as_int(
            model_info.get("general.context_length")
            or model_info.get("gemma4.context_length")
            or details.get("context_length")
        )
        if isinstance(model_info, dict)
        else _as_int(details.get("context_length"))
    )

    parameter_size = details.get("parameter_size") or details.get("size")
    quantization = details.get("quantization_level") or details.get("quantization")

    capabilities = {
        "text_completion": True,
        "vision_input": "vision" in capability_set,
        "audio_input": "audio" in capability_set,
        "tool_calling": "tools" in capability_set,
        "thinking": "thinking" in capability_set,
        "structured_output": False,
        "audio_transcription": "verified" if "audio" in capability_set else "fallback",
        "audio_reasoning": "verified" if "audio" in capability_set else "fallback",
    }

    fallbacks = {
        "stt": "faster_whisper",
        "tts": "piper",
        "vision": "disabled_if_probe_failed",
        "tools": "policy_gate_required",
    }

    return OllamaRuntimeCapabilities(
        runtime_id="ollama",
        endpoint=endpoint.rstrip("/"),
        model_name=model_name,
        probe_status=probe_status,
        ollama_version=ollama_version,
        compatibility_profile=_resolve_compatibility_profile(capability_set),
        context_length=context_length,
        parameter_size=parameter_size,
        quantization=quantization,
        capabilities=capabilities,
        raw_capabilities=sorted(capability_set),
        details=details,
        model_info=model_info,
        fallbacks=fallbacks,
    )


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


__all__ = [
    "OllamaRuntimeCapabilities",
    "normalize_ollama_show_payload",
]
