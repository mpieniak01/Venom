"""Explicit, offline-configured OpenRouter identity and cost policy for Direct chat."""

from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from venom_core.config import SETTINGS

SERVER = "openrouter"
ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
_ROOT = Path(__file__).resolve().parents[2]
_STATE = _ROOT / ".venom_runtime/openrouter"
_LOCK = threading.RLock()


def library():
    """Load the separately installed distribution only when the feature is used."""
    try:
        core = importlib.import_module("agent_execution_core")
        if (
            importlib.metadata.version("agent-execution-core")
            != SETTINGS.OPENROUTER_LIBRARY_VERSION
        ):
            raise ValueError("version")
        return core
    except (ImportError, importlib.metadata.PackageNotFoundError, ValueError) as exc:
        raise HTTPException(503, "openrouter_library_unavailable") from exc


def credential() -> str:
    """Read an injected secret without exposing it in status or configuration hashes."""
    if SETTINGS.OPENROUTER_API_KEY:
        return SETTINGS.OPENROUTER_API_KEY
    name = SETTINGS.OPENROUTER_CREDENTIAL_FILE
    if not name:
        return ""
    try:
        path = Path(name)
        if path.stat().st_mode & 0o077:
            return ""
        return path.read_text().strip()
    except OSError:
        return ""


def selection() -> dict[str, str] | None:
    """Keep a selected broken target explicit instead of falling back locally."""
    try:
        value = json.loads((_STATE / "selection.json").read_text())
        if value is None:
            return None
        if not isinstance(value, dict) or not all(
            isinstance(value.get(k), str) and value[k] for k in ("model", "config_hash")
        ):
            raise ValueError("selection")
        return value
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        return {"model": "unavailable", "config_hash": "unavailable"}


def save_selection(value: dict[str, str] | None) -> None:
    """Persist a selection atomically with private filesystem permissions."""
    with _LOCK:
        _STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, name = tempfile.mkstemp(prefix="selection-", dir=_STATE)
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump(value, stream)
            os.replace(name, _STATE / "selection.json")
        finally:
            Path(name).unlink(missing_ok=True)


def clear_selection() -> None:
    save_selection(None)


def cloud_allowed() -> bool:
    return (
        str(SETTINGS.AI_MODE).upper() in {"HYBRID", "CLOUD"}
        and not SETTINGS.SENSITIVE_DATA_LOCAL_ONLY
    )


def _catalog_row(row, as_of, core):
    """Validate one approved identity and its complete, known tariff."""
    model = row["id"]
    provider = row["provider_endpoint"]
    if isinstance(model, str) and (
        model.lower().rsplit("/", 1)[-1] in {"auto", "latest", "free"}
        or model.lower().endswith("-latest")
    ):
        raise ValueError("unpinned_model")
    if (
        not isinstance(model, str)
        or not model
        or (":" in model and (not model.endswith(":free") or model.count(":") != 1))
        or (not isinstance(provider, str))
        or (not provider)
    ):
        raise ValueError("model")
    context, output = (row["context_length"], row["max_output_tokens"])
    if (
        type(context) is not int
        or type(output) is not int
        or (not 0 < output < context)
    ):
        raise ValueError("limits")
    prices = core.strict_prices(row["pricing"])
    return {
        "id": model,
        "name": model,
        "provider": SERVER,
        "runtime_id": SERVER,
        "chat_compatible": True,
        "context_length": context,
        "max_output_tokens": output,
        "input_price_per_million": str(prices.input_per_million),
        "output_price_per_million": str(prices.output_per_million),
        "request_price": str(prices.request),
        "pricing_as_of": as_of,
        "provider_endpoint": provider,
        "pricing": row["pricing"],
    }


def configured_catalog() -> tuple[str, list[dict[str, Any]]]:
    """Validate the operator-approved snapshot; never discover or generate implicitly."""
    core = library()
    try:
        raw = json.loads(Path(SETTINGS.OPENROUTER_MODELS_FILE).read_text())
        as_of = raw["pricing_as_of"]
        moment = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - moment).total_seconds()
        if moment.tzinfo is None or not 0 <= age <= 86400:
            raise ValueError("stale")
        rows = raw["models"]
        if not isinstance(rows, list) or not 1 <= len(rows) <= 3:
            raise ValueError("shortlist")
        result = []
        for row in rows:
            result.append(_catalog_row(row, as_of, core))
        if len({x["id"] for x in result}) != len(result):
            raise ValueError("duplicate")
        return as_of, result
    except (OSError, KeyError, TypeError, ValueError, AttributeError) as exc:
        raise HTTPException(503, "openrouter_catalog_unavailable") from exc


def limits() -> dict[str, Any]:
    core = library()
    try:
        values = {
            "message_limit": core.decimal_amount(
                SETTINGS.OPENROUTER_MESSAGE_LIMIT_USD, "message_limit"
            ),
            "conversation_limit": core.decimal_amount(
                SETTINGS.OPENROUTER_CONVERSATION_LIMIT_USD, "conversation_limit"
            ),
            "daily_limit": core.decimal_amount(
                SETTINGS.OPENROUTER_DAILY_LIMIT_USD, "daily_limit"
            ),
        }
        if any(v <= 0 for v in values.values()):
            raise ValueError("limits")
        return values
    except ValueError as exc:
        raise HTTPException(503, "openrouter_budget_not_approved") from exc


def config_hash(model: str) -> str:
    as_of, rows = configured_catalog()
    policy = {k: str(v) for k, v in limits().items()}
    value = {
        "model": model,
        "models": rows,
        "pricing_as_of": as_of,
        "limits": policy,
        "library": SETTINGS.OPENROUTER_LIBRARY_VERSION,
        "endpoint": ENDPOINT,
    }
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()[:32]


def require_ready() -> tuple[str, list[dict[str, Any]]]:
    from venom_core.services.remote_provider_control import enabled

    if not enabled(SERVER, SETTINGS.OPENROUTER_ENABLED):
        raise HTTPException(503, "openrouter_disabled")
    if not cloud_allowed():
        raise HTTPException(403, "openrouter_cloud_policy_denied")
    if not credential():
        raise HTTPException(503, "openrouter_missing_credentials")
    limits()
    return configured_catalog()


def runtime_override():
    selected = selection()
    if selected is None:
        return None
    from venom_core.utils.llm_runtime import LLMRuntimeInfo

    return LLMRuntimeInfo(
        provider=SERVER,
        model_name=selected["model"],
        endpoint=ENDPOINT,
        service_type=SERVER,
        mode="CLOUD",
        config_hash=selected["config_hash"],
        runtime_id=SERVER + "@" + selected["model"],
    )


def assert_identity(request) -> dict[str, Any]:
    """Validate captured model/config before any reservation or network operation."""
    _, rows = require_ready()
    active = runtime_override()
    if (
        active is None
        or request.expected_runtime_id != active.runtime_id
        or request.expected_config_hash != active.config_hash
    ):
        raise HTTPException(409, "openrouter_selection_changed")
    if request.model not in {
        None,
        active.model_name,
    } or active.config_hash != config_hash(active.model_name):
        raise HTTPException(409, "openrouter_selection_changed")
    row = next((v for v in rows if v["id"] == active.model_name), None)
    if row is None:
        raise HTTPException(409, "openrouter_model_unavailable")
    return row


def select_model(model: str | None) -> dict[str, Any]:
    _, rows = require_ready()
    if model not in {r["id"] for r in rows}:
        raise HTTPException(400, "openrouter_model_unavailable")
    assert model is not None
    save_selection({"model": model, "config_hash": config_hash(model)})
    active = runtime_override()
    return {
        "status": "success",
        "active_server": SERVER,
        "active_model": model,
        "runtime_id": active.runtime_id,
        "config_hash": active.config_hash,
        "active_endpoint": ENDPOINT,
    }


def status() -> dict[str, Any]:
    """Metadata-only status does not claim authentication from key presence."""
    from venom_core.services.remote_provider_control import enabled

    reason = None
    available = False
    rows: list[dict[str, Any]] = []
    as_of = None
    library_available = False
    try:
        library()
        library_available = True
        as_of, rows = require_ready()
        available = True
    except HTTPException as exc:
        reason = str(exc.detail)
    active = runtime_override()
    return {
        "enabled": enabled(SERVER, SETTINGS.OPENROUTER_ENABLED),
        "configured": bool(credential()),
        "library_available": library_available,
        "available": available,
        "authenticated": None,
        "reason": reason,
        "active": active is not None,
        "active_model": active.model_name if active else None,
        "runtime_id": active.runtime_id if active else None,
        "config_hash": active.config_hash if active else None,
        "pricing_as_of": as_of,
        "models": [
            {k: v for k, v in row.items() if k not in {"pricing", "provider_endpoint"}}
            for row in rows
        ],
        "budget": {
            "message_limit_usd": SETTINGS.OPENROUTER_MESSAGE_LIMIT_USD,
            "conversation_limit_usd": SETTINGS.OPENROUTER_CONVERSATION_LIMIT_USD,
            "daily_limit_usd": SETTINGS.OPENROUTER_DAILY_LIMIT_USD,
        },
    }


def target_payload() -> dict[str, Any]:
    info = status()
    return {
        "runtime_id": SERVER,
        "source_type": "cloud-api",
        "label": "OpenRouter",
        "configured": info["configured"],
        "available": info["available"],
        "active": info["active"],
        "status": "online" if info["available"] else "offline",
        "reason": info["reason"],
        "models": [
            {**row, "active": row["id"] == info["active_model"]}
            for row in info["models"]
        ],
        "supports_text_input": True,
        "supports_text_output": True,
        "supports_streaming": True,
        "adapter_deploy_supported": False,
        "normal_supported": False,
    }


def save_request_receipt(request_id: str, value: dict[str, Any]) -> None:
    """Keep provider accounting identities after STOP without storing conversation text."""
    if len(request_id) != 32 or any(c not in "0123456789abcdef" for c in request_id):
        raise ValueError("request_identity_invalid")
    folder = _STATE / "requests"
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(prefix="receipt-", dir=folder)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream)
        os.replace(name, folder / (request_id + ".json"))
    finally:
        Path(name).unlink(missing_ok=True)
