"""Selected remote Ollama identity; never rewrite the local engine configuration."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Any

from fastapi import HTTPException

SERVER = "vast_ollama"
_ROOT = Path(__file__).resolve().parents[2]
_SELECTION = _ROOT / ".venom_runtime/vast/chat-selection.json"
_LOCK = threading.RLock()
_UNSET = object()
_selected: Any = _UNSET


def selection() -> dict[str, str] | None:
    global _selected
    with _LOCK:
        if _selected is _UNSET:
            try:
                value = json.loads(_SELECTION.read_text())
                if value is None:
                    _selected = None
                elif (
                    isinstance(value, dict)
                    and re.fullmatch(
                        r"ollama@vast:[a-f0-9]{32}:[1-9][0-9]*",
                        str(value.get("target_id", "")),
                    )
                    and isinstance(value.get("model"), str)
                    and value["model"]
                    and re.fullmatch(r"[a-f0-9]{64}", str(value.get("digest", "")))
                ):
                    _selected = value
                else:
                    raise ValueError("invalid_remote_selection")
            except FileNotFoundError:
                _selected = None
            except (OSError, ValueError):
                # Corrupt selection must not silently route to a local engine.
                _selected = {
                    "target_id": "ollama@vast:unavailable",
                    "model": "",
                    "digest": "",
                }
        return dict(_selected) if _selected is not None else None


def _save(value: dict[str, str] | None) -> None:
    global _selected
    with _LOCK:
        _SELECTION.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, temp_name = tempfile.mkstemp(
            prefix="chat-selection-", dir=_SELECTION.parent
        )
        temp = Path(temp_name)
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream)
        os.replace(temp, _SELECTION)
        _selected = value


def clear_selection() -> None:
    _save(None)


def connection():
    from venom_core.services.vast_chat_connection import get_vast_chat_connection

    return get_vast_chat_connection()


def runtime_override():
    """No network I/O here. A selected unavailable target keeps its identity."""
    selected = selection()
    if selected is None:
        return None
    from venom_core.utils.llm_runtime import LLMRuntimeInfo

    state = connection().status(refresh=False)
    same = state.get("target_id") == selected.get("target_id")
    generation = str(state.get("generation") or "offline")
    identity = str(selected.get("target_id", "unknown"))
    runtime_id = identity + ":" + generation
    config = (
        runtime_id + "|" + selected.get("model", "") + "|" + selected.get("digest", "")
    )
    endpoint = state.get("endpoint") if same and state.get("available") else None
    return LLMRuntimeInfo(
        provider="ollama",
        model_name=selected.get("model", ""),
        endpoint=endpoint,
        service_type="local",
        mode="LOCAL",
        config_hash=hashlib.sha256(config.encode()).hexdigest()[:12],
        runtime_id=runtime_id,
    )


def is_remote(runtime=None) -> bool:
    return str(getattr(runtime, "runtime_id", "") or "").startswith("ollama@vast:")


def server_name(runtime) -> str:
    return SERVER if is_remote(runtime) else runtime.provider


async def preflight() -> None:
    selected = selection()
    if selected is None:
        return
    state = await asyncio.to_thread(connection().status, refresh=True)
    models = state.get("models", [])
    valid_model = any(
        row.get("name") == selected.get("model")
        and row.get("digest") == selected.get("digest")
        for row in models
    )
    if (
        not state.get("available")
        or state.get("target_id") != selected.get("target_id")
        or not valid_model
    ):
        raise HTTPException(status_code=503, detail="vast_chat_target_unavailable")


async def select_model(model: str | None) -> dict:
    state = await asyncio.to_thread(connection().status, refresh=True)
    if not state.get("available"):
        raise HTTPException(status_code=503, detail="vast_chat_target_unavailable")
    rows = state.get("models", [])
    match = next((row for row in rows if row.get("name") == model), None)
    if match is None:
        raise HTTPException(status_code=400, detail="vast_chat_model_unavailable")
    _save(
        {
            "target_id": state["target_id"],
            "model": match["name"],
            "digest": match["digest"],
        }
    )
    runtime = runtime_override()
    return {
        "status": "success",
        "active_server": SERVER,
        "active_model": match["name"],
        "runtime_id": runtime.runtime_id,
        "config_hash": runtime.config_hash,
        "active_endpoint": runtime.endpoint,
    }


async def target_payload() -> dict:
    state = await asyncio.to_thread(connection().status, refresh=True)
    selected = selection()
    models = [
        {
            "id": row["name"],
            "name": row["name"],
            "provider": "ollama",
            "runtime_id": SERVER,
            "source_type": "remote",
            "canonical_model_id": row["name"],
            "digest": row["digest"],
            "size": row.get("size"),
            "chat_compatible": True,
            "active": bool(
                selected
                and selected.get("target_id") == state.get("target_id")
                and selected.get("model") == row["name"]
            ),
        }
        for row in state.get("models", [])
        if state.get("available")
    ]
    return {
        "runtime_id": SERVER,
        "source_type": "remote",
        "label": "Ollama · Vast",
        "configured": bool(state.get("target_id")),
        "available": bool(state.get("available")),
        "status": "online" if state.get("available") else "offline",
        "reason": state.get("error"),
        "active": selected is not None,
        "models": models,
        "adapter_deploy_supported": False,
        "adapter_deploy_mode": "unsupported",
        "adapter_deploy_reason": "remote_runtime_not_supported",
        "supports_native_training": False,
        "supports_adapter_import_safetensors": False,
        "supports_adapter_import_gguf": False,
        "supports_adapter_runtime_apply": False,
        "supports_text_input": True,
        "supports_text_output": True,
        "supports_image_input": False,
        "supports_audio_input": False,
    }


def assert_identity(
    runtime, expected_id: str | None, expected_hash: str | None
) -> None:
    if (expected_id is not None and expected_id != runtime.runtime_id) or (
        expected_hash is not None and expected_hash != runtime.config_hash
    ):
        raise HTTPException(status_code=409, detail="runtime_identity_changed")
