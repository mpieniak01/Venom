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


def test_perform_action_for_config_controlled_service():
    controller = RuntimeController()
    result = controller._perform_action(ServiceType.HIVE, action="start")
    assert result["success"] is False
    assert "konfig" in result["message"].lower()


def test_apply_profile_unknown():
    controller = RuntimeController()
    result = controller.apply_profile("nope")
    assert result["success"] is False
    assert "Nieznany profil" in result["message"]


def test_apply_profile_light_starts_core_services(monkeypatch):
    controller = RuntimeController()
    started = []
    stopped = []

    def fake_start(service_type):
        started.append(service_type)
        return {"success": True, "message": f"started {service_type.value}"}

    def fake_stop(service_type):
        stopped.append(service_type)
        return {"success": True, "message": f"stopped {service_type.value}"}

    monkeypatch.setattr(controller, "start_service", fake_start)
    monkeypatch.setattr(controller, "stop_service", fake_stop)

    result = controller.apply_profile("light")
    assert result["success"] is True
    assert ServiceType.BACKEND in started
    assert ServiceType.UI in started
    assert ServiceType.LLM_OLLAMA in stopped
    assert ServiceType.LLM_VLLM in stopped
