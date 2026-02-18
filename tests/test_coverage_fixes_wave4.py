"""Coverage ROI tests for new-code hotspots."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from venom_core.api.routes import system as system_routes
from venom_core.api.routes import system_iot as iot_routes
from venom_core.core import learning_log as learning_log_mod
from venom_core.core import provider_observability as observability_mod
from venom_core.core.provider_observability import (
    Alert,
    AlertSeverity,
    AlertType,
    ProviderObservability,
    SLOTarget,
)


class _Secret:
    def __init__(self, value: str = ""):
        self._value = value

    def get_secret_value(self) -> str:
        return self._value


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
