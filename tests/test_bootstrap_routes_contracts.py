from __future__ import annotations

from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from venom_core.api.routes import models_remote
from venom_core.api.routes import queue as queue_routes
from venom_core.bootstrap import model_services as model_services_module
from venom_core.bootstrap import observability as observability_module
from venom_core.services import module_registry


class _Logger:
    def __init__(self):
        self.info = Mock()
        self.warning = Mock()
        self.error = Mock()
        self.debug = Mock()


@pytest.mark.asyncio
async def test_observability_more_error_paths(tmp_path):
    logger = _Logger()
    settings = SimpleNamespace(MEMORY_ROOT=str(tmp_path))

    class Tracer:
        def __init__(self, **_kwargs):
            pass

        async def start_watchdog(self):
            return None

    result = await observability_module.initialize_observability(
        settings=settings,
        event_broadcaster=object(),
        logger=logger,
        init_metrics_collector_fn=lambda: None,
        request_tracer_cls=Tracer,
        service_registry_cls=lambda: (_ for _ in ()).throw(
            RuntimeError("registry-boom")
        ),
        service_health_monitor_cls=lambda *_args, **_kwargs: object(),
        llm_server_controller_cls=lambda _s: (_ for _ in ()).throw(
            RuntimeError("llm-boom")
        ),
        set_event_broadcaster_fn=lambda _v: None,
    )
    tracer, registry, monitor, llm = result
    assert tracer is not None
    assert registry is None
    assert monitor is None
    assert llm is None


def test_model_services_when_registry_import_fails(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    logger = _Logger()
    settings = SimpleNamespace(ACADEMY_MODELS_DIR=str(tmp_path / "models"))

    model_manager_module = ModuleType("venom_core.core.model_manager")

    class MM:
        def __init__(self, models_dir):
            self.models_dir = models_dir

    model_manager_module.ModelManager = MM

    with pytest.MonkeyPatch.context() as mp:
        mp.setitem(
            __import__("sys").modules,
            model_manager_module.__name__,
            model_manager_module,
        )
        # Force registry import branch to fail.
        monkeypatch.setitem(
            __import__("sys").modules, "venom_core.core.model_registry", None
        )
        monkeypatch.setitem(
            __import__("sys").modules, "venom_core.services.benchmark", None
        )
        mm, mr, bench = model_services_module.initialize_model_services(
            settings=settings,
            service_monitor=object(),
            llm_controller=object(),
            logger=logger,
        )
    assert mm is not None
    assert mr is None
    assert bench is None


@pytest.mark.asyncio
async def test_models_remote_cache_and_probe_paths(monkeypatch: pytest.MonkeyPatch):
    models_remote._catalog_cache.clear()
    models_remote._provider_probe_cache.clear()

    models_remote._cache_put(
        models_remote._catalog_cache,
        models_remote._catalog_cache_lock,
        "openai",
        payload={
            "models": [
                {"id": "m", "name": "m", "provider": "openai", "capabilities": []}
            ],
            "source": "cache",
            "error": None,
        },
    )
    models, source, error = await models_remote._catalog_for_provider("openai")
    assert models and models[0].id == "m"
    assert source == "cache"
    assert error is None

    monkeypatch.setattr(
        models_remote,
        "_validate_openai_connection",
        AsyncMock(return_value=(False, "x", 1.0)),
    )
    status, err, latency = await models_remote._probe_provider_cached("openai")
    assert status == "degraded"
    assert err == "x"
    assert latency == 1.0


@pytest.mark.asyncio
async def test_queue_permission_and_error_paths(monkeypatch: pytest.MonkeyPatch):
    queue_routes.set_dependencies(None)
    with pytest.raises(HTTPException) as exc_info:
        await queue_routes.purge_queue()
    assert exc_info.value.status_code == 503

    orchestrator = SimpleNamespace(
        purge_queue=AsyncMock(return_value={"removed": 0, "success": True}),
        get_queue_status=lambda: {
            "paused": False,
            "pending": 0,
            "active": 0,
            "limit": 1,
        },
    )
    queue_routes.set_dependencies(orchestrator)
    monkeypatch.setattr(
        queue_routes,
        "ensure_data_mutation_allowed",
        lambda _op: (_ for _ in ()).throw(PermissionError("blocked")),
    )
    with pytest.raises(HTTPException) as exc_info_403:
        await queue_routes.purge_queue()
    assert exc_info_403.value.status_code == 403


def test_module_registry_validate_legacy_item_branch():
    errors: list[str] = []
    module_registry._validate_legacy_item("broken-item", errors)
    assert errors and "invalid optional module entry" in errors[0]
