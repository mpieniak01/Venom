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

    if capabilities.capabilities.get("thinking"):
        try:
            probes["thinking"] = await _probe_thinking(client, model_name)
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.warning("Thinking probe failed for %s: %s", model_name, exc)
            probes["thinking"] = {"status": "failed", "reason": str(exc)}
    else:
        probes["thinking"] = {"status": "metadata_only", "reason": "capability_missing"}

    if capabilities.capabilities.get("tool_calling"):
        try:
            probes["tools"] = await _probe_tools(client, model_name)
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.warning("Tool probe failed for %s: %s", model_name, exc)
            probes["tools"] = {"status": "failed", "reason": str(exc)}
    else:
        probes["tools"] = {"status": "metadata_only", "reason": "capability_missing"}

    if capabilities.capabilities.get("vision_input"):
        try:
            probes["vision"] = await _probe_vision(client, model_name)
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.warning("Vision probe failed for %s: %s", model_name, exc)
            probes["vision"] = {"status": "failed", "reason": str(exc)}
    else:
        probes["vision"] = {"status": "metadata_only", "reason": "capability_missing"}

    if capabilities.capabilities.get("audio_input"):
        try:
            probes["audio"] = await _probe_audio(client, model_name)
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.warning("Audio probe failed for %s: %s", model_name, exc)
            probes["audio"] = {"status": "failed", "reason": str(exc)}
    else:
        probes["audio"] = {"status": "metadata_only", "reason": "capability_missing"}

    capabilities.probes = probes
    capabilities.probe_status = "verified"
    return capabilities


__all__ = [
    "VoicePipelineDecision",
    "probe_ollama_runtime_capabilities",
    "resolve_voice_pipeline",
]
