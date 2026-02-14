import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from venom_core.agents.documenter import DocumenterAgent
from venom_core.agents.gardener import GardenerAgent
from venom_core.agents.operator import OperatorAgent
from venom_core.api import dependencies as api_deps
from venom_core.api.audio_stream import AudioStreamHandler

# Import routers
from venom_core.api.routes import academy as academy_routes
from venom_core.api.routes import agents as agents_routes
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
from venom_core.api.stream import EventType, connection_manager, event_broadcaster
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
from venom_core.services.session_store import SessionStore
from venom_core.utils.helpers import extract_secret_value
from venom_core.utils.llm_runtime import (
    get_active_llm_runtime,
    probe_runtime_status,
    warmup_local_runtime,
)
from venom_core.utils.logger import get_logger

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

    init_metrics_collector()

    from venom_core.utils import logger as logger_module

    logger_module.set_event_broadcaster(event_broadcaster)
    logger.info("Live log streaming włączony")

    try:
        traces_path = str(Path(SETTINGS.MEMORY_ROOT) / "request_traces.json")
        request_tracer = RequestTracer(
            watchdog_timeout_minutes=5, trace_file_path=traces_path
        )
        await request_tracer.start_watchdog()
        logger.info(f"RequestTracer zainicjalizowany z historią w {traces_path}")
    except Exception as exc:
        logger.warning(f"Nie udało się zainicjalizować RequestTracer: {exc}")
        request_tracer = None

    try:
        service_registry = ServiceRegistry()
        service_monitor = ServiceHealthMonitor(
            service_registry, event_broadcaster=event_broadcaster
        )
        logger.info("Service Health Monitor zainicjalizowany")
    except Exception as exc:
        logger.warning(f"Nie udało się zainicjalizować Service Health Monitor: {exc}")
        service_registry = None
        service_monitor = None

    try:
        llm_controller = LlmServerController(SETTINGS)
    except Exception as exc:  # pragma: no cover - błędy inicjalizacji są logowane
        logger.warning(f"Nie udało się utworzyć kontrolera LLM: {exc}")
        llm_controller = None


def _initialize_model_services() -> None:
    global model_manager, model_registry, benchmark_service

    from venom_core.core.model_manager import ModelManager

    try:
        model_manager = ModelManager(models_dir=str(Path(SETTINGS.ACADEMY_MODELS_DIR)))
        logger.info(
            f"ModelManager zainicjalizowany (models_dir={model_manager.models_dir})"
        )
    except Exception as exc:
        logger.warning(f"Nie udało się zainicjalizować ModelManager: {exc}")
        model_manager = None

    try:
        from venom_core.core.model_registry import ModelRegistry
        from venom_core.services.benchmark import BenchmarkService

        if not service_monitor:
            raise RuntimeError("Service monitor niedostępny - pomijam BenchmarkService")
        model_registry = ModelRegistry()
        benchmark_service = BenchmarkService(
            model_registry=model_registry,
            service_monitor=service_monitor,
            llm_controller=llm_controller,
        )
        logger.info("BenchmarkService zainicjalizowany")
    except Exception as exc:
        logger.warning(f"Nie udało się zainicjalizować BenchmarkService: {exc}")
        benchmark_service = None


def _initialize_calendar_skill() -> None:
    global google_calendar_skill

    if not SETTINGS.ENABLE_GOOGLE_CALENDAR:
        logger.info("GoogleCalendarSkill wyłączony w konfiguracji")
        return

    try:
        from venom_core.execution.skills.google_calendar_skill import (
            GoogleCalendarSkill,
        )

        google_calendar_skill = GoogleCalendarSkill()
        if google_calendar_skill.credentials_available:
            logger.info("GoogleCalendarSkill zainicjalizowany dla API")
        else:
            logger.info(
                "GoogleCalendarSkill zainicjalizowany bez credentials - "
                "graceful degradation"
            )
    except Exception as exc:
        logger.warning(f"Nie udało się zainicjalizować GoogleCalendarSkill: {exc}")
        google_calendar_skill = None


def _initialize_academy() -> None:
    """Inicjalizacja komponentów THE_ACADEMY (trenowanie modeli)."""
    global professor, dataset_curator, gpu_habitat

    if not SETTINGS.ENABLE_ACADEMY:
        logger.info("THE_ACADEMY wyłączone w konfiguracji (ENABLE_ACADEMY=False)")
        return

    try:
        logger.info("Inicjalizacja THE_ACADEMY...")

        # Import komponentów Academy
        from venom_core.agents.professor import Professor
        from venom_core.infrastructure.gpu_habitat import GPUHabitat
        from venom_core.learning.dataset_curator import DatasetCurator

        # Inicjalizacja DatasetCurator
        dataset_curator = DatasetCurator(lessons_store=lessons_store)
        logger.info("✅ DatasetCurator zainicjalizowany")

        # Inicjalizacja GPUHabitat
        gpu_habitat = GPUHabitat(enable_gpu=SETTINGS.ACADEMY_ENABLE_GPU)
        logger.info(
            f"✅ GPUHabitat zainicjalizowany (GPU: {SETTINGS.ACADEMY_ENABLE_GPU})"
        )

        # Inicjalizacja Professor (wymaga kernela z task_dispatchera orchestratora).
        # Jeśli kernel nie jest jeszcze gotowy, zrobimy retry w setup_router_dependencies().
        kernel = _get_orchestrator_kernel()
        if kernel is not None:
            professor = Professor(
                kernel=kernel,
                dataset_curator=dataset_curator,
                gpu_habitat=gpu_habitat,
                lessons_store=lessons_store,
            )
            logger.info("✅ Professor zainicjalizowany")
        else:
            logger.warning(
                "Orchestrator lub kernel niedostępny - Professor zostanie "
                "zainicjalizowany później"
            )

        # Restore aktywnego adaptera po restarcie (strict + fallback do modelu bazowego).
        if model_manager:
            try:
                restored = model_manager.restore_active_adapter()
                if restored:
                    logger.info("✅ Odtworzono aktywny adapter Academy po starcie")
                else:
                    logger.info("Brak aktywnego adaptera do odtworzenia po starcie")
            except Exception as exc:
                logger.warning(
                    "Nie udało się odtworzyć aktywnego adaptera Academy: %s",
                    exc,
                )

        logger.info("✅ THE_ACADEMY zainicjalizowane pomyślnie")

    except ImportError as exc:
        logger.warning(
            f"THE_ACADEMY dependencies not installed. Install with: "
            f"pip install -r requirements-academy.txt. Error: {exc}"
        )
        professor = None
        dataset_curator = None
        gpu_habitat = None
    except Exception as exc:
        logger.error(f"❌ Błąd podczas inicjalizacji THE_ACADEMY: {exc}", exc_info=True)
        professor = None
        dataset_curator = None
        gpu_habitat = None


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

    if not SETTINGS.ENABLE_NEXUS:
        return

    try:
        from venom_core.core.node_manager import NodeManager

        token = SETTINGS.NEXUS_SHARED_TOKEN.get_secret_value()
        if not token:
            logger.warning(
                "ENABLE_NEXUS=true ale NEXUS_SHARED_TOKEN jest pusty. "
                "Węzły nie będą mogły się połączyć."
            )
            return
        node_manager = NodeManager(
            shared_token=token,
            heartbeat_timeout=SETTINGS.NEXUS_HEARTBEAT_TIMEOUT,
        )
        await node_manager.start()
        logger.info("NodeManager uruchomiony - Venom działa w trybie Nexus")
        app_port = getattr(SETTINGS, "APP_PORT", 8000)
        logger.info(
            f"Węzły mogą łączyć się przez WebSocket: ws://localhost:{app_port}/ws/nodes"
        )
    except Exception as exc:
        logger.warning(f"Nie udało się uruchomić NodeManager: {exc}")
        node_manager = None


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

    try:
        vector_store = VectorStore()
        logger.info("VectorStore zainicjalizowany")
    except Exception as exc:
        logger.warning(f"Nie udało się zainicjalizować VectorStore: {exc}")
        vector_store = None

    try:
        graph_store = CodeGraphStore()
        graph_store.load_graph()
        logger.info("CodeGraphStore zainicjalizowany")
    except Exception as exc:
        logger.warning(f"Nie udało się zainicjalizować CodeGraphStore: {exc}")
        graph_store = None

    try:
        lessons_store = LessonsStore(vector_store=vector_store)
        logger.info(
            f"LessonsStore zainicjalizowany z {len(lessons_store.lessons)} lekcjami"
        )
    except Exception as exc:
        logger.warning(f"Nie udało się zainicjalizować LessonsStore: {exc}")
        lessons_store = None

    if lessons_store and orchestrator:
        orchestrator.lessons_store = lessons_store
        logger.info("LessonsStore podłączony do Orchestrator (meta-uczenie włączone)")


async def _initialize_gardener_and_git(workspace_path: Path) -> None:
    global gardener_agent, git_skill

    try:
        gardener_agent = GardenerAgent(
            graph_store=graph_store,
            orchestrator=orchestrator,
            event_broadcaster=event_broadcaster,
        )
        await gardener_agent.start()
        logger.info("GardenerAgent uruchomiony")
    except Exception as exc:
        logger.warning(f"Nie udało się uruchomić GardenerAgent: {exc}")
        gardener_agent = None

    try:
        git_skill = GitSkill(workspace_root=str(workspace_path))
        logger.info("GitSkill zainicjalizowany dla API")
    except Exception as exc:
        logger.warning(f"Nie udało się zainicjalizować GitSkill: {exc}")
        git_skill = None


async def _initialize_background_scheduler() -> None:
    global background_scheduler

    try:
        background_scheduler = BackgroundScheduler(event_broadcaster=event_broadcaster)
        await background_scheduler.start()
        logger.info("BackgroundScheduler uruchomiony")

        if vector_store and SETTINGS.ENABLE_MEMORY_CONSOLIDATION:

            async def _consolidate_memory_wrapper():
                await job_scheduler.consolidate_memory(event_broadcaster)

            background_scheduler.add_interval_job(
                func=_consolidate_memory_wrapper,
                minutes=SETTINGS.MEMORY_CONSOLIDATION_INTERVAL_MINUTES,
                job_id="consolidate_memory",
                description="common.comingSoon",
            )
            logger.info("Zadanie consolidate_memory zarejestrowane (COMING SOON)")

        if SETTINGS.ENABLE_HEALTH_CHECKS:

            async def _check_health_wrapper():
                await job_scheduler.check_health(event_broadcaster)

            background_scheduler.add_interval_job(
                func=_check_health_wrapper,
                minutes=SETTINGS.HEALTH_CHECK_INTERVAL_MINUTES,
                job_id="check_health",
                description="common.comingSoon",
            )
            logger.info("Zadanie check_health zarejestrowane (COMING SOON)")

        if request_tracer:

            async def _cleanup_traces_wrapper():
                try:
                    await asyncio.to_thread(request_tracer.clear_old_traces, days=7)
                except Exception as exc:
                    logger.warning(f"Błąd podczas czyszczenia śladów: {exc}")

            background_scheduler.add_interval_job(
                func=_cleanup_traces_wrapper,
                minutes=1440,
                job_id="cleanup_traces",
                description="Czyszczenie starych śladów żądań (retencja 7 dni)",
            )
            logger.info("Zadanie cleanup_traces zarejestrowane (retencja 7 dni)")

    except Exception as exc:
        logger.warning(f"Nie udało się uruchomić BackgroundScheduler: {exc}")
        background_scheduler = None


async def _initialize_documenter_and_watcher(workspace_path: Path) -> None:
    global documenter_agent, file_watcher

    try:
        documenter_agent = DocumenterAgent(
            workspace_root=str(workspace_path),
            git_skill=git_skill,
            event_broadcaster=event_broadcaster,
        )
        logger.info("DocumenterAgent zainicjalizowany")
    except Exception as exc:
        logger.warning(f"Nie udało się zainicjalizować DocumenterAgent: {exc}")
        documenter_agent = None

    try:
        file_watcher = FileWatcher(
            workspace_root=str(workspace_path),
            on_change_callback=(
                documenter_agent.handle_code_change if documenter_agent else None
            ),
            event_broadcaster=event_broadcaster,
        )
        await file_watcher.start()
        logger.info("FileWatcher uruchomiony")
    except Exception as exc:
        logger.warning(f"Nie udało się uruchomić FileWatcher: {exc}")
        file_watcher = None


def _initialize_audio_engine_if_enabled() -> AudioEngine | None:
    if not SETTINGS.ENABLE_AUDIO_INTERFACE:
        return None
    try:
        audio = AudioEngine(
            whisper_model_size=SETTINGS.WHISPER_MODEL_SIZE,
            tts_model_path=SETTINGS.TTS_MODEL_PATH,
            device=SETTINGS.AUDIO_DEVICE,
        )
        logger.info("AudioEngine zainicjalizowany")
        return audio
    except Exception as exc:
        logger.warning(f"Nie udało się zainicjalizować AudioEngine: {exc}")
        return None


async def _initialize_hardware_bridge_if_enabled() -> HardwareBridge | None:
    if not SETTINGS.ENABLE_IOT_BRIDGE:
        return None
    try:
        password_value = extract_secret_value(SETTINGS.RIDER_PI_PASSWORD)
        bridge = HardwareBridge(
            host=SETTINGS.RIDER_PI_HOST,
            port=SETTINGS.RIDER_PI_PORT,
            username=SETTINGS.RIDER_PI_USERNAME,
            password=password_value,
            protocol=SETTINGS.RIDER_PI_PROTOCOL,
        )
        connected = await bridge.connect()
        if connected:
            logger.info("HardwareBridge połączony z Rider-Pi")
        else:
            logger.warning("Nie udało się połączyć z Rider-Pi")
        return bridge
    except Exception as exc:
        logger.warning(f"Nie udało się zainicjalizować HardwareBridge: {exc}")
        return None


def _initialize_operator_agent_if_possible(
    current_audio_engine: AudioEngine | None,
    current_hardware_bridge: HardwareBridge | None,
) -> OperatorAgent | None:
    if not (SETTINGS.ENABLE_AUDIO_INTERFACE and current_audio_engine):
        return None
    try:
        from venom_core.execution.kernel_builder import KernelBuilder

        operator_kernel = KernelBuilder().build_kernel()
        agent = OperatorAgent(
            kernel=operator_kernel,
            hardware_bridge=current_hardware_bridge,
        )
        logger.info("OperatorAgent zainicjalizowany")
        return agent
    except Exception as exc:
        logger.warning(f"Nie udało się zainicjalizować OperatorAgent: {exc}")
        return None


def _initialize_audio_stream_handler_if_possible(
    current_audio_engine: AudioEngine | None,
    current_operator_agent: OperatorAgent | None,
) -> AudioStreamHandler | None:
    if not (current_audio_engine and current_operator_agent):
        return None
    try:
        handler = AudioStreamHandler(
            audio_engine=current_audio_engine,
            vad_threshold=SETTINGS.VAD_THRESHOLD,
            silence_duration=SETTINGS.SILENCE_DURATION,
        )
        logger.info("AudioStreamHandler zainicjalizowany")
        return handler
    except Exception as exc:
        logger.warning(f"Nie udało się zainicjalizować AudioStreamHandler: {exc}")
        return None


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

    try:
        from venom_core.agents.shadow import ShadowAgent
        from venom_core.execution.kernel_builder import KernelBuilder
        from venom_core.perception.desktop_sensor import DesktopSensor
        from venom_core.ui.notifier import Notifier

        async def handle_shadow_action(action_payload: dict):
            logger.info(f"Shadow Agent action triggered: {action_payload}")
            action_type = action_payload.get("type", "unknown")
            if action_type == "error_fix":
                logger.info("Action: Error fix requested (not implemented)")
            elif action_type == "code_improvement":
                logger.info("Action: Code improvement requested (not implemented)")
            elif action_type == "task_update":
                logger.info("Action: Task update requested (not implemented)")
            else:
                logger.warning(f"Unknown action type: {action_type}")
            await event_broadcaster.broadcast_event(
                event_type=EventType.SYSTEM_LOG,
                message="config.parameters.sections.shadowActions.foundProblem",
                data=action_payload,
            )

        notifier = Notifier(webhook_handler=handle_shadow_action)
        logger.info("Notifier zainicjalizowany")

        shadow_kernel = KernelBuilder().build_kernel()
        goal_store = getattr(orchestrator, "goal_store", None)
        shadow_agent = ShadowAgent(
            kernel=shadow_kernel,
            goal_store=goal_store,
            lessons_store=lessons_store,
            confidence_threshold=SETTINGS.SHADOW_CONFIDENCE_THRESHOLD,
        )
        await shadow_agent.start()
        logger.info("ShadowAgent uruchomiony")
        shadow = shadow_agent
        note = notifier
        assert shadow is not None
        assert note is not None

        async def handle_sensor_data(sensor_data: dict):
            logger.debug(f"Desktop Sensor data: {sensor_data.get('type')}")
            suggestion = await shadow.analyze_sensor_data(sensor_data)
            if suggestion:
                logger.info(f"Shadow Agent suggestion: {suggestion.title}")
                await note.send_toast(
                    title=suggestion.title,
                    message=suggestion.message,
                    action_payload=suggestion.action_payload,
                )
                await event_broadcaster.broadcast_event(
                    event_type=EventType.SYSTEM_LOG,
                    message=f"Shadow: {suggestion.title}",
                    data=suggestion.to_dict(),
                )

        if SETTINGS.ENABLE_DESKTOP_SENSOR:
            desktop_sensor = DesktopSensor(
                clipboard_callback=handle_sensor_data,
                window_callback=handle_sensor_data,
                privacy_filter=SETTINGS.SHADOW_PRIVACY_FILTER,
            )
            await desktop_sensor.start()
            logger.info(
                "DesktopSensor uruchomiony - monitorowanie schowka i okien aktywne"
            )
        else:
            logger.info("DesktopSensor wyłączony (ENABLE_DESKTOP_SENSOR=False)")

    except Exception as exc:
        logger.warning(f"Nie udało się zainicjalizować Shadow Agent: {exc}")
        shadow_agent = None
        desktop_sensor = None
        notifier = None


async def _ensure_local_llm_ready() -> None:
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


async def _shutdown_runtime_components() -> None:
    logger.info("Zamykanie aplikacji...")

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


app = FastAPI(title="Venom Core", version="1.4.0", lifespan=lifespan)

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

    # Set global dependencies in api/dependencies.py
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

    if service_monitor:
        service_monitor.set_orchestrator(orchestrator)

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
    tasks_routes.set_dependencies(orchestrator, state_manager, request_tracer)
    feedback_routes.set_dependencies(orchestrator, state_manager, request_tracer)
    queue_routes.set_dependencies(orchestrator)
    # TokenEconomist zainicjalizowany w _initialize_token_economist()
    metrics_routes.set_dependencies(token_economist=token_economist)
    llm_simple_routes.set_dependencies(request_tracer)
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
    flow_routes.set_dependencies(request_tracer)
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
app.include_router(benchmark_routes.router)
app.include_router(calendar_routes.router)


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
