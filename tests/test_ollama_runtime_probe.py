import asyncio

from venom_core.core.model_registry_clients import OllamaClient
from venom_core.core.ollama_runtime_probe import (
    _probe_audio,
    _probe_thinking,
    _probe_tools,
    _probe_vision,
    probe_ollama_runtime_capabilities,
    resolve_voice_pipeline,
)


class _DummyOllamaClient(OllamaClient):
    def __init__(self):
        self.endpoint = "http://localhost:11434"

    async def get_model_show(self, model_name: str):
        return {
            "capabilities": ["completion", "vision", "audio", "tools", "thinking"],
            "details": {"family": "gemma4", "parameter_size": "8.0B"},
            "model_info": {"gemma4.context_length": 131072},
        }

    async def chat(self, payload):
        if payload.get("think"):
            return {
                "message": {
                    "role": "assistant",
                    "thinking": "trace",
                    "content": "answer",
                }
            }
        if payload.get("tools"):
            return {
                "message": {
                    "role": "assistant",
                    "tool_calls": [
                        {"function": {"name": "noop_status", "arguments": {}}}
                    ],
                    "content": "",
                }
            }
        if payload.get("messages") and payload["messages"][-1].get("images"):
            return {"message": {"role": "assistant", "content": "image ok"}}
        return {"message": {"role": "assistant", "content": "ok"}}


class _NoopOllamaClient(OllamaClient):
    def __init__(self):
        self.endpoint = "http://localhost:11434"

    async def get_model_show(self, model_name: str):
        return {}

    async def chat(self, payload):
        return {"message": {"role": "assistant", "content": ""}}


def test_probe_ollama_runtime_capabilities_builds_snapshot():
    client = _DummyOllamaClient()
    caps = asyncio.run(
        probe_ollama_runtime_capabilities(
            client=client,
            model_name="gemma4:latest",
            endpoint=client.endpoint,
        )
    )

    assert caps.compatibility_profile == "multimodal_audio"
    assert caps.probes["thinking"]["status"] == "verified"
    assert caps.probes["tools"]["status"] == "verified"
    assert caps.probes["vision"]["status"] == "verified"
    assert caps.probes["audio"]["status"] == "metadata_only"
    assert caps.probe_status == "metadata_only"


def test_resolve_voice_pipeline_uses_whisper_fallback_for_audio_metadata_only():
    client = _DummyOllamaClient()
    caps = asyncio.run(
        probe_ollama_runtime_capabilities(
            client=client,
            model_name="gemma4:latest",
            endpoint=client.endpoint,
        )
    )

    decision = resolve_voice_pipeline(caps)

    assert decision.profile == "multimodal_audio"
    assert decision.stt == "faster_whisper"
    assert decision.reasoning == "think_api"
    assert decision.tools == "policy_gated_tools"
    assert decision.vision == "images_api"


def test_probe_ollama_runtime_capabilities_handles_empty_show_payload():
    client = _NoopOllamaClient()
    caps = asyncio.run(
        probe_ollama_runtime_capabilities(
            client=client,
            model_name="missing-model",
            endpoint=client.endpoint,
        )
    )

    assert caps.probe_status == "failed"
    assert caps.probes["show"]["status"] == "failed"


def test_probe_helpers_cover_metadata_only_and_failed_paths():
    client = _NoopOllamaClient()

    async def _run():
        thinking = await _probe_thinking(client, "model")
        tools = await _probe_tools(client, "model")
        vision = await _probe_vision(client, "model")
        audio = await _probe_audio(client, "model")
        return thinking, tools, vision, audio

    thinking, tools, vision, audio = asyncio.run(_run())

    assert thinking["status"] == "failed"
    assert tools["status"] == "failed"
    assert vision["status"] == "failed"
    assert audio["status"] == "failed"
