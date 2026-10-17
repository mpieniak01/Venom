"""Opt-in async observation hooks. Absent modules require no imports or probes."""

from __future__ import annotations

import asyncio
import hashlib
import importlib
import inspect
import sys
import time
from datetime import datetime, timezone
from typing import Any

from venom_core.api.schemas.integrations import IntegrationObservation


async def _read(app, record):
    root = record.get("module_root")
    inserted = bool(root and root not in sys.path)
    if inserted:
        sys.path.insert(0, root)
    try:
        name, attr = record["integration_provider_import"].split(":", 1)
        factory = getattr(importlib.import_module(name), attr)
    finally:
        if inserted and root in sys.path:
            sys.path.remove(root)
    if not inspect.iscoroutinefunction(factory):
        raise ValueError("async_observation_required")
    return IntegrationObservation.model_validate(await factory(app))


def _observe_done(task):
    if not task.cancelled():
        task.exception()


def _cached_task(app, record, cache):
    key = (record["module_id"], record["integration_provider_import"])
    previous = cache.get(key)
    if previous is None or (previous[1].done() and previous[0] < time.monotonic()):
        task = asyncio.create_task(_read(app, record))
        task.add_done_callback(_observe_done)
        previous = (time.monotonic() + 10.0, task)
        cache[key] = previous
    return previous[1]


async def _read_result(task, item):
    try:
        # Child cancellation is returned as data; cancellation of the requesting
        # host task propagates naturally through this await (never swallowed).
        outcomes = await asyncio.wait_for(
            asyncio.shield(asyncio.gather(task, return_exceptions=True)), timeout=0.5
        )
    except TimeoutError:
        task.cancel()
        item.reason_code, item.state = "observation_timeout", "degraded"
        return None
    result = outcomes[0]
    if isinstance(result, asyncio.CancelledError):
        item.reason_code, item.state = "observation_timeout", "degraded"
        return None
    if isinstance(result, BaseException):
        item.reason_code, item.state = "observation_failed", "degraded"
        return None
    return result


def _observation_time(result, item):
    if not result.observed_at:
        return None
    try:
        observed = datetime.fromisoformat(result.observed_at.replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - observed).total_seconds()
    except (TypeError, ValueError):
        item.reason_code, item.state = "observation_failed", "degraded"
        return None
    if age < -5 or age > 60:
        item.reason_code, item.state = "observation_stale", "stale"
        return None
    return observed


def _apply_result(result, item, observed):
    item.resources = [
        resource.model_copy(
            update={
                "id": item.id
                + ":"
                + hashlib.sha256(resource.id.encode()).hexdigest()[:20]
            }
        )
        for resource in result.resources
    ]
    item.observed_at = observed.isoformat() if observed else None
    item.connectivity = result.connectivity if observed else "unknown"
    item.resource_support = "supported"
    item.resources_complete = result.resources_complete and observed is not None
    item.reason_code = result.reason_code or "provider_observation"
    item.source = "module_observation"
    if result.configuration is not None:
        item.configuration = result.configuration
    item.state = {"ok": "connected", "down": "unavailable", "degraded": "degraded"}.get(
        item.connectivity, "available"
    )
    if item.configuration == "unconfigured":
        item.state = "unconfigured"
    if item.reason_code == "device_configuration_invalid":
        item.state = "unavailable"
    if item.resources_complete:
        item.resource_count = len(item.resources)
        item.active_resource_count = None
        if all(
            resource.state in {"connected", "offline"} for resource in item.resources
        ):
            item.active_resource_count = sum(
                resource.state == "connected" for resource in item.resources
            )


async def _apply(app, record, item, cache):
    result = await _read_result(_cached_task(app, record, cache), item)
    if result is None:
        return
    observed = _observation_time(result, item)
    if result.observed_at and observed is None:
        return
    _apply_result(result, item, observed)


async def apply_module_observations(app: Any, entries):
    records = getattr(app.state, "optional_module_diagnostics", [])
    cache = getattr(app.state, "integration_observation_cache", None)
    if cache is None:
        cache = {}
        app.state.integration_observation_cache = cache
    by_id = {item.id: item for item in entries}
    calls = []
    active = set()
    for record in records:
        item = by_id.get("module:" + record["module_id"])
        if (
            item is None
            or record["state"] != "loaded"
            or not record.get("integration_provider_import")
        ):
            continue
        active.add((record["module_id"], record["integration_provider_import"]))
        calls.append(_apply(app, record, item, cache))
    for key in cache.keys() - active:
        _, task = cache.pop(key)
        if not task.done():
            task.cancel()
    if calls:
        await asyncio.gather(*calls)
