from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from venom_core.agents.documenter import DocumenterAgent
from venom_core.agents.gardener import GardenerAgent
from venom_core.agents.operator import OperatorAgent
from venom_core.api.audio_stream import AudioStreamHandler

# Import routers
from venom_core.api.routes import agents as agents_routes
from venom_core.api.routes import benchmark as benchmark_routes
from venom_core.api.routes import flow as flow_routes
from venom_core.api.routes import git as git_routes
from venom_core.api.routes import knowledge as knowledge_routes
from venom_core.api.routes import memory as memory_routes
from venom_core.api.routes import metrics as metrics_routes
from venom_core.api.routes import models as models_routes
from venom_core.api.routes import nodes as nodes_routes
from venom_core.api.routes import queue as queue_routes
from venom_core.api.routes import strategy as strategy_routes
from venom_core.api.routes import system as system_routes
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
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

# Inicjalizacja StateManager
state_manager = StateManager(state_file_path=SETTINGS.STATE_FILE_PATH)

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Zarządzanie cyklem życia aplikacji."""
    global vector_store, graph_store, lessons_store, gardener_agent, git_skill
    global background_scheduler, file_watcher, documenter_agent
    global audio_engine, operator_agent, hardware_bridge, audio_stream_handler
    global node_manager, orchestrator, request_tracer
    global shadow_agent, desktop_sensor, notifier
    global service_registry, service_monitor, model_manager, llm_controller
    global benchmark_service

    # Startup
    # Inicjalizuj MetricsCollector
    init_metrics_collector()

    # Ustaw EventBroadcaster dla live log streaming
    from venom_core.utils import logger as logger_module

    logger_module.set_event_broadcaster(event_broadcaster)
    logger.info("Live log streaming włączony")

    # Inicjalizuj RequestTracer
    try:
        request_tracer = RequestTracer(watchdog_timeout_minutes=5)
        await request_tracer.start_watchdog()
        logger.info("RequestTracer zainicjalizowany z watchdog")
    except Exception as e:
        logger.warning(f"Nie udało się zainicjalizować RequestTracer: {e}")
        request_tracer = None

    # Inicjalizuj Service Health Monitor
    try:
        service_registry = ServiceRegistry()
        service_monitor = ServiceHealthMonitor(service_registry)
        logger.info("Service Health Monitor zainicjalizowany")
    except Exception as e:
        logger.warning(f"Nie udało się zainicjalizować Service Health Monitor: {e}")
        service_registry = None
        service_monitor = None
    try:
        llm_controller = LlmServerController(SETTINGS)
    except Exception as e:  # pragma: no cover - błędy inicjalizacji są logowane
        logger.warning(f"Nie udało się utworzyć kontrolera LLM: {e}")
        llm_controller = None

    # Inicjalizuj Model Manager (THE_ARMORY)
    from venom_core.core.model_manager import ModelManager

    try:
        model_manager = ModelManager(models_dir=str(Path(SETTINGS.ACADEMY_MODELS_DIR)))
        logger.info(
            f"ModelManager zainicjalizowany (models_dir={model_manager.models_dir})"
        )
    except Exception as e:
        logger.warning(f"Nie udało się zainicjalizować ModelManager: {e}")
        model_manager = None

    # Inicjalizuj Benchmark Service
    try:
        from venom_core.core.model_registry import ModelRegistry
        from venom_core.services.benchmark import BenchmarkService

        model_registry = ModelRegistry()
        benchmark_service = BenchmarkService(
            model_registry=model_registry,
            service_monitor=service_monitor,
            llm_controller=llm_controller,
        )
        logger.info("BenchmarkService zainicjalizowany")
    except Exception as e:
        logger.warning(f"Nie udało się zainicjalizować BenchmarkService: {e}")
        benchmark_service = None

    # Inicjalizuj Node Manager (THE_NEXUS) - jako pierwszy, bo orchestrator go potrzebuje
    if SETTINGS.ENABLE_NEXUS:
        try:
            from venom_core.core.node_manager import NodeManager

            token = SETTINGS.NEXUS_SHARED_TOKEN.get_secret_value()
            if not token:
                logger.warning(
                    "ENABLE_NEXUS=true ale NEXUS_SHARED_TOKEN jest pusty. "
                    "Węzły nie będą mogły się połączyć."
                )
            else:
                node_manager = NodeManager(
                    shared_token=token,
                    heartbeat_timeout=SETTINGS.NEXUS_HEARTBEAT_TIMEOUT,
                )
                await node_manager.start()
                logger.info("NodeManager uruchomiony - Venom działa w trybie Nexus")
                # Port aplikacji FastAPI, domyślnie 8000
                app_port = getattr(SETTINGS, "APP_PORT", 8000)
                logger.info(
                    f"Węzły mogą łączyć się przez WebSocket: ws://localhost:{app_port}/ws/nodes"
                )
        except Exception as e:
            logger.warning(f"Nie udało się uruchomić NodeManager: {e}")
            node_manager = None

    # Inicjalizuj Orchestrator (z node_manager jeśli dostępny)
    orchestrator = Orchestrator(
        state_manager,
        event_broadcaster=event_broadcaster,
        node_manager=node_manager,
        request_tracer=request_tracer,
    )
    logger.info(
        "Orchestrator zainicjalizowany"
        + (" z obsługą węzłów rozproszonych" if node_manager else "")
    )

    # Utwórz katalog workspace jeśli nie istnieje
    workspace_path = Path(SETTINGS.WORKSPACE_ROOT)
    workspace_path.mkdir(parents=True, exist_ok=True)
    logger.info(f"Workspace directory: {workspace_path.resolve()}")

    # Utwórz katalog memory jeśli nie istnieje
    memory_path = Path(SETTINGS.MEMORY_ROOT)
    memory_path.mkdir(parents=True, exist_ok=True)
    logger.info(f"Memory directory: {memory_path.resolve()}")

    # Inicjalizuj VectorStore
    try:
        vector_store = VectorStore()
        logger.info("VectorStore zainicjalizowany")
    except Exception as e:
        logger.warning(f"Nie udało się zainicjalizować VectorStore: {e}")
        vector_store = None

    # Inicjalizuj GraphStore
    try:
        graph_store = CodeGraphStore()
        graph_store.load_graph()  # Załaduj istniejący graf jeśli jest
        logger.info("CodeGraphStore zainicjalizowany")
    except Exception as e:
        logger.warning(f"Nie udało się zainicjalizować CodeGraphStore: {e}")
        graph_store = None

    # Inicjalizuj LessonsStore z VectorStore
    try:
        lessons_store = LessonsStore(vector_store=vector_store)
        logger.info(
            f"LessonsStore zainicjalizowany z {len(lessons_store.lessons)} lekcjami"
        )
    except Exception as e:
        logger.warning(f"Nie udało się zainicjalizować LessonsStore: {e}")
        lessons_store = None

    # Połącz LessonsStore z Orchestrator
    if lessons_store:
        orchestrator.lessons_store = lessons_store
        logger.info("LessonsStore podłączony do Orchestrator (meta-uczenie włączone)")

    # Inicjalizuj i uruchom GardenerAgent
    try:
        gardener_agent = GardenerAgent(
            graph_store=graph_store,
            orchestrator=orchestrator,
            event_broadcaster=event_broadcaster,
        )
        await gardener_agent.start()
        logger.info("GardenerAgent uruchomiony")
    except Exception as e:
        logger.warning(f"Nie udało się uruchomić GardenerAgent: {e}")
        gardener_agent = None

    # Inicjalizuj GitSkill dla API
    try:
        git_skill = GitSkill(workspace_root=str(workspace_path))
        logger.info("GitSkill zainicjalizowany dla API")
    except Exception as e:
        logger.warning(f"Nie udało się zainicjalizować GitSkill: {e}")
        git_skill = None

    # Inicjalizuj BackgroundScheduler (THE_OVERMIND)
    try:
        background_scheduler = BackgroundScheduler(event_broadcaster=event_broadcaster)
        await background_scheduler.start()
        logger.info("BackgroundScheduler uruchomiony")

        # Rejestruj domyślne zadania
        if vector_store and SETTINGS.ENABLE_MEMORY_CONSOLIDATION:
            # Wrapper do przekazania event_broadcaster
            async def _consolidate_memory_wrapper():
                await job_scheduler.consolidate_memory(event_broadcaster)

            background_scheduler.add_interval_job(
                func=_consolidate_memory_wrapper,
                minutes=SETTINGS.MEMORY_CONSOLIDATION_INTERVAL_MINUTES,
                job_id="consolidate_memory",
                description="Konsolidacja pamięci i analiza logów (placeholder)",
            )
            logger.info(
                "Zadanie consolidate_memory zarejestrowane (PLACEHOLDER - wymaga implementacji)"
            )

        if SETTINGS.ENABLE_HEALTH_CHECKS:
            # Wrapper do przekazania event_broadcaster
            async def _check_health_wrapper():
                await job_scheduler.check_health(event_broadcaster)

            background_scheduler.add_interval_job(
                func=_check_health_wrapper,
                minutes=SETTINGS.HEALTH_CHECK_INTERVAL_MINUTES,
                job_id="check_health",
                description="Sprawdzanie zdrowia systemu (placeholder)",
            )
            logger.info(
                "Zadanie check_health zarejestrowane (PLACEHOLDER - wymaga implementacji)"
            )

    except Exception as e:
        logger.warning(f"Nie udało się uruchomić BackgroundScheduler: {e}")
        background_scheduler = None

    # Inicjalizuj DocumenterAgent
    try:
        documenter_agent = DocumenterAgent(
            workspace_root=str(workspace_path),
            git_skill=git_skill,
            event_broadcaster=event_broadcaster,
        )
        logger.info("DocumenterAgent zainicjalizowany")
    except Exception as e:
        logger.warning(f"Nie udało się zainicjalizować DocumenterAgent: {e}")
        documenter_agent = None

    # Inicjalizuj FileWatcher
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
    except Exception as e:
        logger.warning(f"Nie udało się uruchomić FileWatcher: {e}")
        file_watcher = None

    # Inicjalizuj Audio Engine (THE_AVATAR)
    if SETTINGS.ENABLE_AUDIO_INTERFACE:
        try:
            audio_engine = AudioEngine(
                whisper_model_size=SETTINGS.WHISPER_MODEL_SIZE,
                tts_model_path=SETTINGS.TTS_MODEL_PATH,
                device=SETTINGS.AUDIO_DEVICE,
            )
            logger.info("AudioEngine zainicjalizowany")
        except Exception as e:
            logger.warning(f"Nie udało się zainicjalizować AudioEngine: {e}")
            audio_engine = None

    # Inicjalizuj Hardware Bridge (Rider-Pi)
    if SETTINGS.ENABLE_IOT_BRIDGE:
        try:
            hardware_bridge = HardwareBridge(
                host=SETTINGS.RIDER_PI_HOST,
                port=SETTINGS.RIDER_PI_PORT,
                username=SETTINGS.RIDER_PI_USERNAME,
                password=SETTINGS.RIDER_PI_PASSWORD,
                protocol=SETTINGS.RIDER_PI_PROTOCOL,
            )
            # Połącz w tle
            connected = await hardware_bridge.connect()
            if connected:
                logger.info("HardwareBridge połączony z Rider-Pi")
            else:
                logger.warning("Nie udało się połączyć z Rider-Pi")
        except Exception as e:
            logger.warning(f"Nie udało się zainicjalizować HardwareBridge: {e}")
            hardware_bridge = None

    # Inicjalizuj Operator Agent
    if SETTINGS.ENABLE_AUDIO_INTERFACE and audio_engine:
        try:
            from venom_core.execution.kernel_builder import build_kernel

            operator_kernel = build_kernel()
            operator_agent = OperatorAgent(
                kernel=operator_kernel,
                hardware_bridge=hardware_bridge,
            )
            logger.info("OperatorAgent zainicjalizowany")
        except Exception as e:
            logger.warning(f"Nie udało się zainicjalizować OperatorAgent: {e}")
            operator_agent = None

    # Inicjalizuj Audio Stream Handler
    if audio_engine and operator_agent:
        try:
            audio_stream_handler = AudioStreamHandler(
                audio_engine=audio_engine,
                vad_threshold=SETTINGS.VAD_THRESHOLD,
                silence_duration=SETTINGS.SILENCE_DURATION,
            )
            logger.info("AudioStreamHandler zainicjalizowany")
        except Exception as e:
            logger.warning(f"Nie udało się zainicjalizować AudioStreamHandler: {e}")
            audio_stream_handler = None

    # Inicjalizuj Shadow Agent i Desktop Sensor (THE_SHADOW)
    if SETTINGS.ENABLE_PROACTIVE_MODE:
        try:
            from venom_core.agents.shadow import ShadowAgent
            from venom_core.execution.kernel_builder import build_kernel
            from venom_core.perception.desktop_sensor import DesktopSensor
            from venom_core.ui.notifier import Notifier

            # Callback dla desktop sensor
            async def handle_shadow_action(action_payload: dict):
                """
                Obsługa akcji z powiadomień Shadow Agent.

                UWAGA: Podstawowa implementacja - akcje nie wykonują rzeczywistych zmian.
                TODO: Pełna implementacja wymaga integracji z:
                - Orchestrator (error_fix, code_improvement)
                - GoalStore (task_update)
                - Coder Agent (code generation)
                """
                logger.info(f"Shadow Agent action triggered: {action_payload}")

                # Obsługa różnych typów akcji
                action_type = action_payload.get("type", "unknown")

                if action_type == "error_fix":
                    # TODO: Zintegrować z Orchestrator do naprawy błędu
                    # Przykład: await orchestrator.submit_task(TaskRequest(content=f"Fix error: {action_payload['error_text']}"))
                    logger.info("Action: Error fix requested (not implemented)")

                elif action_type == "code_improvement":
                    # TODO: Zintegrować z Coder Agent
                    # Przykład: await coder_agent.improve_code(action_payload['code'])
                    logger.info("Action: Code improvement requested (not implemented)")

                elif action_type == "task_update":
                    # TODO: Zaktualizować status zadania w GoalStore
                    # Przykład: goal_store.update_goal_status(goal_id, GoalStatus.IN_PROGRESS)
                    logger.info("Action: Task update requested (not implemented)")

                else:
                    logger.warning(f"Unknown action type: {action_type}")

                # Broadcast akcji do UI
                await event_broadcaster.broadcast_event(
                    event_type=EventType.SYSTEM_LOG,
                    message=f"Shadow action triggered: {action_type} (implementation pending)",
                    data=action_payload,
                )

            notifier = Notifier(webhook_handler=handle_shadow_action)
            logger.info("Notifier zainicjalizowany")

            # Inicjalizuj Shadow Agent
            shadow_kernel = build_kernel()
            shadow_agent = ShadowAgent(
                kernel=shadow_kernel,
                goal_store=(
                    orchestrator.goal_store
                    if hasattr(orchestrator, "goal_store")
                    else None
                ),
                lessons_store=lessons_store,
                confidence_threshold=SETTINGS.SHADOW_CONFIDENCE_THRESHOLD,
            )
            await shadow_agent.start()
            logger.info("ShadowAgent uruchomiony")

            # Callback dla desktop sensor
            async def handle_sensor_data(sensor_data: dict):
                """Obsługa danych z Desktop Sensor."""
                logger.debug(f"Desktop Sensor data: {sensor_data.get('type')}")

                # Przekaż do Shadow Agent do analizy
                suggestion = await shadow_agent.analyze_sensor_data(sensor_data)

                if suggestion:
                    logger.info(f"Shadow Agent suggestion: {suggestion.title}")

                    # Wyślij powiadomienie
                    await notifier.send_toast(
                        title=suggestion.title,
                        message=suggestion.message,
                        action_payload=suggestion.action_payload,
                    )

                    # Broadcast event do UI
                    await event_broadcaster.broadcast_event(
                        event_type=EventType.SYSTEM_LOG,
                        message=f"Shadow: {suggestion.title}",
                        data=suggestion.to_dict(),
                    )

            # Inicjalizuj Desktop Sensor
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

        except Exception as e:
            logger.warning(f"Nie udało się zainicjalizować Shadow Agent: {e}")
            shadow_agent = None
            desktop_sensor = None
            notifier = None
    else:
        logger.info("Proactive Mode wyłączony (ENABLE_PROACTIVE_MODE=False)")

    # Ustaw zależności routerów po inicjalizacji wszystkich komponentów
    setup_router_dependencies()
    logger.info("Aplikacja uruchomiona - zależności routerów ustawione")

    yield

    # Shutdown
    logger.info("Zamykanie aplikacji...")

    # Zatrzymaj RequestTracer watchdog
    if request_tracer:
        await request_tracer.stop_watchdog()
        logger.info("RequestTracer watchdog zatrzymany")

    # Zatrzymaj Shadow Agent components
    if desktop_sensor:
        await desktop_sensor.stop()
        logger.info("DesktopSensor zatrzymany")

    if shadow_agent:
        await shadow_agent.stop()
        logger.info("ShadowAgent zatrzymany")

    # Zatrzymaj Node Manager
    if node_manager:
        await node_manager.stop()
        logger.info("NodeManager zatrzymany")

    # Zatrzymaj BackgroundScheduler najpierw (może korzystać z innych komponentów)
    if background_scheduler:
        await background_scheduler.stop()
        logger.info("BackgroundScheduler zatrzymany")

    # Zatrzymaj FileWatcher
    if file_watcher:
        await file_watcher.stop()
        logger.info("FileWatcher zatrzymany")

    # Zatrzymaj GardenerAgent
    if gardener_agent:
        await gardener_agent.stop()
        logger.info("GardenerAgent zatrzymany")

    # Rozłącz Hardware Bridge
    if hardware_bridge:
        await hardware_bridge.disconnect()
        logger.info("HardwareBridge rozłączony")

    # Czeka na zakończenie zapisów stanu
    await state_manager.shutdown()
    logger.info("Aplikacja zamknięta")


app = FastAPI(title="Venom Core", version="0.1.0", lifespan=lifespan)


# Funkcja do ustawienia zależności routerów - wywoływana po inicjalizacji w lifespan
def setup_router_dependencies():
    """Konfiguracja zależności routerów po inicjalizacji."""
    tasks_routes.set_dependencies(orchestrator, state_manager, request_tracer)
    queue_routes.set_dependencies(orchestrator)
    # TokenEconomist nie jest jeszcze zainicjalizowany — przekazujemy None.
    # UWAGA: Endpointy metrics mogą zwracać szacunkowe dane, dopóki TokenEconomist nie zostanie dodany.
    # TODO: Zainicjalizować TokenEconomist i przekazać tutaj, gdy będzie dostępny (np. po dodaniu obsługi w lifespan).
    metrics_routes.set_dependencies(token_economist=None)
    memory_routes.set_dependencies(vector_store)
    git_routes.set_dependencies(git_skill)
    knowledge_routes.set_dependencies(graph_store, lessons_store)
    agents_routes.set_dependencies(
        gardener_agent, shadow_agent, file_watcher, documenter_agent, orchestrator
    )
    system_routes.set_dependencies(
        background_scheduler, service_monitor, state_manager, llm_controller
    )
    nodes_routes.set_dependencies(node_manager)
    strategy_routes.set_dependencies(orchestrator)
    models_routes.set_dependencies(model_manager)
    flow_routes.set_dependencies(request_tracer)
    benchmark_routes.set_dependencies(benchmark_service)


# Montowanie routerów
app.include_router(tasks_routes.router)
app.include_router(queue_routes.router)
app.include_router(metrics_routes.router)
app.include_router(memory_routes.router)
app.include_router(git_routes.router)
app.include_router(knowledge_routes.router)
app.include_router(agents_routes.router)
app.include_router(system_routes.router)
app.include_router(nodes_routes.router)
app.include_router(strategy_routes.router)
app.include_router(models_routes.router)
app.include_router(flow_routes.router)
app.include_router(benchmark_routes.router)

# Montowanie plików statycznych
if SETTINGS.SERVE_LEGACY_UI:
    web_dir = Path(__file__).parent.parent / "web"
    if web_dir.exists():
        app.mount(
            "/static", StaticFiles(directory=str(web_dir / "static")), name="static"
        )
        logger.info(f"Static files served from: {web_dir / 'static'}")
    else:
        logger.warning("SERVE_LEGACY_UI=True, ale katalog 'web/' nie istnieje.")

    templates = Jinja2Templates(directory=str(web_dir / "templates"))

    @app.get("/", include_in_schema=False)
    async def serve_dashboard(request: Request):
        """Serwuje główny dashboard (Cockpit) – legacy."""
        return templates.TemplateResponse("index.html", {"request": request})

    @app.get("/strategy", include_in_schema=False)
    async def serve_strategy(request: Request):
        """Serwuje War Room (Strategy Dashboard) – legacy."""
        return templates.TemplateResponse("strategy.html", {"request": request})

    @app.get("/flow-inspector", include_in_schema=False)
    async def serve_flow_inspector(request: Request):
        """Serwuje Flow Inspector - wizualizację procesów decyzyjnych – legacy."""
        return templates.TemplateResponse("flow_inspector.html", {"request": request})

    @app.get("/inspector", include_in_schema=False)
    async def serve_inspector(request: Request):
        """Serwuje Interactive Inspector (Alpine.js + svg-pan-zoom) – legacy."""
        return templates.TemplateResponse("inspector.html", {"request": request})

    @app.get("/brain", include_in_schema=False)
    async def serve_brain(request: Request):
        """Serwuje The Brain - interaktywny graf wiedzy (Cytoscape.js) – legacy."""
        return templates.TemplateResponse("brain.html", {"request": request})

    logger.info("Legacy FastAPI UI włączone (SERVE_LEGACY_UI=True).")
else:
    logger.info("Legacy FastAPI UI wyłączone (SERVE_LEGACY_UI=False).")


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
        # Odbierz pierwszą wiadomość (powinna być handshake)
        from venom_core.nodes.protocol import MessageType, NodeHandshake, NodeMessage

        message_str = await websocket.receive_text()
        import json

        message_dict = json.loads(message_str)
        message = NodeMessage(**message_dict)

        if message.message_type != MessageType.HANDSHAKE:
            await websocket.close(code=1003, reason="Expected HANDSHAKE message")
            return

        # Parsuj handshake
        handshake = NodeHandshake(**message.payload)
        node_id = handshake.node_id

        # Zarejestruj węzeł
        registered = await node_manager.register_node(handshake, websocket)
        if not registered:
            await websocket.close(code=1008, reason="Authentication failed")
            return

        # Broadcast informacji o nowym węźle
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

        # Pętla odbierania wiadomości
        while True:
            try:
                message_str = await websocket.receive_text()
                message_dict = json.loads(message_str)
                message = NodeMessage(**message_dict)

                if message.message_type == MessageType.HEARTBEAT:
                    from venom_core.nodes.protocol import HeartbeatMessage

                    heartbeat = HeartbeatMessage(**message.payload)
                    await node_manager.update_heartbeat(heartbeat)

                elif message.message_type == MessageType.RESPONSE:
                    from venom_core.nodes.protocol import NodeResponse

                    response = NodeResponse(**message.payload)
                    await node_manager.handle_response(response)

                elif message.message_type == MessageType.DISCONNECT:
                    logger.info(f"Węzeł {node_id} zgłosił rozłączenie")
                    break

            except json.JSONDecodeError as e:
                logger.warning(f"Nieprawidłowy JSON od węzła {node_id}: {e}")
                continue  # Kontynuuj pętlę, nie rozłączaj węzła
            except Exception as e:
                logger.warning(f"Błąd parsowania wiadomości od węzła {node_id}: {e}")
                continue

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


# Metrics endpoint moved to venom_core/api/routes/system.py


# --- Graph & Lessons API Endpoints ---


# Graph endpoints moved to venom_core/api/routes/knowledge.py

# Lessons endpoints moved to venom_core/api/routes/knowledge.py


# Gardener endpoint moved to venom_core/api/routes/agents.py

# Scheduler endpoints moved to venom_core/api/routes/system.py

# Watcher and Documenter endpoints moved to venom_core/api/routes/agents.py

# Shadow Agent endpoints moved to venom_core/api/routes/agents.py

# ==================== NODE MANAGEMENT API (THE_NEXUS) ====================


# Strategy endpoints (roadmap, campaign) moved to venom_core/api/routes/strategy.py

# === SYSTEM HEALTH API (Dashboard v2.1) ===
