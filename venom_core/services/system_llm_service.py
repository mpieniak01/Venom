"""Domain helpers for system LLM runtime/profile logic."""

from __future__ import annotations

import importlib.util
import shutil
from typing import Any

import httpx

from venom_core.utils.llm_runtime import (
    build_onnx_worker_health_url,
    is_onnx_worker_health_ready,
    resolve_onnx_worker_endpoint,
)

_RUNTIME_PROVIDER_ALIASES = {
    "google-gemini": "google",
    "gem": "google",
}


def runtime_profile_name(profile_raw: str | None) -> str:
    profile = str(profile_raw or "full").strip().lower()
    if profile in {"light", "llm_off", "full"}:
        return profile
    return "full"


def allowed_local_servers(*, profile: str, onnx_enabled: bool) -> set[str]:
    if profile == "light":
        return {"ollama"}
    if profile == "llm_off":
        return set()
    allowed = {"ollama", "vllm", "multi_runtime"}
    if onnx_enabled:
        allowed.add("onnx")
    return allowed


def is_ollama_installed() -> bool:
    return shutil.which("ollama") is not None


def is_vllm_installed() -> bool:
    if shutil.which("vllm") is not None:
        return True
    return importlib.util.find_spec("vllm") is not None


def is_onnx_worker_configured(endpoint: str | None) -> bool:
    """Configured is distinct from installed/online; no native SDK in the app."""
    return build_onnx_worker_health_url(endpoint) is not None


async def inspect_onnx_worker(
    endpoint: str | None, *, api_key: str = "", timeout: float = 3.0
) -> dict[str, Any]:
    """Read actual CUDA health and served IDs without loading/downloading a model."""
    base = resolve_onnx_worker_endpoint(endpoint) or ""
    health_url = build_onnx_worker_health_url(base)
    result: dict[str, Any] = {
        "ready": False,
        "status": "offline",
        "endpoint": base or None,
        "health_url": health_url,
        "models": [],
        "error": "onnx_worker_endpoint_missing",
    }
    if health_url is None:
        return result
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
            health = await client.get(health_url)
            if not is_onnx_worker_health_ready(health):
                result.update(status="degraded", error="onnx_worker_health_invalid")
                return result
            response = await client.get(base + "/models")
            response.raise_for_status()
            payload = response.json()
        entries = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(entries, list) or not entries:
            raise ValueError("onnx_worker_models_invalid")
        models: list[str] = []
        for item in entries:
            model_id = item.get("id") if isinstance(item, dict) else None
            if (
                not isinstance(model_id, str)
                or not model_id.strip()
                or model_id != model_id.strip()
                or model_id in models
            ):
                raise ValueError("onnx_worker_models_invalid")
            models.append(model_id)
        result.update(
            ready=True,
            status="online",
            models=models,
            error=None,
            engine="onnx-gpu",
            device="cuda",
        )
    except httpx.HTTPError:
        result.update(status="offline", error="onnx_worker_request_failed")
    except ValueError:
        result.update(status="degraded", error="onnx_worker_models_invalid")
    return result


def installed_local_servers(
    *, ollama_installed: bool, vllm_installed: bool, onnx_installed: bool
) -> set[str]:
    installed: set[str] = set()
    if ollama_installed:
        installed.add("ollama")
    if vllm_installed:
        installed.add("vllm")
    if onnx_installed:
        installed.add("onnx")
    # multi_runtime (Gemma 4 multimodal) is always available (pure Python daemon)
    installed.add("multi_runtime")
    return installed


def normalize_runtime_provider(provider_raw: str | None) -> str:
    normalized = str(provider_raw or "").lower()
    return _RUNTIME_PROVIDER_ALIASES.get(normalized, normalized)


def previous_model_key_for_server(server_name: str) -> str:
    if server_name == "ollama":
        return "PREVIOUS_MODEL_OLLAMA"
    if server_name == "vllm":
        return "PREVIOUS_MODEL_VLLM"
    return "PREVIOUS_MODEL_ONNX"


def dedupe_servers_by_name(servers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for server in servers:
        name = str(server.get("name") or "").strip().lower()
        if not name or name in seen:
            continue
        seen.add(name)
        deduped.append(server)
    return deduped
