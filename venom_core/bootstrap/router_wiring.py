"""Router and dependency wiring extracted from main bootstrap flow."""

from typing import Any


def apply_router_dependencies(
    *,
    api_deps: Any,
    system_deps: Any,
    feedback_routes: Any,
    queue_routes: Any,
    metrics_routes: Any,
    git_routes: Any,
    agents_routes: Any,
    nodes_routes: Any,
    strategy_routes: Any,
    models_routes: Any,
    benchmark_routes: Any,
    calendar_routes: Any,
    memory_projection_routes: Any,
    academy_routes: Any,
    orchestrator: Any,
    state_manager: Any,
    vector_store: Any,
    graph_store: Any,
    lessons_store: Any,
    session_store: Any,
    request_tracer: Any,
    service_monitor: Any,
    background_scheduler: Any,
    llm_controller: Any,
    model_manager: Any,
    hardware_bridge: Any,
    token_economist: Any,
    git_skill: Any,
    gardener_agent: Any,
    shadow_agent: Any,
    file_watcher: Any,
    documenter_agent: Any,
    node_manager: Any,
    model_registry: Any,
    benchmark_service: Any,
    google_calendar_skill: Any,
    professor: Any,
    dataset_curator: Any,
    gpu_habitat: Any,
) -> None:
    """Apply all runtime dependencies to API routes and global dependency holders."""
    if orchestrator:
        api_deps.set_orchestrator(orchestrator)
    if state_manager:
        api_deps.set_state_manager(state_manager)
    if vector_store:
        api_deps.set_vector_store(vector_store)
    if graph_store:
        api_deps.set_graph_store(graph_store)
    if lessons_store:
        api_deps.set_lessons_store(lessons_store)
    if session_store:
        api_deps.set_session_store(session_store)
    if request_tracer:
        api_deps.set_request_tracer(request_tracer)

    if service_monitor:
        service_monitor.set_orchestrator(orchestrator)

    # Keep legacy invocation shape to avoid behavior drift.
    system_deps.set_dependencies(
        background_scheduler,
        service_monitor,
        state_manager,
        llm_controller,
        model_manager,
        request_tracer,
        hardware_bridge,
        orchestrator,
    )
    feedback_routes.set_dependencies(orchestrator, state_manager, request_tracer)
    queue_routes.set_dependencies(orchestrator)
    metrics_routes.set_dependencies(token_economist=token_economist)
    git_routes.set_dependencies(git_skill)
    agents_routes.set_dependencies(
        gardener_agent, shadow_agent, file_watcher, documenter_agent, orchestrator
    )
    system_deps.set_dependencies(
        background_scheduler,
        service_monitor,
        state_manager,
        llm_controller,
        model_manager,
        request_tracer,
        hardware_bridge,
    )
    nodes_routes.set_dependencies(node_manager)
    strategy_routes.set_dependencies(orchestrator)
    models_routes.set_dependencies(model_manager, model_registry=model_registry)
    benchmark_routes.set_dependencies(benchmark_service)
    calendar_routes.set_dependencies(google_calendar_skill)
    memory_projection_routes.set_dependencies(vector_store)
    academy_routes.set_dependencies(
        professor=professor,
        dataset_curator=dataset_curator,
        gpu_habitat=gpu_habitat,
        lessons_store=lessons_store,
        model_manager=model_manager,
    )
