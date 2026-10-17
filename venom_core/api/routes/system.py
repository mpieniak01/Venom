from copy import deepcopy
from typing import List, Optional, TypedDict

from fastapi import APIRouter, FastAPI, Request

from venom_core.api.schemas.integrations import IntegrationEntry
from venom_core.api.schemas.system import (
    ApiConnection,
    ApiMapResponse,
    AuthType,
    ConnectionDirection,
    ConnectionProtocol,
    ConnectionStatus,
    SourceType,
)
from venom_core.config import SETTINGS
from venom_core.services.integration_catalog import core_catalog
from venom_core.services.integration_overview import integration_overview
from venom_core.utils.llm_runtime import get_active_llm_runtime

router = APIRouter(prefix="/api/v1", tags=["system"])

# --- Cache for API Map Structure (Connections without status) ---
_API_MAP_CACHE: Optional[ApiMapResponse] = None
_API_MAP_CACHE_OWNER: FastAPI | None = None
_LAST_CACHE_TIME: float = 0
_CACHE_TTL: float = 60.0  # 60 seconds

# --- Reused component labels ---
NODES_API_LABEL = "Nodes API"
FRONTEND_NEXTJS_LABEL = "Frontend (Next.js)"
MODEL_ROUTER_LABEL = "Model Router"
OPENAI_API_LABEL = "OpenAI API"
_SERVICE_MAP = {
    OPENAI_API_LABEL: OPENAI_API_LABEL,
    "Redis": "Redis",
    "LanceDB": "LanceDB",
    "Semantic Kernel": "Orchestrator",
}
_STATUS_MAP = {
    "online": ConnectionStatus.OK,
    "offline": ConnectionStatus.DOWN,
    "degraded": ConnectionStatus.DEGRADED,
}


class _ApiDefinition(TypedDict):
    target: str
    prefix: str
    desc: str
    critical: bool


# --- Helper Functions ---


def _get_method_signatures(app: FastAPI, prefix: str) -> List[str]:
    """Scans app routes for a given prefix and returns list of 'METHOD /path' strings."""
    methods_set = set()
    for route in _iter_routes(app.routes):
        path = getattr(route, "path", None)
        if not path or not path.startswith(prefix):
            continue

        route_methods = getattr(route, "methods", None)
        if not route_methods:
            continue

        for method in route_methods:
            if method in ("HEAD", "OPTIONS"):
                continue
            methods_set.add(f"{method} {path}")

    return sorted(methods_set)


def _iter_routes(routes):
    """Yield concrete route objects, flattening FastAPI included-router wrappers."""
    for route in routes:
        path = getattr(route, "path", None)
        if path is not None:
            yield route
            continue

        original_router = getattr(route, "original_router", None)
        if original_router is not None:
            yield from _iter_routes(getattr(original_router, "routes", []))
            continue

        include_context = getattr(route, "include_context", None)
        included_router = getattr(include_context, "included_router", None)
        if included_router is not None:
            yield from _iter_routes(getattr(included_router, "routes", []))


def _generate_internal_map(request: Request) -> List[ApiConnection]:
    """Generates internal API connections based on known components and discovered routes."""
    internal = []
    app = request.app

    # Define the Core Components and their route prefixes
    # This removes the hardcoded list of methods and relies on discovery
    # Define the Core Components and their route prefixes
    # This removes the hardcoded list of methods and relies on discovery

    # Use the explicit list of "Internal Services" (logical) defined by valid route prefixes.
    # Logical Components hosted within this FastAPI instance:

    definitions: List[_ApiDefinition] = [
        {
            "target": "System Status API",
            "prefix": "/api/v1/system/status",
            "desc": "Status i zdrowie systemu",
            "critical": True,
        },
        {
            "target": "System Services API",
            "prefix": "/api/v1/system/services",
            "desc": "Zarządzanie usługami systemowymi",
            "critical": True,
        },
        {
            "target": "System Runtime API",
            "prefix": "/api/v1/system/runtime",
            "desc": "Konfiguracja środowiska uruchomieniowego",
            "critical": True,
        },
        {
            "target": "System Storage API",
            "prefix": "/api/v1/system/storage",
            "desc": "Zarządzanie pamięcią masową",
            "critical": False,
        },
        {
            "target": "System IoT API",
            "prefix": "/api/v1/system/iot",
            "desc": "Integracja z urządzeniami IoT",
            "critical": False,
        },
        {
            "target": "Tasks API",
            "prefix": "/api/v1/tasks",
            "desc": "Zarządzanie zadaniami asynchronicznymi",
            "critical": True,
        },
        {
            "target": "Queue API",
            "prefix": "/api/v1/queue",
            "desc": "Status i metryki kolejki zadań",
            "critical": True,
        },
        {
            "target": "Agents API",
            "prefix": "/api/v1/agents",
            "desc": "Zarządzanie i status agentów",
            "critical": True,
        },
        {
            "target": "Strategy API",
            "prefix": "/api/roadmap",
            "desc": "Planowanie i roadmapa",
            "critical": False,
        },
        {
            "target": "Governance API",
            "prefix": "/api/v1/governance",
            "desc": "Polityki bezpieczeństwa i audyt",
            "critical": True,
        },
        {
            "target": "Memory API",
            "prefix": "/api/v1/memory",
            "desc": "Projekcja i wizualizacja pamięci",
            "critical": False,
        },
        {
            "target": NODES_API_LABEL,
            "prefix": "/api/v1/nodes",
            "desc": "Zarządzanie węzłami (Nexus)",
            "critical": False,
        },
        {
            "target": "Feedback API",
            "prefix": "/api/v1/feedback",
            "desc": "Informacje zwrotne od użytkownika",
            "critical": False,
        },
        # Chat/Models - Core
        {
            "target": FRONTEND_NEXTJS_LABEL,
            "prefix": "/api/v1/chat",
            "desc": "Interfejs użytkownika (Chat)",
            "critical": True,
        },
    ]

    # Base Source for these is usually "Backend" (The Monolith) or specific managers.
    # To keep it compatible with previous visualization, we map logical "Source Managers".

    manager_map = {
        "System Status API": "System Monitor",
        "System Services API": "Service Manager",
        "System Runtime API": "Runtime Manager",
        "System Storage API": "Storage Manager",
        "System IoT API": "IoT Controller",
        "Tasks API": "Task Manager",
        "Queue API": "Queue Manager",
        "Agents API": "Agent Orchestrator",
        "Strategy API": "Strategist",
        "Governance API": "Governance",
        "Memory API": "Memory Projector",
        NODES_API_LABEL: "Node Manager",
        "Feedback API": "User Feedback",
        FRONTEND_NEXTJS_LABEL: "Backend API",
    }

    for item in definitions:
        target = item["target"]
        source = manager_map.get(target, "Backend System")
        prefix = item["prefix"]

        # Dynamic discovery of methods
        methods = _get_method_signatures(app, prefix)

        if not methods and target != FRONTEND_NEXTJS_LABEL:
            # If no methods found for this prefix, skip it (Dynamic!)
            # But "Frontend (Next.js)" might have multiple prefixes like /api/v1/models
            continue

        if target == FRONTEND_NEXTJS_LABEL:
            # Aggregate multiple prefixes for Frontend
            methods.extend(_get_method_signatures(app, "/api/v1/models"))
            # WS special case
            methods.append("WS /ws/events")
            methods.append("SSE /api/v1/stream")

        connection = ApiConnection(
            source_component=source,
            target_component=target,
            protocol=ConnectionProtocol.HTTP
            if "WS" not in str(methods)
            else ConnectionProtocol.WS,  # Simplification
            direction=ConnectionDirection.BIDIRECTIONAL,
            auth_type=AuthType.NONE,
            source_type=SourceType.LOCAL,
            status=ConnectionStatus.UNKNOWN,
            description=item["desc"],
            is_critical=item["critical"],
            methods=sorted(set(methods)),
        )
        internal.append(connection)

    # Add Non-HTTP Internal components (Services)
    if SETTINGS.ENABLE_NEXUS:
        internal.append(
            ApiConnection(
                source_component="Nexus (Master)",
                target_component="Node (Worker)",
                protocol=ConnectionProtocol.WS,
                direction=ConnectionDirection.BIDIRECTIONAL,
                auth_type=AuthType.SERVICE_TOKEN,
                source_type=SourceType.LOCAL,
                status=ConnectionStatus.UNKNOWN,
                description="Magistrala rozproszona Venom Nexus",
                is_critical=False,
                methods=["WS /nexus/connect", "WS /nexus/stream"],
            )
        )

    if SETTINGS.ENABLE_HIVE:
        internal.append(
            ApiConnection(
                source_component="The Hive",
                target_component="Redis",
                protocol=ConnectionProtocol.TCP,
                direction=ConnectionDirection.BIDIRECTIONAL,
                auth_type=AuthType.NONE,
                source_type=SourceType.LOCAL,
                status=ConnectionStatus.UNKNOWN,
                description="Kolejka zadań i broker wiadomości",
                is_critical=False,
                methods=["LPUSH job_queue", "BRPOP job_queue", "PUBLISH events"],
            )
        )

    # LanceDB (Always present usually)
    internal.append(
        ApiConnection(
            source_component="Orchestrator",
            target_component="LanceDB",
            protocol=ConnectionProtocol.HTTP,
            direction=ConnectionDirection.BIDIRECTIONAL,
            auth_type=AuthType.NONE,
            source_type=SourceType.LOCAL,
            status=ConnectionStatus.UNKNOWN,
            description="Pamięć długoterminowa (wektorowa)",
            is_critical=True,
            methods=["query_vectors", "add_vectors", "create_table"],
        )
    )

    return internal


def _generate_external_map() -> List[ApiConnection]:
    """Compatibility projection of the same core integration declarations."""
    external = []
    try:
        runtime = get_active_llm_runtime()
    except Exception:
        runtime = None
    if SETTINGS.LLM_SERVICE_TYPE == "local":
        external.append(
            _build_local_llm_connection(str(getattr(runtime, "provider", "") or ""), "")
        )
    if SETTINGS.AI_MODE in ["HYBRID", "CLOUD"]:
        external.append(_build_cloud_llm_connection())
    for item in core_catalog(SETTINGS):
        external.append(
            ApiConnection(
                source_component="Venom",
                target_component=item.label,
                description=None,
                is_critical=False,
                protocol=ConnectionProtocol.HTTP
                if item.location == "local"
                else ConnectionProtocol.HTTPS,
                direction=ConnectionDirection.OUTBOUND,
                auth_type=AuthType.API_KEY
                if item.configuration_keys
                else AuthType.NONE,
                source_type=SourceType.LOCAL
                if item.location == "local"
                else SourceType.CLOUD,
                status=ConnectionStatus.UNKNOWN,
                methods=[],
            )
        )
    return external


def _build_local_llm_connection(
    runtime_provider: str,
    runtime_endpoint: str,
) -> ApiConnection:
    local_runtime_label = runtime_provider or "auto"
    return ApiConnection(
        source_component=MODEL_ROUTER_LABEL,
        target_component=f"Local LLM ({local_runtime_label})",
        protocol=ConnectionProtocol.HTTP,
        direction=ConnectionDirection.BIDIRECTIONAL,
        auth_type=AuthType.NONE,
        source_type=SourceType.LOCAL,
        status=ConnectionStatus.UNKNOWN,
        description="Lokalny runtime LLM",
        is_critical=True,
        methods=["POST /api/generate", "POST /api/chat", "GET /api/tags"],
    )


def _build_cloud_llm_connection() -> ApiConnection:
    provider = SETTINGS.HYBRID_CLOUD_PROVIDER
    return ApiConnection(
        source_component=MODEL_ROUTER_LABEL,
        target_component=f"Cloud LLM ({provider.upper()})",
        protocol=ConnectionProtocol.HTTPS,
        direction=ConnectionDirection.OUTBOUND,
        auth_type=AuthType.API_KEY,
        source_type=SourceType.CLOUD,
        status=ConnectionStatus.UNKNOWN,
        description="Zewnętrzny model dla zadań złożonych",
        is_critical=SETTINGS.AI_MODE == "CLOUD",
        methods=["POST /v1/chat/completions", "POST /v1/embeddings"],
    )


def _update_runtime_statuses(connections: List[ApiConnection], service_monitor) -> None:
    """Updates the status of connections based on the ServiceMonitor."""
    if not service_monitor or not hasattr(service_monitor, "get_all_services"):
        return

    try:
        real_services = {s.name: s for s in service_monitor.get_all_services()}
    except Exception:
        return
    target_to_service = {target: service for service, target in _SERVICE_MAP.items()}

    for conn in connections:
        service_name = target_to_service.get(conn.target_component)
        if not service_name:
            continue
        svc = real_services.get(service_name)
        if not svc:
            continue
        conn.status = _map_connection_status(svc.status.value)
        conn.observed_at = getattr(svc, "last_check", None)
        # We don't change description to keep structure clean, but status is live.


def _map_connection_status(svc_status: str) -> ConnectionStatus:
    return _STATUS_MAP.get(svc_status, ConnectionStatus.UNKNOWN)


@router.get("/system/api-map")
async def get_system_api_map(request: Request) -> ApiMapResponse:
    """Returns the map of internal and external API connections."""
    global _API_MAP_CACHE, _LAST_CACHE_TIME, _API_MAP_CACHE_OWNER
    import time

    now = time.time()

    # Generate Structure if not cached or expired
    if (
        _API_MAP_CACHE is None
        or _API_MAP_CACHE_OWNER is not request.app
        or (now - _LAST_CACHE_TIME > _CACHE_TTL)
    ):
        internal = _generate_internal_map(request)
        external = _generate_external_map()
        _API_MAP_CACHE = ApiMapResponse(
            internal_connections=internal, external_connections=external
        )
        _LAST_CACHE_TIME = now
        _API_MAP_CACHE_OWNER = request.app

    # Clone from cache to update statuses without mutating cache structure per se
    # (though deepcopy is expensive, structure is small enough)
    response = deepcopy(_API_MAP_CACHE)

    # Update Runtime Status
    from venom_core.api.routes import system_deps

    service_monitor = system_deps.get_service_monitor()

    if service_monitor:
        _update_runtime_statuses(response.internal_connections, service_monitor)
        _update_runtime_statuses(response.external_connections, service_monitor)

    from venom_core.api.routes import nodes

    response.integrations = await integration_overview(
        request.app, response, SETTINGS, getattr(nodes, "_node_manager", None)
    )
    current = {item.label: item for item in response.integrations}
    for connection in response.internal_connections + response.external_connections:
        item = current.get(connection.target_component)
        if item is not None:
            connection.status = item.connectivity
            connection.observed_at = item.observed_at
    from datetime import datetime, timezone

    response.generated_at = datetime.now(timezone.utc).isoformat()
    return response


@router.post("/system/integrations/vast/probe")
async def probe_vast_integration(request: Request) -> IntegrationEntry:
    """Explicit account/instance GETs only; opening the map never triggers this."""
    from venom_core.services.vast_observation import probe_vast

    return await probe_vast(request.app, SETTINGS)
