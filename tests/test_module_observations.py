import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI

from venom_core.services.conversation_providers import ConversationProviderRegistry
from venom_core.services.module_observations import module_candidates
from venom_core.services.module_registry import include_optional_api_routers


def settings(raw):
    return SimpleNamespace(API_OPTIONAL_MODULES=raw)


def test_missing_optional_module_does_not_block_core_or_disclose_path(tmp_path):
    raw = f"manifest:{tmp_path}/private-module.json"
    app = FastAPI()
    assert include_optional_api_routers(app, settings(raw)) == []
    record = app.state.optional_module_diagnostics[0]
    assert record["state"] == "unavailable"
    assert str(tmp_path) not in json.dumps(record)
    assert module_candidates(settings(raw))[0][1]["module_id"] == record["module_id"]


def test_metadata_discovery_never_imports_module_and_filters_unsafe_navigation(
    tmp_path,
):
    path = tmp_path / "module.json"
    path.write_text(
        json.dumps(
            {
                "module_id": "sample",
                "display_name": "Sample",
                "frontend": {"nav_path": "//evil.test"},
            }
        )
    )
    record = module_candidates(settings(f"manifest:{path},manifest:{path}"))
    assert len(record) == 1
    assert record[0][1]["display_name"] == "Sample"
    assert record[0][1]["state"] == "unverified"
    assert record[0][1]["nav_path"] is None


@pytest.mark.asyncio
async def test_failed_optional_provider_does_not_block_healthy_provider_or_retry_storm():
    healthy = SimpleNamespace(handle=AsyncMock(return_value=None), close=AsyncMock())
    attempts = []

    def broken(app):
        attempts.append(True)
        raise RuntimeError("secret detail")

    registry = ConversationProviderRegistry(
        None,
        lambda: {"bad": broken, "good": lambda app: healthy},
        isolate_failures=True,
    )
    await registry.refresh()
    await registry.refresh()
    assert list(registry.providers) == ["good"]
    assert attempts == [True]
    assert registry.failures == {"bad": "provider_initialization_failed"}
    healthy.close.side_effect = RuntimeError("private error")
    await registry.close()
    assert registry.failures["good"] == "provider_close_failed"


@pytest.mark.asyncio
async def test_optional_async_initialization_failure_is_isolated():
    async def broken(app):
        raise ValueError("private")

    registry = ConversationProviderRegistry(
        None, lambda: {"bad": broken}, isolate_failures=True
    )
    await registry.refresh()
    assert registry.providers == {}
    assert registry.failures["bad"] == "provider_initialization_failed"
    await registry.close()


def test_unregistered_local_manifest_is_visible_without_loading_package(
    tmp_path, monkeypatch
):
    from venom_core.services.module_observations import module_inventory

    monkeypatch.chdir(tmp_path)
    path = tmp_path / "modules" / "sample" / "module.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({"module_id": "sample", "display_name": "Local optional module"})
    )
    rows = module_inventory(settings(""), [])
    assert len(rows) == 1
    assert rows[0]["module_id"] == "sample"
    assert rows[0]["state"] == "disabled"
    assert rows[0]["reason_code"] == "module_not_registered"
    assert rows[0]["backend_configured"] is False


def test_activated_module_metadata_is_not_duplicated(tmp_path, monkeypatch):
    from venom_core.services.module_observations import module_inventory

    monkeypatch.chdir(tmp_path)
    path = tmp_path / "modules" / "sample" / "module.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"module_id": "sample"}))
    original = {"module_id": "sample", "state": "loaded"}
    assert module_inventory(settings(""), [original]) == [original]


def test_router_lifespan_failure_is_local_to_the_optional_module(tmp_path, monkeypatch):
    from contextlib import asynccontextmanager
    from types import ModuleType

    from fastapi import APIRouter
    from fastapi.testclient import TestClient

    @asynccontextmanager
    async def broken_lifespan(app):
        raise RuntimeError("device unavailable")
        yield

    router = APIRouter(lifespan=broken_lifespan)

    @router.get("/optional/health")
    async def optional_health():
        return {"ok": True}

    module = ModuleType("test_optional_lifespan")
    module.router = router
    monkeypatch.setitem(__import__("sys").modules, module.__name__, module)
    manifest = tmp_path / "module.json"
    manifest.write_text(
        json.dumps(
            {
                "module_id": "optional",
                "backend": {
                    "router_import": "test_optional_lifespan:router",
                    "data_policy": {
                        "storage_mode": "core_prefixed",
                        "mutation_guard": "core_environment_policy",
                        "state_files": [],
                    },
                },
            }
        )
    )
    app = FastAPI()

    @app.get("/core/health")
    async def core_health():
        return {"ok": True}

    include_optional_api_routers(app, settings(str(manifest)))
    with TestClient(app) as client:
        assert client.get("/core/health").status_code == 200
        assert client.get("/optional/health").status_code == 503
        assert (
            app.state.optional_module_diagnostics[0]["reason_code"]
            == "module_initialization_failed"
        )


def test_router_cleanup_failure_is_isolated_and_original_context_is_restored():
    from contextlib import asynccontextmanager

    from fastapi import APIRouter
    from fastapi.testclient import TestClient

    from venom_core.services.module_runtime import include_isolated_router

    @asynccontextmanager
    async def cleanup_failure(app):
        yield
        raise RuntimeError("cleanup failed")

    router = APIRouter(lifespan=cleanup_failure)
    original = router.lifespan_context
    record = {"state": "loaded"}
    app = FastAPI()
    include_isolated_router(app, router, record)
    assert router.lifespan_context is original
    with TestClient(app):
        pass
    assert record["reason_code"] == "module_cleanup_failed"


def test_optional_lifecycle_does_not_swallow_core_request_failures():
    from fastapi import APIRouter
    from fastapi.testclient import TestClient

    from venom_core.services.module_runtime import include_isolated_router

    app = FastAPI()
    record = {"state": "loaded"}
    include_isolated_router(app, APIRouter(), record)

    @app.get("/core/failure")
    async def failure():
        raise RuntimeError("core failure")

    with TestClient(app) as client:
        with pytest.raises(RuntimeError, match="core failure"):
            client.get("/core/failure")
    assert record["state"] == "loaded"


@pytest.mark.asyncio
async def test_device_inventory_preserves_unknown_connectivity_and_resource_context(
    monkeypatch,
):
    from datetime import datetime, timezone

    from venom_core.api.schemas.integrations import (
        IntegrationEntry,
        IntegrationObservation,
    )
    from venom_core.services import integration_hooks

    app = FastAPI()
    app.state.optional_module_diagnostics = [
        {
            "module_id": "rider",
            "state": "loaded",
            "integration_provider_import": "example:observe",
        }
    ]
    observation = IntegrationObservation.model_validate(
        {
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "configuration": "configured",
            "resources_complete": True,
            "resources": [
                {
                    "id": "robot-1",
                    "label": "Robot",
                    "kind": "robot",
                    "state": "unverified",
                    "mode": "device",
                    "selected": True,
                    "configuration": "configured",
                    "reason_code": "not_observed",
                    "supported_capabilities": ["camera"],
                    "reported_capabilities": None,
                    "available_capabilities": None,
                }
            ],
        }
    )
    read = AsyncMock(return_value=observation)
    monkeypatch.setattr(integration_hooks, "_read", read)
    entry = IntegrationEntry(
        id="module:rider", label="Rider", scope="internal", kind="module"
    )
    await integration_hooks.apply_module_observations(app, [entry])
    assert entry.resource_count == 1
    assert entry.active_resource_count is None
    assert entry.resources[0].id.startswith("module:rider:")
    assert entry.resources[0].mode == "device"
    assert entry.resources[0].selected is True
    assert entry.resources[0].reported_capabilities is None
    assert entry.resources[0].available_capabilities is None
    assert entry.connectivity == "unknown"
    assert entry.configuration == "configured"
    await integration_hooks.apply_module_observations(app, [entry])
    read.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "configuration,reason,complete,expected",
    [
        ("unconfigured", "device_not_configured", True, "unconfigured"),
        ("unknown", "device_configuration_invalid", False, "unavailable"),
    ],
)
async def test_empty_and_invalid_device_configuration_are_distinct(
    monkeypatch, configuration, reason, complete, expected
):
    from datetime import datetime, timezone

    from venom_core.api.schemas.integrations import (
        IntegrationEntry,
        IntegrationObservation,
    )
    from venom_core.services import integration_hooks

    app = FastAPI()
    app.state.optional_module_diagnostics = [
        {
            "module_id": "rider",
            "state": "loaded",
            "integration_provider_import": "example:observe",
        }
    ]
    monkeypatch.setattr(
        integration_hooks,
        "_read",
        AsyncMock(
            return_value=IntegrationObservation(
                observed_at=datetime.now(timezone.utc).isoformat(),
                configuration=configuration,
                reason_code=reason,
                resources_complete=complete,
            )
        ),
    )
    entry = IntegrationEntry(
        id="module:rider", label="Rider", scope="internal", kind="module"
    )
    await integration_hooks.apply_module_observations(app, [entry])
    assert entry.state == expected
    assert entry.reason_code == reason
    assert entry.resource_count == (0 if complete else None)
    assert entry.active_resource_count == (0 if complete else None)


def test_observation_context_defaults_and_public_reason_validation():
    from pydantic import ValidationError

    from venom_core.api.schemas.integrations import (
        IntegrationObservation,
        IntegrationResource,
    )

    legacy = IntegrationObservation(
        resources=[IntegrationResource(id="x", label="Legacy", kind="robot")]
    )
    assert legacy.configuration is None
    assert legacy.reason_code is None
    assert legacy.resources[0].mode is None
    assert legacy.resources[0].available_capabilities is None
    with pytest.raises(ValidationError):
        IntegrationObservation(reason_code="http://private-host?token=secret")


@pytest.mark.parametrize("phase", ["startup", "shutdown"])
def test_legacy_module_events_are_isolated_and_context_is_closed(phase):
    from contextlib import asynccontextmanager

    from fastapi import APIRouter
    from fastapi.testclient import TestClient

    from venom_core.services.module_runtime import include_isolated_router

    calls = []

    @asynccontextmanager
    async def context(_app):
        calls.append("context-enter")
        try:
            yield
        finally:
            calls.append("context-exit")

    router = APIRouter(lifespan=context)

    async def startup():
        calls.append("startup")
        if phase == "startup":
            raise RuntimeError("startup failed")

    async def shutdown():
        calls.append("shutdown")
        if phase == "shutdown":
            raise RuntimeError("shutdown failed")

    router.add_event_handler("startup", startup)
    router.add_event_handler("shutdown", shutdown)

    @router.get("/optional/events")
    async def optional():
        return {"ok": True}

    app = FastAPI()

    @app.get("/core/alive")
    async def alive():
        return {"ok": True}

    record = {"state": "loaded", "reason_code": "router_loaded"}
    original = router.lifespan_context
    include_isolated_router(app, router, record)
    assert router.lifespan_context is original
    assert router.on_startup == [startup]
    assert router.on_shutdown == [shutdown]
    with TestClient(app) as client:
        assert client.get("/core/alive").status_code == 200
        assert client.get("/optional/events").status_code == (
            503 if phase == "startup" else 200
        )
    assert calls.count("startup") == 1
    assert calls.count("context-exit") == 1
    assert record["reason_code"] == (
        "module_initialization_failed"
        if phase == "startup"
        else "module_cleanup_failed"
    )


def test_default_router_legacy_handlers_run_once_and_remain_available_to_other_host():
    from fastapi import APIRouter
    from fastapi.testclient import TestClient

    from venom_core.services.module_runtime import include_isolated_router

    calls = []
    router = APIRouter()
    router.add_event_handler("startup", lambda: calls.append("start"))
    router.add_event_handler("shutdown", lambda: calls.append("stop"))
    app = FastAPI()
    include_isolated_router(app, router, {"state": "loaded"})
    with TestClient(app):
        assert calls == ["start"]
    assert calls == ["start", "stop"]
    second = FastAPI()
    include_isolated_router(second, router, {"state": "loaded"})
    with TestClient(second):
        assert calls == ["start", "stop", "start"]
    assert calls == ["start", "stop", "start", "stop"]


@pytest.mark.asyncio
async def test_cancelled_observation_caller_still_propagates_cancellation(monkeypatch):
    import asyncio

    from venom_core.api.schemas.integrations import IntegrationEntry
    from venom_core.services import integration_hooks

    started = asyncio.Event()

    async def read(*_args):
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(integration_hooks, "_read", read)
    cache = {}
    entry = IntegrationEntry(id="module:rider", label="Rider", scope="internal")
    call = asyncio.create_task(
        integration_hooks._apply(
            FastAPI(),
            {"module_id": "rider", "integration_provider_import": "example:observe"},
            entry,
            cache,
        )
    )
    await started.wait()
    call.cancel()
    with pytest.raises(asyncio.CancelledError):
        await call
    for _, task in cache.values():
        task.cancel()
    await asyncio.gather(*(task for _, task in cache.values()), return_exceptions=True)


def test_service_observation_invalid_or_old_time_cannot_stay_healthy():
    from datetime import datetime, timedelta, timezone

    from venom_core.api.schemas.integrations import IntegrationEntry
    from venom_core.services.integration_overview import _apply_service_freshness

    for timestamp in [
        "2024-01-01 12:00:00",
        "invalid",
        (datetime.now(timezone.utc) - timedelta(seconds=61)).isoformat(),
    ]:
        item = IntegrationEntry(
            id="api:test",
            label="Test",
            scope="internal",
            state="connected",
            connectivity="ok",
            source="service_monitor",
            observed_at=timestamp,
        )
        _apply_service_freshness(item)
        assert item.state == "stale"
        assert item.connectivity == "unknown"
    current = IntegrationEntry(
        id="api:test",
        label="Test",
        scope="internal",
        state="connected",
        connectivity="ok",
        source="service_monitor",
        observed_at=datetime.now(timezone.utc).isoformat(),
    )
    _apply_service_freshness(current)
    assert current.state == "connected"


@pytest.mark.parametrize("phase", ["startup", "shutdown"])
def test_hanging_legacy_handler_is_bounded_and_does_not_escape_to_host(phase):
    import asyncio
    from contextlib import asynccontextmanager

    from fastapi import APIRouter
    from fastapi.testclient import TestClient

    from venom_core.services.module_runtime import include_isolated_router

    calls = []

    @asynccontextmanager
    async def context(_app):
        try:
            yield
        finally:
            calls.append("closed")

    router = APIRouter(lifespan=context)

    async def hang():
        calls.append("handler")
        await asyncio.Event().wait()

    router.add_event_handler(phase, hang)
    app = FastAPI()
    record = {"state": "loaded"}
    include_isolated_router(app, router, record)
    with TestClient(app):
        pass
    assert calls == ["handler", "closed"]
    assert record["reason_code"] == (
        "module_initialization_failed"
        if phase == "startup"
        else "module_cleanup_failed"
    )
