"""Moduł: routes/system_iot - Endpointy IoT bridge."""

from typing import Any, Optional

from fastapi import APIRouter

from venom_core.api.routes import system_deps
from venom_core.api.schemas.system_iot import IoTReconnectResponse, IoTStatusResponse
from venom_core.config import SETTINGS
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["system"])

IOT_STATUS_RESPONSES: dict[int | str, dict[str, Any]] = {
    500: {"description": "Błąd wewnętrzny podczas pobierania statusu IoT bridge"},
}
IOT_RECONNECT_RESPONSES: dict[int | str, dict[str, Any]] = {
    500: {"description": "Błąd wewnętrzny podczas reconnect Rider-Pi"},
}


def _iot_disabled_response() -> IoTStatusResponse:
    return IoTStatusResponse(
        connected=False,
        message="IoT bridge jest wyłączony w konfiguracji.",
    )


def _iot_disconnected_response() -> IoTStatusResponse:
    return IoTStatusResponse(
        connected=False,
        message="Brak połączenia z Rider-Pi.",
    )


def _iot_non_ssh_response() -> IoTStatusResponse:
    return IoTStatusResponse(
        connected=True,
        message="Połączono z Rider-Pi, telemetria tylko w trybie SSH.",
    )


async def _read_cpu_temperature(hardware_bridge) -> Optional[str]:
    try:
        temp_value = await hardware_bridge.read_sensor("cpu_temp")
        if temp_value is None:
            return None
        return f"{temp_value:.1f}°C"
    except Exception as exc:
        logger.warning("Nie udało się pobrać temperatury CPU Rider-Pi: %s", exc)
        return None


async def _read_bridge_command_metric(
    hardware_bridge, command: str, warning_message: str
) -> Optional[str]:
    try:
        result = await hardware_bridge.execute_command(command)
        if result.get("return_code") != 0:
            return None
        return result.get("stdout", "").strip() or None
    except Exception as exc:
        logger.warning("%s: %s", warning_message, exc)
        return None


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
        return _iot_disabled_response()

    hardware_bridge = system_deps.get_hardware_bridge()
    if hardware_bridge is None or not getattr(hardware_bridge, "connected", False):
        return _iot_disconnected_response()

    if getattr(hardware_bridge, "protocol", None) != "ssh":
        return _iot_non_ssh_response()

    cpu_temp = await _read_cpu_temperature(hardware_bridge)
    memory = await _read_bridge_command_metric(
        hardware_bridge,
        "free -m | awk 'NR==2{printf \"%s/%sMB\", $3, $2}'",
        "Nie udało się pobrać pamięci Rider-Pi",
    )
    disk = await _read_bridge_command_metric(
        hardware_bridge,
        "df -h / | awk 'NR==2{print $3\"/\"$2}'",
        "Nie udało się pobrać dysku Rider-Pi",
    )

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


@router.post(
    "/iot/reconnect",
    response_model=IoTReconnectResponse,
    responses=IOT_RECONNECT_RESPONSES,
)
async def reconnect_iot_bridge():
    """Próbuje odtworzyć połączenie z Rider-Pi."""
    if not SETTINGS.ENABLE_IOT_BRIDGE:
        return IoTReconnectResponse(
            connected=False,
            attempts=0,
            message="IoT bridge jest wyłączony w konfiguracji.",
        )

    hardware_bridge = system_deps.get_hardware_bridge()
    if hardware_bridge is None:
        return IoTReconnectResponse(
            connected=False,
            attempts=0,
            message="Rider-Pi bridge nie został zainicjalizowany.",
        )

    try:
        reconnect_method = getattr(hardware_bridge, "reconnect", None)
        if callable(reconnect_method):
            result = await reconnect_method()
            return IoTReconnectResponse(
                connected=bool(result.get("connected")),
                attempts=int(result.get("attempts", 0)),
                message=(
                    "Połączenie z Rider-Pi odtworzone."
                    if result.get("connected")
                    else "Nie udało się odtworzyć połączenia z Rider-Pi."
                ),
            )

        # Fallback dla legacy bridge bez metody reconnect
        if getattr(hardware_bridge, "connected", False):
            disconnect_method = getattr(hardware_bridge, "disconnect", None)
            if callable(disconnect_method):
                await disconnect_method()
        connect_method = getattr(hardware_bridge, "connect", None)
        connected = bool(await connect_method()) if callable(connect_method) else False
        return IoTReconnectResponse(
            connected=connected,
            attempts=1,
            message=(
                "Połączenie z Rider-Pi odtworzone."
                if connected
                else "Nie udało się odtworzyć połączenia z Rider-Pi."
            ),
        )
    except Exception as exc:
        logger.exception("Błąd podczas reconnect Rider-Pi")
        return IoTReconnectResponse(
            connected=False,
            attempts=1,
            message=f"Błąd reconnect: {exc}",
        )
