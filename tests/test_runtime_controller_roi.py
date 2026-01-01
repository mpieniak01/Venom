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


def test_actionable_field_for_controllable_services(monkeypatch):
    """Test że usługi sterowalne (backend, ui, llm_ollama, llm_vllm) mają actionable=True."""
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

    # Test backend
    backend_info = controller.get_service_status(ServiceType.BACKEND)
    assert backend_info.actionable is True

    # Test UI
    ui_info = controller.get_service_status(ServiceType.UI)
    assert ui_info.actionable is True

    # Test LLM Ollama
    ollama_info = controller.get_service_status(ServiceType.LLM_OLLAMA)
    assert ollama_info.actionable is True

    # Test LLM vLLM
    vllm_info = controller.get_service_status(ServiceType.LLM_VLLM)
    assert vllm_info.actionable is True


def test_actionable_field_for_config_based_services(monkeypatch):
    """Test że usługi konfigurowalne (hive, nexus, background_tasks) mają actionable=False."""
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

    # Test Hive
    hive_info = controller.get_service_status(ServiceType.HIVE)
    assert hive_info.actionable is False

    # Test Nexus
    nexus_info = controller.get_service_status(ServiceType.NEXUS)
    assert nexus_info.actionable is False

    # Test Background Tasks
    bg_tasks_info = controller.get_service_status(ServiceType.BACKGROUND_TASKS)
    assert bg_tasks_info.actionable is False
