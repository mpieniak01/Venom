import asyncio

from venom_core.core.model_registry_clients import OllamaClient
from venom_core.core.ollama_runtime_probe import (
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
