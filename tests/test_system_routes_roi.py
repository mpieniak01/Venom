from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from venom_core.api.routes import system_deps
from venom_core.api.routes import system_iot as system_iot_routes
from venom_core.api.routes import system_metrics as system_metrics_routes
from venom_core.api.routes import system_services as system_services_routes


@pytest.mark.asyncio
async def test_get_metrics_requires_collector(monkeypatch):
    monkeypatch.setattr(system_metrics_routes.metrics_module, "metrics_collector", None)
    with pytest.raises(HTTPException) as exc:
        await system_metrics_routes.get_metrics()
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_get_iot_status_disabled(monkeypatch):
    monkeypatch.setattr(
        system_iot_routes.SETTINGS, "ENABLE_IOT_BRIDGE", False, raising=False
    )
    response = await system_iot_routes.get_iot_status()
    assert response.connected is False
    assert "wyłączony" in (response.message or "")


@pytest.mark.asyncio
async def test_iot_helper_responses():
    assert "wyłączony" in (system_iot_routes._iot_disabled_response().message or "")
    assert "Brak połączenia" in (
        system_iot_routes._iot_disconnected_response().message or ""
    )
    assert "telemetria tylko w trybie SSH" in (
        system_iot_routes._iot_non_ssh_response().message or ""
    )


@pytest.mark.asyncio
async def test_iot_metric_helpers(monkeypatch):
    class GoodBridge:
        async def read_sensor(self, _name):
            return 42.34

        async def execute_command(self, _command):
            return {"return_code": 0, "stdout": " 123/456MB "}

    class BadBridge:
        async def read_sensor(self, _name):
            raise RuntimeError("boom")

        async def execute_command(self, _command):
            return {"return_code": 1, "stdout": "x"}

    assert await system_iot_routes._read_cpu_temperature(GoodBridge()) == "42.3°C"
    assert await system_iot_routes._read_cpu_temperature(BadBridge()) is None
    assert (
        await system_iot_routes._read_bridge_command_metric(
            GoodBridge(), "cmd", "warn-msg"
        )
        == "123/456MB"
    )
    assert (
        await system_iot_routes._read_bridge_command_metric(BadBridge(), "cmd", "warn")
        is None
    )

    class ExplodingBridge:
        async def execute_command(self, _command):
            raise RuntimeError("boom")

    assert (
        await system_iot_routes._read_bridge_command_metric(
            ExplodingBridge(), "cmd", "warn"
        )
        is None
    )


@pytest.mark.asyncio
async def test_get_iot_status_non_ssh_and_ssh_metrics(monkeypatch):
    monkeypatch.setattr(
        system_iot_routes.SETTINGS, "ENABLE_IOT_BRIDGE", True, raising=False
    )

    non_ssh = type("Bridge", (), {"connected": True, "protocol": "serial"})()
    monkeypatch.setattr(system_deps, "get_hardware_bridge", lambda: non_ssh)
    response = await system_iot_routes.get_iot_status()
    assert response.connected is True
    assert "telemetria tylko w trybie SSH" in (response.message or "")

    ssh_bridge = type("Bridge", (), {"connected": True, "protocol": "ssh"})()
    monkeypatch.setattr(system_deps, "get_hardware_bridge", lambda: ssh_bridge)
    monkeypatch.setattr(
        system_iot_routes, "_read_cpu_temperature", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        system_iot_routes, "_read_bridge_command_metric", AsyncMock(return_value=None)
    )
    response = await system_iot_routes.get_iot_status()
    assert response.connected is True
    assert "Brak danych telemetrycznych" in (response.message or "")


@pytest.mark.asyncio
async def test_get_service_status_not_found(monkeypatch):
    class DummyMonitor:
        def get_all_services(self):
            return []

    monkeypatch.setattr(system_deps, "_service_monitor", DummyMonitor())
    with pytest.raises(HTTPException) as exc:
        await system_services_routes.get_service_status("missing")
    assert exc.value.status_code == 404
