import asyncio
import json
import os
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from venom_core.agents.documenter import DocumenterAgent
from venom_core.agents.gardener import GardenerAgent
from venom_core.agents.operator import OperatorAgent
from venom_core.api import dependencies as api_deps
from venom_core.api.audio_stream import AudioStreamHandler
from venom_core.api.middleware.traffic_control import TrafficControlMiddleware

# Import routers
from venom_core.api.routes import academy as academy_routes
from venom_core.api.routes import agents as agents_routes
from venom_core.api.routes import audit_stream as audit_stream_routes
from venom_core.api.routes import benchmark as benchmark_routes
from venom_core.api.routes import calendar as calendar_routes
from venom_core.api.routes import feedback as feedback_routes
from venom_core.api.routes import flow as flow_routes
from venom_core.api.routes import git as git_routes
from venom_core.api.routes import governance as governance_routes
from venom_core.api.routes import knowledge as knowledge_routes
from venom_core.api.routes import learning as learning_routes
from venom_core.api.routes import llm_simple as llm_simple_routes
from venom_core.api.routes import memory as memory_routes
from venom_core.api.routes import memory_projection as memory_projection_routes
from venom_core.api.routes import models as models_routes
from venom_core.api.routes import nodes as nodes_routes
from venom_core.api.routes import providers as providers_routes
from venom_core.api.routes import queue as queue_routes
from venom_core.api.routes import strategy as strategy_routes
from venom_core.api.routes import system as system_routes
from venom_core.api.routes import system_config as system_config_routes
from venom_core.api.routes import system_deps
from venom_core.api.routes import system_governance as system_governance_routes
from venom_core.api.routes import system_iot as system_iot_routes
from venom_core.api.routes import system_llm as system_llm_routes
from venom_core.api.routes import system_metrics as metrics_routes
from venom_core.api.routes import system_runtime as system_runtime_routes
from venom_core.api.routes import system_scheduler as system_scheduler_routes
from venom_core.api.routes import system_services as system_services_routes
from venom_core.api.routes import system_status as system_status_routes
from venom_core.api.routes import system_storage as system_storage_routes
from venom_core.api.routes import tasks as tasks_routes
from venom_core.api.routes import traffic_control as traffic_control_routes
from venom_core.api.routes import workflow_control as workflow_control_routes
from venom_core.api.routes import workflow_operations as workflow_operations_routes
from venom_core.api.stream import EventType, connection_manager, event_broadcaster
from venom_core.bootstrap.agents import initialize_academy, initialize_calendar_skill
from venom_core.bootstrap.model_services import initialize_model_services
from venom_core.bootstrap.observability import initialize_observability
from venom_core.bootstrap.router_wiring import (
    RouterModules,
    RuntimeDependencies,
    apply_router_dependencies,
)
from venom_core.bootstrap.runtime_stack import (
    initialize_audio_engine_if_enabled as rt_initialize_audio_engine_if_enabled,
)
from venom_core.bootstrap.runtime_stack import (
    initialize_audio_stream_handler_if_possible as rt_initialize_audio_stream_handler_if_possible,
)
from venom_core.bootstrap.runtime_stack import (
    initialize_background_scheduler as rt_initialize_background_scheduler,
)
from venom_core.bootstrap.runtime_stack import (
    initialize_documenter_and_watcher as rt_initialize_documenter_and_watcher,
)
from venom_core.bootstrap.runtime_stack import (
    initialize_gardener_and_git as rt_initialize_gardener_and_git,
)
from venom_core.bootstrap.runtime_stack import (
    initialize_hardware_bridge_if_enabled as rt_initialize_hardware_bridge_if_enabled,
)
from venom_core.bootstrap.runtime_stack import (
    initialize_memory_stores as rt_initialize_memory_stores,
)
from venom_core.bootstrap.runtime_stack import (
    initialize_node_manager as rt_initialize_node_manager,
)
from venom_core.bootstrap.runtime_stack import (
    initialize_operator_agent_if_possible as rt_initialize_operator_agent_if_possible,
)
from venom_core.bootstrap.runtime_stack import (
    initialize_shadow_stack as rt_initialize_shadow_stack,
)
from venom_core.config import SETTINGS
from venom_core.core.llm_server_controller import LlmServerController
from venom_core.core.metrics import init_metrics_collector
from venom_core.core.orchestrator import Orchestrator
from venom_core.core.permission_guard import permission_guard
from venom_core.core.scheduler import BackgroundScheduler
from venom_core.core.service_monitor import ServiceHealthMonitor, ServiceRegistry
from venom_core.core.state_manager import StateManager
from venom_core.core.tracer import RequestTracer
from venom_core.execution.skills.git_skill import GitSkill
from venom_core.infrastructure.hardware_pi import HardwareBridge
from venom_core.jobs import scheduler as job_scheduler
from venom_core.memory.graph_store import CodeGraphStore
from venom_core.memory.lessons_store import LessonsStore
from venom_core.memory.vector_store import VectorStore
from venom_core.perception.audio_engine import AudioEngine
from venom_core.perception.watcher import FileWatcher
from venom_core.services.audit_stream import get_audit_stream
from venom_core.services.module_registry import include_optional_api_routers
from venom_core.services.session_store import SessionStore
from venom_core.utils.helpers import extract_secret_value
from venom_core.utils.llm_runtime import (
    get_active_llm_runtime,
    probe_runtime_status,
    warmup_local_runtime,
)
from venom_core.utils.logger import get_logger, set_event_broadcaster

logger = get_logger(__name__)
TESTING_MODE = bool(os.getenv("PYTEST_CURRENT_TEST"))

# Inicjalizacja StateManager
state_manager = StateManager(state_file_path=SETTINGS.STATE_FILE_PATH)

# Inicjalizacja SessionStore (źródło prawdy historii sesji)
session_store = SessionStore()

# Inicjalizacja PermissionGuard z StateManager
permission_guard.set_state_manager(state_manager)

# Note: orchestrator zostanie zainicjalizowany w lifespan po utworzeniu node_manager
orchestrator = None

# Inicjalizacja RequestTracer
request_tracer = None

# Inicjalizacja VectorStore dla API
vector_store = None

# Inicjalizacja GraphStore i LessonsStore dla API
graph_store = None
lessons_store = None
gardener_agent = None
git_skill = None

# Inicjalizacja Background Services (THE_OVERMIND)
background_scheduler = None
file_watcher = None
documenter_agent = None
startup_runtime_retention_task: asyncio.Task[None] | None = None

# Inicjalizacja Audio i IoT (THE_AVATAR)
audio_engine = None
operator_agent = None
hardware_bridge = None
audio_stream_handler = None

# Inicjalizacja Node Manager (THE_NEXUS)
node_manager = None

# Inicjalizacja Shadow Agent (THE_SHADOW)
shadow_agent = None
desktop_sensor = None
notifier = None

# Inicjalizacja Service Health Monitor
service_registry = None
service_monitor = None
llm_controller = None

# Inicjalizacja Model Manager (THE_ARMORY)
model_manager = None

# Inicjalizacja Benchmark Service
benchmark_service = None

# Inicjalizacja Model Registry (dla endpointów models)
model_registry = None

# Inicjalizacja Google Calendar Skill (THE_CALENDAR)
google_calendar_skill = None

# Inicjalizacja THE_ACADEMY (Knowledge Distillation & Fine-tuning)
professor = None
dataset_curator = None
gpu_habitat = None

# Inicjalizacja TokenEconomist (Token Usage & Cost Tracking)
token_economist = None


def _get_orchestrator_kernel():
    """Zwraca kernel orchestratora (nowy i legacy kształt obiektu)."""
    if not orchestrator:
        return None
    task_dispatcher = getattr(orchestrator, "task_dispatcher", None)
    if task_dispatcher is not None:
        kernel = getattr(task_dispatcher, "kernel", None)
        if kernel is not None:
            return kernel
    return getattr(orchestrator, "kernel", None)


def _get_orchestrator_skill_manager():
    """Zwraca SkillManager orchestratora, jeśli dostępny."""
    if not orchestrator:
        return None
    task_dispatcher = getattr(orchestrator, "task_dispatcher", None)
    if task_dispatcher is None:
        return None
    return getattr(task_dispatcher, "skill_manager", None)


def _extract_available_local_models(
    models: list[dict[str, object]], server_name: str
) -> set[str]:
    return {
        str(model["name"])
        for model in models
        if model.get("provider") == server_name and model.get("name")
    }


def _select_startup_model(
    available: set[str], desired_model: str, previous_model: str
) -> str:
    if desired_model in available:
        return desired_model
    if previous_model in available:
        return previous_model
    return next(iter(available))


async def _synchronize_startup_local_model(runtime) -> None:
    if not model_manager:
        return
    try:
        from venom_core.services.config_manager import config_manager
        from venom_core.utils.llm_runtime import compute_llm_config_hash

        server_name = (SETTINGS.ACTIVE_LLM_SERVER or runtime.provider or "").lower()
        models = await model_manager.list_local_models()
        available = _extract_available_local_models(models, server_name)
        if not available or SETTINGS.LLM_MODEL_NAME in available:
            return

        config = config_manager.get_config(mask_secrets=False)
        last_model_key = (
            "LAST_MODEL_OLLAMA" if server_name == "ollama" else "LAST_MODEL_VLLM"
        )
        prev_model_key = (
            "PREVIOUS_MODEL_OLLAMA"
            if server_name == "ollama"
            else "PREVIOUS_MODEL_VLLM"
        )
        desired_model = (
            config.get(last_model_key)
            or config.get("HYBRID_LOCAL_MODEL")
            or config.get("LLM_MODEL_NAME", "")
        )
        previous_model = config.get(prev_model_key) or ""
        selected_model = _select_startup_model(available, desired_model, previous_model)
        updates = {
            "LLM_MODEL_NAME": selected_model,
            "HYBRID_LOCAL_MODEL": selected_model,
            last_model_key: selected_model,
        }
        old_last = config.get(last_model_key) or ""
        if old_last and old_last != selected_model:
            updates[prev_model_key] = old_last
        config_manager.update_config(updates)
        try:
            SETTINGS.LLM_MODEL_NAME = selected_model
            SETTINGS.HYBRID_LOCAL_MODEL = selected_model
        except Exception:
            logger.warning("Nie udało się zaktualizować SETTINGS dla modelu LLM.")

        config_hash = compute_llm_config_hash(
            server_name, runtime.endpoint, selected_model
        )
        config_manager.update_config({"LLM_CONFIG_HASH": config_hash})
        try:
            SETTINGS.LLM_CONFIG_HASH = config_hash
            SETTINGS.ACTIVE_LLM_SERVER = server_name
        except Exception:
            logger.warning("Nie udało się zaktualizować SETTINGS dla hash LLM.")
        logger.warning(
            "Skorygowano model LLM na starcie: %s -> %s",
            config.get("LLM_MODEL_NAME", ""),
            selected_model,
        )
    except Exception as exc:
        logger.warning("Nie udało się zweryfikować modelu LLM: %s", exc)


async def _start_configured_local_server(active_server: str) -> None:
    if not llm_controller or not active_server:
        return
    if not llm_controller.has_server(active_server):
        return

    try:
        for server in llm_controller.list_servers():
            name = server.get("name", "").lower()
            if not name or name == active_server:
                continue
            if server.get("supports", {}).get("stop"):
                await llm_controller.run_action(name, "stop")
        await llm_controller.run_action(active_server, "start")
        logger.info("Uruchamianie lokalnego LLM (%s) na starcie.", active_server)
    except Exception as exc:
        logger.warning("Nie udało się uruchomić lokalnego LLM: %s", exc)


async def _wait_for_runtime_online(
    runtime, attempts: int = 90, delay_seconds: float = 1.0
) -> str:
    status = "offline"
    for _ in range(attempts):
        status, _ = await probe_runtime_status(runtime)
        if status == "online":
            return status
        await asyncio.sleep(delay_seconds)
    return status


async def _start_local_runtime_if_needed(runtime) -> str:
    status, _ = await probe_runtime_status(runtime)
    if status == "online":
        return status

    active_server = (SETTINGS.ACTIVE_LLM_SERVER or runtime.provider or "").lower()
    await _start_configured_local_server(active_server)
    status = await _wait_for_runtime_online(runtime)
    if status == "online":
        return status
    logger.warning("Lokalny LLM nadal offline po oczekiwaniu na start.")
    return status


def _parse_node_message(message_str: str):
    from venom_core.nodes.protocol import NodeMessage

    message_dict = json.loads(message_str)
    return NodeMessage(**message_dict)


async def _receive_node_handshake(websocket: WebSocket):
    from venom_core.nodes.protocol import MessageType, NodeHandshake

    message = _parse_node_message(await websocket.receive_text())
    if message.message_type != MessageType.HANDSHAKE:
        await websocket.close(code=1003, reason="Expected HANDSHAKE message")
        return None
    return NodeHandshake(**message.payload)


async def _handle_node_message(message, current_node_id: str) -> bool:
    from venom_core.nodes.protocol import HeartbeatMessage, MessageType, NodeResponse

    if node_manager is None:
        logger.warning(
            "NodeManager niedostępny podczas obsługi wiadomości węzła %s.",
            current_node_id,
        )
        return False

    if message.message_type == MessageType.HEARTBEAT:
        heartbeat = HeartbeatMessage(**message.payload)
        await node_manager.update_heartbeat(heartbeat)
        return True
    if message.message_type == MessageType.RESPONSE:
        response = NodeResponse(**message.payload)
        await node_manager.handle_response(response)
        return True
    if message.message_type == MessageType.DISCONNECT:
        logger.info(f"Węzeł {current_node_id} zgłosił rozłączenie")
        return False
    return True


async def _run_node_message_loop(websocket: WebSocket, current_node_id: str) -> None:
    while True:
        try:
            message = _parse_node_message(await websocket.receive_text())
            keep_connected = await _handle_node_message(message, current_node_id)
            if not keep_connected:
                break
        except json.JSONDecodeError as exc:
            logger.warning(f"Nieprawidłowy JSON od węzła {current_node_id}: {exc}")
            continue
        except Exception as exc:
            logger.warning(
                f"Błąd parsowania wiadomości od węzła {current_node_id}: {exc}"
            )
            continue


async def _initialize_observability() -> None:
    global request_tracer, service_registry, service_monitor, llm_controller

    (
        request_tracer,
        service_registry,
        service_monitor,
        llm_controller,
    ) = await initialize_observability(
        settings=SETTINGS,
        event_broadcaster=event_broadcaster,
        logger=logger,
        init_metrics_collector_fn=init_metrics_collector,
        request_tracer_cls=RequestTracer,
        service_registry_cls=ServiceRegistry,
        service_health_monitor_cls=ServiceHealthMonitor,
        llm_server_controller_cls=LlmServerController,
        set_event_broadcaster_fn=set_event_broadcaster,
    )


def _initialize_model_services() -> None:
    global model_manager, model_registry, benchmark_service

    previous_model_registry = model_registry
    model_manager, new_model_registry, benchmark_service = initialize_model_services(
        settings=SETTINGS,
        service_monitor=service_monitor,
        llm_controller=llm_controller,
        logger=logger,
    )
    if new_model_registry is not None:
        model_registry = new_model_registry
    else:
        model_registry = previous_model_registry


def _initialize_calendar_skill() -> None:
    global google_calendar_skill

    calendar_skill = initialize_calendar_skill(
        settings=SETTINGS,
        logger=logger,
    )
    if calendar_skill is not None:
        google_calendar_skill = calendar_skill


def _initialize_academy() -> None:
    """Inicjalizacja komponentów THE_ACADEMY (trenowanie modeli)."""
    global professor, dataset_curator, gpu_habitat

    professor, dataset_curator, gpu_habitat = initialize_academy(
        settings=SETTINGS,
        logger=logger,
        lessons_store=lessons_store,
        model_manager=model_manager,
        get_orchestrator_kernel=_get_orchestrator_kernel,
    )


def _initialize_token_economist() -> None:
    """Inicjalizacja TokenEconomist dla śledzenia użycia tokenów i kosztów."""
    global token_economist

    try:
        logger.info("Inicjalizacja TokenEconomist...")
        from venom_core.core.token_economist import TokenEconomist

        # Inicjalizacja z domyślnymi ustawieniami
        token_economist = TokenEconomist(
            enable_compression=True,
            pricing_file=None,  # Używamy wbudowanego cennika
        )
        logger.info("✅ TokenEconomist zainicjalizowany")

    except Exception as exc:
        logger.error(
            f"❌ Błąd podczas inicjalizacji TokenEconomist: {exc}", exc_info=True
        )
        token_economist = None


async def _initialize_node_manager() -> None:
    global node_manager

    node_manager = await rt_initialize_node_manager(
        settings=SETTINGS,
        logger=logger,
    )


def _initialize_orchestrator() -> None:
    global orchestrator

    if orchestrator is not None:
        logger.info(
            "Orchestrator już zainicjalizowany (np. tryb testowy) – pomijam "
            "ponowną inicjalizację"
        )
        return

    orchestrator = Orchestrator(
        state_manager,
        event_broadcaster=event_broadcaster,
        node_manager=node_manager,
        session_store=session_store,
        request_tracer=request_tracer,
    )
    logger.info(
        "Orchestrator zainicjalizowany"
        + (" z obsługą węzłów rozproszonych" if node_manager else "")
    )


def _ensure_storage_dirs() -> Path:
    workspace_path = Path(SETTINGS.WORKSPACE_ROOT)
    workspace_path.mkdir(parents=True, exist_ok=True)
    logger.info(f"Workspace directory: {workspace_path.resolve()}")

    memory_path = Path(SETTINGS.MEMORY_ROOT)
    memory_path.mkdir(parents=True, exist_ok=True)
    logger.info(f"Memory directory: {memory_path.resolve()}")
    return workspace_path


def _initialize_memory_stores() -> None:
    global vector_store, graph_store, lessons_store

    vector_store, graph_store, lessons_store = rt_initialize_memory_stores(
        logger=logger,
        vector_store_cls=VectorStore,
        graph_store_cls=CodeGraphStore,
        lessons_store_cls=LessonsStore,
        orchestrator=orchestrator,
    )


async def _initialize_gardener_and_git(workspace_path: Path) -> None:
    global gardener_agent, git_skill

    gardener_agent, git_skill = await rt_initialize_gardener_and_git(
        workspace_path=workspace_path,
        graph_store=graph_store,
        orchestrator=orchestrator,
        event_broadcaster=event_broadcaster,
        logger=logger,
        gardener_agent_cls=GardenerAgent,
        git_skill_cls=GitSkill,
    )


async def _initialize_background_scheduler() -> None:
    global background_scheduler, startup_runtime_retention_task

    (
        background_scheduler,
        startup_runtime_retention_task,
    ) = await rt_initialize_background_scheduler(
        settings=SETTINGS,
        logger=logger,
        event_broadcaster=event_broadcaster,
        vector_store=vector_store,
        request_tracer=request_tracer,
        background_scheduler_cls=BackgroundScheduler,
        job_scheduler_module=job_scheduler,
        asyncio_module=asyncio,
        clear_startup_runtime_retention_task=_clear_startup_runtime_retention_task,
    )


async def _initialize_documenter_and_watcher(workspace_path: Path) -> None:
    global documenter_agent, file_watcher

    documenter_agent, file_watcher = await rt_initialize_documenter_and_watcher(
        workspace_path=workspace_path,
        git_skill=git_skill,
        skill_manager=_get_orchestrator_skill_manager(),
        event_broadcaster=event_broadcaster,
        logger=logger,
        documenter_agent_cls=DocumenterAgent,
        file_watcher_cls=FileWatcher,
    )


def _initialize_audio_engine_if_enabled() -> AudioEngine | None:
    return rt_initialize_audio_engine_if_enabled(
        settings=SETTINGS,
        logger=logger,
        audio_engine_cls=AudioEngine,
    )


async def _initialize_hardware_bridge_if_enabled() -> HardwareBridge | None:
    return await rt_initialize_hardware_bridge_if_enabled(
        settings=SETTINGS,
        logger=logger,
        extract_secret_value_fn=extract_secret_value,
        hardware_bridge_cls=HardwareBridge,
    )


def _initialize_operator_agent_if_possible(
    current_audio_engine: AudioEngine | None,
    current_hardware_bridge: HardwareBridge | None,
) -> OperatorAgent | None:
    return rt_initialize_operator_agent_if_possible(
        settings=SETTINGS,
        logger=logger,
        current_audio_engine=current_audio_engine,
        current_hardware_bridge=current_hardware_bridge,
        operator_agent_cls=OperatorAgent,
    )


def _initialize_audio_stream_handler_if_possible(
    current_audio_engine: AudioEngine | None,
    current_operator_agent: OperatorAgent | None,
) -> AudioStreamHandler | None:
    return rt_initialize_audio_stream_handler_if_possible(
        settings=SETTINGS,
        logger=logger,
        current_audio_engine=current_audio_engine,
        current_operator_agent=current_operator_agent,
        audio_stream_handler_cls=AudioStreamHandler,
    )


async def _initialize_avatar_stack() -> None:
    global audio_engine, hardware_bridge, operator_agent, audio_stream_handler

    audio_engine = _initialize_audio_engine_if_enabled()
    hardware_bridge = await _initialize_hardware_bridge_if_enabled()
    operator_agent = _initialize_operator_agent_if_possible(
        audio_engine, hardware_bridge
    )
    audio_stream_handler = _initialize_audio_stream_handler_if_possible(
        audio_engine, operator_agent
    )


async def _initialize_shadow_stack() -> None:
    global shadow_agent, desktop_sensor, notifier

    if not SETTINGS.ENABLE_PROACTIVE_MODE:
        logger.info("Proactive Mode wyłączony (ENABLE_PROACTIVE_MODE=False)")
        return

    shadow_agent, desktop_sensor, notifier = await rt_initialize_shadow_stack(
        settings=SETTINGS,
        logger=logger,
        orchestrator=orchestrator,
        lessons_store=lessons_store,
        event_broadcaster=event_broadcaster,
        system_log_event_type=EventType.SYSTEM_LOG,
    )


async def _ensure_local_llm_ready() -> None:
    runtime_profile = (
        (getattr(SETTINGS, "VENOM_RUNTIME_PROFILE", "") or "").strip().lower()
    )
    if runtime_profile == "llm_off":
        logger.info(
            "Pomijam inicjalizację lokalnego LLM (VENOM_RUNTIME_PROFILE=llm_off)."
        )
        return
    runtime = get_active_llm_runtime()
    if runtime.service_type != "local":
        return
    await _synchronize_startup_local_model(runtime)
    await _start_local_runtime_if_needed(runtime)
    if SETTINGS.LLM_WARMUP_ON_STARTUP:
        await warmup_local_runtime(
            runtime=runtime,
            prompt=SETTINGS.LLM_WARMUP_PROMPT,
            timeout_seconds=SETTINGS.LLM_WARMUP_TIMEOUT_SECONDS,
            max_tokens=SETTINGS.LLM_WARMUP_MAX_TOKENS,
        )
        logger.info("Warm-up LLM uruchomiony w tle.")


def _clear_startup_runtime_retention_task() -> None:
    global startup_runtime_retention_task
    startup_runtime_retention_task = None


async def _shutdown_runtime_components() -> None:
    global startup_runtime_retention_task
    logger.info("Zamykanie aplikacji...")

    if startup_runtime_retention_task and not startup_runtime_retention_task.done():
        startup_runtime_retention_task.cancel()
        with suppress(asyncio.CancelledError):
            await startup_runtime_retention_task
    startup_runtime_retention_task = None

    # Release in-process ONNX caches/pools early to free VRAM/RAM on shutdown.
    try:
        llm_simple_routes.release_onnx_simple_client()
    except Exception:
        logger.warning("Nie udało się zwolnić klienta ONNX (simple mode).")
    try:
        tasks_routes.release_onnx_task_runtime(wait=False)
    except Exception:
        logger.warning("Nie udało się zwolnić runtime ONNX (tasks mode).")

    if request_tracer:
        await request_tracer.stop_watchdog()
        logger.info("RequestTracer watchdog zatrzymany")
    if desktop_sensor:
        await desktop_sensor.stop()
        logger.info("DesktopSensor zatrzymany")
    if shadow_agent:
        await shadow_agent.stop()
        logger.info("ShadowAgent zatrzymany")
    if node_manager:
        await node_manager.stop()
        logger.info("NodeManager zatrzymany")
    if background_scheduler:
        await background_scheduler.stop()
        logger.info("BackgroundScheduler zatrzymany")
    if file_watcher:
        await file_watcher.stop()
        logger.info("FileWatcher zatrzymany")
    if gardener_agent:
        await gardener_agent.stop()
        logger.info("GardenerAgent zatrzymany")
    if hardware_bridge:
        await hardware_bridge.disconnect()
        logger.info("HardwareBridge rozłączony")

    await state_manager.shutdown()
    logger.info("Aplikacja zamknięta")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Zarządzanie cyklem życia aplikacji."""
    await _initialize_observability()
    _initialize_model_services()
    _initialize_calendar_skill()
    await _initialize_node_manager()
    _initialize_orchestrator()
    workspace_path = _ensure_storage_dirs()
    _initialize_memory_stores()
    _initialize_academy()  # Inicjalizacja THE_ACADEMY
    _initialize_token_economist()  # Inicjalizacja TokenEconomist
    await _initialize_gardener_and_git(workspace_path)
    await _initialize_background_scheduler()
    await _initialize_documenter_and_watcher(workspace_path)
    await _initialize_avatar_stack()
    await _initialize_shadow_stack()
    setup_router_dependencies()
    logger.info("Aplikacja uruchomiona - zależności routerów ustawione")
    app.state.startup_llm_task = asyncio.create_task(_ensure_local_llm_ready())

    yield

    await _shutdown_runtime_components()


app = FastAPI(title="Venom Core", version="1.5.0", lifespan=lifespan)

# Traffic Control Middleware (must be added before CORS for proper ordering)
app.add_middleware(TrafficControlMiddleware)

# CORS dla lokalnego UI (bezpośredni dostęp do API, bez proxy Next).
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3100",
        "http://127.0.0.1:3100",
        "https://localhost:3000",
        "https://127.0.0.1:3000",
        "https://localhost:3100",
        "https://127.0.0.1:3100",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["x-request-id", "x-session-id"],
)


_AUDIT_CHANNEL_BY_PATH_PREFIX: tuple[tuple[str, str], ...] = (
    ("/api/v1/system/status", "System Status API"),
    ("/api/v1/system/services", "System Services API"),
    ("/api/v1/system/runtime", "System Runtime API"),
    ("/api/v1/system/storage", "System Storage API"),
    ("/api/v1/system/iot", "System IoT API"),
    ("/api/v1/tasks", "Tasks API"),
    ("/api/v1/queue", "Queue API"),
    ("/api/v1/agents", "Agents API"),
    ("/api/roadmap", "Strategy API"),
    ("/api/v1/governance", "Governance API"),
    ("/api/v1/providers", "Governance API"),
    ("/api/v1/memory", "Memory API"),
    ("/api/v1/nodes", "Nodes API"),
    ("/api/v1/feedback", "Feedback API"),
    ("/api/v1/chat", "Frontend (Next.js)"),
    ("/api/v1/models", "Frontend (Next.js)"),
)


def _resolve_audit_channel_for_path(path: str) -> str:
    for prefix, channel in _AUDIT_CHANNEL_BY_PATH_PREFIX:
        if path.startswith(prefix):
            return channel
    return "System Services API"


def _resolve_audit_actor(request: Request) -> str:
    for header_name in ("X-Authenticated-User", "X-User", "X-Admin-User"):
        header_value = (request.headers.get(header_name) or "").strip()
        if header_value:
            return header_value
    if hasattr(request, "state") and hasattr(request.state, "user"):
        state_user = str(getattr(request.state, "user", "")).strip()
        if state_user:
            return state_user
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _resolve_audit_status(status_code: int) -> str:
    if status_code >= 500:
        return "failure"
    if status_code >= 400:
        return "warning"
    return "success"


def _resolve_audit_autonomy_snapshot() -> tuple[int, str]:
    try:
        return (
            permission_guard.get_current_level(),
            permission_guard.get_current_level_name(),
        )
    except Exception:
        return (-1, "UNKNOWN")


def _resolve_http_autonomy_policy(
    method: str, status_code: int
) -> tuple[str, bool | None]:
    read_only_methods = {"GET"}
    mutating_methods = {"POST", "PUT", "PATCH", "DELETE"}
    normalized_method = method.upper()

    if normalized_method in read_only_methods:
        return ("not_applicable_read_only", True)
    if normalized_method in mutating_methods and status_code in {401, 403}:
        return ("blocked", False)
    if normalized_method in mutating_methods and 200 <= status_code < 400:
        return ("allowed", True)
    return ("unknown", None)


@app.middleware("http")
async def audit_http_requests(request: Request, call_next):
    response = await call_next(request)

    try:
        path = request.url.path or ""
        if not path.startswith("/api/"):
            return response
        if path.startswith("/api/v1/audit/stream"):
            return response
        if request.method.upper() in {"OPTIONS", "HEAD"}:
            return response

        api_channel = _resolve_audit_channel_for_path(path)
        method = request.method.upper()
        status = _resolve_audit_status(response.status_code)
        current_level, current_level_name = _resolve_audit_autonomy_snapshot()
        autonomy_policy_check, autonomy_policy_compliant = (
            _resolve_http_autonomy_policy(method, response.status_code)
        )
        get_audit_stream().publish(
            source="core.http",
            action=f"http.{method.lower()}",
            actor=_resolve_audit_actor(request),
            status=status,
            context=path,
            details={
                "api_channel": api_channel,
                "http_method": method,
                "http_path": path,
                "status_code": response.status_code,
                "current_autonomy_level": current_level,
                "current_autonomy_level_name": current_level_name,
                "autonomy_policy_check": autonomy_policy_check,
                "autonomy_policy_compliant": autonomy_policy_compliant,
            },
        )
    except Exception:
        logger.debug("HTTP audit mirror skipped due to runtime error", exc_info=True)

    return response


# Funkcja do ustawienia zależności routerów - wywoływana po inicjalizacji w lifespan
def setup_router_dependencies():
    """Konfiguracja zależności routerów po inicjalizacji."""
    global professor

    logger.info(
        f"Setting system dependencies. Orchestrator: {orchestrator is not None}"
    )

    # Academy: druga próba inicjalizacji Professor po pełnym starcie orchestratora.
    retry_kernel = _get_orchestrator_kernel()
    if (
        SETTINGS.ENABLE_ACADEMY
        and professor is None
        and dataset_curator is not None
        and gpu_habitat is not None
        and lessons_store is not None
        and retry_kernel is not None
    ):
        try:
            from venom_core.agents.professor import Professor

            professor = Professor(
                kernel=retry_kernel,
                dataset_curator=dataset_curator,
                gpu_habitat=gpu_habitat,
                lessons_store=lessons_store,
            )
            logger.info(
                "✅ Professor zainicjalizowany (retry po starcie orchestratora)"
            )
        except Exception as exc:
            logger.warning(
                "Nie udało się zainicjalizować Professor w setup_router_dependencies: %s",
                exc,
            )

    apply_router_dependencies(
        api_deps=api_deps,
        system_deps=system_deps,
        routes=RouterModules(
            feedback_routes=feedback_routes,
            queue_routes=queue_routes,
            metrics_routes=metrics_routes,
            git_routes=git_routes,
            agents_routes=agents_routes,
            nodes_routes=nodes_routes,
            strategy_routes=strategy_routes,
            models_routes=models_routes,
            benchmark_routes=benchmark_routes,
            calendar_routes=calendar_routes,
            memory_projection_routes=memory_projection_routes,
            academy_routes=academy_routes,
        ),
        runtime=RuntimeDependencies(
            orchestrator=orchestrator,
            state_manager=state_manager,
            vector_store=vector_store,
            graph_store=graph_store,
            lessons_store=lessons_store,
            session_store=session_store,
            request_tracer=request_tracer,
            service_monitor=service_monitor,
            background_scheduler=background_scheduler,
            llm_controller=llm_controller,
            model_manager=model_manager,
            hardware_bridge=hardware_bridge,
            token_economist=token_economist,
            git_skill=git_skill,
            gardener_agent=gardener_agent,
            shadow_agent=shadow_agent,
            file_watcher=file_watcher,
            documenter_agent=documenter_agent,
            node_manager=node_manager,
            model_registry=model_registry,
            benchmark_service=benchmark_service,
            google_calendar_skill=google_calendar_skill,
            professor=professor,
            dataset_curator=dataset_curator,
            gpu_habitat=gpu_habitat,
        ),
    )


# W trybie testowym (np. httpx ASGITransport bez lifespan) preinicjalizujemy
# orchestratora i zależności routerów, żeby uniknąć 503 Service Unavailable.
if TESTING_MODE and orchestrator is None:
    try:
        # Prowizoryczna inicjalizacja dla testów (bez lifespan)
        if vector_store is None:
            vector_store = VectorStore()
        if graph_store is None:
            graph_store = CodeGraphStore()
        if lessons_store is None:
            lessons_store = LessonsStore(vector_store=vector_store)

        orchestrator = Orchestrator(
            state_manager,
            event_broadcaster=event_broadcaster,
            node_manager=node_manager,
            session_store=session_store,
            request_tracer=request_tracer,
        )
        setup_router_dependencies()
        logger.info(
            "Tryb testowy: orchestrator i magazyny zainicjalizowane bez lifespan"
        )
    except Exception as e:  # pragma: no cover - log zamiast crash w teście
        logger.warning(
            "Tryb testowy: nie udało się zainicjalizować orchestratora "
            f"bez lifespan: {e}"
        )


# Montowanie routerów
app.include_router(tasks_routes.router)
app.include_router(queue_routes.router)
app.include_router(metrics_routes.router)
app.include_router(memory_routes.router)
app.include_router(memory_projection_routes.router)
app.include_router(git_routes.router)
app.include_router(feedback_routes.router)
app.include_router(learning_routes.router)
app.include_router(academy_routes.router)
app.include_router(llm_simple_routes.router)
app.include_router(knowledge_routes.router)
app.include_router(agents_routes.router)
app.include_router(system_scheduler_routes.router)
app.include_router(system_services_routes.router)
app.include_router(system_llm_routes.router)
app.include_router(system_runtime_routes.router)
app.include_router(system_config_routes.router)
app.include_router(system_governance_routes.router)
app.include_router(governance_routes.router)
app.include_router(system_iot_routes.router)
app.include_router(system_status_routes.router)
app.include_router(system_storage_routes.router)
app.include_router(system_routes.router)
app.include_router(nodes_routes.router)
app.include_router(strategy_routes.router)
app.include_router(models_routes.router)
app.include_router(providers_routes.router)
app.include_router(flow_routes.router)
app.include_router(audit_stream_routes.router)
app.include_router(workflow_control_routes.router)
app.include_router(workflow_operations_routes.router)
app.include_router(benchmark_routes.router)
app.include_router(calendar_routes.router)
app.include_router(traffic_control_routes.router)
include_optional_api_routers(app, SETTINGS)


@app.websocket("/ws/events")
async def websocket_endpoint(websocket: WebSocket):
    """
    Endpoint WebSocket dla streamingu zdarzeń w czasie rzeczywistym.

    Args:
        websocket: Połączenie WebSocket
    """
    await connection_manager.connect(websocket)
    try:
        # Send welcome message
        await event_broadcaster.broadcast_event(
            event_type=EventType.SYSTEM_LOG,
            message="Connected to Venom Telemetry",
            data={"level": "INFO"},
        )

        # Keep connection open and listen for client messages
        while True:
            # Receive messages from client (optional)
            data = await websocket.receive_text()
            logger.debug(f"Received from client: {data}")

    except WebSocketDisconnect:
        await connection_manager.disconnect(websocket)
        logger.info("Client disconnected WebSocket")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await connection_manager.disconnect(websocket)


@app.websocket("/ws/audio")
async def audio_websocket_endpoint(websocket: WebSocket):
    """
    Endpoint WebSocket dla streamingu audio (STT/TTS).
    Umożliwia komunikację głosową z systemem Venom.

    Args:
        websocket: Połączenie WebSocket
    """
    if not audio_stream_handler:
        await websocket.close(code=1003, reason="Audio interface not enabled")
        return

    try:
        await audio_stream_handler.handle_websocket(
            websocket,
            operator_agent=operator_agent,
        )
    except Exception as e:
        logger.error(f"Audio WebSocket error: {e}")


@app.websocket("/ws/nodes")
async def nodes_websocket_endpoint(websocket: WebSocket):
    """
    Endpoint WebSocket dla węzłów Venom Spore.
    Umożliwia rejestrację i komunikację z węzłami zdalnymi.

    Args:
        websocket: Połączenie WebSocket
    """
    if not node_manager:
        await websocket.close(code=1003, reason="Nexus mode not enabled")
        return

    await websocket.accept()
    node_id = None

    try:
        handshake = await _receive_node_handshake(websocket)
        if handshake is None:
            return

        node_id = handshake.node_id

        registered = await node_manager.register_node(handshake, websocket)
        if not registered:
            await websocket.close(code=1008, reason="Authentication failed")
            return

        await event_broadcaster.broadcast_event(
            event_type="NODE_CONNECTED",
            message=f"Węzeł {handshake.node_name} ({node_id}) połączył się z Nexusem",
            data={
                "node_id": node_id,
                "node_name": handshake.node_name,
                "skills": handshake.capabilities.skills,
                "tags": handshake.capabilities.tags,
            },
        )

        await _run_node_message_loop(websocket, node_id)

    except WebSocketDisconnect:
        logger.info(f"Węzeł {node_id} rozłączony (WebSocket disconnect)")
    except Exception as e:
        logger.error(f"Błąd w WebSocket węzła {node_id}: {e}")
    finally:
        if node_id is not None:
            await node_manager.unregister_node(node_id)
            await event_broadcaster.broadcast_event(
                event_type="NODE_DISCONNECTED",
                message=f"Węzeł {node_id} rozłączony",
                data={"node_id": node_id},
            )


@app.get("/healthz")
def healthz():
    """Prosty endpoint zdrowia – do sprawdzenia, czy Venom żyje."""
    return {"status": "ok", "component": "venom-core"}


# Tasks endpoints moved to venom_core/api/routes/tasks.py


# History endpoints moved to venom_core/api/routes/tasks.py,

# Memory endpoints moved to venom_core/api/routes/memory.py


# Metrics endpoint moved to venom_core/api/routes/system_metrics.py


# --- Graph & Lessons API Endpoints ---


# Graph endpoints moved to venom_core/api/routes/knowledge.py

# Lessons endpoints moved to venom_core/api/routes/knowledge.py


# Gardener endpoint moved to venom_core/api/routes/agents.py

# Scheduler endpoints moved to venom_core/api/routes/system_scheduler.py

# Watcher and Documenter endpoints moved to venom_core/api/routes/agents.py

# Shadow Agent endpoints moved to venom_core/api/routes/agents.py

# ==================== NODE MANAGEMENT API (THE_NEXUS) ====================


# Strategy endpoints (roadmap, campaign) moved to venom_core/api/routes/strategy.py

# === SYSTEM HEALTH API (Dashboard v2.1) ===
