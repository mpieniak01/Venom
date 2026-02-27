"""Bootstrap helpers for model-oriented services initialization."""

from pathlib import Path
from typing import Any, Tuple


def initialize_model_services(
    *,
    settings: Any,
    service_monitor: Any,
    llm_controller: Any,
    logger: Any,
) -> Tuple[Any, Any, Any]:
    """
    Initialize model services and return tuple:
    (model_manager, model_registry, benchmark_service).
    """
    model_manager = None
    model_registry = None
    benchmark_service = None

    from venom_core.core.model_manager import ModelManager

    try:
        model_manager = ModelManager(models_dir=str(Path(settings.ACADEMY_MODELS_DIR)))
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

    return model_manager, model_registry, benchmark_service
