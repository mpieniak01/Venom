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

PROVIDERS = ("openrouter", "vast_ollama")
_STATE = (
    Path(__file__).resolve().parents[2] / ".venom_runtime/remote-providers/control.json"
)
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


def status(provider: str) -> dict[str, Any]:
    _provider(provider)
    from venom_core.services import openrouter_runtime, vast_chat_runtime

    if provider == "openrouter":
        info = openrouter_runtime.status()
        on = enabled(provider, bool(openrouter_runtime.SETTINGS.OPENROUTER_ENABLED))
        configured = info["configured"]
        selected = info["active"]
        reason = info["reason"]
    else:
        on = enabled(provider)
        info = vast_chat_runtime.connection().status(refresh=False)
        configured = bool(info.get("target_id") or info.get("plan_id"))
        selected = vast_chat_runtime.selection() is not None
        reason = info.get("error")
    with _LOCK:
        probe = dict(_CHECKS.get(provider, {}))
    available = probe.get("available") if on else False
    if provider == "vast_ollama":
        available = bool(on and info.get("available"))
    return {
        "provider": provider,
        "enabled": on,
        "configured": configured,
        "selected": selected,
        "available": available,
        "status": "disabled"
        if not on
        else (
            "reachable"
            if available
            else ("degraded" if available is False else "configured")
        ),
        "last_check": probe.get("last_check"),
        "latency_ms": probe.get("latency_ms"),
        "error": (probe.get("error") or reason) if on else "remote_provider_disabled",
        "infrastructure_managed_separately": provider == "vast_ollama",
    }


async def check(provider: str) -> dict[str, Any]:
    _provider(provider)
    info = status(provider)
    available = False
    error = None
    start = time.monotonic()
    if not info["enabled"]:
        error = "remote_provider_disabled"
    elif provider == "vast_ollama":
        from venom_core.services import vast_chat_runtime

        state = await asyncio.to_thread(
            vast_chat_runtime.connection().status, refresh=True
        )
        available = bool(state.get("available"))
        error = None if available else "vast_chat_target_unavailable"
    else:
        from venom_core.services import openrouter_runtime

        if not info["configured"]:
            error = "openrouter_missing_credentials"
        elif not openrouter_runtime.cloud_allowed():
            error = "openrouter_cloud_policy_denied"
        else:
            try:
                async with httpx.AsyncClient(
                    timeout=6, follow_redirects=False
                ) as client:
                    response = await client.get(
                        "https://openrouter.ai/api/v1/key",
                        headers={
                            "Authorization": "Bearer " + openrouter_runtime.credential()
                        },
                    )
                    available = response.status_code == 200
                    error = None if available else "openrouter_authentication_failed"
            except (httpx.HTTPError, TimeoutError):
                error = "openrouter_connection_unavailable"
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
    if not info["enabled"]:
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
