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
async def test_get_service_status_not_found(monkeypatch):
    class DummyMonitor:
        def get_all_services(self):
            return []

    monkeypatch.setattr(system_deps, "_service_monitor", DummyMonitor())
    with pytest.raises(HTTPException) as exc:
        await system_services_routes.get_service_status("missing")
    assert exc.value.status_code == 404
