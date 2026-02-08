"""Moduł: routes/system_iot - Endpointy IoT bridge."""

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from venom_core.api.routes import system_deps
from venom_core.config import SETTINGS
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["system"])

IOT_STATUS_RESPONSES: dict[int | str, dict[str, Any]] = {
    500: {"description": "Błąd wewnętrzny podczas pobierania statusu IoT bridge"},
}


class IoTStatusResponse(BaseModel):
    connected: bool
    cpu_temp: Optional[str] = None
    memory: Optional[str] = None
    disk: Optional[str] = None
    message: Optional[str] = None


@router.get(
    "/iot/status",
    response_model=IoTStatusResponse,
    responses=IOT_STATUS_RESPONSES,
)
async def get_iot_status():
    """
    Zwraca podstawowy status Rider-Pi (IoT bridge).
    """
    if not SETTINGS.ENABLE_IOT_BRIDGE:
        return IoTStatusResponse(
            connected=False,
            message="IoT bridge jest wyłączony w konfiguracji.",
        )

    hardware_bridge = system_deps.get_hardware_bridge()
    if hardware_bridge is None or not getattr(hardware_bridge, "connected", False):
        return IoTStatusResponse(
            connected=False,
            message="Brak połączenia z Rider-Pi.",
        )

    if getattr(hardware_bridge, "protocol", None) != "ssh":
        return IoTStatusResponse(
            connected=True,
            message="Połączono z Rider-Pi, telemetria tylko w trybie SSH.",
        )

    cpu_temp = None
    memory = None
    disk = None

    try:
        temp_value = await hardware_bridge.read_sensor("cpu_temp")
        if temp_value is not None:
            cpu_temp = f"{temp_value:.1f}°C"
    except Exception as exc:
        logger.warning("Nie udało się pobrać temperatury CPU Rider-Pi: %s", exc)

    try:
        mem_result = await hardware_bridge.execute_command(
            "free -m | awk 'NR==2{printf \"%s/%sMB\", $3, $2}'"
        )
        if mem_result.get("return_code") == 0:
            memory = mem_result.get("stdout", "").strip() or None
    except Exception as exc:
        logger.warning("Nie udało się pobrać pamięci Rider-Pi: %s", exc)

    try:
        disk_result = await hardware_bridge.execute_command(
            "df -h / | awk 'NR==2{print $3\"/\"$2}'"
        )
        if disk_result.get("return_code") == 0:
            disk = disk_result.get("stdout", "").strip() or None
    except Exception as exc:
        logger.warning("Nie udało się pobrać dysku Rider-Pi: %s", exc)

    message = None
    if not any([cpu_temp, memory, disk]):
        message = "Brak danych telemetrycznych z Rider-Pi."

    return IoTStatusResponse(
        connected=True,
        cpu_temp=cpu_temp,
        memory=memory,
        disk=disk,
        message=message,
    )
