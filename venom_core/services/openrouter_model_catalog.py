"""Metadata discovery and an operator-managed registry of fixed OpenRouter models."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import threading
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
from fastapi import HTTPException

BASE = "https://openrouter.ai/api/v1"
CATEGORIES = {
    "programming",
    "roleplay",
    "marketing",
    "marketing/seo",
    "technology",
    "science",
    "translation",
    "legal",
    "finance",
    "health",
    "trivia",
    "academia",
}
_CACHE: dict[str, tuple[float, str, list[dict[str, Any]]]] = {}
_CACHE_LOCK = asyncio.Lock()
_WRITE_LOCK = threading.RLock()
MAX_CONNECTED = 100


def _runtime():
    from venom_core.services import openrouter_runtime

    return openrouter_runtime


def _path() -> Path:
    return _runtime()._STATE / "connected-models.json"


def _allowed() -> None:
    rt = _runtime()
    if not rt.is_enabled():
        raise HTTPException(503, "openrouter_disabled")
    if not rt.cloud_allowed():
        raise HTTPException(403, "openrouter_cloud_policy_denied")
    if not rt.credential():
        raise HTTPException(503, "openrouter_missing_credentials")


def fixed_model(model: Any) -> bool:
    return bool(
        isinstance(model, str)
        and 0 < len(model) <= 300
        and "/" in model
        and not model.startswith("openrouter/")
        and not any(c.isspace() or ord(c) < 32 for c in model)
        and model.rsplit("/", 1)[-1] not in {"auto", "latest", "free"}
        and not model.endswith("-latest")
        and (":" not in model or model.endswith(":free") and model.count(":") == 1)
    )


async def _get(path: str, params=None) -> Any:
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
            response = await client.get(
                BASE + path,
                params=params,
                headers={"Authorization": "Bearer " + _runtime().credential()},
            )
        if response.status_code != 200:
            raise HTTPException(
                502, "openrouter_catalog_http_" + str(response.status_code)
            )
        payload = response.json()
        if not isinstance(payload, dict) or "data" not in payload:
            raise ValueError("metadata")
        return payload["data"]
    except (httpx.HTTPError, TimeoutError, ValueError) as exc:
        raise HTTPException(502, "openrouter_catalog_unavailable") from exc


async def _models(category: str = "", fresh=False) -> tuple[str, list[dict[str, Any]]]:
    _allowed()
    async with _CACHE_LOCK:
        cached = _CACHE.get(category)
        if not fresh and cached and time.monotonic() - cached[0] < 300:
            return cached[1], cached[2]
        # category must be sent alone: upstream rejects some combinations.
        rows = await _get("/models", {"category": category} if category else None)
        if not isinstance(rows, list) or any(not isinstance(x, dict) for x in rows):
            raise HTTPException(502, "openrouter_catalog_invalid")
        fetched = datetime.now(timezone.utc).isoformat()
        _CACHE[category] = (time.monotonic(), fetched, rows)
        return fetched, rows


def _price(value):
    try:
        amount = Decimal(str(value))
        return str(amount * 1000000) if amount.is_finite() and amount >= 0 else None
    except (ValueError, TypeError, ArithmeticError):
        return None


def _parameters(row):
    value = row.get("supported_parameters")
    return (
        [item for item in value if isinstance(item, str)]
        if isinstance(value, list)
        else []
    )


def _textual(row):
    architecture = row.get("architecture")
    if not isinstance(architecture, dict):
        return False
    source, target = (
        architecture.get("input_modalities"),
        architecture.get("output_modalities"),
    )
    return (
        isinstance(source, list)
        and isinstance(target, list)
        and "text" in source
        and "text" in target
    )


def _display(row, connected=False):
    pricing = row.get("pricing")
    if not isinstance(pricing, dict):
        pricing = {}
    context = row.get("context_length")
    return {
        "id": row["id"],
        "name": row.get("name")
        if isinstance(row.get("name"), str) and row["name"]
        else row["id"],
        "description": str(row.get("description") or "")[:2000],
        "context_length": context if type(context) is int and context > 0 else None,
        "input_price_per_million": _price(pricing.get("prompt")),
        "output_price_per_million": _price(pricing.get("completion")),
        "supports_tools": "tools" in _parameters(row),
        "connected": connected,
    }


def raw_connected() -> list[dict[str, Any]] | None:
    try:
        value = json.loads(_path().read_text(encoding="utf-8"))
        rows = value["models"]
        if (
            not isinstance(rows, list)
            or len(rows) > MAX_CONNECTED
            or any(
                not isinstance(row, dict) or not fixed_model(row.get("id"))
                for row in rows
            )
            or len({row["id"] for row in rows}) != len(rows)
        ):
            raise ValueError("registry")
        return rows
    except FileNotFoundError:
        return None
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(503, "openrouter_registry_unavailable") from exc


def _legacy() -> list[dict[str, Any]]:
    try:
        payload = json.loads(
            Path(_runtime().SETTINGS.OPENROUTER_MODELS_FILE).read_text()
        )
        rows = payload["models"]
        if not isinstance(rows, list) or len(rows) > MAX_CONNECTED:
            raise ValueError("legacy")
        return [{**row, "pricing_as_of": payload["pricing_as_of"]} for row in rows]
    except (OSError, ValueError, KeyError, TypeError):
        return []


def _validate(row):
    stamp = row["pricing_as_of"]
    moment = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    if (
        moment.tzinfo is None
        or not 0 <= (datetime.now(timezone.utc) - moment).total_seconds() <= 86400
    ):
        raise ValueError("stale")
    return _runtime()._catalog_row(row, stamp, _runtime().library())


def runtime_catalog():
    rows = raw_connected()
    if rows is None:
        return None
    result = []
    for row in rows:
        try:
            result.append(_validate(row))
        except (KeyError, ValueError, TypeError, AttributeError):
            continue
    return min((row["pricing_as_of"] for row in result), default=""), result


def connected() -> dict[str, Any]:
    rows = raw_connected()
    if rows is None:
        rows = _legacy()
    models = []
    for row in rows:
        try:
            valid = _validate(row)
            display = _display(row, True)
            display.update(
                input_price_per_million=valid["input_price_per_million"],
                output_price_per_million=valid["output_price_per_million"],
            )
            available, reason = True, None
        except (KeyError, ValueError, TypeError, AttributeError, HTTPException):
            display = {
                "id": row.get("id", "unavailable"),
                "name": row.get("name") or row.get("id", "unavailable"),
                "description": "",
                "context_length": row.get("context_length"),
                "input_price_per_million": None,
                "output_price_per_million": None,
                "supports_tools": False,
                "connected": True,
            }
            available, reason = False, "openrouter_model_refresh_required"
        models.append({**display, "available": available, "reason": reason})
    return {"models": models, "count": len(models)}


def _save(rows):
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(prefix="connected-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump({"version": 1, "models": rows}, stream)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


async def search(q="", purpose="chat", category="", offset=0, limit=25):
    if (
        purpose not in {"chat", "tasks", "programming"}
        or category
        and category not in CATEGORIES
        or len(q) > 120
        or offset < 0
        or not 1 <= limit <= 100
    ):
        raise HTTPException(400, "openrouter_search_invalid")
    category = "programming" if purpose == "programming" else category
    fetched, rows = await _models(category)
    ids = {row["id"] for row in connected()["models"]}
    result = []
    for row in rows:
        model = row.get("id", "")
        if not fixed_model(model) or not _textual(row):
            continue
        if purpose in {"tasks", "programming"} and "tools" not in _parameters(row):
            continue
        if q.casefold() not in (model + " " + str(row.get("name", ""))).casefold():
            continue
        result.append(_display(row, model in ids))

    def rank(row):
        a, b = row["input_price_per_million"], row["output_price_per_million"]
        return (
            Decimal(a) + Decimal(b)
            if a is not None and b is not None
            else Decimal("Infinity"),
            row["id"],
        )

    result.sort(key=rank)
    total = len(result)
    page = result[offset : offset + limit]
    return {
        "models": page,
        "count": len(page),
        "total": total,
        "offset": offset,
        "limit": limit,
        "next_offset": offset + limit if offset + limit < total else None,
        "fetched_at": fetched,
        "source": "openrouter-live-metadata",
    }


async def connect(model_id: str):
    _allowed()
    if not fixed_model(model_id):
        raise HTTPException(400, "openrouter_model_identity_invalid")
    _, models = await _models(fresh=True)
    model = next((x for x in models if x.get("id") == model_id), None)
    if model is None:
        raise HTTPException(404, "openrouter_model_not_found")
    if not _textual(model):
        raise HTTPException(400, "openrouter_text_chat_only")
    data = await _get("/models/" + quote(model_id, safe="/:") + "/endpoints")
    options = []
    core = _runtime().library()
    for endpoint in (
        (data.get("endpoints") or [])
        if isinstance(data, dict) and isinstance(data.get("endpoints"), list)
        else []
    ):
        try:
            if not isinstance(endpoint, dict):
                continue
            if endpoint.get("status") != 0 or not {"max_tokens", "temperature"} <= set(
                _parameters(endpoint)
            ):
                continue
            tariff = dict(endpoint["pricing"])
            if (
                model_id.endswith(":free")
                and tariff.get("prompt") == "0"
                and tariff.get("completion") == "0"
            ):
                tariff.setdefault("request", "0")
            prices = core.strict_prices(tariff)
            provider = endpoint.get("tag") or endpoint.get("provider_name")
            context_raw = endpoint.get("context_length") or model.get("context_length")
            output_raw = endpoint.get("max_completion_tokens") or 256
            if (
                type(context_raw) is not int
                or context_raw < 2
                or type(output_raw) is not int
                or output_raw < 1
            ):
                continue
            context = min(context_raw, 32768)
            output = min(output_raw, 256, context - 1)
            if not isinstance(provider, str) or not provider or output < 1:
                continue
            options.append(
                (
                    prices.estimate(1024, output),
                    provider,
                    {
                        "id": model_id,
                        "name": model.get("name") or model_id,
                        "description": str(model.get("description") or "")[:2000],
                        "supported_parameters": _parameters(model),
                        "provider_endpoint": provider,
                        "context_length": context,
                        "max_output_tokens": output,
                        "pricing": tariff,
                        "pricing_as_of": datetime.now(timezone.utc).isoformat(),
                    },
                )
            )
        except (ValueError, KeyError, TypeError, ArithmeticError):
            continue
    if not options:
        raise HTTPException(400, "openrouter_model_endpoint_unavailable")
    row = min(options, key=lambda x: (x[0], x[1]))[2]
    with _WRITE_LOCK:
        rows = raw_connected()
        if rows is None:
            rows = _legacy()
        rows = [x for x in rows if x["id"] != model_id]
        if len(rows) >= MAX_CONNECTED:
            raise HTTPException(400, "openrouter_connected_limit")
        _save([*rows, row])
    return {"status": "success", **connected()}


def disconnect(model_id: str):
    if not fixed_model(model_id):
        raise HTTPException(400, "openrouter_model_identity_invalid")
    with _WRITE_LOCK:
        rows = raw_connected()
        if rows is None:
            rows = _legacy()
        _save([x for x in rows if x["id"] != model_id])
    return {"status": "success", **connected()}
