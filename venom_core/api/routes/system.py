from copy import deepcopy
from typing import List, Optional

from fastapi import APIRouter, FastAPI, Request

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

router = APIRouter(prefix="/api/v1", tags=["system"])

# --- Cache for API Map Structure (Connections without status) ---
_API_MAP_CACHE: Optional[ApiMapResponse] = None
_LAST_CACHE_TIME: float = 0
_CACHE_TTL: float = 60.0  # 60 seconds

# --- Reused component labels ---
NODES_API_LABEL = "Nodes API"
FRONTEND_NEXTJS_LABEL = "Frontend (Next.js)"
MODEL_ROUTER_LABEL = "Model Router"
OPENAI_API_LABEL = "OpenAI API"

# --- Helper Functions ---


def _get_method_signatures(app: FastAPI, prefix: str) -> List[str]:
    """Scans app routes for a given prefix and returns list of 'METHOD /path' strings."""
    methods_set = set()
    for route in app.routes:
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

    return sorted(list(methods_set))


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

    definitions = [
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
            status=ConnectionStatus.OK,
            description=item["desc"],
            is_critical=item["critical"],
            methods=sorted(list(set(methods))),
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
                status=ConnectionStatus.OK,
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
                status=ConnectionStatus.OK,
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
            status=ConnectionStatus.OK,
            description="Pamięć długoterminowa (wektorowa)",
            is_critical=True,
            methods=["query_vectors", "add_vectors", "create_table"],
        )
    )

    return internal


def _generate_external_map() -> List[ApiConnection]:
    """Generates external API connections based on configuration settings."""
    external = []

    # Local LLM
    if SETTINGS.LLM_SERVICE_TYPE == "local":
        external.append(
            ApiConnection(
                source_component=MODEL_ROUTER_LABEL,
                target_component=f"Local LLM ({SETTINGS.ACTIVE_LLM_SERVER or 'auto'})",
                protocol=ConnectionProtocol.HTTP,
                direction=ConnectionDirection.BIDIRECTIONAL,
                auth_type=AuthType.NONE,
                source_type=SourceType.LOCAL,
                status=ConnectionStatus.OK,
                description=f"Lokalny model językowy ({SETTINGS.LLM_LOCAL_ENDPOINT})",
                is_critical=True,
                methods=["POST /api/generate", "POST /api/chat", "GET /api/tags"],
            )
        )

    # Cloud Providers
    if SETTINGS.AI_MODE in ["HYBRID", "CLOUD"]:
        provider = SETTINGS.HYBRID_CLOUD_PROVIDER
        external.append(
            ApiConnection(
                source_component=MODEL_ROUTER_LABEL,
                target_component=f"Cloud LLM ({provider.upper()})",
                protocol=ConnectionProtocol.HTTPS,
                direction=ConnectionDirection.OUTBOUND,
                auth_type=AuthType.API_KEY,
                source_type=SourceType.CLOUD,
                status=ConnectionStatus.OK,
                description="Zewnętrzny model dla zadań złożonych",
                is_critical=True if SETTINGS.AI_MODE == "CLOUD" else False,
                methods=["POST /v1/chat/completions", "POST /v1/embeddings"],
            )
        )

    # Search
    if SETTINGS.TAVILY_API_KEY.get_secret_value():
        external.append(
            ApiConnection(
                source_component="Researcher",
                target_component="Tavily AI Search",
                protocol=ConnectionProtocol.HTTPS,
                direction=ConnectionDirection.OUTBOUND,
                auth_type=AuthType.API_KEY,
                source_type=SourceType.CLOUD,
                status=ConnectionStatus.OK,
                description="Silnik wyszukiwania AI",
                is_critical=False,
                methods=["POST /search", "POST /extract"],
            )
        )
    else:
        external.append(
            ApiConnection(
                source_component="Researcher",
                target_component="DuckDuckGo",
                protocol=ConnectionProtocol.HTTPS,
                direction=ConnectionDirection.OUTBOUND,
                auth_type=AuthType.NONE,
                source_type=SourceType.CLOUD,
                status=ConnectionStatus.OK,
                description="Publiczny silnik wyszukiwania (Privacy-First)",
                is_critical=False,
                methods=["GET /search?q=..."],
            )
        )

    # Google Calendar
    if SETTINGS.ENABLE_GOOGLE_CALENDAR:
        external.append(
            ApiConnection(
                source_component="Calendar Skill",
                target_component="Google Calendar API",
                protocol=ConnectionProtocol.HTTPS,
                direction=ConnectionDirection.BIDIRECTIONAL,
                auth_type=AuthType.OAUTH,
                source_type=SourceType.CLOUD,
                status=ConnectionStatus.OK,
                description="Integracja z kalendarzem użytkownika",
                is_critical=False,
                methods=[
                    "GET /calendars/primary/events",
                    "POST /calendars/primary/events",
                ],
            )
        )

    # Hugging Face
    if SETTINGS.ENABLE_HF_INTEGRATION:
        external.append(
            ApiConnection(
                source_component="Model Manager",
                target_component="Hugging Face Hub",
                protocol=ConnectionProtocol.HTTPS,
                direction=ConnectionDirection.OUTBOUND,
                auth_type=AuthType.API_KEY
                if SETTINGS.HF_TOKEN.get_secret_value()
                else AuthType.NONE,
                source_type=SourceType.CLOUD,
                status=ConnectionStatus.OK,
                description="Pobieranie modeli i metadanych",
                is_critical=False,
                methods=["GET /api/models/{model_id}", "GET /api/datasets"],
            )
        )

    # OpenAI Direct
    if SETTINGS.OPENAI_API_KEY:
        external.append(
            ApiConnection(
                source_component=MODEL_ROUTER_LABEL,
                target_component=OPENAI_API_LABEL,
                protocol=ConnectionProtocol.HTTPS,
                direction=ConnectionDirection.OUTBOUND,
                auth_type=AuthType.API_KEY,
                source_type=SourceType.CLOUD,
                status=ConnectionStatus.OK,
                description="Modele GPT-4o / GPT-3.5 Turbo",
                is_critical=False,
                methods=[
                    "POST /v1/chat/completions",
                    "POST /v1/embeddings",
                    "POST /v1/images/generations",
                ],
            )
        )

    # Google AI Direct
    if SETTINGS.GOOGLE_API_KEY:
        external.append(
            ApiConnection(
                source_component=MODEL_ROUTER_LABEL,
                target_component="Google AI Studio",
                protocol=ConnectionProtocol.HTTPS,
                direction=ConnectionDirection.OUTBOUND,
                auth_type=AuthType.API_KEY,
                source_type=SourceType.CLOUD,
                status=ConnectionStatus.OK,
                description="Modele Gemini 1.5 Pro / Flash",
                is_critical=False,
                methods=["POST /v1beta/models/gemini-pro:generateContent"],
            )
        )

    # Stable Diffusion (Always local if enabled/configured)
    # Assuming enabled for map purposes
    external.append(
        ApiConnection(
            source_component="Image Generator",
            target_component="Stable Diffusion",
            protocol=ConnectionProtocol.HTTP,
            direction=ConnectionDirection.OUTBOUND,
            auth_type=AuthType.NONE,
            source_type=SourceType.LOCAL,
            status=ConnectionStatus.OK,
            description="Generowanie obrazów (Automatic1111)",
            is_critical=False,
            methods=["POST /sdapi/v1/txt2img", "GET /sdapi/v1/options"],
        )
    )

    return external


def _update_runtime_statuses(connections: List[ApiConnection], service_monitor) -> None:
    """Updates the status of connections based on the ServiceMonitor."""
    if not service_monitor:
        return

    real_services = {s.name: s for s in service_monitor.get_all_services()}

    # Mapping Service Name -> Target Component Name
    service_map = {
        OPENAI_API_LABEL: OPENAI_API_LABEL,
        "Redis": "Redis",
        "LanceDB": "LanceDB",
        "Docker Daemon": NODES_API_LABEL,
        "Semantic Kernel": "Orchestrator",
    }

    def map_status(svc_status: str) -> ConnectionStatus:
        if svc_status == "online":
            return ConnectionStatus.OK
        if svc_status == "offline":
            return ConnectionStatus.DOWN
        if svc_status == "degraded":
            return ConnectionStatus.DEGRADED
        return ConnectionStatus.UNKNOWN

    for conn in connections:
        service_name_to_check = None
        for svc_name, target_name in service_map.items():
            if target_name == conn.target_component:
                service_name_to_check = svc_name
                break

        if service_name_to_check and service_name_to_check in real_services:
            svc = real_services[service_name_to_check]
            conn.status = map_status(svc.status.value)
            # We don't change description to keep structure clean, but status is live.


@router.get("/system/api-map")
async def get_system_api_map(request: Request) -> ApiMapResponse:
    """Returns the map of internal and external API connections."""
    global _API_MAP_CACHE, _LAST_CACHE_TIME
    import time

    now = time.time()

    # Generate Structure if not cached or expired
    if _API_MAP_CACHE is None or (now - _LAST_CACHE_TIME > _CACHE_TTL):
        internal = _generate_internal_map(request)
        external = _generate_external_map()
        _API_MAP_CACHE = ApiMapResponse(
            internal_connections=internal, external_connections=external
        )
        _LAST_CACHE_TIME = now

    # Clone from cache to update statuses without mutating cache structure per se
    # (though deepcopy is expensive, structure is small enough)
    response = deepcopy(_API_MAP_CACHE)

    # Update Runtime Status
    from venom_core.api.routes import system_deps

    service_monitor = system_deps.get_service_monitor()

    if service_monitor:
        _update_runtime_statuses(response.internal_connections, service_monitor)
        _update_runtime_statuses(response.external_connections, service_monitor)

    return response
