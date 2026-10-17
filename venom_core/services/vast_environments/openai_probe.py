"""Readiness of a private vLLM endpoint, distinct from a measured benchmark."""

import json
import time

import httpx

from venom_core.infrastructure.providers.vast.client import VastError
from venom_core.infrastructure.providers.vast.models import WorkloadProfile
from venom_core.services.vast_environments.evaluation import OllamaProbe, StreamCapture


def ready(client: httpx.Client, profile: WorkloadProfile) -> dict:
    models = client.get("/v1/models")
    models.raise_for_status()
    data = models.json().get("data", [])
    if not any(row.get("id") == profile.model for row in data):
        raise VastError("vast.model_missing")
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": profile.model,
            "messages": [{"role": "user", "content": "Reply with OK."}],
            "max_tokens": 8,
            "temperature": 0,
            "stream": False,
        },
    )
    response.raise_for_status()
    choices = response.json().get("choices") or []
    if not choices or not choices[0].get("message", {}).get("content"):
        raise VastError("vast.model_not_ready")
    return {
        "runtime": "ready",
        "engine": "vllm",
        "model": profile.model,
        "configured_revision": profile.model_digest,
        "revision_verification": "startup_pinned; endpoint_does_not_attest_weights",
    }


def openai_payload(body: dict) -> dict:
    messages = []
    for row in body["messages"]:
        content = row["content"]
        if row.get("images"):
            content = [{"type": "text", "text": content}] + [
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64," + image},
                }
                for image in row["images"]
            ]
        messages.append({"role": row["role"], "content": content})
    options = body["options"]
    result = {
        "model": body["model"],
        "messages": messages,
        "stream": True,
        "stream_options": {"include_usage": True},
        "max_tokens": options["num_predict"],
        "temperature": options["temperature"],
        "seed": options["seed"],
    }
    if body.get("format") == "json":
        result["response_format"] = {"type": "json_object"}
    if body.get("tools"):
        result["tools"] = body["tools"]
    return result


class OpenAIProbe(OllamaProbe):
    """Same synthetic cases and metrics; SSE adapter for the vLLM wire format."""

    def metadata(self) -> dict:
        response = self.client.get("/v1/models")
        response.raise_for_status()
        if not any(
            row.get("id") == self.profile.model
            for row in response.json().get("data", [])
        ):
            raise VastError("vast.model_missing")
        return {
            "engine": "vllm",
            "model": self.profile.model,
            "configured_revision": self.profile.model_digest,
            "revision_verification": "startup_pinned; endpoint_does_not_attest_weights",
        }

    def capture(self, body: dict, started: float) -> StreamCapture:
        capture = StreamCapture(started)
        finished = False
        calls: dict[int, dict] = {}
        with self.client.stream(
            "POST", "/v1/chat/completions", json=openai_payload(body)
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                capture.size += len(line)
                if capture.size > 2_000_000 or time.monotonic() - started > 60:
                    raise VastError("vast.sample_limit")
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    if finished:
                        capture.last["done"] = True
                    break
                item = json.loads(data)
                if item.get("error"):
                    raise VastError("vast.backend_error")
                for choice in item.get("choices", []):
                    delta = choice.get("delta") or {}
                    text = delta.get("content") or ""
                    if text and capture.first is None:
                        capture.first = time.monotonic() - started
                    capture.text += text
                    for call in delta.get("tool_calls", []):
                        target = calls.setdefault(
                            call["index"], {"function": {"name": ""}}
                        )
                        target["function"]["name"] += (
                            call.get("function", {}).get("name") or ""
                        )
                    finished = finished or choice.get("finish_reason") is not None
                usage = item.get("usage") or {}
                if usage:
                    capture.last.update(
                        prompt_eval_count=usage.get("prompt_tokens"),
                        eval_count=usage.get("completion_tokens"),
                    )
        capture.tool_calls = list(calls.values())
        if not capture.last.get("done"):
            capture.last = {}
        return capture
