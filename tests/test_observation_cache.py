"""Observation TTL cache ownership across request event loops."""

import asyncio
import sys
import time
from datetime import datetime, timezone
from types import ModuleType

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from venom_core.api.schemas.integrations import IntegrationEntry
from venom_core.services import integration_hooks as hooks

KEY = ("example", "observation_cache_fixture:observe")


def fixture_app(monkeypatch, outcome="ok", gate=None):
    calls = []
    module = ModuleType("observation_cache_fixture")

    async def observe(app):
        calls.append(asyncio.get_running_loop())
        if gate is not None:
            await gate.wait()
        if outcome == "error":
            raise RuntimeError("provider failure")
        if outcome == "cancelled":
            raise asyncio.CancelledError()
        return {
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "connectivity": "ok",
            "resources_complete": True,
        }

    module.observe = observe
    monkeypatch.setitem(sys.modules, module.__name__, module)
    app = FastAPI()
    app.state.optional_module_diagnostics = [
        {"module_id": KEY[0], "state": "loaded", "integration_provider_import": KEY[1]}
    ]
    return app, calls


async def observe(app):
    item = IntegrationEntry(id="module:example", label="Example", scope="external")
    await hooks.apply_module_observations(app, [item])
    return item


@pytest.mark.parametrize(
    "outcome,reason",
    [
        ("ok", "provider_observation"),
        ("error", "observation_failed"),
        ("cancelled", "observation_timeout"),
    ],
)
def test_finished_observation_is_reused_on_new_loop_without_extending_ttl(
    monkeypatch, outcome, reason
):
    app, calls = fixture_app(monkeypatch, outcome)
    first = asyncio.run(observe(app))
    expiry, original = app.state.integration_observation_cache[KEY]
    second = asyncio.run(observe(app))
    new_expiry, local = app.state.integration_observation_cache[KEY]
    assert first.reason_code == second.reason_code == reason
    assert len(calls) == 1
    assert local is not original
    assert local.get_loop() is not original.get_loop()
    assert new_expiry == expiry


def test_cross_loop_completed_cache_refreshes_only_when_ttl_expires(monkeypatch):
    app, calls = fixture_app(monkeypatch)
    asyncio.run(observe(app))
    _, task = app.state.integration_observation_cache[KEY]
    app.state.integration_observation_cache[KEY] = (time.monotonic() - 1, task)
    asyncio.run(observe(app))
    assert len(calls) == 2
    expiry, refreshed = app.state.integration_observation_cache[KEY]
    assert refreshed is not task
    assert expiry > time.monotonic()


def test_repeated_testclient_requests_share_completed_value_without_foreign_future(
    monkeypatch,
):
    app, calls = fixture_app(monkeypatch)

    @app.get("/observations")
    async def endpoint():
        return (await observe(app)).model_dump()

    client = TestClient(app)
    first = client.get("/observations")
    second = client.get("/observations")
    assert first.status_code == second.status_code == 200
    assert first.json()["connectivity"] == second.json()["connectivity"] == "ok"
    assert len(calls) == 1


class OwnedTask(asyncio.Task):
    def cancel(self, msg=None):
        assert asyncio.get_running_loop() is self.get_loop(), "cross-loop cancellation"
        return super().cancel(msg)


@pytest.mark.parametrize("active", [True, False])
def test_pending_foreign_probe_is_never_cancelled_from_request_loop(
    monkeypatch, active
):
    app, calls = fixture_app(monkeypatch)
    owner = asyncio.new_event_loop()

    async def pending():
        await asyncio.Event().wait()

    foreign = OwnedTask(pending(), loop=owner)
    owner.run_until_complete(asyncio.sleep(0))
    app.state.integration_observation_cache = {KEY: (time.monotonic() + 10, foreign)}
    try:
        if active:
            item = asyncio.run(observe(app))
            assert item.connectivity == "ok"
            assert len(calls) == 1
        else:
            app.state.optional_module_diagnostics = []
            asyncio.run(hooks.apply_module_observations(app, []))
            assert not app.state.integration_observation_cache
        assert not foreign.done()
    finally:

        async def cleanup():
            foreign.cancel()
            await asyncio.gather(foreign, return_exceptions=True)

        owner.run_until_complete(cleanup())
        owner.close()


@pytest.mark.asyncio
async def test_inactive_current_loop_probe_is_still_cancelled(monkeypatch):
    app, _ = fixture_app(monkeypatch)

    async def pending():
        await asyncio.Event().wait()

    task = asyncio.create_task(pending())
    app.state.integration_observation_cache = {KEY: (time.monotonic() + 10, task)}
    app.state.optional_module_diagnostics = []
    await hooks.apply_module_observations(app, [])
    await asyncio.sleep(0)
    assert task.cancelled()
    assert not app.state.integration_observation_cache


@pytest.mark.asyncio
async def test_request_cancellation_does_not_cancel_shared_probe(monkeypatch):
    gate = asyncio.Event()
    app, calls = fixture_app(monkeypatch, gate=gate)
    request = asyncio.create_task(observe(app))
    while not calls:
        await asyncio.sleep(0)
    shared = app.state.integration_observation_cache[KEY][1]
    request.cancel()
    with pytest.raises(asyncio.CancelledError):
        await request
    assert not shared.done()
    gate.set()
    await shared
    assert not shared.cancelled()
