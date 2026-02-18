from unittest.mock import AsyncMock, MagicMock

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
    good_bridge = MagicMock()
    good_bridge.read_sensor = AsyncMock(return_value=42.34)
    good_bridge.execute_command = AsyncMock(
        return_value={"return_code": 0, "stdout": " 123/456MB "}
    )

    bad_bridge = MagicMock()
    bad_bridge.read_sensor = AsyncMock(side_effect=RuntimeError("boom"))
    bad_bridge.execute_command = AsyncMock(
        return_value={"return_code": 1, "stdout": "x"}
    )

    assert await system_iot_routes._read_cpu_temperature(good_bridge) == "42.3°C"
    assert await system_iot_routes._read_cpu_temperature(bad_bridge) is None
    assert (
        await system_iot_routes._read_bridge_command_metric(
            good_bridge, "cmd", "warn-msg"
        )
        == "123/456MB"
    )
    assert (
        await system_iot_routes._read_bridge_command_metric(bad_bridge, "cmd", "warn")
        is None
    )

    exploding_bridge = MagicMock()
    exploding_bridge.execute_command = AsyncMock(side_effect=RuntimeError("boom"))

    assert (
        await system_iot_routes._read_bridge_command_metric(
            exploding_bridge, "cmd", "warn"
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
async def test_reconnect_iot_bridge_paths(monkeypatch):
    monkeypatch.setattr(
        system_iot_routes.SETTINGS, "ENABLE_IOT_BRIDGE", False, raising=False
    )
    disabled = await system_iot_routes.reconnect_iot_bridge()
    assert disabled.connected is False
    assert disabled.attempts == 0

    monkeypatch.setattr(
        system_iot_routes.SETTINGS, "ENABLE_IOT_BRIDGE", True, raising=False
    )
    monkeypatch.setattr(system_deps, "get_hardware_bridge", lambda: None)
    missing = await system_iot_routes.reconnect_iot_bridge()
    assert missing.connected is False
    assert missing.attempts == 0

    bridge = MagicMock()
    bridge.reconnect = AsyncMock(return_value={"connected": True, "attempts": 2})
    monkeypatch.setattr(system_deps, "get_hardware_bridge", lambda: bridge)
    success = await system_iot_routes.reconnect_iot_bridge()
    assert success.connected is True
    assert success.attempts == 2

    legacy_bridge = type(
        "LegacyBridge",
        (),
        {
            "connected": True,
            "disconnect": AsyncMock(),
            "connect": AsyncMock(return_value=False),
        },
    )()
    monkeypatch.setattr(system_deps, "get_hardware_bridge", lambda: legacy_bridge)
    legacy = await system_iot_routes.reconnect_iot_bridge()
    assert legacy.connected is False
    assert legacy.attempts == 1


@pytest.mark.asyncio
async def test_get_service_status_not_found(monkeypatch):
    class DummyMonitor:
        def get_all_services(self):
            return []

    monkeypatch.setattr(system_deps, "_service_monitor", DummyMonitor())
    with pytest.raises(HTTPException) as exc:
        await system_services_routes.get_service_status("missing")
    assert exc.value.status_code == 404
