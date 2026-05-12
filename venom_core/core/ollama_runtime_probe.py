"""Aktywne proby i routing capability dla runtime Ollama."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from venom_core.core.model_registry_clients import OllamaClient
from venom_core.core.ollama_runtime_capabilities import (
    OllamaRuntimeCapabilities,
    normalize_ollama_show_payload,
)
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

_TINY_PNG_BASE64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO2r2foAAAAASUVORK5CYII="


@dataclass(slots=True)
class VoicePipelineDecision:
    """Znormalizowany wybór pipeline voice dla aktywnego runtime."""

    profile: str
    stt: str
    reasoning: str
    tools: str
    vision: str
    tts: str
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "stt": self.stt,
            "reasoning": self.reasoning,
            "tools": self.tools,
            "vision": self.vision,
            "tts": self.tts,
            "notes": self.notes,
        }


def resolve_voice_pipeline(
    capabilities: OllamaRuntimeCapabilities,
) -> VoicePipelineDecision:
    """Wybiera pipeline zgodnie z capability snapshotem."""

    caps = capabilities.capabilities
    probes = capabilities.probes
    notes: list[str] = []

    if caps.get("audio_input") and probes.get("audio", {}).get("status") == "verified":
        stt = "native_audio"
    else:
        stt = "faster_whisper"
        if caps.get("audio_input"):
            notes.append("audio capability metadata only, using whisper fallback")

    reasoning = (
        "think_api"
        if probes.get("thinking", {}).get("status") == "verified"
        else "prompt_fallback"
    )
    if reasoning != "think_api" and caps.get("thinking"):
        notes.append("thinking capability metadata only or probe failed")

    tools = (
        "policy_gated_tools"
        if probes.get("tools", {}).get("status") == "verified"
        else "disabled"
    )
    vision = (
        "images_api"
        if probes.get("vision", {}).get("status") == "verified"
        else "disabled"
    )
    if caps.get("vision_input") and vision == "disabled":
        notes.append("vision capability metadata only or probe failed")

    tts = "piper"
    return VoicePipelineDecision(
        profile=capabilities.compatibility_profile,
        stt=stt,
        reasoning=reasoning,
        tools=tools,
        vision=vision,
        tts=tts,
        notes=notes,
    )


def _aggregate_probe_status(probes: dict[str, dict[str, Any]]) -> str:
    """Scala status probe z poziomu pojedynczych wyników."""

    show_status = probes.get("show", {}).get("status")
    if show_status == "failed":
        return "failed"

    probe_statuses = [
        probe.get("status")
        for probe_name, probe in probes.items()
        if probe_name != "show"
    ]
    if any(status == "metadata_only" for status in probe_statuses):
        return "metadata_only"
    if show_status == "verified":
        return "verified"
    return show_status or "metadata_only"


async def _record_optional_probe(
    probes: dict[str, dict[str, Any]],
    *,
    capability_enabled: bool,
    probe_name: str,
    capability_missing_reason: str,
    probe_fn,
    client: OllamaClient,
    model_name: str,
) -> None:
    if not capability_enabled:
        probes[probe_name] = {
            "status": "metadata_only",
            "reason": capability_missing_reason,
        }
        return

    try:
        probes[probe_name] = await probe_fn(client, model_name)
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.warning(
            "%s probe failed for %s: %s", probe_name.title(), model_name, exc
        )
        probes[probe_name] = {"status": "failed", "reason": str(exc)}


async def _probe_thinking(client: OllamaClient, model_name: str) -> dict[str, Any]:
    response = await client.chat(
        {
            "model": model_name,
            "messages": [{"role": "user", "content": "How many r are in strawberry?"}],
            "think": True,
            "stream": False,
        }
    )
    message = response.get("message") or {}
    thinking = str(message.get("thinking") or "").strip()
    content = str(message.get("content") or "").strip()
    if thinking or content:
        return {
            "status": "verified",
            "thinking": bool(thinking),
            "content": content[:200],
        }
    return {"status": "failed", "reason": "empty_response"}


async def _probe_tools(client: OllamaClient, model_name: str) -> dict[str, Any]:
    response = await client.chat(
        {
            "model": model_name,
            "messages": [
                {
                    "role": "user",
                    "content": "Return the temperature for Paris using tools.",
                }
            ],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "noop_status",
                        "description": "Return a stable status string.",
                        "parameters": {
                            "type": "object",
                            "properties": {},
                            "additionalProperties": False,
                        },
                    },
                }
            ],
            "stream": False,
        }
    )
    message = response.get("message") or {}
    tool_calls = message.get("tool_calls") or []
    if tool_calls:
        return {
            "status": "verified",
            "tool_calls": len(tool_calls),
        }
    content = str(message.get("content") or "").strip()
    if content:
        return {
            "status": "metadata_only",
            "reason": "no_tool_call_returned",
            "content": content[:200],
        }
    return {"status": "failed", "reason": "empty_response"}


async def _probe_vision(client: OllamaClient, model_name: str) -> dict[str, Any]:
    response = await client.chat(
        {
            "model": model_name,
            "messages": [
                {
                    "role": "user",
                    "content": "Describe this image in one short sentence.",
                    "images": [_TINY_PNG_BASE64],
                }
            ],
            "stream": False,
        }
    )
    message = response.get("message") or {}
    content = str(message.get("content") or "").strip()
    if content:
        return {"status": "verified", "content": content[:200]}
    return {"status": "failed", "reason": "empty_response"}


async def _probe_audio(client: OllamaClient, model_name: str) -> dict[str, Any]:
    # Ollama docs nie opisują jeszcze stabilnego REST request shape dla audio input.
    # Traktujemy capability jako metadata-only dopóki nie potwierdzimy formatu aktywną próbą.
    response = await client.chat(
        {
            "model": model_name,
            "messages": [
                {
                    "role": "user",
                    "content": "Confirm whether audio input is available for this model.",
                }
            ],
            "stream": False,
        }
    )
    message = response.get("message") or {}
    content = str(message.get("content") or "").strip()
    if content:
        return {
            "status": "metadata_only",
            "reason": "ollama_audio_api_not_verified",
            "content": content[:200],
        }
    return {"status": "failed", "reason": "empty_response"}


async def probe_ollama_runtime_capabilities(
    *,
    client: OllamaClient,
    model_name: str,
    endpoint: str,
    ollama_version: str | None = None,
) -> OllamaRuntimeCapabilities:
    """Łączy /api/show z aktywnymi probe capability."""

    show_payload = await client.get_model_show(model_name)
    capabilities = normalize_ollama_show_payload(
        model_name=model_name,
        payload=show_payload,
        endpoint=endpoint,
        ollama_version=ollama_version,
        probe_status="metadata_only",
    )

    if not show_payload:
        capabilities.probe_status = "failed"
        capabilities.probes = {"show": {"status": "failed", "reason": "empty_response"}}
        return capabilities

    probes: dict[str, dict[str, Any]] = {"show": {"status": "verified"}}

    await _record_optional_probe(
        probes,
        capability_enabled=bool(capabilities.capabilities.get("thinking")),
        probe_name="thinking",
        capability_missing_reason="capability_missing",
        probe_fn=_probe_thinking,
        client=client,
        model_name=model_name,
    )
    await _record_optional_probe(
        probes,
        capability_enabled=bool(capabilities.capabilities.get("tool_calling")),
        probe_name="tools",
        capability_missing_reason="capability_missing",
        probe_fn=_probe_tools,
        client=client,
        model_name=model_name,
    )
    await _record_optional_probe(
        probes,
        capability_enabled=bool(capabilities.capabilities.get("vision_input")),
        probe_name="vision",
        capability_missing_reason="capability_missing",
        probe_fn=_probe_vision,
        client=client,
        model_name=model_name,
    )
    await _record_optional_probe(
        probes,
        capability_enabled=bool(capabilities.capabilities.get("audio_input")),
        probe_name="audio",
        capability_missing_reason="capability_missing",
        probe_fn=_probe_audio,
        client=client,
        model_name=model_name,
    )

    capabilities.probes = probes
    capabilities.probe_status = _aggregate_probe_status(probes)
    return capabilities


__all__ = [
    "VoicePipelineDecision",
    "probe_ollama_runtime_capabilities",
    "resolve_voice_pipeline",
]
