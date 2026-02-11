import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

import venom_core.main as main_module


def test_setup_router_dependencies_wires_globals(monkeypatch):
    calls = {}

    def make_dummy(name):
        def set_dependencies(*args, **kwargs):
            calls[name] = {"args": args, "kwargs": kwargs}

        return SimpleNamespace(set_dependencies=set_dependencies, router=None)

    monkeypatch.setattr(main_module, "tasks_routes", make_dummy("tasks"))
    monkeypatch.setattr(main_module, "feedback_routes", make_dummy("feedback"))
    monkeypatch.setattr(main_module, "queue_routes", make_dummy("queue"))
    monkeypatch.setattr(main_module, "metrics_routes", make_dummy("metrics"))
    monkeypatch.setattr(main_module, "memory_routes", make_dummy("memory"))
    monkeypatch.setattr(main_module, "git_routes", make_dummy("git"))
    monkeypatch.setattr(main_module, "knowledge_routes", make_dummy("knowledge"))
    monkeypatch.setattr(main_module, "agents_routes", make_dummy("agents"))
    monkeypatch.setattr(main_module, "system_deps", make_dummy("system_deps"))
    monkeypatch.setattr(main_module, "nodes_routes", make_dummy("nodes"))
    monkeypatch.setattr(main_module, "strategy_routes", make_dummy("strategy"))
    monkeypatch.setattr(main_module, "models_routes", make_dummy("models"))
    monkeypatch.setattr(main_module, "flow_routes", make_dummy("flow"))
    monkeypatch.setattr(main_module, "benchmark_routes", make_dummy("benchmark"))
    monkeypatch.setattr(main_module, "calendar_routes", make_dummy("calendar"))

    monkeypatch.setattr(main_module, "orchestrator", object())
    monkeypatch.setattr(main_module, "state_manager", object())
    monkeypatch.setattr(main_module, "request_tracer", object())
    monkeypatch.setattr(main_module, "vector_store", object())
    monkeypatch.setattr(main_module, "git_skill", object())
    monkeypatch.setattr(main_module, "graph_store", object())
    monkeypatch.setattr(main_module, "lessons_store", object())
    monkeypatch.setattr(main_module, "gardener_agent", object())
    monkeypatch.setattr(main_module, "shadow_agent", object())
    monkeypatch.setattr(main_module, "file_watcher", object())
    monkeypatch.setattr(main_module, "documenter_agent", object())
    monkeypatch.setattr(main_module, "background_scheduler", object())
    monkeypatch.setattr(
        main_module, "service_monitor", SimpleNamespace(set_orchestrator=lambda x: None)
    )
    monkeypatch.setattr(main_module, "llm_controller", object())
    monkeypatch.setattr(main_module, "model_manager", object())
    monkeypatch.setattr(main_module, "node_manager", object())
    monkeypatch.setattr(main_module, "benchmark_service", object())
    monkeypatch.setattr(main_module, "google_calendar_skill", object())
    monkeypatch.setattr(main_module, "model_registry", object())
    monkeypatch.setattr(main_module, "hardware_bridge", object())

    main_module.setup_router_dependencies()

    assert calls["tasks"]["args"][0] is main_module.orchestrator
    assert calls["tasks"]["args"][1] is main_module.state_manager
    assert calls["tasks"]["args"][2] is main_module.request_tracer
    assert calls["system_deps"]["args"][0] is main_module.background_scheduler
    assert calls["system_deps"]["args"][1] is main_module.service_monitor
    assert calls["models"]["kwargs"]["model_registry"] is main_module.model_registry


def _install_academy_dummy_modules(monkeypatch):
    professor_mod = ModuleType("venom_core.agents.professor")
    dataset_mod = ModuleType("venom_core.learning.dataset_curator")
    habitat_mod = ModuleType("venom_core.infrastructure.gpu_habitat")

    class DummyProfessor:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class DummyDatasetCurator:
        def __init__(self, lessons_store):
            self.lessons_store = lessons_store

    class DummyGPUHabitat:
        def __init__(self, enable_gpu):
            self.enable_gpu = enable_gpu

    professor_mod.Professor = DummyProfessor
    dataset_mod.DatasetCurator = DummyDatasetCurator
    habitat_mod.GPUHabitat = DummyGPUHabitat

    monkeypatch.setitem(sys.modules, "venom_core.agents.professor", professor_mod)
    monkeypatch.setitem(sys.modules, "venom_core.learning.dataset_curator", dataset_mod)
    monkeypatch.setitem(
        sys.modules, "venom_core.infrastructure.gpu_habitat", habitat_mod
    )


def test_initialize_academy_restores_active_adapter(monkeypatch):
    _install_academy_dummy_modules(monkeypatch)
    monkeypatch.setattr(main_module.SETTINGS, "ENABLE_ACADEMY", True, raising=False)
    monkeypatch.setattr(
        main_module.SETTINGS, "ACADEMY_ENABLE_GPU", False, raising=False
    )
    monkeypatch.setattr(main_module, "lessons_store", object())
    monkeypatch.setattr(main_module, "orchestrator", SimpleNamespace(kernel=object()))
    model_manager = MagicMock()
    model_manager.restore_active_adapter.return_value = True
    monkeypatch.setattr(main_module, "model_manager", model_manager)

    main_module._initialize_academy()

    assert main_module.dataset_curator is not None
    assert main_module.gpu_habitat is not None
    assert main_module.professor is not None
    model_manager.restore_active_adapter.assert_called_once()


def test_initialize_academy_restore_error_falls_back(monkeypatch):
    _install_academy_dummy_modules(monkeypatch)
    monkeypatch.setattr(main_module.SETTINGS, "ENABLE_ACADEMY", True, raising=False)
    monkeypatch.setattr(main_module.SETTINGS, "ACADEMY_ENABLE_GPU", True, raising=False)
    monkeypatch.setattr(main_module, "lessons_store", object())
    monkeypatch.setattr(main_module, "orchestrator", SimpleNamespace(kernel=object()))
    model_manager = MagicMock()
    model_manager.restore_active_adapter.side_effect = RuntimeError("restore failed")
    monkeypatch.setattr(main_module, "model_manager", model_manager)

    main_module._initialize_academy()

    assert main_module.professor is not None
    model_manager.restore_active_adapter.assert_called_once()


def test_initialize_academy_disabled_returns_early(monkeypatch):
    monkeypatch.setattr(main_module.SETTINGS, "ENABLE_ACADEMY", False, raising=False)
    main_module._initialize_academy()
