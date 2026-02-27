"""Bootstrap helpers for optional agent/service stacks."""

from typing import Any, Callable, Tuple


def initialize_calendar_skill(*, settings: Any, logger: Any) -> Any:
    """Initialize Google Calendar skill or return None when unavailable."""
    if not settings.ENABLE_GOOGLE_CALENDAR:
        logger.info("GoogleCalendarSkill wyłączony w konfiguracji")
        return None

    try:
        from venom_core.execution.skills.google_calendar_skill import (
            GoogleCalendarSkill,
        )

        calendar_skill = GoogleCalendarSkill()
        if calendar_skill.credentials_available:
            logger.info("GoogleCalendarSkill zainicjalizowany dla API")
        else:
            logger.info(
                "GoogleCalendarSkill zainicjalizowany bez credentials - "
                "graceful degradation"
            )
        return calendar_skill
    except Exception as exc:
        logger.warning(f"Nie udało się zainicjalizować GoogleCalendarSkill: {exc}")
        return None


def initialize_academy(
    *,
    settings: Any,
    logger: Any,
    lessons_store: Any,
    model_manager: Any,
    get_orchestrator_kernel: Callable[[], Any],
) -> Tuple[Any, Any, Any]:
    """Initialize THE_ACADEMY components and return (professor, dataset_curator, gpu_habitat)."""
    if not settings.ENABLE_ACADEMY:
        logger.info("THE_ACADEMY wyłączone w konfiguracji (ENABLE_ACADEMY=False)")
        return None, None, None

    try:
        logger.info("Inicjalizacja THE_ACADEMY...")
        from venom_core.agents.professor import Professor
        from venom_core.infrastructure.gpu_habitat import GPUHabitat
        from venom_core.learning.dataset_curator import DatasetCurator

        dataset_curator = DatasetCurator(lessons_store=lessons_store)
        logger.info("✅ DatasetCurator zainicjalizowany")

        gpu_habitat = GPUHabitat(enable_gpu=settings.ACADEMY_ENABLE_GPU)
        logger.info(
            f"✅ GPUHabitat zainicjalizowany (GPU: {settings.ACADEMY_ENABLE_GPU})"
        )

        professor = None
        kernel = get_orchestrator_kernel()
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
        return professor, dataset_curator, gpu_habitat
    except ImportError as exc:
        logger.warning(
            f"THE_ACADEMY dependencies not installed. Install with: "
            f"pip install -r requirements-academy.txt. Error: {exc}"
        )
        return None, None, None
    except Exception as exc:
        logger.error(f"❌ Błąd podczas inicjalizacji THE_ACADEMY: {exc}", exc_info=True)
        return None, None, None
