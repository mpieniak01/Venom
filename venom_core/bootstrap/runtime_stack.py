"""Bootstrap helpers for runtime stack initialization."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Tuple


async def initialize_node_manager(*, settings: Any, logger: Any) -> Any:
    """Initialize NodeManager for Nexus mode."""
    if not settings.ENABLE_NEXUS:
        return None

    try:
        from venom_core.core.node_manager import NodeManager

        token = settings.NEXUS_SHARED_TOKEN.get_secret_value()
        if not token:
            logger.warning(
                "ENABLE_NEXUS=true ale NEXUS_SHARED_TOKEN jest pusty. "
                "Węzły nie będą mogły się połączyć."
            )
            return None
        node_manager = NodeManager(
            shared_token=token,
            heartbeat_timeout=settings.NEXUS_HEARTBEAT_TIMEOUT,
        )
        await node_manager.start()
        logger.info("NodeManager uruchomiony - Venom działa w trybie Nexus")
        app_port = getattr(settings, "APP_PORT", 8000)
        logger.info(
            f"Węzły mogą łączyć się przez WebSocket: ws://localhost:{app_port}/ws/nodes"
        )
        return node_manager
    except Exception as exc:
        logger.warning(f"Nie udało się uruchomić NodeManager: {exc}")
        return None


def initialize_memory_stores(
    *,
    settings: Any,
    logger: Any,
    vector_store_cls: Any,
    graph_store_cls: Any,
    lessons_store_cls: Any,
    orchestrator: Any,
) -> Tuple[Any, Any, Any]:
    """Initialize VectorStore/GraphStore/LessonsStore and wire lessons into orchestrator."""
    vector_store = None
    graph_store = None
    lessons_store = None

    try:
        vector_store = vector_store_cls()
        logger.info("VectorStore zainicjalizowany")
    except Exception as exc:
        logger.warning(f"Nie udało się zainicjalizować VectorStore: {exc}")

    try:
        graph_store = graph_store_cls()
        graph_store.load_graph()
        logger.info("CodeGraphStore zainicjalizowany i graf załadowany")
    except Exception as exc:
        logger.warning(f"Nie udało się zainicjalizować CodeGraphStore: {exc}")

    try:
        lessons_store = lessons_store_cls(vector_store=vector_store)
        logger.info(
            f"LessonsStore zainicjalizowany z {len(lessons_store.lessons)} lekcjami"
        )
    except Exception as exc:
        logger.warning(f"Nie udało się zainicjalizować LessonsStore: {exc}")

    if lessons_store and orchestrator:
        orchestrator.lessons_store = lessons_store
        logger.info("LessonsStore podłączony do Orchestrator (meta-uczenie włączone)")

    return vector_store, graph_store, lessons_store


async def initialize_gardener_and_git(
    *,
    workspace_path: Path,
    graph_store: Any,
    orchestrator: Any,
    event_broadcaster: Any,
    logger: Any,
    gardener_agent_cls: Any,
    git_skill_cls: Any,
) -> Tuple[Any, Any]:
    """Initialize GardenerAgent and GitSkill."""
    gardener_agent = None
    git_skill = None

    try:
        gardener_agent = gardener_agent_cls(
            graph_store=graph_store,
            orchestrator=orchestrator,
            event_broadcaster=event_broadcaster,
        )
        await gardener_agent.start()
        logger.info("GardenerAgent uruchomiony")
    except Exception as exc:
        logger.warning(f"Nie udało się uruchomić GardenerAgent: {exc}")

    try:
        git_skill = git_skill_cls(workspace_root=str(workspace_path))
        logger.info("GitSkill zainicjalizowany dla API")
    except Exception as exc:
        logger.warning(f"Nie udało się zainicjalizować GitSkill: {exc}")

    return gardener_agent, git_skill


async def initialize_background_scheduler(
    *,
    settings: Any,
    logger: Any,
    event_broadcaster: Any,
    vector_store: Any,
    request_tracer: Any,
    background_scheduler_cls: Any,
    job_scheduler_module: Any,
    asyncio_module: Any,
    clear_startup_runtime_retention_task: Callable[[], None],
) -> Tuple[Any, Any]:
    """Initialize background scheduler jobs and optional startup retention task."""
    background_scheduler = None
    startup_runtime_retention_task = None

    try:
        background_scheduler = background_scheduler_cls(
            event_broadcaster=event_broadcaster
        )
        await background_scheduler.start()
        logger.info("BackgroundScheduler uruchomiony")

        if vector_store and settings.ENABLE_MEMORY_CONSOLIDATION:

            async def _consolidate_memory_wrapper():
                await job_scheduler_module.consolidate_memory(event_broadcaster)

            background_scheduler.add_interval_job(
                func=_consolidate_memory_wrapper,
                minutes=settings.MEMORY_CONSOLIDATION_INTERVAL_MINUTES,
                job_id="consolidate_memory",
                description="common.comingSoon",
            )
            logger.info("Zadanie consolidate_memory zarejestrowane (COMING SOON)")

        if settings.ENABLE_HEALTH_CHECKS:

            async def _check_health_wrapper():
                await job_scheduler_module.check_health(event_broadcaster)

            background_scheduler.add_interval_job(
                func=_check_health_wrapper,
                minutes=settings.HEALTH_CHECK_INTERVAL_MINUTES,
                job_id="check_health",
                description="common.comingSoon",
            )
            logger.info("Zadanie check_health zarejestrowane (COMING SOON)")

        if request_tracer:

            async def _cleanup_traces_wrapper():
                try:
                    await asyncio_module.to_thread(
                        request_tracer.clear_old_traces, days=7
                    )
                except Exception as exc:
                    logger.warning(f"Błąd podczas czyszczenia śladów: {exc}")

            background_scheduler.add_interval_job(
                func=_cleanup_traces_wrapper,
                minutes=1440,
                job_id="cleanup_traces",
                description="Czyszczenie starych śladów żądań (retencja 7 dni)",
            )
            logger.info("Zadanie cleanup_traces zarejestrowane (retencja 7 dni)")

        if settings.ENABLE_RUNTIME_RETENTION_CLEANUP:

            async def _cleanup_runtime_files_wrapper():
                try:
                    await asyncio_module.to_thread(
                        job_scheduler_module.cleanup_runtime_files,
                        retention_days=settings.RUNTIME_RETENTION_DAYS,
                        target_dirs=settings.RUNTIME_RETENTION_TARGETS,
                        base_dir=Path(settings.REPO_ROOT),
                    )
                except Exception as exc:
                    logger.warning(f"Błąd podczas retencji plików runtime: {exc}")

            background_scheduler.add_interval_job(
                func=_cleanup_runtime_files_wrapper,
                minutes=settings.RUNTIME_RETENTION_INTERVAL_MINUTES,
                job_id="cleanup_runtime_files",
                description=(
                    "Czyszczenie plików runtime starszych niż "
                    f"{settings.RUNTIME_RETENTION_DAYS} dni"
                ),
            )
            logger.info(
                "Zadanie cleanup_runtime_files zarejestrowane "
                f"(retencja {settings.RUNTIME_RETENTION_DAYS} dni)"
            )
            should_run_initial_retention = await asyncio_module.to_thread(
                job_scheduler_module.should_run_runtime_retention_now,
                min_interval_minutes=settings.RUNTIME_RETENTION_INTERVAL_MINUTES,
                base_dir=Path(settings.REPO_ROOT),
            )
            if should_run_initial_retention:
                startup_runtime_retention_task = asyncio_module.create_task(
                    _cleanup_runtime_files_wrapper()
                )
                startup_runtime_retention_task.add_done_callback(
                    lambda _task: clear_startup_runtime_retention_task()
                )
                logger.info(
                    "Uruchomiono jednorazowe czyszczenie runtime po starcie aplikacji"
                )
            else:
                logger.info(
                    "Pomijam jednorazowe czyszczenie runtime na starcie "
                    "(ostatni run w bieżącym interwale retencji)"
                )
    except Exception as exc:
        logger.warning(f"Nie udało się uruchomić BackgroundScheduler: {exc}")
        return None, None

    return background_scheduler, startup_runtime_retention_task


async def initialize_documenter_and_watcher(
    *,
    workspace_path: Path,
    git_skill: Any,
    skill_manager: Any,
    event_broadcaster: Any,
    logger: Any,
    documenter_agent_cls: Any,
    file_watcher_cls: Any,
) -> Tuple[Any, Any]:
    """Initialize DocumenterAgent and FileWatcher."""
    documenter_agent = None
    file_watcher = None

    try:
        documenter_kwargs = {
            "workspace_root": str(workspace_path),
            "git_skill": git_skill,
            "event_broadcaster": event_broadcaster,
        }
        if skill_manager is not None:
            documenter_kwargs["skill_manager"] = skill_manager
        documenter_agent = documenter_agent_cls(
            **documenter_kwargs,
        )
        logger.info("DocumenterAgent zainicjalizowany")
    except Exception as exc:
        logger.warning(f"Nie udało się zainicjalizować DocumenterAgent: {exc}")

    try:
        file_watcher = file_watcher_cls(
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

    return documenter_agent, file_watcher


def initialize_audio_engine_if_enabled(
    *,
    settings: Any,
    logger: Any,
    audio_engine_cls: Any,
) -> Any:
    """Initialize AudioEngine when enabled."""
    if not settings.ENABLE_AUDIO_INTERFACE:
        return None
    try:
        audio_engine = audio_engine_cls(
            whisper_model_size=settings.WHISPER_MODEL_SIZE,
            tts_model_path=settings.TTS_MODEL_PATH,
            device=settings.AUDIO_DEVICE,
        )
        logger.info("AudioEngine zainicjalizowany")
        return audio_engine
    except Exception as exc:
        logger.warning(f"Nie udało się zainicjalizować AudioEngine: {exc}")
        return None


async def initialize_hardware_bridge_if_enabled(
    *,
    settings: Any,
    logger: Any,
    extract_secret_value_fn: Callable[[Any], str | None],
    hardware_bridge_cls: Any,
) -> Any:
    """Initialize HardwareBridge when enabled."""
    if not settings.ENABLE_IOT_BRIDGE:
        return None
    try:
        password_value = extract_secret_value_fn(settings.RIDER_PI_PASSWORD)
        bridge = hardware_bridge_cls(
            host=settings.RIDER_PI_HOST,
            port=settings.RIDER_PI_PORT,
            username=settings.RIDER_PI_USERNAME,
            password=password_value,
            protocol=settings.RIDER_PI_PROTOCOL,
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


def initialize_operator_agent_if_possible(
    *,
    settings: Any,
    logger: Any,
    current_audio_engine: Any,
    current_hardware_bridge: Any,
    operator_agent_cls: Any,
) -> Any:
    """Initialize OperatorAgent when audio stack is available."""
    if not (settings.ENABLE_AUDIO_INTERFACE and current_audio_engine):
        return None
    try:
        from venom_core.execution.kernel_builder import KernelBuilder

        operator_kernel = KernelBuilder().build_kernel()
        operator_agent = operator_agent_cls(
            kernel=operator_kernel,
            hardware_bridge=current_hardware_bridge,
        )
        logger.info("OperatorAgent zainicjalizowany")
        return operator_agent
    except Exception as exc:
        logger.warning(f"Nie udało się zainicjalizować OperatorAgent: {exc}")
        return None


def initialize_audio_stream_handler_if_possible(
    *,
    settings: Any,
    logger: Any,
    current_audio_engine: Any,
    current_operator_agent: Any,
    audio_stream_handler_cls: Any,
) -> Any:
    """Initialize AudioStreamHandler when audio and operator stacks are available."""
    if not (current_audio_engine and current_operator_agent):
        return None
    try:
        audio_stream_handler = audio_stream_handler_cls(
            audio_engine=current_audio_engine,
            vad_threshold=settings.VAD_THRESHOLD,
            silence_duration=settings.SILENCE_DURATION,
        )
        logger.info("AudioStreamHandler zainicjalizowany")
        return audio_stream_handler
    except Exception as exc:
        logger.warning(f"Nie udało się zainicjalizować AudioStreamHandler: {exc}")
        return None


async def initialize_shadow_stack(
    *,
    settings: Any,
    logger: Any,
    orchestrator: Any,
    lessons_store: Any,
    event_broadcaster: Any,
    system_log_event_type: Any,
) -> Tuple[Any, Any, Any]:
    """Initialize ShadowAgent stack and return (shadow_agent, desktop_sensor, notifier)."""
    if not settings.ENABLE_PROACTIVE_MODE:
        logger.info("Proactive Mode wyłączony (ENABLE_PROACTIVE_MODE=False)")
        return None, None, None

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
                event_type=system_log_event_type,
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
            confidence_threshold=settings.SHADOW_CONFIDENCE_THRESHOLD,
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
                    event_type=system_log_event_type,
                    message=f"Shadow: {suggestion.title}",
                    data=suggestion.to_dict(),
                )

        desktop_sensor = None
        if settings.ENABLE_DESKTOP_SENSOR:
            desktop_sensor = DesktopSensor(
                clipboard_callback=handle_sensor_data,
                window_callback=handle_sensor_data,
                privacy_filter=settings.SHADOW_PRIVACY_FILTER,
            )
            await desktop_sensor.start()
            logger.info(
                "DesktopSensor uruchomiony - monitorowanie schowka i okien aktywne"
            )
        else:
            logger.info("DesktopSensor wyłączony (ENABLE_DESKTOP_SENSOR=False)")

        return shadow_agent, desktop_sensor, notifier
    except Exception as exc:
        logger.warning(f"Nie udało się zainicjalizować Shadow Agent: {exc}")
        return None, None, None
