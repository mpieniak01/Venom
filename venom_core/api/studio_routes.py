"""Explicit Studio subset of the existing Full API route objects.

No endpoint is reimplemented. FastAPI binds selected routes to the application
while preserving endpoint identity, dependencies, body/response schemas and
operation IDs. Binding is necessary for application-scoped dependency overrides.
"""

from collections.abc import Callable
from functools import partial
from typing import Any

from fastapi import APIRouter, FastAPI
from fastapi.routing import APIRoute

from venom_core.api import dependencies as api_deps
from venom_core.api.routes import (
    chat_audio,
    chat_materials,
    chat_tasks,
    health,
    llm_simple,
    memory,
    models_dependencies,
    system_config,
    system_deps,
    system_llm,
    system_status,
    tasks,
)

# Deliberately exclude training, RAG search, rental/order, legacy dashboard,
# configuration screens, optional modules and global queue emergency.
STUDIO_ROUTES: dict[str, frozenset[str]] = {
    "/healthz": frozenset({"GET"}),
    "/api/v1/config/runtime": frozenset({"GET", "POST"}),
    "/api/v1/system/status": frozenset({"GET"}),
    "/api/v1/system/llm-runtime/options": frozenset({"GET"}),
    "/api/v1/system/llm-runtime/active": frozenset({"GET", "POST"}),
    "/api/v1/system/llm-servers/active": frozenset({"GET", "POST"}),
    "/api/v1/openrouter/status": frozenset({"GET"}),
    "/api/v1/openrouter/catalog": frozenset({"GET"}),
    "/api/v1/openrouter/quote": frozenset({"POST"}),
    "/api/v1/tasks": frozenset({"POST"}),
    "/api/v1/tasks/{task_id}": frozenset({"GET"}),
    "/api/v1/tasks/{task_id}/stream": frozenset({"GET"}),
    "/api/v1/llm/simple/stream": frozenset({"POST"}),
    "/api/v1/memory/session/{session_id}": frozenset({"GET", "DELETE"}),
    "/api/v1/memory/ingest": frozenset({"POST"}),
    "/api/v1/chat/materials": frozenset({"GET", "POST"}),
    "/api/v1/chat/materials/capabilities": frozenset({"GET"}),
    "/api/v1/chat/materials/{material_id}": frozenset({"DELETE"}),
    "/api/v1/chat/materials/{material_id}/content": frozenset({"GET"}),
    "/api/v1/chat/audio/transcribe": frozenset({"POST"}),
    "/api/v1/chat/audio/speak": frozenset({"POST"}),
    "/api/v1/chat/tasks/{task_id}/cancel": frozenset({"POST"}),
}
ROUTE_MODULES = (
    health,
    system_config,
    system_status,
    system_llm,
    tasks,
    llm_simple,
    memory,
    chat_audio,
    chat_materials,
    chat_tasks,
)


def studio_routes() -> list[APIRoute]:
    result = []
    for module in ROUTE_MODULES:
        for route in module.router.routes:
            if not isinstance(route, APIRoute):
                continue
            allowed = STUDIO_ROUTES.get(route.path)
            if allowed is not None and route.methods <= allowed:
                result.append(route)
    return result


def include_studio_routes(app: FastAPI) -> None:
    selected = APIRouter()
    selected.routes.extend(studio_routes())
    app.include_router(selected)


def configure_studio_dependencies(app: FastAPI, runtime: Any) -> None:
    """Bind API-specific globals and app-owned lazy overrides at the API boundary."""
    restore: list[Callable[[], Any]] = []
    previous_system = tuple(
        getattr(system_deps, "get_" + name)()
        for name in (
            "background_scheduler",
            "service_monitor",
            "state_manager",
            "llm_controller",
            "model_manager",
            "request_tracer",
            "hardware_bridge",
            "orchestrator",
        )
    )
    restore.append(partial(system_deps.set_dependencies, *previous_system))
    restore.append(
        partial(
            models_dependencies.set_dependencies,
            models_dependencies.get_model_manager(),
            models_dependencies.get_model_registry(),
        )
    )
    previous_callback = runtime.on_dependencies_changed
    overrides: dict[Callable[..., Any], Callable[..., Any]] = {
        api_deps.get_orchestrator: runtime.get_orchestrator,
        api_deps.get_vector_store: runtime.get_vector_store,
    }
    previous_overrides = {
        dependency: app.dependency_overrides.get(dependency) for dependency in overrides
    }

    def wire() -> None:
        system_deps.set_dependencies(
            None,
            runtime.service_monitor,
            runtime.state_manager,
            runtime.controller,
            runtime.model_manager,
            runtime.request_tracer,
            orchestrator=runtime.orchestrator,
        )
        models_dependencies.set_dependencies(
            runtime.model_manager, runtime.model_registry
        )

    def restore_bindings() -> None:
        runtime.on_dependencies_changed = previous_callback
        for dependency, previous in previous_overrides.items():
            if previous is None:
                app.dependency_overrides.pop(dependency, None)
            else:
                app.dependency_overrides[dependency] = previous
        for callback in reversed(restore):
            callback()

    runtime.register_cleanup(restore_bindings)
    runtime.on_dependencies_changed = wire
    app.dependency_overrides.update(overrides)
    wire()
