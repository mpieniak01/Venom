"""Readiness of a private vLLM endpoint, distinct from a measured benchmark."""

import httpx

from venom_core.infrastructure.providers.vast.client import VastError
from venom_core.infrastructure.providers.vast.models import WorkloadProfile


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
