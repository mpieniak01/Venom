from types import SimpleNamespace

from venom_core.services import runtime_controller
from venom_core.services.runtime_controller import (
    RuntimeController,
    ServiceInfo,
    ServiceStatus,
    ServiceType,
)


def test_check_dependencies_hive_disabled(monkeypatch):
    controller = RuntimeController()
    monkeypatch.setattr(
        runtime_controller,
        "SETTINGS",
        SimpleNamespace(
            ENABLE_HIVE=False,
            ENABLE_NEXUS=True,
            VENOM_PAUSE_BACKGROUND_TASKS=False,
        ),
    )
    assert (
        controller._check_service_dependencies(ServiceType.HIVE)
        == "Hive jest wyłączone w konfiguracji (ENABLE_HIVE=false)"
    )


def test_check_dependencies_nexus_requires_backend(monkeypatch):
    controller = RuntimeController()
    monkeypatch.setattr(
        runtime_controller,
        "SETTINGS",
        SimpleNamespace(
            ENABLE_HIVE=True,
            ENABLE_NEXUS=True,
            VENOM_PAUSE_BACKGROUND_TASKS=False,
        ),
    )
    monkeypatch.setattr(
        controller,
        "get_service_status",
        lambda _service: ServiceInfo(
            name="backend",
            service_type=ServiceType.BACKEND,
            status=ServiceStatus.STOPPED,
        ),
    )
    assert (
        controller._check_service_dependencies(ServiceType.NEXUS)
        == "Nexus wymaga działającego backendu. Uruchom najpierw backend."
    )


def test_start_service_already_running(monkeypatch):
    controller = RuntimeController()
    monkeypatch.setattr(
        controller,
        "get_service_status",
        lambda _service: ServiceInfo(
            name="backend",
            service_type=ServiceType.BACKEND,
            status=ServiceStatus.RUNNING,
            pid=1234,
        ),
    )
    result = controller.start_service(ServiceType.BACKEND)
    assert result["success"] is False
    assert "już działa" in result["message"]
    assert controller.history
