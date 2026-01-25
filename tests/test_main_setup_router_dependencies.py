from types import SimpleNamespace

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

    main_module.orchestrator = object()
    main_module.state_manager = object()
    main_module.request_tracer = object()
    main_module.vector_store = object()
    main_module.git_skill = object()
    main_module.graph_store = object()
    main_module.lessons_store = object()
    main_module.gardener_agent = object()
    main_module.shadow_agent = object()
    main_module.file_watcher = object()
    main_module.documenter_agent = object()
    main_module.background_scheduler = object()
    main_module.service_monitor = object()
    main_module.llm_controller = object()
    main_module.model_manager = object()
    main_module.node_manager = object()
    main_module.benchmark_service = object()
    main_module.google_calendar_skill = object()
    main_module.model_registry = object()
    main_module.hardware_bridge = object()

    main_module.setup_router_dependencies()

    assert calls["tasks"]["args"][0] is main_module.orchestrator
    assert calls["tasks"]["args"][1] is main_module.state_manager
    assert calls["tasks"]["args"][2] is main_module.request_tracer
    assert calls["system_deps"]["args"][0] is main_module.background_scheduler
    assert calls["system_deps"]["args"][1] is main_module.service_monitor
    assert calls["models"]["kwargs"]["model_registry"] is main_module.model_registry
