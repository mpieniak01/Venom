# venom/main.py
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from venom_core.agents.documenter import DocumenterAgent
from venom_core.agents.gardener import GardenerAgent
from venom_core.agents.operator import OperatorAgent
from venom_core.api.audio_stream import AudioStreamHandler
from venom_core.api.stream import EventType, connection_manager, event_broadcaster
from venom_core.config import SETTINGS
from venom_core.core.metrics import init_metrics_collector, metrics_collector
from venom_core.core.models import TaskRequest, TaskResponse, VenomTask
from venom_core.core.orchestrator import Orchestrator
from venom_core.core.scheduler import BackgroundScheduler
from venom_core.core.service_monitor import ServiceHealthMonitor, ServiceRegistry
from venom_core.core.state_manager import StateManager
from venom_core.core.tracer import RequestTracer
from venom_core.execution.skills.git_skill import GitSkill
from venom_core.infrastructure.hardware_pi import HardwareBridge
from venom_core.memory.graph_store import CodeGraphStore
from venom_core.memory.lessons_store import LessonsStore
from venom_core.memory.vector_store import VectorStore
from venom_core.perception.audio_engine import AudioEngine
from venom_core.perception.watcher import FileWatcher
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

# Inicjalizacja StateManager
state_manager = StateManager(state_file_path=SETTINGS.STATE_FILE_PATH)

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Zarządzanie cyklem życia aplikacji."""
    global vector_store, graph_store, lessons_store, gardener_agent, git_skill
    global background_scheduler, file_watcher, documenter_agent
    global audio_engine, operator_agent, hardware_bridge, audio_stream_handler
    global node_manager, orchestrator, request_tracer
    global shadow_agent, desktop_sensor, notifier
    global service_registry, service_monitor

    # Startup
    # Inicjalizuj MetricsCollector
    init_metrics_collector()

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
            background_scheduler.add_interval_job(
                func=_consolidate_memory,
                minutes=SETTINGS.MEMORY_CONSOLIDATION_INTERVAL_MINUTES,
                job_id="consolidate_memory",
                description="Konsolidacja pamięci i analiza logów (placeholder)",
            )
            logger.info(
                "Zadanie consolidate_memory zarejestrowane (PLACEHOLDER - wymaga implementacji)"
            )

        if SETTINGS.ENABLE_HEALTH_CHECKS:
            background_scheduler.add_interval_job(
                func=_check_health,
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


# Funkcje pomocnicze dla scheduled jobs
async def _consolidate_memory():
    """Konsolidacja pamięci - analiza logów i zapis wniosków (PLACEHOLDER)."""
    logger.info("Uruchamiam konsolidację pamięci (placeholder)...")
    if event_broadcaster:
        await event_broadcaster.broadcast_event(
            event_type=EventType.BACKGROUND_JOB_STARTED,
            message="Memory consolidation started (placeholder)",
            data={"job": "consolidate_memory"},
        )

    try:
        # PLACEHOLDER: W przyszłości tutaj będzie analiza logów i zapis do GraphRAG
        logger.debug("Konsolidacja pamięci - placeholder, brak implementacji")

        if event_broadcaster:
            await event_broadcaster.broadcast_event(
                event_type=EventType.MEMORY_CONSOLIDATED,
                message="Memory consolidation completed (placeholder)",
                data={"job": "consolidate_memory"},
            )

    except Exception as e:
        logger.error(f"Błąd podczas konsolidacji pamięci: {e}")
        if event_broadcaster:
            await event_broadcaster.broadcast_event(
                event_type=EventType.BACKGROUND_JOB_FAILED,
                message=f"Memory consolidation failed: {e}",
                data={"job": "consolidate_memory", "error": str(e)},
            )


async def _check_health():
    """Sprawdzenie zdrowia systemu (PLACEHOLDER)."""
    logger.debug("Sprawdzanie zdrowia systemu (placeholder)...")

    try:
        from datetime import datetime

        # Placeholder: W przyszłości tutaj będzie sprawdzanie Docker, LLM endpoints, etc.
        health_status = {"status": "ok", "timestamp": datetime.now().isoformat()}

        if event_broadcaster:
            await event_broadcaster.broadcast_event(
                event_type=EventType.BACKGROUND_JOB_COMPLETED,
                message="Health check completed",
                data={"job": "check_health", "status": health_status},
            )

    except Exception as e:
        logger.error(f"Błąd podczas sprawdzania zdrowia: {e}")
        if event_broadcaster:
            await event_broadcaster.broadcast_event(
                event_type=EventType.BACKGROUND_JOB_FAILED,
                message=f"Health check failed: {e}",
                data={"job": "check_health", "error": str(e)},
            )


app = FastAPI(title="Venom Core", version="0.1.0", lifespan=lifespan)

# Montowanie plików statycznych
web_dir = Path(__file__).parent.parent / "web"
if web_dir.exists():
    app.mount("/static", StaticFiles(directory=str(web_dir / "static")), name="static")
    logger.info(f"Static files served from: {web_dir / 'static'}")


@app.get("/")
async def serve_dashboard():
    """Serwuje główny dashboard."""
    index_path = web_dir / "templates" / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"message": "Dashboard niedostępny - brak pliku index.html"}


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


@app.post("/api/v1/tasks", response_model=TaskResponse, status_code=201)
async def create_task(request: TaskRequest):
    """
    Tworzy nowe zadanie i uruchamia je w tle.

    Args:
        request: Żądanie z treścią zadania

    Returns:
        Odpowiedź z ID zadania i statusem

    Raises:
        HTTPException: 400 przy błędnym body, 500 przy błędzie wewnętrznym
    """
    try:
        # Inkrementuj licznik zadań
        if metrics_collector:
            metrics_collector.increment_task_created()

        response = await orchestrator.submit_task(request)
        return response
    except Exception as e:
        logger.exception("Błąd podczas tworzenia zadania")
        raise HTTPException(
            status_code=500, detail="Błąd wewnętrzny podczas tworzenia zadania"
        ) from e


@app.get("/api/v1/tasks/{task_id}", response_model=VenomTask)
async def get_task(task_id: UUID):
    """
    Pobiera szczegóły zadania po ID.

    Args:
        task_id: UUID zadania

    Returns:
        Szczegóły zadania

    Raises:
        HTTPException: 404 jeśli zadanie nie istnieje
    """
    task = state_manager.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Zadanie {task_id} nie istnieje")
    return task


@app.get("/api/v1/tasks", response_model=list[VenomTask])
async def get_all_tasks():
    """
    Pobiera listę wszystkich zadań.

    Returns:
        Lista wszystkich zadań w systemie
    """
    return state_manager.get_all_tasks()


# --- History API Endpoints ---


class HistoryRequestSummary(BaseModel):
    """Skrócony widok requestu dla listy historii."""

    request_id: UUID
    prompt: str
    status: str
    created_at: str
    finished_at: str = None
    duration_seconds: float = None


class HistoryRequestDetail(BaseModel):
    """Szczegółowy widok requestu z krokami."""

    request_id: UUID
    prompt: str
    status: str
    created_at: str
    finished_at: str = None
    duration_seconds: float = None
    steps: list


@app.get("/api/v1/history/requests", response_model=list[HistoryRequestSummary])
async def get_request_history(limit: int = 50, offset: int = 0, status: str = None):
    """
    Pobiera listę requestów z historii (paginowana).

    Args:
        limit: Maksymalna liczba wyników (domyślnie 50)
        offset: Offset dla paginacji (domyślnie 0)
        status: Opcjonalny filtr po statusie (PENDING, PROCESSING, COMPLETED, FAILED, LOST)

    Returns:
        Lista requestów z podstawowymi informacjami
    """
    if request_tracer is None:
        raise HTTPException(status_code=503, detail="RequestTracer nie jest dostępny")

    traces = request_tracer.get_all_traces(
        limit=limit, offset=offset, status_filter=status
    )

    result = []
    for trace in traces:
        duration = None
        if trace.finished_at:
            duration = (trace.finished_at - trace.created_at).total_seconds()

        result.append(
            HistoryRequestSummary(
                request_id=trace.request_id,
                prompt=trace.prompt,
                status=trace.status,
                created_at=trace.created_at.isoformat(),
                finished_at=(
                    trace.finished_at.isoformat() if trace.finished_at else None
                ),
                duration_seconds=duration,
            )
        )

    return result


@app.get("/api/v1/history/requests/{request_id}", response_model=HistoryRequestDetail)
async def get_request_detail(request_id: UUID):
    """
    Pobiera szczegóły requestu z pełną listą kroków.

    Args:
        request_id: UUID requestu

    Returns:
        Szczegółowe informacje o requestie wraz z timeline kroków

    Raises:
        HTTPException: 404 jeśli request nie istnieje
    """
    if request_tracer is None:
        raise HTTPException(status_code=503, detail="RequestTracer nie jest dostępny")

    trace = request_tracer.get_trace(request_id)
    if trace is None:
        raise HTTPException(
            status_code=404, detail=f"Request {request_id} nie istnieje w historii"
        )

    duration = None
    if trace.finished_at:
        duration = (trace.finished_at - trace.created_at).total_seconds()

    # Konwertuj steps do słowników dla serializacji
    steps_list = []
    for step in trace.steps:
        steps_list.append(
            {
                "component": step.component,
                "action": step.action,
                "timestamp": step.timestamp.isoformat(),
                "status": step.status,
                "details": step.details,
            }
        )

    return HistoryRequestDetail(
        request_id=trace.request_id,
        prompt=trace.prompt,
        status=trace.status,
        created_at=trace.created_at.isoformat(),
        finished_at=trace.finished_at.isoformat() if trace.finished_at else None,
        duration_seconds=duration,
        steps=steps_list,
    )


# --- Memory API Endpoints ---


class MemoryIngestRequest(BaseModel):
    """Model żądania ingestion do pamięci."""

    text: str
    category: str = "general"
    collection: str = "default"


class MemoryIngestResponse(BaseModel):
    """Model odpowiedzi po ingestion."""

    status: str
    message: str
    chunks_count: int = 0


class MemorySearchRequest(BaseModel):
    """Model żądania wyszukiwania w pamięci."""

    query: str
    limit: int = 3
    collection: str = "default"


@app.post("/api/v1/memory/ingest", response_model=MemoryIngestResponse, status_code=201)
async def ingest_to_memory(request: MemoryIngestRequest):
    """
    Zapisuje tekst do pamięci wektorowej.

    Args:
        request: Żądanie z tekstem do zapamiętania

    Returns:
        Potwierdzenie zapisu z liczbą fragmentów

    Raises:
        HTTPException: 503 jeśli VectorStore nie jest dostępny, 400 przy błędnych danych
    """
    if vector_store is None:
        raise HTTPException(
            status_code=503,
            detail="VectorStore nie jest dostępny. Upewnij się, że dependencies są zainstalowane.",
        )

    try:
        if not request.text or not request.text.strip():
            raise HTTPException(status_code=400, detail="Tekst nie może być pusty")

        # Zapisz do pamięci
        metadata = {"category": request.category}
        result = vector_store.upsert(
            text=request.text,
            metadata=metadata,
            collection_name=request.collection,
            chunk_text=True,
        )

        logger.info(
            f"Ingestion pomyślny: {result['chunks_count']} fragmentów do '{request.collection}'"
        )

        return MemoryIngestResponse(
            status="success",
            message=result["message"],
            chunks_count=result["chunks_count"],
        )

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Błąd podczas ingestion do pamięci")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@app.post("/api/v1/memory/search")
async def search_memory(request: MemorySearchRequest):
    """
    Wyszukuje informacje w pamięci wektorowej.

    Args:
        request: Żądanie z zapytaniem

    Returns:
        Wyniki wyszukiwania

    Raises:
        HTTPException: 503 jeśli VectorStore nie jest dostępny, 400 przy błędnych danych
    """
    if vector_store is None:
        raise HTTPException(
            status_code=503,
            detail="VectorStore nie jest dostępny. Upewnij się, że dependencies są zainstalowane.",
        )

    try:
        if not request.query or not request.query.strip():
            raise HTTPException(status_code=400, detail="Zapytanie nie może być puste")

        results = vector_store.search(
            query=request.query,
            limit=request.limit,
            collection_name=request.collection,
        )

        logger.info(
            f"Wyszukiwanie w pamięci: znaleziono {len(results)} wyników dla '{request.query[:50]}...'"
        )

        return {
            "status": "success",
            "query": request.query,
            "results": results,
            "count": len(results),
        }

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Błąd podczas wyszukiwania w pamięci")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


# --- Metrics API Endpoint ---


@app.get("/api/v1/metrics")
async def get_metrics():
    """
    Zwraca metryki systemowe.

    Returns:
        Słownik z metrykami wydajności i użycia

    Raises:
        HTTPException: 503 jeśli MetricsCollector nie jest dostępny
    """
    if metrics_collector is None:
        raise HTTPException(status_code=503, detail="Metrics collector not initialized")
    return metrics_collector.get_metrics()


# --- Graph & Lessons API Endpoints ---


def validate_file_path(file_path: str, workspace_root: Path) -> None:
    """
    Waliduje ścieżkę do pliku, zapobiegając path traversal attacks.

    Args:
        file_path: Ścieżka do walidacji
        workspace_root: Katalog workspace

    Raises:
        HTTPException: Jeśli ścieżka jest nieprawidłowa
    """
    try:
        # Normalizuj ścieżkę i sprawdź czy zawiera ..
        if ".." in file_path or file_path.startswith("/"):
            raise HTTPException(
                status_code=400, detail="Nieprawidłowa ścieżka do pliku"
            )

        # Zweryfikuj że ścieżka jest w workspace
        full_path = (workspace_root / file_path).resolve()

        if not str(full_path).startswith(str(workspace_root)):
            raise HTTPException(status_code=400, detail="Ścieżka poza workspace")
    except ValueError:
        raise HTTPException(status_code=400, detail="Nieprawidłowa ścieżka")


@app.get("/api/v1/graph/summary")
async def get_graph_summary():
    """
    Zwraca podsumowanie grafu wiedzy o kodzie.

    Returns:
        Statystyki grafu (liczba węzłów, krawędzi, typy)

    Raises:
        HTTPException: 503 jeśli GraphStore nie jest dostępny
    """
    if graph_store is None:
        raise HTTPException(status_code=503, detail="GraphStore nie jest dostępny")

    try:
        summary = graph_store.get_graph_summary()
        return {"status": "success", "summary": summary}
    except Exception as e:
        logger.exception("Błąd podczas pobierania podsumowania grafu")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@app.get("/api/v1/graph/file/{file_path:path}")
async def get_file_graph_info(file_path: str):
    """
    Zwraca informacje o pliku z grafu (klasy, funkcje, zależności).

    Args:
        file_path: Ścieżka do pliku (relatywna do workspace)

    Returns:
        Informacje o pliku z grafu

    Raises:
        HTTPException: 404 jeśli plik nie istnieje w grafie, 503 jeśli GraphStore nie jest dostępny
    """
    if graph_store is None:
        raise HTTPException(status_code=503, detail="GraphStore nie jest dostępny")

    try:
        # Walidacja ścieżki - zapobieganie path traversal
        workspace_root = Path(graph_store.workspace_root).resolve()
        validate_file_path(file_path, workspace_root)

        info = graph_store.get_file_info(file_path)

        if not info:
            raise HTTPException(
                status_code=404, detail=f"Plik {file_path} nie istnieje w grafie"
            )

        return {"status": "success", "file_path": file_path, "info": info}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Błąd podczas pobierania informacji o pliku {file_path}")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@app.get("/api/v1/graph/impact/{file_path:path}")
async def get_impact_analysis(file_path: str):
    """
    Analizuje wpływ usunięcia/modyfikacji pliku.

    Args:
        file_path: Ścieżka do pliku (relatywna do workspace)

    Returns:
        Raport wpływu na inne pliki

    Raises:
        HTTPException: 404 jeśli plik nie istnieje w grafie, 503 jeśli GraphStore nie jest dostępny
    """
    if graph_store is None:
        raise HTTPException(status_code=503, detail="GraphStore nie jest dostępny")

    try:
        # Walidacja ścieżki - zapobieganie path traversal
        workspace_root = Path(graph_store.workspace_root).resolve()
        validate_file_path(file_path, workspace_root)

        impact = graph_store.get_impact_analysis(file_path)

        if "error" in impact:
            raise HTTPException(status_code=404, detail=impact["error"])

        return {"status": "success", "impact": impact}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Błąd podczas analizy wpływu pliku {file_path}")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@app.post("/api/v1/graph/scan")
async def trigger_graph_scan():
    """
    Wyzwala manualne skanowanie workspace i aktualizację grafu.

    Returns:
        Statystyki skanowania

    Raises:
        HTTPException: 503 jeśli GardenerAgent nie jest dostępny
    """
    if gardener_agent is None:
        raise HTTPException(status_code=503, detail="GardenerAgent nie jest dostępny")

    try:
        stats = await gardener_agent.trigger_manual_scan()
        return {"status": "success", "scan_stats": stats}
    except Exception as e:
        logger.exception("Błąd podczas manualnego skanowania")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@app.get("/api/v1/lessons")
async def get_lessons(limit: int = 10, tags: str = None):
    """
    Pobiera listę lekcji.

    Args:
        limit: Maksymalna liczba lekcji do zwrócenia
        tags: Opcjonalne tagi do filtrowania (oddzielone przecinkami)

    Returns:
        Lista lekcji

    Raises:
        HTTPException: 503 jeśli LessonsStore nie jest dostępny
    """
    if lessons_store is None:
        raise HTTPException(status_code=503, detail="LessonsStore nie jest dostępny")

    try:
        if tags:
            tag_list = [t.strip() for t in tags.split(",")]
            lessons = lessons_store.get_lessons_by_tags(tag_list)
        else:
            lessons = lessons_store.get_all_lessons(limit=limit)

        # Konwertuj do dict
        lessons_data = [lesson.to_dict() for lesson in lessons]

        return {
            "status": "success",
            "count": len(lessons_data),
            "lessons": lessons_data,
        }
    except Exception as e:
        logger.exception("Błąd podczas pobierania lekcji")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@app.get("/api/v1/lessons/stats")
async def get_lessons_stats():
    """
    Zwraca statystyki magazynu lekcji.

    Returns:
        Statystyki lekcji

    Raises:
        HTTPException: 503 jeśli LessonsStore nie jest dostępny
    """
    if lessons_store is None:
        raise HTTPException(status_code=503, detail="LessonsStore nie jest dostępny")

    try:
        stats = lessons_store.get_statistics()
        return {"status": "success", "stats": stats}
    except Exception as e:
        logger.exception("Błąd podczas pobierania statystyk lekcji")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@app.get("/api/v1/gardener/status")
async def get_gardener_status():
    """
    Zwraca status agenta Ogrodnika.

    Returns:
        Status GardenerAgent

    Raises:
        HTTPException: 503 jeśli GardenerAgent nie jest dostępny
    """
    if gardener_agent is None:
        raise HTTPException(status_code=503, detail="GardenerAgent nie jest dostępny")

    try:
        status = gardener_agent.get_status()
        return {"status": "success", "gardener": status}
    except Exception as e:
        logger.exception("Błąd podczas pobierania statusu Ogrodnika")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


# --- Git & Repository API Endpoints ---


@app.get("/api/v1/git/status")
async def get_git_status():
    """
    Zwraca status repozytorium Git (aktualny branch, zmiany, liczba zmodyfikowanych plików).

    Returns:
        Status repozytorium Git

    Raises:
        HTTPException: 503 jeśli GitSkill nie jest dostępny lub workspace nie jest repozytorium Git
    """
    if git_skill is None:
        raise HTTPException(
            status_code=503,
            detail="GitSkill nie jest dostępny. Upewnij się, że dependencies są zainstalowane.",
        )

    try:
        # Pobierz aktualny branch
        branch = await git_skill.get_current_branch()

        # Sprawdź czy to błąd
        if branch.startswith("❌"):
            return {
                "status": "error",
                "is_git_repo": False,
                "message": "Workspace nie jest repozytorium Git",
            }

        # Pobierz status
        status_output = await git_skill.get_status()

        # Parsuj status aby określić czy są zmiany
        has_changes = (
            "nothing to commit" not in status_output
            and "working tree clean" not in status_output
        )

        # Użyj GitPython do dokładniejszego liczenia zmian
        modified_count = 0
        if has_changes:
            try:
                # Pobierz obiekt Repo i policz zmiany
                from git import GitCommandError, Repo

                repo = Repo(git_skill.workspace_root)
                # Sprawdź czy HEAD istnieje (czy repo ma commity)
                if repo.head.is_valid():
                    # Zmodyfikowane i staged pliki względem HEAD
                    modified_count = len(repo.index.diff("HEAD"))
                else:
                    # Brak HEAD — policz tylko nieśledzone pliki
                    modified_count = len(repo.untracked_files)
                # Dodaj nieśledzone pliki (jeśli HEAD istnieje)
                if repo.head.is_valid():
                    modified_count += len(repo.untracked_files)
            except (GitCommandError, ValueError):
                # Fallback: proste parsowanie jeśli GitPython zawiedzie (np. HEAD nie istnieje)
                lines = status_output.split("\n")
                for line in lines:
                    if (
                        "modified:" in line
                        or "new file:" in line
                        or "deleted:" in line
                        or "renamed:" in line
                    ):
                        modified_count += 1

        return {
            "status": "success",
            "is_git_repo": True,
            "branch": branch,
            "has_changes": has_changes,
            "modified_count": modified_count,
            "status_output": status_output,
        }

    except Exception as e:
        logger.exception("Błąd podczas pobierania statusu Git")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@app.post("/api/v1/git/sync")
async def sync_repository():
    """
    Synchronizuje repozytorium (pull z remote).

    Returns:
        Wynik synchronizacji

    Raises:
        HTTPException: 501 jeśli nie zaimplementowano, 503 jeśli GitSkill nie jest dostępny
    """
    if git_skill is None:
        raise HTTPException(status_code=503, detail="GitSkill nie jest dostępny")

    # Feature nie jest jeszcze zaimplementowana - wymaga dodania metody pull() do GitSkill
    raise HTTPException(
        status_code=501,
        detail="Synchronizacja (git pull) nie jest jeszcze zaimplementowana. Użyj Integrator Agent lub wykonaj manualnie.",
    )


@app.post("/api/v1/git/undo")
async def undo_changes():
    """
    Cofa wszystkie niezapisane zmiany (git reset --hard).

    UWAGA: To jest destrukcyjna operacja!

    Returns:
        Wynik cofnięcia zmian

    Raises:
        HTTPException: 501 jeśli nie zaimplementowano, 503 jeśli GitSkill nie jest dostępny
    """
    if git_skill is None:
        raise HTTPException(status_code=503, detail="GitSkill nie jest dostępny")

    # Feature nie jest jeszcze zaimplementowana - wymaga dodania metody reset() do GitSkill
    raise HTTPException(
        status_code=501,
        detail="Cofnięcie zmian (git reset) nie jest jeszcze zaimplementowane. Użyj Integrator Agent z odpowiednim potwierdzeniem.",
    )


# --- Background Jobs API Endpoints (THE_OVERMIND) ---


@app.get("/api/v1/scheduler/status")
async def get_scheduler_status():
    """
    Zwraca status schedulera zadań w tle.

    Returns:
        Status schedulera

    Raises:
        HTTPException: 503 jeśli scheduler nie jest dostępny
    """
    if background_scheduler is None:
        raise HTTPException(
            status_code=503, detail="BackgroundScheduler nie jest dostępny"
        )

    try:
        status = background_scheduler.get_status()
        return {"status": "success", "scheduler": status}
    except Exception as e:
        logger.exception("Błąd podczas pobierania statusu schedulera")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@app.get("/api/v1/scheduler/jobs")
async def get_scheduler_jobs():
    """
    Zwraca listę zadań w tle.

    Returns:
        Lista zadań

    Raises:
        HTTPException: 503 jeśli scheduler nie jest dostępny
    """
    if background_scheduler is None:
        raise HTTPException(
            status_code=503, detail="BackgroundScheduler nie jest dostępny"
        )

    try:
        jobs = background_scheduler.get_jobs()
        return {"status": "success", "jobs": jobs, "count": len(jobs)}
    except Exception as e:
        logger.exception("Błąd podczas pobierania listy zadań")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@app.post("/api/v1/scheduler/pause")
async def pause_scheduler():
    """
    Wstrzymuje wszystkie zadania w tle.

    Returns:
        Potwierdzenie wstrzymania

    Raises:
        HTTPException: 503 jeśli scheduler nie jest dostępny
    """
    if background_scheduler is None:
        raise HTTPException(
            status_code=503, detail="BackgroundScheduler nie jest dostępny"
        )

    try:
        await background_scheduler.pause_all_jobs()
        return {"status": "success", "message": "All background jobs paused"}
    except Exception as e:
        logger.exception("Błąd podczas wstrzymywania zadań")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@app.post("/api/v1/scheduler/resume")
async def resume_scheduler():
    """
    Wznawia wszystkie zadania w tle.

    Returns:
        Potwierdzenie wznowienia

    Raises:
        HTTPException: 503 jeśli scheduler nie jest dostępny
    """
    if background_scheduler is None:
        raise HTTPException(
            status_code=503, detail="BackgroundScheduler nie jest dostępny"
        )

    try:
        await background_scheduler.resume_all_jobs()
        return {"status": "success", "message": "All background jobs resumed"}
    except Exception as e:
        logger.exception("Błąd podczas wznawiania zadań")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@app.get("/api/v1/watcher/status")
async def get_watcher_status():
    """
    Zwraca status obserwatora plików.

    Returns:
        Status watchera

    Raises:
        HTTPException: 503 jeśli watcher nie jest dostępny
    """
    if file_watcher is None:
        raise HTTPException(status_code=503, detail="FileWatcher nie jest dostępny")

    try:
        status = file_watcher.get_status()
        return {"status": "success", "watcher": status}
    except Exception as e:
        logger.exception("Błąd podczas pobierania statusu watchera")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@app.get("/api/v1/documenter/status")
async def get_documenter_status():
    """
    Zwraca status agenta dokumentalisty.

    Returns:
        Status DocumenterAgent

    Raises:
        HTTPException: 503 jeśli documenter nie jest dostępny
    """
    if documenter_agent is None:
        raise HTTPException(status_code=503, detail="DocumenterAgent nie jest dostępny")

    try:
        status = documenter_agent.get_status()
        return {"status": "success", "documenter": status}
    except Exception as e:
        logger.exception("Błąd podczas pobierania statusu dokumentalisty")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


# ==================== SHADOW AGENT API (THE_SHADOW) ====================


@app.get("/api/v1/shadow/status")
async def get_shadow_status():
    """
    Zwraca status Shadow Agent, Desktop Sensor i Notifier.

    Returns:
        Status komponentów Shadow Agent

    Raises:
        HTTPException: 503 jeśli Shadow Agent nie jest dostępny
    """
    if not SETTINGS.ENABLE_PROACTIVE_MODE:
        raise HTTPException(
            status_code=503,
            detail="Proactive Mode wyłączony (ENABLE_PROACTIVE_MODE=False)",
        )

    try:
        status_data = {
            "shadow_agent": shadow_agent.get_status() if shadow_agent else None,
            "desktop_sensor": desktop_sensor.get_status() if desktop_sensor else None,
            "notifier": notifier.get_status() if notifier else None,
            "config": {
                "confidence_threshold": SETTINGS.SHADOW_CONFIDENCE_THRESHOLD,
                "privacy_filter": SETTINGS.SHADOW_PRIVACY_FILTER,
                "desktop_sensor_enabled": SETTINGS.ENABLE_DESKTOP_SENSOR,
            },
        }
        return {"status": "success", "shadow": status_data}
    except Exception as e:
        logger.exception("Błąd podczas pobierania statusu Shadow Agent")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@app.post("/api/v1/shadow/reject")
async def reject_shadow_suggestion(request: TaskRequest):
    """
    Rejestruje odrzuconą sugestię Shadow Agent dla uczenia się.

    Args:
        request: Request body z polem 'content' zawierającym suggestion_type

    Returns:
        Potwierdzenie rejestracji

    Raises:
        HTTPException: 503 jeśli Shadow Agent nie jest dostępny
    """
    if shadow_agent is None:
        raise HTTPException(status_code=503, detail="Shadow Agent nie jest dostępny")

    try:
        suggestion_type = request.content

        # Użyj nowego API z suggestion_type string
        shadow_agent.record_rejection(suggestion_type=suggestion_type)

        return {
            "status": "success",
            "message": f"Odrzucona sugestia typu '{suggestion_type}' zarejestrowana",
        }
    except Exception as e:
        logger.exception("Błąd podczas rejestrowania odrzuconej sugestii")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


# ==================== NODE MANAGEMENT API (THE_NEXUS) ====================


@app.get("/api/v1/nodes")
async def list_nodes(online_only: bool = False):
    """
    Zwraca listę zarejestrowanych węzłów.

    Args:
        online_only: Czy zwrócić tylko węzły online (domyślnie False)

    Returns:
        Lista węzłów z ich informacjami

    Raises:
        HTTPException: 503 jeśli NodeManager nie jest dostępny
    """
    if node_manager is None:
        raise HTTPException(
            status_code=503,
            detail="NodeManager nie jest dostępny - włącz tryb Nexus (ENABLE_NEXUS=true)",
        )

    try:
        nodes = node_manager.list_nodes(online_only=online_only)
        nodes_data = [node.to_dict() for node in nodes]
        return {
            "status": "success",
            "count": len(nodes_data),
            "online_count": len([n for n in nodes if n.is_online]),
            "nodes": nodes_data,
        }
    except Exception as e:
        logger.exception("Błąd podczas pobierania listy węzłów")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@app.get("/api/v1/nodes/{node_id}")
async def get_node_info(node_id: str):
    """
    Zwraca szczegółowe informacje o węźle.

    Args:
        node_id: ID węzła

    Returns:
        Informacje o węźle

    Raises:
        HTTPException: 404 jeśli węzeł nie istnieje, 503 jeśli NodeManager nie jest dostępny
    """
    if node_manager is None:
        raise HTTPException(
            status_code=503,
            detail="NodeManager nie jest dostępny - włącz tryb Nexus (ENABLE_NEXUS=true)",
        )

    try:
        node = node_manager.get_node(node_id)
        if node is None:
            raise HTTPException(status_code=404, detail=f"Węzeł {node_id} nie istnieje")

        return {"status": "success", "node": node.to_dict()}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Błąd podczas pobierania informacji o węźle {node_id}")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


class NodeExecuteRequest(BaseModel):
    """Model żądania wykonania skilla na węźle."""

    skill_name: str
    method_name: str
    parameters: dict = {}
    timeout: int = 30


@app.post("/api/v1/nodes/{node_id}/execute")
async def execute_on_node(node_id: str, request: NodeExecuteRequest):
    """
    Wykonuje skill na określonym węźle.

    Args:
        node_id: ID węzła docelowego
        request: Żądanie wykonania

    Returns:
        Wynik wykonania

    Raises:
        HTTPException: 404 jeśli węzeł nie istnieje, 400 jeśli węzeł offline,
                      503 jeśli NodeManager nie jest dostępny, 504 jeśli timeout
    """
    if node_manager is None:
        raise HTTPException(
            status_code=503,
            detail="NodeManager nie jest dostępny - włącz tryb Nexus (ENABLE_NEXUS=true)",
        )

    try:
        response = await node_manager.execute_skill_on_node(
            node_id=node_id,
            skill_name=request.skill_name,
            method_name=request.method_name,
            parameters=request.parameters,
            timeout=request.timeout,
        )

        return {
            "status": "success",
            "node_id": node_id,
            "request_id": response.request_id,
            "success": response.success,
            "result": response.result,
            "error": response.error,
            "execution_time": response.execution_time,
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except TimeoutError as e:
        raise HTTPException(status_code=504, detail=str(e)) from e
    except Exception as e:
        logger.exception(f"Błąd podczas wykonywania skilla na węźle {node_id}")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


# === WAR ROOM / STRATEGY API ENDPOINTS ===


@app.get("/strategy")
async def serve_strategy_dashboard():
    """Serwuje dashboard strategiczny (War Room)."""
    strategy_path = web_dir / "templates" / "strategy.html"
    if strategy_path.exists():
        return FileResponse(str(strategy_path))
    raise HTTPException(
        status_code=404,
        detail="Strategy Dashboard niedostępny - brak pliku strategy.html",
    )


class RoadmapCreateRequest(BaseModel):
    """Request dla utworzenia roadmapy."""

    vision: str


@app.get("/api/roadmap")
async def get_roadmap():
    """
    Pobiera aktualną roadmapę projektu.

    Returns:
        Roadmapa z Vision, Milestones, Tasks i KPI

    Raises:
        HTTPException: 503 jeśli orchestrator nie jest dostępny
    """
    if orchestrator is None:
        raise HTTPException(status_code=503, detail="Orchestrator nie jest dostępny")

    try:
        goal_store = orchestrator.task_dispatcher.goal_store

        # Vision
        vision = goal_store.get_vision()
        vision_data = None
        if vision:
            vision_data = {
                "title": vision.title,
                "description": vision.description,
                "status": vision.status.value,
                "progress": vision.get_progress(),
            }

        # Milestones
        milestones = goal_store.get_milestones()
        milestones_data = []
        for milestone in milestones:
            # Tasks dla milestone
            tasks = goal_store.get_tasks(parent_id=milestone.goal_id)
            tasks_data = [
                {
                    "title": t.title,
                    "description": t.description,
                    "status": t.status.value,
                    "priority": t.priority,
                }
                for t in tasks
            ]

            milestones_data.append(
                {
                    "title": milestone.title,
                    "description": milestone.description,
                    "status": milestone.status.value,
                    "progress": milestone.get_progress(),
                    "priority": milestone.priority,
                    "tasks": tasks_data,
                }
            )

        # KPIs
        completed_milestones = [m for m in milestones if m.status.value == "COMPLETED"]
        all_tasks_list = []
        for m in milestones:
            all_tasks_list.extend(goal_store.get_tasks(parent_id=m.goal_id))
        completed_tasks = [t for t in all_tasks_list if t.status.value == "COMPLETED"]

        completion_rate = 0.0
        if milestones:
            completion_rate = (len(completed_milestones) / len(milestones)) * 100

        kpis = {
            "completion_rate": completion_rate,
            "milestones_completed": len(completed_milestones),
            "milestones_total": len(milestones),
            "tasks_completed": len(completed_tasks),
            "tasks_total": len(all_tasks_list),
        }

        # Full report
        report = goal_store.generate_roadmap_report()

        return {
            "status": "success",
            "vision": vision_data,
            "milestones": milestones_data,
            "kpis": kpis,
            "report": report,
        }

    except Exception as e:
        logger.exception("Błąd podczas pobierania roadmapy")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@app.post("/api/roadmap/create")
async def create_roadmap(request: RoadmapCreateRequest):
    """
    Tworzy roadmapę na podstawie wizji użytkownika.

    Args:
        request: Vision text

    Returns:
        Potwierdzenie utworzenia roadmapy

    Raises:
        HTTPException: 503 jeśli orchestrator nie jest dostępny
    """
    if orchestrator is None:
        raise HTTPException(status_code=503, detail="Orchestrator nie jest dostępny")

    try:
        executive_agent = orchestrator.task_dispatcher.executive_agent
        roadmap_result = await executive_agent.create_roadmap(request.vision)

        return {
            "status": "success",
            "message": "Roadmapa utworzona",
            "roadmap": roadmap_result,
        }

    except Exception as e:
        logger.exception("Błąd podczas tworzenia roadmapy")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@app.get("/api/roadmap/status")
async def get_roadmap_status():
    """
    Generuje raport statusu wykonawczy.

    Returns:
        Raport z analizą Executive

    Raises:
        HTTPException: 503 jeśli orchestrator nie jest dostępny
    """
    if orchestrator is None:
        raise HTTPException(status_code=503, detail="Orchestrator nie jest dostępny")

    try:
        executive_agent = orchestrator.task_dispatcher.executive_agent
        report = await executive_agent.generate_status_report()

        return {"status": "success", "report": report}

    except Exception as e:
        logger.exception("Błąd podczas generowania raportu statusu")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@app.post("/api/campaign/start")
async def start_campaign():
    """
    Uruchamia Tryb Kampanii (autonomiczna realizacja roadmapy).

    Returns:
        Potwierdzenie rozpoczęcia kampanii

    Raises:
        HTTPException: 503 jeśli orchestrator nie jest dostępny
    """
    if orchestrator is None:
        raise HTTPException(status_code=503, detail="Orchestrator nie jest dostępny")

    try:
        # Utwórz task request dla kampanii
        task_request = TaskRequest(content="Rozpocznij kampanię autonomiczną")
        task_response = await orchestrator.submit_task(task_request)

        return {
            "status": "success",
            "message": "Kampania rozpoczęta",
            "task_id": str(task_response.task_id),
        }

    except Exception as e:
        logger.exception("Błąd podczas uruchamiania kampanii")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


# === SYSTEM HEALTH API (Dashboard v2.1) ===


@app.get("/api/v1/system/services")
async def get_system_services():
    """
    Zwraca status wszystkich usług systemowych.

    Returns:
        Lista usług z ich statusem, opóźnieniem i ostatnim sprawdzeniem

    Raises:
        HTTPException: 503 jeśli Service Monitor nie jest dostępny
    """
    if service_monitor is None or service_registry is None:
        raise HTTPException(
            status_code=503, detail="Service Health Monitor nie jest dostępny"
        )

    try:
        # Sprawdź zdrowie wszystkich usług
        services = await service_monitor.check_health()

        # Pobierz podsumowanie
        summary = service_monitor.get_summary()

        # Konwertuj usługi do dict
        services_data = [
            {
                "name": s.name,
                "type": s.service_type,
                "status": s.status.value,
                "latency_ms": s.latency_ms,
                "last_check": s.last_check,
                "is_critical": s.is_critical,
                "error_message": s.error_message,
                "description": s.description,
            }
            for s in services
        ]

        return {
            "status": "success",
            "summary": summary,
            "services": services_data,
        }

    except Exception as e:
        logger.exception("Błąd podczas sprawdzania statusu usług")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@app.get("/api/v1/system/services/{service_name}")
async def get_service_status(service_name: str):
    """
    Zwraca status konkretnej usługi.

    Args:
        service_name: Nazwa usługi

    Returns:
        Status usługi

    Raises:
        HTTPException: 404 jeśli usługa nie istnieje, 503 jeśli Service Monitor nie jest dostępny
    """
    if service_monitor is None or service_registry is None:
        raise HTTPException(
            status_code=503, detail="Service Health Monitor nie jest dostępny"
        )

    try:
        # Sprawdź zdrowie konkretnej usługi
        services = await service_monitor.check_health(service_name=service_name)

        if not services:
            raise HTTPException(
                status_code=404, detail=f"Usługa '{service_name}' nie znaleziona"
            )

        service = services[0]

        return {
            "status": "success",
            "service": {
                "name": service.name,
                "type": service.service_type,
                "status": service.status.value,
                "latency_ms": service.latency_ms,
                "last_check": service.last_check,
                "is_critical": service.is_critical,
                "error_message": service.error_message,
                "description": service.description,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Błąd podczas sprawdzania statusu usługi {service_name}")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e
