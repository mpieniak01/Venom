"""State/dependency helpers for RuntimeController."""

from __future__ import annotations

from typing import Any, Callable, Optional, Protocol


class LoggerLike(Protocol):
    def warning(self, msg: str, *args: Any, **kwargs: Any) -> Any: ...


def update_config_managed_status(
    *,
    info: Any,
    service_type: Any,
    settings: Any,
    service_type_enum: Any,
    service_status_enum: Any,
) -> None:
    if service_type == service_type_enum.HIVE:
        info.status = (
            service_status_enum.RUNNING
            if settings.ENABLE_HIVE
            else service_status_enum.STOPPED
        )
        return
    if service_type == service_type_enum.NEXUS:
        info.status = (
            service_status_enum.RUNNING
            if settings.ENABLE_NEXUS
            else service_status_enum.STOPPED
        )
        if settings.ENABLE_NEXUS:
            info.port = getattr(settings, "NEXUS_PORT", None)
        return
    if service_type == service_type_enum.BACKGROUND_TASKS:
        info.status = (
            service_status_enum.STOPPED
            if settings.VENOM_PAUSE_BACKGROUND_TASKS
            else service_status_enum.RUNNING
        )
        return
    if service_type in {
        service_type_enum.ACADEMY,
        service_type_enum.INTENT_EMBEDDING_ROUTER,
    }:
        setting_name = f"ENABLE_{service_type.name}"
        info.status = (
            service_status_enum.RUNNING
            if getattr(settings, setting_name, False)
            else service_status_enum.STOPPED
        )


def config_controlled_result(
    *, service_type: Any, service_type_enum: Any
) -> dict[str, Any]:
    messages = {
        service_type_enum.HIVE: "Hive kontrolowany przez konfigurację",
        service_type_enum.NEXUS: "Nexus kontrolowany przez konfigurację",
        service_type_enum.BACKGROUND_TASKS: "Background tasks kontrolowane przez konfigurację",
        service_type_enum.ACADEMY: "Academy kontrolowane przez konfigurację",
        service_type_enum.INTENT_EMBEDDING_ROUTER: "Intent embedding router kontrolowany przez konfigurację",
    }
    message = messages.get(service_type, "Nieznany typ usługi")
    return {"success": False, "message": message}


def check_service_dependencies(
    *,
    service_type: Any,
    get_service_status_fn: Callable[[Any], Any],
    settings: Any,
    service_type_enum: Any,
    service_status_enum: Any,
    logger: LoggerLike,
) -> Optional[str]:
    if service_type == service_type_enum.HIVE and not settings.ENABLE_HIVE:
        return "Hive jest wyłączone w konfiguracji (ENABLE_HIVE=false)"

    if service_type == service_type_enum.NEXUS:
        if not settings.ENABLE_NEXUS:
            return "Nexus jest wyłączone w konfiguracji (ENABLE_NEXUS=false)"
        backend_status = get_service_status_fn(service_type_enum.BACKEND)
        if backend_status.status != service_status_enum.RUNNING:
            return "Nexus wymaga działającego backendu. Uruchom najpierw backend."

    if service_type == service_type_enum.BACKGROUND_TASKS:
        backend_status = get_service_status_fn(service_type_enum.BACKEND)
        if backend_status.status != service_status_enum.RUNNING:
            return "Background tasks wymagają działającego backendu. Uruchom najpierw backend."

    if service_type == service_type_enum.UI:
        backend_status = get_service_status_fn(service_type_enum.BACKEND)
        if backend_status.status != service_status_enum.RUNNING:
            logger.warning("UI uruchamiany bez backendu - ograniczona funkcjonalność")

    return None
