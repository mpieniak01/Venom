"""Domain helpers for system LLM runtime/profile logic."""

from __future__ import annotations

import importlib.util
import shutil
from typing import Any


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
    allowed = {"ollama", "vllm"}
    if onnx_enabled:
        allowed.add("onnx")
    return allowed


def is_ollama_installed() -> bool:
    return shutil.which("ollama") is not None


def is_vllm_installed() -> bool:
    if shutil.which("vllm") is not None:
        return True
    return importlib.util.find_spec("vllm") is not None


def is_onnx_runtime_installed() -> bool:
    return importlib.util.find_spec("onnxruntime_genai") is not None


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
    return installed


def normalize_runtime_provider(provider_raw: str | None) -> str:
    normalized = str(provider_raw or "").lower()
    if normalized in ("google-gemini", "gem"):
        return "google"
    return normalized


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
