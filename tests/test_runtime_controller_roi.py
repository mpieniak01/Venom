from types import SimpleNamespace

import psutil
import pytest

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
    """Test że usługi konfigurowalne mają actionable=False."""
    controller = RuntimeController()
    monkeypatch.setattr(
        runtime_controller,
        "SETTINGS",
        SimpleNamespace(
            ENABLE_HIVE=True,
            ENABLE_NEXUS=True,
            VENOM_PAUSE_BACKGROUND_TASKS=False,
            ENABLE_ACADEMY=True,
            ENABLE_INTENT_EMBEDDING_ROUTER=True,
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

    # Test Academy
    academy_info = controller.get_service_status(ServiceType.ACADEMY)
    assert academy_info.actionable is False

    # Test Intent Embedding Router
    embedding_info = controller.get_service_status(ServiceType.INTENT_EMBEDDING_ROUTER)
    assert embedding_info.actionable is False


def test_perform_action_for_config_controlled_service():
    controller = RuntimeController()
    result = controller._perform_action(ServiceType.HIVE, action="start")
    assert result["success"] is False
    assert "konfig" in result["message"].lower()


def test_apply_profile_unknown():
    controller = RuntimeController()
    result = controller.apply_profile("nope")
    assert result["success"] is False
    assert "Unknown profile" in result["message"]


@pytest.mark.parametrize(
    "selected", ["ollama", "vllm", "none", "openrouter", "multi_runtime"]
)
@pytest.mark.parametrize(
    "active,requested", [("full", "light"), ("light", "full"), ("full", "full")]
)
def test_apply_profile_preserves_provider_and_requires_restart(
    monkeypatch, selected, active, requested
):
    controller = RuntimeController()
    monkeypatch.setattr(
        runtime_controller,
        "SETTINGS",
        SimpleNamespace(ACTIVE_LLM_SERVER=selected, VENOM_RUNTIME_PROFILE=active),
    )
    monkeypatch.setattr(
        controller, "start_service", lambda *_: pytest.fail("must not start a provider")
    )
    monkeypatch.setattr(
        controller,
        "stop_service",
        lambda *_: pytest.fail("must not stop another environment"),
    )
    result = controller.apply_profile(requested)
    assert result["success"] is (active == requested)
    if active != requested:
        assert result["restart_required"] is True
    assert runtime_controller.SETTINGS.ACTIVE_LLM_SERVER == selected


def test_legacy_llm_off_does_not_stop_shared_llm(monkeypatch):
    controller = RuntimeController()
    monkeypatch.setattr(
        controller,
        "stop_service",
        lambda *_: pytest.fail("shared provider must survive"),
    )
    assert controller.apply_profile("llm_off")["success"] is False


def test_update_pid_file_service_status_backend_and_ui(tmp_path):
    controller = RuntimeController()
    backend_pid = tmp_path / ".venom.pid"
    ui_pid = tmp_path / ".web-next.pid"
    backend_pid.write_text("123", encoding="utf-8")
    ui_pid.write_text("321", encoding="utf-8")
    controller.pid_files = {ServiceType.BACKEND: backend_pid, ServiceType.UI: ui_pid}
    controller._get_process_info = lambda _pid: {"cpu_percent": 1.0, "memory_mb": 2.0}

    backend_info = ServiceInfo("backend", ServiceType.BACKEND, ServiceStatus.UNKNOWN)
    controller._update_pid_file_service_status(backend_info, ServiceType.BACKEND)
    assert backend_info.status == ServiceStatus.RUNNING
    assert backend_info.port == 8000

    ui_info = ServiceInfo("ui", ServiceType.UI, ServiceStatus.UNKNOWN)
    controller._update_pid_file_service_status(ui_info, ServiceType.UI)
    assert ui_info.status == ServiceStatus.RUNNING
    assert ui_info.port == 3000


def test_update_pid_file_service_status_stopped_and_error(monkeypatch):
    controller = RuntimeController()
    info = ServiceInfo("backend", ServiceType.BACKEND, ServiceStatus.UNKNOWN)
    monkeypatch.setattr(controller, "_read_pid_file", lambda _st: None)
    controller._update_pid_file_service_status(info, ServiceType.BACKEND)
    assert info.status == ServiceStatus.STOPPED

    info2 = ServiceInfo("backend", ServiceType.BACKEND, ServiceStatus.UNKNOWN)
    monkeypatch.setattr(
        controller,
        "_read_pid_file",
        lambda _st: (_ for _ in ()).throw(ValueError("bad")),
    )
    controller._update_pid_file_service_status(info2, ServiceType.BACKEND)
    assert info2.status == ServiceStatus.ERROR


def test_update_llm_status_stopped_and_running(monkeypatch):
    controller = RuntimeController()
    info = ServiceInfo("ollama", ServiceType.LLM_OLLAMA, ServiceStatus.UNKNOWN)
    monkeypatch.setattr(controller, "_check_port_listening", lambda _port: False)
    controller._update_llm_status(
        info,
        port=11434,
        process_match="ollama",
        service_type=ServiceType.LLM_OLLAMA,
    )
    assert info.status == ServiceStatus.STOPPED

    class DummyProc:
        def __init__(self):
            self.info = {"pid": 99, "name": "ollama", "cmdline": ["serve"]}

    info2 = ServiceInfo("ollama", ServiceType.LLM_OLLAMA, ServiceStatus.UNKNOWN)
    monkeypatch.setattr(controller, "_check_port_listening", lambda _port: True)
    monkeypatch.setattr(psutil, "process_iter", lambda _attrs: [DummyProc()])
    monkeypatch.setattr(
        controller, "_apply_process_metrics", lambda _i, pid: setattr(_i, "pid", pid)
    )
    controller._update_llm_status(
        info2,
        port=11434,
        process_match="ollama",
        service_type=ServiceType.LLM_OLLAMA,
    )
    assert info2.status == ServiceStatus.RUNNING
    assert info2.pid == 99


def test_update_config_managed_status_variants(monkeypatch):
    controller = RuntimeController()
    monkeypatch.setattr(
        runtime_controller,
        "SETTINGS",
        SimpleNamespace(
            ENABLE_HIVE=True,
            ENABLE_NEXUS=True,
            NEXUS_PORT=7788,
            VENOM_PAUSE_BACKGROUND_TASKS=True,
            ENABLE_ACADEMY=True,
            ENABLE_INTENT_EMBEDDING_ROUTER=False,
        ),
    )
    hive = ServiceInfo("hive", ServiceType.HIVE, ServiceStatus.UNKNOWN)
    controller._update_config_managed_status(hive, ServiceType.HIVE)
    assert hive.status == ServiceStatus.RUNNING

    nexus = ServiceInfo("nexus", ServiceType.NEXUS, ServiceStatus.UNKNOWN)
    controller._update_config_managed_status(nexus, ServiceType.NEXUS)
    assert nexus.status == ServiceStatus.RUNNING
    assert nexus.port == 7788

    bg = ServiceInfo("bg", ServiceType.BACKGROUND_TASKS, ServiceStatus.UNKNOWN)
    controller._update_config_managed_status(bg, ServiceType.BACKGROUND_TASKS)
    assert bg.status == ServiceStatus.STOPPED

    academy = ServiceInfo("academy", ServiceType.ACADEMY, ServiceStatus.UNKNOWN)
    controller._update_config_managed_status(academy, ServiceType.ACADEMY)
    assert academy.status == ServiceStatus.RUNNING

    embedding = ServiceInfo(
        "intent_embedding_router",
        ServiceType.INTENT_EMBEDDING_ROUTER,
        ServiceStatus.UNKNOWN,
    )
    controller._update_config_managed_status(
        embedding, ServiceType.INTENT_EMBEDDING_ROUTER
    )
    assert embedding.status == ServiceStatus.STOPPED


def test_stop_and_restart_paths(monkeypatch):
    controller = RuntimeController()
    monkeypatch.setattr(
        controller,
        "get_service_status",
        lambda _st: ServiceInfo("svc", ServiceType.BACKEND, ServiceStatus.STOPPED),
    )
    stopped = controller.stop_service(ServiceType.BACKEND)
    assert stopped["success"] is True

    monkeypatch.setattr(
        controller, "stop_service", lambda _st: {"success": False, "message": "fail"}
    )
    monkeypatch.setattr(
        controller,
        "get_service_status",
        lambda _st: ServiceInfo("svc", ServiceType.BACKEND, ServiceStatus.RUNNING),
    )
    assert controller.restart_service(ServiceType.BACKEND)["success"] is False

    monkeypatch.setattr(
        controller, "stop_service", lambda _st: {"success": True, "message": "ok"}
    )
    monkeypatch.setattr(
        controller, "start_service", lambda _st: {"success": True, "message": "started"}
    )
    monkeypatch.setattr(runtime_controller.time, "sleep", lambda _s: None)
    assert controller.restart_service(ServiceType.BACKEND)["success"] is True


def test_start_backend_stop_backend_and_ui(monkeypatch):
    controller = RuntimeController()
    monkeypatch.setattr(runtime_controller.time, "sleep", lambda _s: None)
    monkeypatch.setattr(
        runtime_controller.subprocess,
        "Popen",
        lambda *args, **kwargs: SimpleNamespace(pid=1),
    )
    monkeypatch.setattr(
        controller,
        "get_service_status",
        lambda _st: ServiceInfo(
            "backend", ServiceType.BACKEND, ServiceStatus.RUNNING, pid=11
        ),
    )
    assert controller._start_backend()["success"] is True

    monkeypatch.setattr(
        runtime_controller.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stderr=""),
    )
    assert controller._stop_backend()["success"] is True

    monkeypatch.setattr(
        controller,
        "get_service_status",
        lambda _st: ServiceInfo("ui", ServiceType.UI, ServiceStatus.STOPPED),
    )
    assert controller._start_ui()["success"] is False
    assert controller._stop_ui()["success"] is True


def test_ollama_and_vllm_start_stop(monkeypatch):
    controller = RuntimeController()
    monkeypatch.setattr(runtime_controller.time, "sleep", lambda _s: None)
    monkeypatch.setattr(
        runtime_controller,
        "SETTINGS",
        SimpleNamespace(
            OLLAMA_START_COMMAND="echo start_o",
            OLLAMA_STOP_COMMAND="echo stop_o",
            VLLM_START_COMMAND="echo start_v",
            VLLM_STOP_COMMAND="echo stop_v",
        ),
    )
    monkeypatch.setattr(
        runtime_controller.subprocess,
        "Popen",
        lambda *args, **kwargs: SimpleNamespace(pid=1),
    )
    monkeypatch.setattr(
        runtime_controller.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stderr=""),
    )

    monkeypatch.setattr(
        controller,
        "get_service_status",
        lambda service: ServiceInfo(
            service.value, service, ServiceStatus.RUNNING, pid=1
        ),
    )
    assert controller._start_ollama()["success"] is True
    assert controller._stop_ollama()["success"] is True
    assert controller._start_vllm()["success"] is True
    assert controller._stop_vllm()["success"] is True


def test_ollama_start_falls_back_to_repo_script_when_env_command_missing(monkeypatch):
    controller = RuntimeController()
    captured = {}

    monkeypatch.setattr(runtime_controller.time, "sleep", lambda _s: None)
    monkeypatch.setattr(
        runtime_controller,
        "SETTINGS",
        SimpleNamespace(
            OLLAMA_START_COMMAND="",
            OLLAMA_STOP_COMMAND="",
            VLLM_START_COMMAND="",
            VLLM_STOP_COMMAND="",
        ),
    )
    monkeypatch.setattr(
        runtime_controller.subprocess,
        "Popen",
        lambda *args, **kwargs: captured.update({"args": args, "kwargs": kwargs})
        or SimpleNamespace(pid=7),
    )
    monkeypatch.setattr(
        controller,
        "get_service_status",
        lambda service: ServiceInfo(
            service.value, service, ServiceStatus.RUNNING, pid=7
        ),
    )

    result = controller._start_ollama()
    assert result["success"] is True
    assert captured["args"][0] == [
        "bash",
        str(controller.project_root / "scripts/llm/ollama_service.sh"),
        "start",
    ]


def test_get_history_limit():
    controller = RuntimeController()
    controller._add_to_history("a", "start", True, "m1")
    controller._add_to_history("b", "stop", False, "m2")
    assert len(controller.get_history(limit=1)) == 1


def test_start_service_dependency_and_exception_paths(monkeypatch):
    controller = RuntimeController()
    monkeypatch.setattr(
        controller,
        "get_service_status",
        lambda _st: ServiceInfo("svc", ServiceType.BACKEND, ServiceStatus.STOPPED),
    )
    monkeypatch.setattr(
        controller, "_check_service_dependencies", lambda _st: "deps missing"
    )
    result = controller.start_service(ServiceType.BACKEND)
    assert result["success"] is False
    assert "deps missing" in result["message"]

    monkeypatch.setattr(controller, "_check_service_dependencies", lambda _st: None)
    monkeypatch.setattr(
        controller,
        "_perform_action",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("explode")),
    )
    result2 = controller.start_service(ServiceType.BACKEND)
    assert result2["success"] is False
    assert "explode" in result2["message"]


def test_stop_service_exception_path(monkeypatch):
    controller = RuntimeController()
    monkeypatch.setattr(
        controller,
        "get_service_status",
        lambda _st: ServiceInfo("svc", ServiceType.BACKEND, ServiceStatus.RUNNING),
    )
    monkeypatch.setattr(
        controller,
        "_perform_action",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("stop-fail")),
    )
    result = controller.stop_service(ServiceType.BACKEND)
    assert result["success"] is False
    assert "stop-fail" in result["message"]


def test_backend_and_llm_command_failure_paths(monkeypatch):
    controller = RuntimeController()
    monkeypatch.setattr(runtime_controller.time, "sleep", lambda _s: None)
    monkeypatch.setattr(
        runtime_controller.subprocess,
        "Popen",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("popen-fail")),
    )
    assert controller._start_backend()["success"] is False

    monkeypatch.setattr(
        runtime_controller.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stderr="bad"),
    )
    assert controller._stop_backend()["success"] is False

    monkeypatch.setattr(
        runtime_controller,
        "SETTINGS",
        SimpleNamespace(
            OLLAMA_START_COMMAND="",
            OLLAMA_STOP_COMMAND="",
            VLLM_START_COMMAND="",
            VLLM_STOP_COMMAND="",
        ),
    )
    assert controller._start_ollama()["success"] is False
    assert controller._stop_ollama()["success"] is False
    assert controller._start_vllm()["success"] is False
    assert controller._stop_vllm()["success"] is False


def test_backend_start_keeps_preprod_profile_in_make_command(monkeypatch):
    controller = RuntimeController()
    monkeypatch.setattr(
        runtime_controller,
        "SETTINGS",
        SimpleNamespace(ENVIRONMENT_ROLE="preprod", VENOM_RUNTIME_PROFILE="light"),
    )
    launched = []
    monkeypatch.setattr(
        runtime_controller.subprocess,
        "Popen",
        lambda command, **kwargs: launched.append(command),
    )
    monkeypatch.setattr(runtime_controller.time, "sleep", lambda *_: None)
    monkeypatch.setattr(
        controller,
        "get_service_status",
        lambda *_: SimpleNamespace(status=ServiceStatus.RUNNING, pid=123),
    )
    assert controller._start_backend()["success"] is True
    assert launched == [["make", "start", "ENVIRONMENT=preprod", "PROFILE=light"]]


def test_runtime_paths_are_anchored_to_project_when_cwd_differs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    overrides = {
        "PID_FILE": "custom/api.pid",
        "WEB_PID_FILE": "custom/ui.pid",
        "BACKEND_LOG": "custom/api.log",
        "WEB_LOG": "custom/ui.log",
    }
    for key, value in overrides.items():
        monkeypatch.setenv(key, value)
    controller = RuntimeController()
    assert (
        controller.pid_files[ServiceType.BACKEND]
        == controller.project_root / overrides["PID_FILE"]
    )
    assert (
        controller.pid_files[ServiceType.UI]
        == controller.project_root / overrides["WEB_PID_FILE"]
    )
    assert (
        controller.log_files[ServiceType.BACKEND]
        == controller.project_root / overrides["BACKEND_LOG"]
    )
    assert (
        controller.log_files[ServiceType.UI]
        == controller.project_root / overrides["WEB_LOG"]
    )
