"""Bootstrap helpers for observability stack initialization."""

from pathlib import Path
from typing import Any, Callable, Tuple


async def initialize_observability(
    *,
    settings: Any,
    event_broadcaster: Any,
    logger: Any,
    init_metrics_collector_fn: Callable[[], None],
    request_tracer_cls: Any,
    service_registry_cls: Any,
    service_health_monitor_cls: Any,
    llm_server_controller_cls: Any,
    set_event_broadcaster_fn: Callable[[Any], None],
) -> Tuple[Any, Any, Any, Any]:
    """
    Initialize observability components and return tuple:
    (request_tracer, service_registry, service_monitor, llm_controller).
    """
    init_metrics_collector_fn()
    set_event_broadcaster_fn(event_broadcaster)
    logger.info("Live log streaming włączony")

    request_tracer = None
    service_registry = None
    service_monitor = None
    llm_controller = None

    try:
        traces_path = str(Path(settings.MEMORY_ROOT) / "request_traces.json")
        request_tracer = request_tracer_cls(
            watchdog_timeout_minutes=5, trace_file_path=traces_path
        )
        await request_tracer.start_watchdog()
        logger.info(f"RequestTracer zainicjalizowany z historią w {traces_path}")
    except Exception as exc:
        logger.warning(f"Nie udało się zainicjalizować RequestTracer: {exc}")
        request_tracer = None

    try:
        service_registry = service_registry_cls()
        service_monitor = service_health_monitor_cls(
            service_registry, event_broadcaster=event_broadcaster
        )
        logger.info("Service Health Monitor zainicjalizowany")
    except Exception as exc:
        logger.warning(f"Nie udało się zainicjalizować Service Health Monitor: {exc}")
        service_registry = None
        service_monitor = None

    try:
        llm_controller = llm_server_controller_cls(settings)
    except Exception as exc:  # pragma: no cover
        logger.warning(f"Nie udało się utworzyć kontrolera LLM: {exc}")
        llm_controller = None

    return request_tracer, service_registry, service_monitor, llm_controller
