import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from venom_core.api.routes import nodes, system
from venom_core.api.schemas.system import ApiConnection, ApiMapResponse
from venom_core.services.integration_catalog import core_catalog
from venom_core.services.integration_overview import integration_overview


def settings(**kwargs):
    return SimpleNamespace(API_OPTIONAL_MODULES="", ENABLE_NEXUS=False, **kwargs)


def connection(label, **kwargs):
    return ApiConnection(
        source_component="Core",
        target_component=label,
        protocol="http",
        direction="outbound",
        auth_type="none",
        source_type="local",
        status=kwargs.pop("status", "unknown"),
        **kwargs,
    )


def snapshot(internal=(), external=()):
    return ApiMapResponse(
        internal_connections=list(internal), external_connections=list(external)
    )


def by_id(rows, id):
    return next(row for row in rows if row.id == id)


def test_supported_catalog_does_not_treat_credentials_as_connectivity():
    config = settings(VAST_API_KEY=SecretStr("never-export-this"))
    entries = core_catalog(config)
    vast = by_id(entries, "core:vast")
    assert vast.configuration == "configured" and vast.state == "configured"
    assert vast.connectivity == "unknown" and vast.resource_count is None
    assert "cli" in vast.access
    assert "never-export-this" not in json.dumps([row.model_dump() for row in entries])
    assert {
        "core:github",
        "core:slack",
        "core:discord",
        "core:huggingface",
        "core:google-calendar",
    } <= {row.id for row in entries}
    assert by_id(entries, "core:google-calendar").activation == "disabled"


@pytest.mark.asyncio
async def test_no_modules_and_disabled_nexus_are_valid_partial_inventory(
    monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path)
    rows = await integration_overview(
        FastAPI(), snapshot([connection("Nodes API")]), settings()
    )
    node = next(row for row in rows if row.label == "Nodes API")
    assert node.state == "disabled" and node.connectivity == "unknown"
    assert by_id(rows, "core:vast").configuration == "unconfigured"
    assert not any(row.kind == "module" for row in rows)


@pytest.mark.asyncio
async def test_nexus_uses_worker_registry_and_keeps_zero_distinct_from_unavailable(
    monkeypatch,
):
    config = settings()
    config.ENABLE_NEXUS = True
    manager = SimpleNamespace(list_nodes=lambda: [])
    monkeypatch.setattr(nodes, "_node_manager", manager)
    rows = await integration_overview(
        FastAPI(), snapshot([connection("Nodes API")]), config, manager
    )
    item = next(row for row in rows if row.label == "Nodes API")
    assert item.resource_count == 0 and item.active_resource_count == 0
    manager.list_nodes = Mock(side_effect=RuntimeError("private exception"))
    rows = await integration_overview(
        FastAPI(), snapshot([connection("Nodes API")]), config, manager
    )
    item = next(row for row in rows if row.label == "Nodes API")
    assert item.resource_count is None and item.reason_code == "source_unavailable"
    monkeypatch.setattr(nodes, "_node_manager", None)
    rows = await integration_overview(
        FastAPI(), snapshot([connection("Nodes API")]), config
    )
    assert (
        next(row for row in rows if row.label == "Nodes API").reason_code
        == "manager_unavailable"
    )


@pytest.mark.asyncio
async def test_local_vast_records_are_history_and_never_claim_complete_or_live(
    monkeypatch, tmp_path
):
    from venom_core.infrastructure.providers.vast.models import EnvironmentRecord
    from venom_core.services.vast_environments.store import Journal

    monkeypatch.chdir(tmp_path)
    journal = Journal(tmp_path / ".venom_runtime/vast")
    journal.save_record(
        EnvironmentRecord(plan_id="a" * 32, instance_id=123, state="running")
    )
    rows = await integration_overview(FastAPI(), snapshot(), settings())
    vast = by_id(rows, "core:vast")
    assert vast.resources[0].id == "vast:123"
    assert vast.resources[0].state == "stale"
    assert vast.resource_count is None and vast.connectivity == "unknown"
    assert vast.reason_code == "local_records_only"


def module_record(**kwargs):
    return dict(
        module_id="example",
        display_name="Example",
        state="loaded",
        reason_code="router_loaded",
        observed_at=datetime.now(timezone.utc).isoformat(),
        module_root=None,
        integration_provider_import=kwargs.pop("hook", None),
        **kwargs,
    )


@pytest.mark.asyncio
async def test_old_module_is_visible_without_hook_or_device_calls():
    app = FastAPI()
    app.state.optional_module_diagnostics = [module_record()]
    rows = await integration_overview(app, snapshot(), settings())
    module = by_id(rows, "module:example")
    assert module.state == "available" and module.connectivity == "unknown"
    assert module.resource_count is None
    assert module.reason_code == "observation_provider_absent"


@pytest.mark.asyncio
async def test_hook_is_single_flight_cached_and_namespaces_resources(monkeypatch):
    calls = []
    module = ModuleType("test_observation_hook")

    async def observe(app):
        calls.append(True)
        await asyncio.sleep(0)
        return {
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "connectivity": "ok",
            "resources_complete": True,
            "resources": [
                {
                    "id": "core:spoof",
                    "label": "Robot",
                    "kind": "robot",
                    "state": "connected",
                }
            ],
        }

    module.observe = observe
    monkeypatch.setitem(__import__("sys").modules, module.__name__, module)
    app = FastAPI()
    app.state.optional_module_diagnostics = [
        module_record(hook="test_observation_hook:observe")
    ]
    first, second = await asyncio.gather(
        integration_overview(app, snapshot(), settings()),
        integration_overview(app, snapshot(), settings()),
    )
    assert calls == [True]
    for rows in [first, second]:
        row = by_id(rows, "module:example")
        assert row.resource_count == 1 and row.active_resource_count == 1
        assert row.resources[0].id.startswith("module:example:")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "outcome,reason",
    [
        ("error", "observation_failed"),
        ("stale", "observation_stale"),
        ("timeout", "observation_timeout"),
        ("invalid", "observation_failed"),
    ],
)
async def test_bad_hook_cannot_break_other_integrations(monkeypatch, outcome, reason):
    module = ModuleType("test_bad_hook")

    async def observe(app):
        if outcome == "error":
            raise RuntimeError("secret")
        if outcome == "timeout":
            await asyncio.Event().wait()
        if outcome == "invalid":
            return {"private": "secret"}
        return {
            "observed_at": (
                datetime.now(timezone.utc) - timedelta(minutes=10)
            ).isoformat(),
            "resources_complete": True,
        }

    module.observe = observe
    monkeypatch.setitem(__import__("sys").modules, module.__name__, module)
    app = FastAPI()
    app.state.optional_module_diagnostics = [
        module_record(hook="test_bad_hook:observe")
    ]
    rows = await integration_overview(app, snapshot(), settings())
    assert by_id(rows, "module:example").reason_code == reason
    assert by_id(rows, "module:example").resource_count is None
    assert by_id(rows, "core:vast").label == "Vast.ai"
    assert "secret" not in json.dumps([row.model_dump() for row in rows])
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_stale_service_monitor_reading_does_not_look_current():
    old = (datetime.now(timezone.utc) - timedelta(minutes=3)).isoformat()
    rows = await integration_overview(
        FastAPI(),
        snapshot([connection("LanceDB", status="ok", observed_at=old)]),
        settings(),
    )
    item = next(row for row in rows if row.label == "LanceDB")
    assert item.state == "stale" and item.connectivity == "unknown"


def test_real_map_contract_exposes_inventory_and_legacy_fields_without_network(
    monkeypatch,
):
    monkeypatch.setattr(system, "_API_MAP_CACHE", None)
    monkeypatch.setattr(
        system,
        "get_active_llm_runtime",
        lambda: SimpleNamespace(provider="multi_runtime"),
    )
    monkeypatch.setattr(system.SETTINGS, "ENABLE_NEXUS", False)
    from venom_core.api.routes import system_deps

    monkeypatch.setattr(system_deps, "get_service_monitor", lambda: None)
    app = FastAPI()
    app.include_router(system.router)
    response = TestClient(app).get("/api/v1/system/api-map")
    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == 2
    assert "internal_connections" in body and "external_connections" in body
    assert (
        next(item for item in body["integrations"] if item["id"] == "core:vast")[
            "connectivity"
        ]
        == "unknown"
    )
    assert all(item["status"] == "unknown" for item in body["internal_connections"])
