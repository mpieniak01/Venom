from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from venom_core.api.routes import (
    models_translation,
    system_deps,
    system_runtime,
    system_services,
)


@pytest.fixture
def translation_client():
    app = FastAPI()
    app.include_router(models_translation.router)
    return TestClient(app)


@pytest.fixture
def runtime_client():
    app = FastAPI()
    app.include_router(system_runtime.router)
    return TestClient(app)


@pytest.fixture
def services_client():
    app = FastAPI()
    app.include_router(system_services.router)
    return TestClient(app)


def test_system_deps_setters_and_getters_roundtrip():
    deps = {
        "background_scheduler": object(),
        "service_monitor": object(),
        "state_manager": object(),
        "llm_controller": object(),
        "model_manager": object(),
        "request_tracer": object(),
        "hardware_bridge": object(),
        "orchestrator": object(),
    }
    system_deps.set_dependencies(**deps)

    assert system_deps.get_background_scheduler() is deps["background_scheduler"]
    assert system_deps.get_service_monitor() is deps["service_monitor"]
    assert system_deps.get_state_manager() is deps["state_manager"]
    assert system_deps.get_llm_controller() is deps["llm_controller"]
    assert system_deps.get_model_manager() is deps["model_manager"]
    assert system_deps.get_request_tracer() is deps["request_tracer"]
    assert system_deps.get_hardware_bridge() is deps["hardware_bridge"]
    assert system_deps.get_orchestrator() is deps["orchestrator"]


def test_get_translation_service_imports_from_models_module(monkeypatch):
    marker = object()

    def _fake_import(name: str):
        assert name == "venom_core.api.routes.models"
        return SimpleNamespace(translation_service=marker)

    monkeypatch.setattr(models_translation.importlib, "import_module", _fake_import)

    assert models_translation._get_translation_service() is marker


@pytest.mark.asyncio
async def test_models_translation_value_error_branch(monkeypatch):
    svc = SimpleNamespace(translate_text=AsyncMock(side_effect=ValueError("bad input")))
    monkeypatch.setattr(models_translation, "_get_translation_service", lambda: svc)

    request = models_translation.TranslationRequest(
        text="hello", source_lang="en", target_lang="pl"
    )

    with pytest.raises(models_translation.HTTPException) as exc:
        await models_translation.translate_text_endpoint(request)

    assert exc.value.status_code == 400
    assert exc.value.detail == "bad input"


@pytest.mark.asyncio
async def test_models_translation_unexpected_error_branch(monkeypatch):
    svc = SimpleNamespace(translate_text=AsyncMock(side_effect=RuntimeError("boom")))
    monkeypatch.setattr(models_translation, "_get_translation_service", lambda: svc)

    request = models_translation.TranslationRequest(
        text="hello", source_lang="en", target_lang="pl"
    )

    with pytest.raises(models_translation.HTTPException) as exc:
        await models_translation.translate_text_endpoint(request)

    assert exc.value.status_code == 500
    assert "Błąd serwera" in exc.value.detail


def test_models_translation_success_uses_stable_contract(
    translation_client, monkeypatch
):
    translate = AsyncMock(return_value="czesc")
    svc = SimpleNamespace(translate_text=translate)
    monkeypatch.setattr(models_translation, "_get_translation_service", lambda: svc)

    response = translation_client.post(
        "/api/v1/translate",
        json={"text": "hello", "source_lang": "en", "target_lang": "pl"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["translated_text"] == "czesc"
    translate.assert_awaited_once_with(
        "hello",
        target_lang="pl",
        source_lang="en",
        use_cache=True,
        allow_fallback=False,
    )


def test_system_services_requires_monitor(services_client, monkeypatch):
    monkeypatch.setattr(system_deps, "get_service_monitor", lambda: None)

    response = services_client.get("/api/v1/system/services")
    assert response.status_code == 503

    response = services_client.get("/api/v1/system/services/backend")
    assert response.status_code == 503


def test_system_services_cached_lookup_not_found(services_client, monkeypatch):
    monitor = MagicMock()
    monkeypatch.setattr(system_deps, "get_service_monitor", lambda: monitor)
    system_services._services_cache.set(
        {
            "status": "success",
            "count": 1,
            "services": [{"name": "api", "status": "running"}],
        }
    )

    response = services_client.get("/api/v1/system/services/worker")
    assert response.status_code == 404
    monitor.get_all_services.assert_not_called()


def test_system_services_get_all_services_internal_error(services_client, monkeypatch):
    monitor = MagicMock()
    monitor.check_health = AsyncMock(side_effect=RuntimeError("monitor down"))
    monkeypatch.setattr(system_deps, "get_service_monitor", lambda: monitor)
    system_services._services_cache.clear()

    response = services_client.get("/api/v1/system/services")
    assert response.status_code == 500
    assert "Błąd wewnętrzny" in response.json()["detail"]


def test_runtime_status_merges_service_monitor_entries(runtime_client, monkeypatch):
    base_service = SimpleNamespace(
        name="backend",
        service_type=SimpleNamespace(value="backend"),
        status=SimpleNamespace(value="running"),
        pid=123,
        port=8000,
        cpu_percent=1.0,
        memory_mb=100.0,
        uptime_seconds=10,
        last_log=None,
        error_message=None,
        runtime_version="1.0.0",
        actionable=True,
    )

    runtime_ctrl = MagicMock()
    runtime_ctrl.get_all_services_status.return_value = [base_service]
    runtime_ctrl.get_aux_runtime_version.return_value = "aux-1.2.3"
    monkeypatch.setattr(system_runtime, "runtime_controller", runtime_ctrl)

    monitor_services = [
        SimpleNamespace(
            name="API",
            service_type="api",
            status=SimpleNamespace(value="online"),
            error_message=None,
            endpoint="http://localhost",
            latency_ms=1.2,
        ),
        SimpleNamespace(
            name="Ollama",
            service_type="llm",
            status=SimpleNamespace(value="online"),
            error_message=None,
            endpoint=None,
            latency_ms=0.0,
        ),
        SimpleNamespace(
            name="backend",
            service_type="service",
            status=SimpleNamespace(value="online"),
            error_message=None,
            endpoint=None,
            latency_ms=0.0,
        ),
        SimpleNamespace(
            name="worker",
            service_type="worker",
            status=SimpleNamespace(value="degraded"),
            error_message="slow",
            endpoint="n/a",
            latency_ms=55.0,
        ),
    ]
    monitor = MagicMock()
    monitor.check_health = AsyncMock(return_value=None)
    monitor.get_all_services.return_value = monitor_services
    monkeypatch.setattr(system_deps, "get_service_monitor", lambda: monitor)

    response = runtime_client.get("/api/v1/runtime/status")

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 2
    names = {svc["name"] for svc in data["services"]}
    assert names == {"backend", "worker"}

    worker_payload = [svc for svc in data["services"] if svc["name"] == "worker"][0]
    assert worker_payload["status"] == "degraded"
    assert worker_payload["runtime_version"] == "aux-1.2.3"
    assert worker_payload["actionable"] is False


def test_runtime_action_internal_error_returns_500(runtime_client, monkeypatch):
    runtime_ctrl = MagicMock()
    runtime_ctrl.start_service.side_effect = RuntimeError("crash")
    monkeypatch.setattr(system_runtime, "runtime_controller", runtime_ctrl)

    response = runtime_client.post("/api/v1/runtime/backend/start")
    assert response.status_code == 500


def test_runtime_history_internal_error_returns_500(runtime_client, monkeypatch):
    runtime_ctrl = MagicMock()
    runtime_ctrl.get_history.side_effect = RuntimeError("history failed")
    monkeypatch.setattr(system_runtime, "runtime_controller", runtime_ctrl)

    response = runtime_client.get("/api/v1/runtime/history")
    assert response.status_code == 500
