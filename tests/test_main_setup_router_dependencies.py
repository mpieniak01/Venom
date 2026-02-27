import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import venom_core.main as main_module


def test_setup_router_dependencies_wires_globals(monkeypatch):
    calls = {}

    def make_dummy(name):
        def set_dependencies(*args, **kwargs):
            calls[name] = {"args": args, "kwargs": kwargs}

        return SimpleNamespace(set_dependencies=set_dependencies, router=None)

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

    assert calls["feedback"]["args"][0] is main_module.orchestrator
    assert calls["feedback"]["args"][1] is main_module.state_manager
    assert calls["feedback"]["args"][2] is main_module.request_tracer
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


def test_get_orchestrator_kernel_prefers_task_dispatcher_kernel(monkeypatch):
    sentinel_dispatcher_kernel = object()
    sentinel_orchestrator_kernel = object()
    monkeypatch.setattr(
        main_module,
        "orchestrator",
        SimpleNamespace(
            task_dispatcher=SimpleNamespace(kernel=sentinel_dispatcher_kernel),
            kernel=sentinel_orchestrator_kernel,
        ),
    )

    assert main_module._get_orchestrator_kernel() is sentinel_dispatcher_kernel


def test_get_orchestrator_kernel_falls_back_to_orchestrator_kernel(monkeypatch):
    sentinel_orchestrator_kernel = object()
    monkeypatch.setattr(
        main_module,
        "orchestrator",
        SimpleNamespace(
            task_dispatcher=SimpleNamespace(), kernel=sentinel_orchestrator_kernel
        ),
    )

    assert main_module._get_orchestrator_kernel() is sentinel_orchestrator_kernel


def test_get_orchestrator_kernel_returns_none_when_orchestrator_missing(monkeypatch):
    monkeypatch.setattr(main_module, "orchestrator", None)
    assert main_module._get_orchestrator_kernel() is None


def test_get_orchestrator_skill_manager_from_task_dispatcher(monkeypatch):
    sentinel_skill_manager = object()
    monkeypatch.setattr(
        main_module,
        "orchestrator",
        SimpleNamespace(
            task_dispatcher=SimpleNamespace(skill_manager=sentinel_skill_manager)
        ),
    )

    assert main_module._get_orchestrator_skill_manager() is sentinel_skill_manager


def test_get_orchestrator_skill_manager_returns_none_when_missing(monkeypatch):
    monkeypatch.setattr(
        main_module,
        "orchestrator",
        SimpleNamespace(task_dispatcher=SimpleNamespace()),
    )

    assert main_module._get_orchestrator_skill_manager() is None


def test_select_startup_model_prefers_first_available_when_no_match():
    selected = main_module._select_startup_model(
        {"model-a", "model-b"},
        desired_model="missing-desired",
        previous_model="missing-previous",
    )
    assert selected in {"model-a", "model-b"}


def _patch_setup_routes(monkeypatch):
    def make_dummy():
        return SimpleNamespace(
            set_dependencies=lambda *args, **kwargs: None, router=None
        )

    monkeypatch.setattr(main_module, "tasks_routes", make_dummy())
    monkeypatch.setattr(main_module, "feedback_routes", make_dummy())
    monkeypatch.setattr(main_module, "queue_routes", make_dummy())
    monkeypatch.setattr(main_module, "metrics_routes", make_dummy())
    monkeypatch.setattr(main_module, "memory_routes", make_dummy())
    monkeypatch.setattr(main_module, "memory_projection_routes", make_dummy())
    monkeypatch.setattr(main_module, "git_routes", make_dummy())
    monkeypatch.setattr(main_module, "knowledge_routes", make_dummy())
    monkeypatch.setattr(main_module, "agents_routes", make_dummy())
    monkeypatch.setattr(main_module, "academy_routes", make_dummy())
    monkeypatch.setattr(main_module, "system_deps", make_dummy())
    monkeypatch.setattr(main_module, "nodes_routes", make_dummy())
    monkeypatch.setattr(main_module, "strategy_routes", make_dummy())
    monkeypatch.setattr(main_module, "models_routes", make_dummy())
    monkeypatch.setattr(main_module, "flow_routes", make_dummy())
    monkeypatch.setattr(main_module, "benchmark_routes", make_dummy())
    monkeypatch.setattr(main_module, "calendar_routes", make_dummy())


def _patch_setup_runtime_globals(monkeypatch):
    monkeypatch.setattr(main_module, "state_manager", object())
    monkeypatch.setattr(main_module, "request_tracer", object())
    monkeypatch.setattr(main_module, "vector_store", object())
    monkeypatch.setattr(main_module, "graph_store", object())
    monkeypatch.setattr(main_module, "lessons_store", object())
    monkeypatch.setattr(main_module, "session_store", object())
    monkeypatch.setattr(main_module, "git_skill", object())
    monkeypatch.setattr(main_module, "gardener_agent", object())
    monkeypatch.setattr(main_module, "shadow_agent", object())
    monkeypatch.setattr(main_module, "file_watcher", object())
    monkeypatch.setattr(main_module, "documenter_agent", object())
    monkeypatch.setattr(main_module, "background_scheduler", object())
    monkeypatch.setattr(
        main_module,
        "service_monitor",
        SimpleNamespace(set_orchestrator=lambda *_: None),
    )
    monkeypatch.setattr(main_module, "llm_controller", object())
    monkeypatch.setattr(main_module, "model_manager", object())
    monkeypatch.setattr(main_module, "node_manager", object())
    monkeypatch.setattr(main_module, "benchmark_service", object())
    monkeypatch.setattr(main_module, "google_calendar_skill", object())
    monkeypatch.setattr(main_module, "model_registry", object())
    monkeypatch.setattr(main_module, "hardware_bridge", object())
    monkeypatch.setattr(main_module, "token_economist", None)


def test_setup_router_dependencies_retries_professor_init_success(monkeypatch):
    _patch_setup_routes(monkeypatch)
    _patch_setup_runtime_globals(monkeypatch)
    monkeypatch.setattr(main_module.SETTINGS, "ENABLE_ACADEMY", True, raising=False)
    monkeypatch.setattr(main_module, "professor", None)
    monkeypatch.setattr(main_module, "dataset_curator", object())
    monkeypatch.setattr(main_module, "gpu_habitat", object())
    monkeypatch.setattr(
        main_module,
        "orchestrator",
        SimpleNamespace(task_dispatcher=SimpleNamespace(kernel=object())),
    )

    professor_mod = ModuleType("venom_core.agents.professor")

    class DummyProfessor:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    professor_mod.Professor = DummyProfessor
    monkeypatch.setitem(sys.modules, "venom_core.agents.professor", professor_mod)

    main_module.setup_router_dependencies()

    assert isinstance(main_module.professor, DummyProfessor)
    assert (
        main_module.professor.kwargs["dataset_curator"] is main_module.dataset_curator
    )


def test_setup_router_dependencies_retries_professor_init_handles_exception(
    monkeypatch,
):
    _patch_setup_routes(monkeypatch)
    _patch_setup_runtime_globals(monkeypatch)
    monkeypatch.setattr(main_module.SETTINGS, "ENABLE_ACADEMY", True, raising=False)
    monkeypatch.setattr(main_module, "professor", None)
    monkeypatch.setattr(main_module, "dataset_curator", object())
    monkeypatch.setattr(main_module, "gpu_habitat", object())
    monkeypatch.setattr(
        main_module,
        "orchestrator",
        SimpleNamespace(task_dispatcher=SimpleNamespace(kernel=object())),
    )

    professor_mod = ModuleType("venom_core.agents.professor")

    class FailingProfessor:
        def __init__(self, **_kwargs):
            raise RuntimeError("boom")

    professor_mod.Professor = FailingProfessor
    monkeypatch.setitem(sys.modules, "venom_core.agents.professor", professor_mod)

    main_module.setup_router_dependencies()

    assert main_module.professor is None


async def _done_task() -> None:
    return None


def test_initialize_background_scheduler_retention_recent_no_startup_task(monkeypatch):
    class DummyScheduler:
        def __init__(self, event_broadcaster):
            self.event_broadcaster = event_broadcaster
            self.job_ids = []

        async def start(self):
            return None

        def add_interval_job(self, func, minutes, job_id, description):
            self.job_ids.append(job_id)

    monkeypatch.setattr(main_module, "BackgroundScheduler", DummyScheduler)
    monkeypatch.setattr(main_module.job_scheduler, "consolidate_memory", AsyncMock())
    monkeypatch.setattr(main_module.job_scheduler, "check_health", AsyncMock())
    monkeypatch.setattr(
        main_module.job_scheduler, "cleanup_runtime_files", lambda **_: {}
    )
    monkeypatch.setattr(
        main_module.asyncio, "to_thread", AsyncMock(side_effect=[False])
    )
    monkeypatch.setattr(main_module.SETTINGS, "ENABLE_MEMORY_CONSOLIDATION", False)
    monkeypatch.setattr(main_module.SETTINGS, "ENABLE_HEALTH_CHECKS", False)
    monkeypatch.setattr(main_module.SETTINGS, "ENABLE_RUNTIME_RETENTION_CLEANUP", True)
    monkeypatch.setattr(main_module.SETTINGS, "RUNTIME_RETENTION_DAYS", 7)
    monkeypatch.setattr(main_module.SETTINGS, "RUNTIME_RETENTION_INTERVAL_MINUTES", 11)
    monkeypatch.setattr(main_module.SETTINGS, "RUNTIME_RETENTION_TARGETS", ["./logs"])
    monkeypatch.setattr(main_module.SETTINGS, "REPO_ROOT", ".")
    monkeypatch.setattr(main_module, "request_tracer", None)
    monkeypatch.setattr(main_module, "vector_store", None)
    monkeypatch.setattr(main_module, "event_broadcaster", object())
    main_module.startup_runtime_retention_task = None

    import asyncio

    asyncio.run(main_module._initialize_background_scheduler())

    assert "cleanup_runtime_files" in main_module.background_scheduler.job_ids
    assert main_module.startup_runtime_retention_task is None


def test_shutdown_runtime_components_clears_startup_retention_task(monkeypatch):
    import asyncio

    async def _runner() -> None:
        task = asyncio.create_task(_done_task())
        main_module.startup_runtime_retention_task = task

        monkeypatch.setattr(
            main_module.llm_simple_routes,
            "release_onnx_simple_client",
            MagicMock(side_effect=RuntimeError("boom")),
        )
        monkeypatch.setattr(
            main_module.tasks_routes,
            "release_onnx_task_runtime",
            MagicMock(side_effect=RuntimeError("boom")),
        )
        main_module.request_tracer = None
        main_module.desktop_sensor = None
        main_module.shadow_agent = None
        main_module.node_manager = None
        main_module.background_scheduler = None
        main_module.file_watcher = None
        main_module.gardener_agent = None
        main_module.hardware_bridge = None
        main_module.state_manager = SimpleNamespace(shutdown=AsyncMock())

        await main_module._shutdown_runtime_components()
        assert main_module.startup_runtime_retention_task is None

    asyncio.run(_runner())


def test_clear_startup_runtime_retention_task_sets_none():
    main_module.startup_runtime_retention_task = object()
    main_module._clear_startup_runtime_retention_task()
    assert main_module.startup_runtime_retention_task is None


def test_shutdown_runtime_components_stops_all_components_when_set(monkeypatch):
    import asyncio

    async def _runner() -> None:
        done_task = asyncio.create_task(_done_task())
        await done_task
        main_module.startup_runtime_retention_task = done_task

        monkeypatch.setattr(
            main_module.llm_simple_routes,
            "release_onnx_simple_client",
            MagicMock(return_value=None),
        )
        monkeypatch.setattr(
            main_module.tasks_routes,
            "release_onnx_task_runtime",
            MagicMock(return_value=None),
        )

        main_module.request_tracer = SimpleNamespace(stop_watchdog=AsyncMock())
        main_module.desktop_sensor = SimpleNamespace(stop=AsyncMock())
        main_module.shadow_agent = SimpleNamespace(stop=AsyncMock())
        main_module.node_manager = SimpleNamespace(stop=AsyncMock())
        main_module.background_scheduler = SimpleNamespace(stop=AsyncMock())
        main_module.file_watcher = SimpleNamespace(stop=AsyncMock())
        main_module.gardener_agent = SimpleNamespace(stop=AsyncMock())
        main_module.hardware_bridge = SimpleNamespace(disconnect=AsyncMock())
        main_module.state_manager = SimpleNamespace(shutdown=AsyncMock())

        await main_module._shutdown_runtime_components()

        main_module.request_tracer.stop_watchdog.assert_awaited_once()
        main_module.desktop_sensor.stop.assert_awaited_once()
        main_module.shadow_agent.stop.assert_awaited_once()
        main_module.node_manager.stop.assert_awaited_once()
        main_module.background_scheduler.stop.assert_awaited_once()
        main_module.file_watcher.stop.assert_awaited_once()
        main_module.gardener_agent.stop.assert_awaited_once()
        main_module.hardware_bridge.disconnect.assert_awaited_once()
        main_module.state_manager.shutdown.assert_awaited_once()
        assert main_module.startup_runtime_retention_task is None

    asyncio.run(_runner())
