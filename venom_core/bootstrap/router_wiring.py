"""Router and dependency wiring extracted from main bootstrap flow."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RouterModules:
    feedback_routes: Any
    queue_routes: Any
    metrics_routes: Any
    git_routes: Any
    agents_routes: Any
    nodes_routes: Any
    strategy_routes: Any
    models_routes: Any
    benchmark_routes: Any
    benchmark_coding_routes: Any
    calendar_routes: Any
    memory_projection_routes: Any
    academy_routes: Any
    academy_self_learning_routes: Any


@dataclass(frozen=True)
class RuntimeDependencies:
    orchestrator: Any
    state_manager: Any
    vector_store: Any
    graph_store: Any
    lessons_store: Any
    session_store: Any
    request_tracer: Any
    service_monitor: Any
    background_scheduler: Any
    llm_controller: Any
    model_manager: Any
    hardware_bridge: Any
    token_economist: Any
    git_skill: Any
    gardener_agent: Any
    shadow_agent: Any
    file_watcher: Any
    documenter_agent: Any
    node_manager: Any
    model_registry: Any
    benchmark_service: Any
    coding_benchmark_service: Any
    runtime_exclusive_guard: Any
    google_calendar_skill: Any
    professor: Any
    dataset_curator: Any
    gpu_habitat: Any
    self_learning_service: Any
    ghost_agent: Any = None


def apply_router_dependencies(
    *,
    api_deps: Any,
    system_deps: Any,
    routes: RouterModules,
    runtime: RuntimeDependencies,
) -> None:
    """Apply all runtime dependencies to API routes and global dependency holders."""
    if runtime.orchestrator:
        api_deps.set_orchestrator(runtime.orchestrator)
    if runtime.state_manager:
        api_deps.set_state_manager(runtime.state_manager)
    if runtime.vector_store:
        api_deps.set_vector_store(runtime.vector_store)
    if runtime.graph_store:
        api_deps.set_graph_store(runtime.graph_store)
    if runtime.lessons_store:
        api_deps.set_lessons_store(runtime.lessons_store)
    if runtime.session_store:
        api_deps.set_session_store(runtime.session_store)
    if runtime.request_tracer:
        api_deps.set_request_tracer(runtime.request_tracer)

    if runtime.service_monitor:
        runtime.service_monitor.set_orchestrator(runtime.orchestrator)

    # Keep legacy invocation shape to avoid behavior drift.
    system_deps.set_dependencies(
        runtime.background_scheduler,
        runtime.service_monitor,
        runtime.state_manager,
        runtime.llm_controller,
        runtime.model_manager,
        runtime.request_tracer,
        runtime.hardware_bridge,
        runtime.orchestrator,
    )
    routes.feedback_routes.set_dependencies(
        runtime.orchestrator, runtime.state_manager, runtime.request_tracer
    )
    routes.queue_routes.set_dependencies(runtime.orchestrator)
    routes.metrics_routes.set_dependencies(token_economist=runtime.token_economist)
    routes.git_routes.set_dependencies(runtime.git_skill)
    routes.agents_routes.set_dependencies(
        runtime.gardener_agent,
        runtime.shadow_agent,
        runtime.file_watcher,
        runtime.documenter_agent,
        runtime.orchestrator,
        runtime.ghost_agent,
    )
    system_deps.set_dependencies(
        runtime.background_scheduler,
        runtime.service_monitor,
        runtime.state_manager,
        runtime.llm_controller,
        runtime.model_manager,
        runtime.request_tracer,
        runtime.hardware_bridge,
    )
    routes.nodes_routes.set_dependencies(runtime.node_manager)
    routes.strategy_routes.set_dependencies(runtime.orchestrator)
    routes.models_routes.set_dependencies(
        runtime.model_manager,
        model_registry=runtime.model_registry,
    )
    routes.benchmark_routes.set_dependencies(
        runtime.benchmark_service,
        runtime_exclusive_guard=runtime.runtime_exclusive_guard,
        coding_benchmark_service=runtime.coding_benchmark_service,
    )
    routes.benchmark_coding_routes.set_dependencies(
        runtime.coding_benchmark_service,
        runtime_exclusive_guard=runtime.runtime_exclusive_guard,
        benchmark_service=runtime.benchmark_service,
    )
    routes.calendar_routes.set_dependencies(runtime.google_calendar_skill)
    routes.memory_projection_routes.set_dependencies(runtime.vector_store)
    routes.academy_routes.set_dependencies(
        professor=runtime.professor,
        dataset_curator=runtime.dataset_curator,
        gpu_habitat=runtime.gpu_habitat,
        lessons_store=runtime.lessons_store,
        model_manager=runtime.model_manager,
    )
    routes.academy_self_learning_routes.set_dependencies(
        self_learning_service=runtime.self_learning_service,
    )
