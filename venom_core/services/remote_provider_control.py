"""Operator controls for optional external APIs; no provisioning or startup probes."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import HTTPException

from venom_core.utils.runtime_state import runtime_state_root

PROVIDERS = ("openai", "google", "openrouter", "vast_ollama")
CATALOG_PROVIDERS = ("openrouter", "vast_ollama")
_STATE = runtime_state_root() / "remote-providers/control.json"
_LOCK = threading.RLock()
_CHECKS: dict[str, dict[str, Any]] = {}


def _provider(provider: str) -> None:
    if provider not in PROVIDERS:
        raise HTTPException(400, "remote_provider_unknown")


def enabled(provider: str, default: bool = True) -> bool:
    _provider(provider)
    with _LOCK:
        try:
            data = json.loads(_STATE.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or any(
                k not in PROVIDERS or type(v) is not bool for k, v in data.items()
            ):
                return False
            return data.get(provider, default)
        except FileNotFoundError:
            return default
        except (OSError, ValueError):
            return False


def set_enabled(provider: str, value: bool) -> None:
    _provider(provider)
    with _LOCK:
        try:
            data = json.loads(_STATE.read_text(encoding="utf-8"))
        except FileNotFoundError:
            data = {}
        except (OSError, ValueError) as exc:
            raise HTTPException(503, "remote_provider_state_unavailable") from exc
        if not isinstance(data, dict) or any(
            k not in PROVIDERS or type(v) is not bool for k, v in data.items()
        ):
            raise HTTPException(503, "remote_provider_state_invalid")
        data[provider] = value
        _STATE.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, name = tempfile.mkstemp(dir=_STATE.parent, prefix="control-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(data, stream)
            os.replace(name, _STATE)
        finally:
            Path(name).unlink(missing_ok=True)
        _CHECKS.pop(provider, None)


def assert_enabled(provider: str) -> None:
    """Operator disablement blocks new work without changing the selected identity."""
    if not enabled(provider):
        raise HTTPException(
            503, {"code": "remote_provider_disabled", "provider": provider}
        )


def _legacy_metadata(provider: str) -> dict[str, Any]:
    from venom_core.config import SETTINGS
    from venom_core.utils.llm_runtime import get_active_llm_runtime

    key = SETTINGS.OPENAI_API_KEY if provider == "openai" else SETTINGS.GOOGLE_API_KEY
    from venom_core.services.remote_models_service import is_api_key_configured

    configured = is_api_key_configured(key)
    return {
        "enabled": enabled(provider),
        "configured": configured,
        "selected": get_active_llm_runtime().provider == provider,
        "reason": None if configured else "remote_provider_missing_credentials",
        "connection": {},
    }


def _provider_metadata(provider: str) -> dict[str, Any]:
    from venom_core.services import openrouter_runtime, vast_chat_runtime

    if provider in {"openai", "google"}:
        return _legacy_metadata(provider)
    if provider == "openrouter":
        info = openrouter_runtime.status()
        return {
            "enabled": enabled(
                provider, bool(openrouter_runtime.SETTINGS.OPENROUTER_ENABLED)
            ),
            "configured": info["configured"],
            "selected": info["active"],
            "reason": info["reason"],
            "connection": info,
        }
    info = vast_chat_runtime.connection().status(refresh=False)
    return {
        "enabled": enabled(provider),
        "configured": bool(info.get("target_id") or info.get("plan_id")),
        "selected": vast_chat_runtime.selection() is not None,
        "reason": info.get("error"),
        "connection": info,
    }


def _status_name(on: bool, available: bool | None) -> str:
    if not on:
        return "disabled"
    if available:
        return "reachable"
    if available is False:
        return "degraded"
    return "configured"


def status(provider: str) -> dict[str, Any]:
    _provider(provider)
    metadata = _provider_metadata(provider)
    on = metadata["enabled"]
    reason = metadata["reason"]
    with _LOCK:
        probe = dict(_CHECKS.get(provider, {}))
    available: bool | None = False
    if on and metadata["configured"]:
        available = probe.get("available")
    if provider == "vast_ollama":
        info = metadata["connection"]
        available = bool(on and info.get("available") and info.get("models"))
        if available:
            probe.pop("error", None)
            reason = None
        if on and info.get("available") and not info.get("models"):
            reason = "vast.chat_model_missing"
    error = "remote_provider_disabled"
    if on:
        error = probe.get("error") or reason
    return {
        "provider": provider,
        "enabled": on,
        "configured": metadata["configured"],
        "selected": metadata["selected"],
        "available": available,
        "status": _status_name(on, available),
        "last_check": probe.get("last_check"),
        "latency_ms": probe.get("latency_ms"),
        "error": error,
        "infrastructure_managed_separately": provider == "vast_ollama",
    }


async def _check_openrouter(configured: bool) -> tuple[bool, str | None]:
    from venom_core.services import openrouter_runtime

    if not configured:
        return False, "openrouter_missing_credentials"
    if not openrouter_runtime.cloud_allowed():
        return False, "openrouter_cloud_policy_denied"
    try:
        async with httpx.AsyncClient(timeout=6, follow_redirects=False) as client:
            response = await client.get(
                "https://openrouter.ai/api/v1/key",
                headers={"Authorization": "Bearer " + openrouter_runtime.credential()},
            )
        if response.status_code != 200:
            return False, "openrouter_authentication_failed"
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
            return False, "openrouter_authentication_failed"
        return True, None
    except (httpx.HTTPError, TimeoutError, ValueError):
        return False, "openrouter_connection_unavailable"


async def _check_legacy(provider: str, configured: bool) -> tuple[bool, str | None]:
    from venom_core.config import SETTINGS
    from venom_core.services.remote_models_service import openai_models_url

    if not configured:
        return False, "remote_provider_missing_credentials"
    if provider == "openai":
        url = openai_models_url(
            chat_completions_endpoint=SETTINGS.OPENAI_CHAT_COMPLETIONS_ENDPOINT
        )
        headers = {"Authorization": "Bearer " + SETTINGS.OPENAI_API_KEY}
    else:
        url = "https://generativelanguage.googleapis.com/v1beta/models"
        headers = {"x-goog-api-key": SETTINGS.GOOGLE_API_KEY}
    try:
        async with httpx.AsyncClient(timeout=6, follow_redirects=False) as client:
            response = await client.get(url, headers=headers)
        if response.status_code in {401, 403}:
            return False, "remote_provider_authentication_failed"
        if response.status_code != 200:
            return False, "remote_provider_connection_unavailable"
        payload = response.json()
        field = "data" if provider == "openai" else "models"
        if not isinstance(payload, dict) or not isinstance(payload.get(field), list):
            return False, "remote_provider_connection_unavailable"
        return True, None
    except (httpx.HTTPError, TimeoutError, ValueError):
        return False, "remote_provider_connection_unavailable"


async def check(provider: str) -> dict[str, Any]:
    _provider(provider)
    info = status(provider)
    available = False
    error = None
    start = time.monotonic()
    if not info["enabled"]:
        error = "remote_provider_disabled"
    elif provider in {"openai", "google"}:
        available, error = await _check_legacy(provider, info["configured"])
    elif provider == "vast_ollama":
        from venom_core.services import vast_chat_runtime

        state = await asyncio.to_thread(
            vast_chat_runtime.connection().status, refresh=True
        )
        available = bool(state.get("available"))
        error = None if available else "vast_chat_target_unavailable"
    else:
        available, error = await _check_openrouter(info["configured"])
    with _LOCK:
        _CHECKS[provider] = {
            "available": available,
            "error": error,
            "last_check": datetime.now(timezone.utc).isoformat(),
            "latency_ms": round((time.monotonic() - start) * 1000, 2),
        }
    return status(provider)


def catalog(provider: str) -> list[dict[str, Any]]:
    info = status(provider)
    if not info["enabled"] or provider in {"openai", "google"}:
        return []
    if provider == "openrouter":
        from venom_core.services import openrouter_runtime

        rows = openrouter_runtime.configured_catalog()[1]
        return [
            {
                "id": row["id"],
                "name": row["name"],
                "provider": provider,
                "capabilities": ["chat", "text-generation"],
                "model_alias": None,
            }
            for row in rows
        ]
    from venom_core.services import vast_chat_runtime

    rows = vast_chat_runtime.connection().status(refresh=False).get("models", [])
    return [
        {
            "id": row["name"],
            "name": row["name"],
            "provider": provider,
            "capabilities": ["chat", "text-generation"],
            "model_alias": None,
        }
        for row in rows
    ]
