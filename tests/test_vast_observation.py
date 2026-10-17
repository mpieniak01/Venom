import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from fastapi import FastAPI
from pydantic import SecretStr

from venom_core.infrastructure.providers.vast.client import VastError
from venom_core.services import vast_observation as observation
from venom_core.services.integration_catalog import core_catalog


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "responses,expected,reason",
    [
        (
            [(200, {"credit": 4}), (200, {"instances": []})],
            "connected",
            "provider_observation",
        ),
        ([(401, {})], "unavailable", "provider_unauthorized"),
        ([(200, {"credit": 4}), (403, {})], "degraded", "provider_unauthorized"),
        (
            [
                (200, {"credit": 4}),
                (200, {"instances": [{"id": 123, "actual_status": "running"}]}),
            ],
            "connected",
            "provider_observation",
        ),
    ],
)
async def test_explicit_vast_check_uses_existing_get_client_only(
    monkeypatch, responses, expected, reason
):
    calls = []

    class Transport:
        def __init__(self, **kwargs):
            pass

        def request(self, method, url, **kwargs):
            calls.append((method, url))
            status, data = responses[len(calls) - 1]
            return httpx.Response(status, json=data)

        def close(self):
            pass

    monkeypatch.setattr(observation, "TrafficControlledHttpClient", Transport)
    config = SimpleNamespace(VAST_API_KEY=SecretStr("private-key"))
    app = FastAPI()
    first, second = await asyncio.gather(
        observation.probe_vast(app, config), observation.probe_vast(app, config)
    )
    assert first.state == second.state == expected
    assert first.reason_code == reason
    assert len(calls) == len(responses)
    assert all(method == "GET" for method, _ in calls)
    assert "private-key" not in first.model_dump_json()
    if expected == "connected":
        assert first.resource_count == len(responses[-1][1]["instances"])
    else:
        assert first.resource_count is None
    cached = next(item for item in core_catalog(config) if item.id == "core:vast")
    observation.apply_vast_observation(app, cached, config)
    assert cached.state == expected
    config.VAST_API_KEY = SecretStr("changed-key")
    changed = next(item for item in core_catalog(config) if item.id == "core:vast")
    observation.apply_vast_observation(app, changed, config)
    assert changed.connectivity == "unknown"


@pytest.mark.asyncio
async def test_missing_key_does_not_construct_a_client(monkeypatch):
    client = Mock(side_effect=AssertionError("network not allowed"))
    monkeypatch.setattr(observation, "VastClient", client)
    result = await observation.probe_vast(FastAPI(), SimpleNamespace())
    assert result.state == "unconfigured"
    client.assert_not_called()


def test_vast_read_budget_rejects_mutations_and_expired_requests(monkeypatch):
    monkeypatch.setattr(observation, "TrafficControlledHttpClient", Mock())
    budget = observation._ReadBudget()
    with pytest.raises(VastError):
        budget.request("POST", "unused")
    budget.deadline = 0
    with pytest.raises(VastError):
        budget.request("GET", "unused")
    with pytest.raises(VastError):
        budget.sleep(1)
    budget.close()


@pytest.mark.asyncio
async def test_expired_provider_observation_does_not_claim_current_totals(monkeypatch):
    old = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
    monkeypatch.setattr(
        observation,
        "_read",
        lambda key: dict(
            source="provider_api",
            observed_at=old,
            connectivity="ok",
            state="connected",
            reason_code="provider_observation",
            resources=[],
            resources_complete=True,
        ),
    )
    result = await observation.probe_vast(
        FastAPI(), SimpleNamespace(VAST_API_KEY=SecretStr("key"))
    )
    assert result.state == "stale"
    assert result.connectivity == "unknown"
    assert result.resource_count is None
