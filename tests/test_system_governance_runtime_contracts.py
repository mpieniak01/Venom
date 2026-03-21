"""Coverage ROI tests for new-code hotspots."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.testclient import TestClient

from venom_core.api.routes import system as system_routes
from venom_core.api.routes import system_governance as governance_routes
from venom_core.api.routes import system_iot as iot_routes
from venom_core.core import learning_log as learning_log_mod
from venom_core.core import provider_observability as observability_mod
from venom_core.core.permission_guard import permission_guard
from venom_core.core.provider_observability import (
    Alert,
    AlertSeverity,
    AlertType,
    ProviderObservability,
    SLOTarget,
)
from venom_core.core.service_monitor import (
    ServiceHealthMonitor,
    ServiceInfo,
    ServiceRegistry,
    ServiceStatus,
)
from venom_core.infrastructure import docker_habitat as docker_habitat_mod
from venom_core.services import translation_service as translation_module
from venom_core.services.audit_stream import get_audit_stream


class _Secret:
    def __init__(self, value: str = ""):
        self._value = value

    def get_secret_value(self) -> str:
        return self._value


def _configure_translation_settings(monkeypatch) -> None:
    monkeypatch.setattr(
        translation_module.SETTINGS, "LLM_MODEL_NAME", "test-model", raising=False
    )
    monkeypatch.setattr(
        translation_module.SETTINGS,
        "LLM_LOCAL_ENDPOINT",
        "http://localhost:11434/v1",
        raising=False,
    )
    monkeypatch.setattr(
        translation_module.SETTINGS, "LLM_LOCAL_API_KEY", "local-key", raising=False
    )
    monkeypatch.setattr(
        translation_module.SETTINGS, "OPENAI_API_TIMEOUT", 1.0, raising=False
    )


class _DummyDockerContainer:
    def __init__(self, *, status: str = "running"):
        self.status = status

    def reload(self) -> None:
        return None

    def remove(self, force: bool = False) -> None:
        return None


def _new_docker_habitat_with_client(client):
    habitat = object.__new__(docker_habitat_mod.DockerHabitat)
    habitat.client = client
    return habitat


def test_translation_endpoint_and_model_helpers_cover_branches(monkeypatch):
    _configure_translation_settings(monkeypatch)
    service = translation_module.TranslationService()

    monkeypatch.setattr(
        translation_module,
        "get_active_llm_runtime",
        lambda: SimpleNamespace(service_type="local"),
    )
    monkeypatch.setattr(
        translation_module.SETTINGS,
        "LLM_LOCAL_ENDPOINT",
        "http://localhost:11434/v1",
        raising=False,
    )
    assert (
        service._resolve_chat_endpoint() == "http://localhost:11434/v1/chat/completions"
    )
    assert service._normalize_target_lang("PL") == "pl"
    assert service._resolve_model_name() == "test-model"


@pytest.mark.asyncio
async def test_translation_missing_model_uses_fallback_when_enabled(monkeypatch):
    _configure_translation_settings(monkeypatch)
    monkeypatch.setattr(
        translation_module.SETTINGS, "LLM_MODEL_NAME", "", raising=False
    )
    service = translation_module.TranslationService()
    assert await service.translate_text("Hello", target_lang="pl") == "Hello"


@pytest.mark.asyncio
async def test_translation_non_http_error_raises_without_fallback(monkeypatch):
    _configure_translation_settings(monkeypatch)
    service = translation_module.TranslationService()
    monkeypatch.setattr(
        service,
        "_resolve_model_name",
        lambda: (_ for _ in ()).throw(RuntimeError("no-model")),
    )

    with pytest.raises(RuntimeError, match="no-model"):
        await service.translate_text("Hello", target_lang="pl", allow_fallback=False)


def test_translation_get_cached_value_expired_returns_none():
    service = translation_module.TranslationService(cache_ttl_seconds=1)
    cache_key = "k"
    service._cache[cache_key] = {"value": "cached", "timestamp": 10.0}

    assert service._get_cached_value(cache_key=cache_key, now=11.0) is None


def test_service_monitor_check_health_missing_service_returns_empty_list():
    registry = ServiceRegistry()
    monitor = ServiceHealthMonitor(registry)
    result = asyncio.run(monitor.check_health(service_name="missing"))
    assert result == []


def test_service_monitor_check_health_exception_marks_service_offline(monkeypatch):
    registry = ServiceRegistry()
    registry.services = {
        "svc": ServiceInfo(name="svc", service_type="api", endpoint="http://x"),
    }
    monitor = ServiceHealthMonitor(registry)

    async def _fail(_service):
        raise RuntimeError("boom")

    monkeypatch.setattr(monitor, "_check_service_health", _fail)
    result = asyncio.run(monitor.check_health())

    assert len(result) == 1
    assert result[0].status == ServiceStatus.OFFLINE
    assert result[0].error_message == "boom"


def test_governance_extract_actor_uses_x_user_id_fallback():
    request = SimpleNamespace(
        state=SimpleNamespace(user=None),
        headers={"X-User-Id": "uid-1"},
    )
    assert governance_routes._extract_actor_from_request(request) == "uid-1"


def test_governance_set_autonomy_invalid_level_publishes_failure(monkeypatch):
    previous = permission_guard.get_current_level()
    stream = get_audit_stream()
    stream.clear()

    monkeypatch.setattr(governance_routes, "get_audit_stream", lambda: stream)
    monkeypatch.setattr(permission_guard, "get_current_level", lambda: 0)
    monkeypatch.setattr(permission_guard, "set_level", lambda _level: False)
    monkeypatch.setattr(
        permission_guard,
        "get_level_info",
        lambda level: SimpleNamespace(name="ISOLATED") if level == 0 else None,
    )

    request = SimpleNamespace(
        state=SimpleNamespace(user=None),
        headers={"X-Actor": "roi-tester"},
    )
    with pytest.raises(HTTPException) as exc:
        governance_routes.set_autonomy_level(
            request=request,
            payload=SimpleNamespace(level=99),
        )
    assert exc.value.status_code == 400
    entries = stream.get_entries(action="autonomy.level_changed", limit=1)
    assert entries and entries[0].status == "failure"
    assert entries[0].details["new_level"] == 99
    permission_guard.set_level(previous)
    stream.clear()


def test_docker_conflict_helpers_cover_branches(monkeypatch):
    class ApiError(Exception):
        def __init__(self, msg: str, status_code=None):
            super().__init__(msg)
            self.status_code = status_code

    monkeypatch.setattr(docker_habitat_mod, "APIError", ApiError)

    assert docker_habitat_mod.DockerHabitat._is_name_conflict_error(
        ApiError("any", status_code=409)
    )
    assert docker_habitat_mod.DockerHabitat._is_name_conflict_error(
        ApiError("already in use")
    )
    assert (
        docker_habitat_mod.DockerHabitat._resolve_conflict_retries(
            docker_habitat_mod.DockerHabitat, None
        )
        == docker_habitat_mod.DockerHabitat.CONTAINER_CONFLICT_RETRIES
    )
    assert (
        docker_habitat_mod.DockerHabitat._resolve_conflict_retries(
            docker_habitat_mod.DockerHabitat, -3
        )
        == 0
    )


def test_docker_wait_until_absent_handles_timeout_and_notfound(monkeypatch):
    class NotFoundError(Exception):
        pass

    monkeypatch.setattr(docker_habitat_mod, "NotFound", NotFoundError)
    ticks = {"now": 0.0}

    def fake_time():
        ticks["now"] += 1.0
        return ticks["now"]

    monkeypatch.setattr(docker_habitat_mod.time, "time", fake_time)
    monkeypatch.setattr(docker_habitat_mod.time, "sleep", lambda _x: None)

    def _raise_not_found(_name):
        raise NotFoundError()

    client_not_found = SimpleNamespace(containers=SimpleNamespace(get=_raise_not_found))
    habitat = _new_docker_habitat_with_client(client_not_found)
    habitat._wait_until_container_absent()

    client_timeout = SimpleNamespace(
        containers=SimpleNamespace(get=lambda _name: _DummyDockerContainer())
    )
    habitat_timeout = _new_docker_habitat_with_client(client_timeout)
    habitat_timeout._wait_until_container_absent()


def test_docker_recover_from_name_conflict_notfound_path(monkeypatch, tmp_path):
    class NotFoundError(Exception):
        pass

    class ApiError(Exception):
        pass

    monkeypatch.setattr(docker_habitat_mod, "NotFound", NotFoundError)
    monkeypatch.setattr(docker_habitat_mod, "APIError", ApiError)
    workspace = tmp_path / "ws"
    workspace.mkdir(parents=True, exist_ok=True)

    def _raise_not_found(_name):
        raise NotFoundError()

    client = SimpleNamespace(containers=SimpleNamespace(get=_raise_not_found))
    habitat = _new_docker_habitat_with_client(client)
    habitat._resolve_workspace_path = lambda: workspace
    habitat._remove_container_by_name_if_exists = lambda: None
    expected_container = _DummyDockerContainer()
    habitat._create_container = lambda *args, **kwargs: expected_container

    result = habitat._recover_from_name_conflict(
        error=ApiError("conflict"),
        workspace_path=workspace,
        retries_left=1,
    )
    assert result is expected_container


def test_docker_create_container_raises_runtime_on_non_conflict_api_error(
    monkeypatch, tmp_path
):
    class ApiError(Exception):
        def __init__(self, msg: str, status_code=None):
            super().__init__(msg)
            self.status_code = status_code

    monkeypatch.setattr(docker_habitat_mod, "APIError", ApiError)
    monkeypatch.setattr(docker_habitat_mod.SETTINGS, "DOCKER_IMAGE_NAME", "venom-image")
    workspace = tmp_path / "ws"
    workspace.mkdir(parents=True, exist_ok=True)
    client = SimpleNamespace(images=SimpleNamespace(get=lambda _img: object()))
    habitat = _new_docker_habitat_with_client(client)
    habitat._resolve_workspace_path = lambda: workspace
    habitat._run_container = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        ApiError("forbidden", status_code=403)
    )

    with pytest.raises(RuntimeError, match="Błąd API Docker"):
        habitat._create_container(workspace)


def test_docker_recover_from_name_conflict_raises_when_retries_exhausted(
    monkeypatch, tmp_path
):
    class ApiError(Exception):
        pass

    monkeypatch.setattr(docker_habitat_mod, "APIError", ApiError)
    workspace = tmp_path / "ws"
    workspace.mkdir(parents=True, exist_ok=True)
    habitat = _new_docker_habitat_with_client(
        SimpleNamespace(containers=SimpleNamespace())
    )

    with pytest.raises(RuntimeError, match="Wyczerpano limit retry"):
        habitat._recover_from_name_conflict(
            error=ApiError("conflict"),
            workspace_path=workspace,
            retries_left=0,
        )


def test_system_generate_external_map_covers_config_branches(monkeypatch):
    monkeypatch.setattr(
        system_routes.SETTINGS, "LLM_SERVICE_TYPE", "local", raising=False
    )
    monkeypatch.setattr(
        system_routes.SETTINGS, "ACTIVE_LLM_SERVER", "ollama", raising=False
    )
    monkeypatch.setattr(system_routes.SETTINGS, "AI_MODE", "CLOUD", raising=False)
    monkeypatch.setattr(
        system_routes.SETTINGS, "HYBRID_CLOUD_PROVIDER", "openai", raising=False
    )
    monkeypatch.setattr(
        system_routes.SETTINGS, "TAVILY_API_KEY", _Secret("t"), raising=False
    )
    monkeypatch.setattr(
        system_routes.SETTINGS, "ENABLE_GOOGLE_CALENDAR", True, raising=False
    )
    monkeypatch.setattr(
        system_routes.SETTINGS, "ENABLE_HF_INTEGRATION", True, raising=False
    )
    monkeypatch.setattr(
        system_routes.SETTINGS, "HF_TOKEN", _Secret("hf"), raising=False
    )
    monkeypatch.setattr(system_routes.SETTINGS, "OPENAI_API_KEY", "k", raising=False)
    monkeypatch.setattr(system_routes.SETTINGS, "GOOGLE_API_KEY", "k2", raising=False)

    external = system_routes._generate_external_map()
    targets = {c.target_component for c in external}

    assert any(target.startswith("Local LLM") for target in targets)
    assert any(target.startswith("Cloud LLM") for target in targets)
    assert "Tavily AI Search" in targets
    assert "Google Calendar API" in targets
    assert "Hugging Face Hub" in targets
    assert "OpenAI API" in targets
    assert "Google AI Studio" in targets
    assert "Stable Diffusion" in targets


def test_system_generate_internal_map_optional_components(monkeypatch):
    app = FastAPI()
    test_router = APIRouter()

    @test_router.get("/api/v1/system/status")
    def _status():
        return {"ok": True}

    @test_router.post("/api/v1/chat")
    def _chat():
        return {"ok": True}

    app.include_router(test_router)
    request = SimpleNamespace(app=app)

    monkeypatch.setattr(system_routes.SETTINGS, "ENABLE_NEXUS", True, raising=False)
    monkeypatch.setattr(system_routes.SETTINGS, "ENABLE_HIVE", True, raising=False)

    internal = system_routes._generate_internal_map(request)
    targets = {c.target_component for c in internal}

    assert "System Status API" in targets
    assert "Frontend (Next.js)" in targets
    assert "Node (Worker)" in targets
    assert "Redis" in targets


def test_system_api_map_cache_and_runtime_update(monkeypatch):
    app = FastAPI()
    app.include_router(system_routes.router)
    client = TestClient(app)

    monitor = SimpleNamespace(
        get_all_services=lambda: [
            SimpleNamespace(name="Redis", status=SimpleNamespace(value="offline"))
        ]
    )

    monkeypatch.setattr(system_routes.SETTINGS, "ENABLE_HIVE", True, raising=False)

    with patch(
        "venom_core.api.routes.system_deps.get_service_monitor", return_value=monitor
    ):
        previous_cache = system_routes._API_MAP_CACHE
        previous_time = system_routes._LAST_CACHE_TIME
        try:
            system_routes._API_MAP_CACHE = None
            system_routes._LAST_CACHE_TIME = 0

            first = client.get("/api/v1/system/api-map")
            second = client.get("/api/v1/system/api-map")

            assert first.status_code == 200
            assert second.status_code == 200
            assert system_routes._API_MAP_CACHE is not None

            redis = next(
                (
                    c
                    for c in first.json()["internal_connections"]
                    if c["target_component"] == "Redis"
                ),
                None,
            )
            assert redis is not None
            assert redis["status"] == "down"
        finally:
            system_routes._API_MAP_CACHE = previous_cache
            system_routes._LAST_CACHE_TIME = previous_time


def test_ensure_learning_log_boot_id_rotates_log(tmp_path, monkeypatch):
    log_path = tmp_path / "requests.jsonl"
    meta_path = tmp_path / "requests_meta.json"
    log_path.write_text('{"legacy": true}\n', encoding="utf-8")
    meta_path.write_text(json.dumps({"boot_id": "old-boot"}), encoding="utf-8")

    monkeypatch.setattr(learning_log_mod, "LEARNING_LOG_PATH", log_path)
    monkeypatch.setattr(learning_log_mod, "LEARNING_LOG_META_PATH", meta_path)
    monkeypatch.setattr(learning_log_mod, "BOOT_ID", "new-boot")

    learning_log_mod.ensure_learning_log_boot_id()

    assert not log_path.exists()
    payload = json.loads(meta_path.read_text(encoding="utf-8"))
    assert payload["boot_id"] == "new-boot"


def test_ensure_learning_log_boot_id_rotates_only_once_per_boot(tmp_path, monkeypatch):
    log_path = tmp_path / "requests.jsonl"
    meta_path = tmp_path / "requests_meta.json"
    log_path.write_text('{"task_id":"t-1"}\n', encoding="utf-8")
    meta_path.write_text(json.dumps({"boot_id": "old-boot"}), encoding="utf-8")

    monkeypatch.setattr(learning_log_mod, "LEARNING_LOG_PATH", log_path)
    monkeypatch.setattr(learning_log_mod, "LEARNING_LOG_META_PATH", meta_path)
    monkeypatch.setattr(learning_log_mod, "BOOT_ID", "stable-boot")
    monkeypatch.setattr(learning_log_mod, "_ROTATION_LOCK_BOOT_ID", None)

    learning_log_mod.ensure_learning_log_boot_id()
    assert not log_path.exists()

    # Simulate concurrent worker process rewriting meta with a different boot id.
    log_path.write_text('{"task_id":"t-2"}\n', encoding="utf-8")
    meta_path.write_text(json.dumps({"boot_id": "worker-boot"}), encoding="utf-8")

    learning_log_mod.ensure_learning_log_boot_id()

    assert log_path.exists()
    assert log_path.read_text(encoding="utf-8").strip() == '{"task_id":"t-2"}'
    payload = json.loads(meta_path.read_text(encoding="utf-8"))
    assert payload["boot_id"] == "stable-boot"


def test_append_learning_log_entry_sets_timestamp(tmp_path, monkeypatch):
    log_path = tmp_path / "requests.jsonl"
    meta_path = tmp_path / "requests_meta.json"

    monkeypatch.setattr(learning_log_mod, "LEARNING_LOG_PATH", log_path)
    monkeypatch.setattr(learning_log_mod, "LEARNING_LOG_META_PATH", meta_path)
    monkeypatch.setattr(learning_log_mod, "BOOT_ID", "boot-id")
    monkeypatch.setattr(
        learning_log_mod, "get_utc_now_iso", lambda: "2026-02-18T12:00:00Z"
    )

    learning_log_mod.append_learning_log_entry({"event": "iteration_completed"})
    row = json.loads(log_path.read_text(encoding="utf-8").strip())

    assert row["event"] == "iteration_completed"
    assert row["timestamp"] == "2026-02-18T12:00:00Z"


def test_provider_observability_history_trim_and_singleton(monkeypatch):
    obs = ProviderObservability()
    for idx in range(101):
        emitted = obs.emit_alert(
            Alert(
                id=f"a-{idx}",
                severity=AlertSeverity.WARNING,
                alert_type=AlertType.HIGH_LATENCY,
                provider="openai",
                message="providers.alerts.highLatency",
                fingerprint=f"fp-{idx}",
            )
        )
        assert emitted

    assert len(obs.alert_history) == 100
    assert obs.alert_history[0].id == "a-1"

    monkeypatch.setattr(observability_mod, "_observability_instance", None)
    first = observability_mod.get_provider_observability()
    second = observability_mod.get_provider_observability()
    assert first is second


def test_provider_observability_budget_alert_disabled():
    obs = ProviderObservability()
    obs.set_slo_target("custom", SLOTarget(provider="custom", cost_budget_usd=0.0))
    status = obs.calculate_slo_status(
        "custom",
        {
            "success_rate": 100.0,
            "error_rate": 0.0,
            "latency": {"p99_ms": 100.0},
            "cost": {"total_usd": 999.0},
        },
    )

    assert obs._build_budget_alert("custom", status) is None


@pytest.mark.asyncio
async def test_iot_reconnect_legacy_without_connect_method(monkeypatch):
    class LegacyBridge:
        connected = False
        connect = None

    monkeypatch.setattr(iot_routes.SETTINGS, "ENABLE_IOT_BRIDGE", True, raising=False)
    monkeypatch.setattr(
        iot_routes.system_deps, "get_hardware_bridge", lambda: LegacyBridge()
    )

    result = await iot_routes.reconnect_iot_bridge()
    assert result.connected is False
    assert result.attempts == 1


@pytest.mark.asyncio
async def test_iot_reconnect_handles_exception(monkeypatch):
    class BrokenBridge:
        async def reconnect(self):
            raise RuntimeError("boom")

    monkeypatch.setattr(iot_routes.SETTINGS, "ENABLE_IOT_BRIDGE", True, raising=False)
    monkeypatch.setattr(
        iot_routes.system_deps, "get_hardware_bridge", lambda: BrokenBridge()
    )

    result = await iot_routes.reconnect_iot_bridge()
    assert result.connected is False
    assert result.attempts == 1
    assert "Błąd reconnect" in (result.message or "")
