"""Explicit read-only Vast check using the existing client; never rental operations."""

from __future__ import annotations

import asyncio
import hashlib
import time
from datetime import datetime, timezone

from pydantic import SecretStr

from venom_core.api.schemas.integrations import IntegrationResource
from venom_core.infrastructure.providers.vast.client import VastClient, VastError
from venom_core.infrastructure.traffic_control.http_client import (
    TrafficControlledHttpClient,
)
from venom_core.services.integration_catalog import core_catalog

OBSERVATION_DEADLINE = "vast.observation_deadline"


def _fingerprint(settings):
    value = getattr(settings, "VAST_API_KEY", SecretStr(""))
    if not isinstance(value, SecretStr):
        value = SecretStr(str(value or ""))
    return value, hashlib.sha256(value.get_secret_value().encode()).hexdigest()


class _ReadBudget:
    def __init__(self):
        self.deadline = time.monotonic() + 4.0
        self.expired = False
        self.client = TrafficControlledHttpClient(provider="vast", timeout=1.0)

    def request(self, method, url, **kwargs):
        if method != "GET":
            raise VastError("vast.invalid_read_method")
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            self.expired = True
            raise VastError(OBSERVATION_DEADLINE)
        kwargs["timeout"] = min(1.0, remaining)
        return self.client.request(method, url, **kwargs)

    def sleep(self, delay):
        if time.monotonic() + delay >= self.deadline:
            self.expired = True
            raise VastError(OBSERVATION_DEADLINE)
        time.sleep(delay)

    def close(self):
        self.client.close()


def _read(key):
    budget = _ReadBudget()
    client = VastClient(key, transport=budget, sleep=budget.sleep)
    result = {
        "source": "provider_api",
        "observed_at": None,
        "connectivity": "unknown",
        "reason_code": "provider_unavailable",
        "state": "unavailable",
        "resources": [],
        "resources_complete": False,
    }
    try:
        client.account()
        result.update(
            connectivity="ok", state="degraded", reason_code="resources_unavailable"
        )
        rows = client.instances()
        resources = []
        for row in rows[:64]:
            instance_id = row.get("id")
            if type(instance_id) is not int:
                raise VastError("vast.invalid_response")
            status = row.get("actual_status")
            state = "unverified"
            if status == "running":
                state = "connected"
            elif status in {"stopped", "exited", "offline"}:
                state = "offline"
            resources.append(
                IntegrationResource(
                    id="vast:" + str(instance_id),
                    label=str(instance_id),
                    kind="instance",
                    state=state,
                    observed_at=datetime.now(timezone.utc).isoformat(),
                )
            )
        result.update(
            resources=resources,
            resources_complete=len(rows) <= 64,
            state="connected",
            reason_code="provider_observation",
        )
    except VastError as exc:
        if exc.status in {401, 403}:
            result.update(reason_code="provider_unauthorized")
        elif exc.code == OBSERVATION_DEADLINE or budget.expired:
            result.update(reason_code="probe_timeout")
        if result["connectivity"] == "unknown":
            result["connectivity"] = "down"
    except Exception:
        result["reason_code"] = "provider_unavailable"
    finally:
        client.close()
    result["observed_at"] = datetime.now(timezone.utc).isoformat()
    return result


def _completed(task):
    if not task.cancelled():
        task.exception()


def apply_vast_observation(app, item, settings):
    state = getattr(app.state, "vast_observation", None)
    _, fingerprint = _fingerprint(settings)
    if not state or state["fingerprint"] != fingerprint:
        return
    task = state["task"]
    if not task.done() or task.cancelled() or task.exception():
        return
    data = task.result()
    for field, value in data.items():
        setattr(item, field, value)
    if item.resources_complete:
        item.resource_count = len(item.resources)
        item.active_resource_count = (
            sum(row.state == "connected" for row in item.resources)
            if all(row.state in {"connected", "offline"} for row in item.resources)
            else None
        )
    observed = datetime.fromisoformat(item.observed_at)
    if (datetime.now(timezone.utc) - observed).total_seconds() > 60:
        item.state, item.connectivity, item.reason_code = (
            "stale",
            "unknown",
            "observation_stale",
        )
        item.active_resource_count = None
        item.resource_count = None
        item.resources_complete = False
        item.resources = [
            row.model_copy(update={"state": "stale"}) for row in item.resources
        ]


async def probe_vast(app, settings):
    item = next(row for row in core_catalog(settings) if row.id == "core:vast")
    if item.configuration != "configured":
        return item
    key, fingerprint = _fingerprint(settings)
    state = getattr(app.state, "vast_observation", None)
    if state is None or (
        state["task"].done()
        and (
            state["fingerprint"] != fingerprint
            or state["retry_after"] < time.monotonic()
        )
    ):
        task = asyncio.create_task(asyncio.to_thread(_read, key))
        task.add_done_callback(_completed)
        state = {
            "fingerprint": fingerprint,
            "task": task,
            "retry_after": time.monotonic() + 10.0,
        }
        app.state.vast_observation = state
    if state["fingerprint"] != fingerprint:
        item.state, item.reason_code = "degraded", "probe_in_progress"
        return item
    try:
        await asyncio.wait_for(asyncio.shield(state["task"]), timeout=5.0)
    except TimeoutError:
        item.state, item.reason_code = "degraded", "probe_timeout"
        return item
    except Exception:
        item.state, item.reason_code = "unavailable", "provider_unavailable"
        return item
    apply_vast_observation(app, item, settings)
    return item
