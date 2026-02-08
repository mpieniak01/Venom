"""Moduł: routes/system_governance - Cost Guard i AutonomyGate."""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from venom_core.api.routes import system_deps
from venom_core.config import SETTINGS
from venom_core.core.permission_guard import permission_guard
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["system"])

COST_MODE_RESPONSES: dict[int | str, dict[str, Any]] = {
    503: {"description": "StateManager nie jest dostępny (Cost Guard)"},
    500: {"description": "Błąd wewnętrzny podczas obsługi Cost Guard"},
}
AUTONOMY_GET_RESPONSES: dict[int | str, dict[str, Any]] = {
    500: {"description": "Błąd wewnętrzny podczas pobierania poziomu autonomii"},
}
AUTONOMY_SET_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"description": "Nieprawidłowy poziom autonomii"},
    500: {"description": "Błąd wewnętrzny podczas zmiany poziomu autonomii"},
}
AUTONOMY_LEVELS_RESPONSES: dict[int | str, dict[str, Any]] = {
    500: {"description": "Błąd wewnętrzny podczas pobierania listy poziomów"},
}


class CostModeRequest(BaseModel):
    """Request do zmiany trybu kosztowego."""

    enable: bool


class CostModeResponse(BaseModel):
    """Response z informacją o trybie kosztowym."""

    enabled: bool
    provider: str


@router.get(
    "/system/cost-mode",
    response_model=CostModeResponse,
    responses=COST_MODE_RESPONSES,
)
async def get_cost_mode():
    """
    Zwraca aktualny stan Global Cost Guard.
    """
    state_manager = system_deps.get_state_manager()
    if state_manager is None:
        raise HTTPException(
            status_code=503, detail="StateManager nie jest dostępny (Cost Guard)"
        )

    try:
        enabled = state_manager.is_paid_mode_enabled()
        provider = (
            "hybrid" if SETTINGS.AI_MODE == "HYBRID" else SETTINGS.AI_MODE.lower()
        )

        return CostModeResponse(enabled=enabled, provider=provider)

    except Exception as e:
        logger.exception("Błąd podczas pobierania statusu Cost Guard")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@router.post("/system/cost-mode", responses=COST_MODE_RESPONSES)
async def set_cost_mode(request: CostModeRequest):
    """
    Ustawia tryb kosztowy (Eco/Pro).
    """
    state_manager = system_deps.get_state_manager()
    if state_manager is None:
        raise HTTPException(
            status_code=503, detail="StateManager nie jest dostępny (Cost Guard)"
        )

    try:
        if request.enable:
            state_manager.enable_paid_mode()
            logger.warning(
                "🔓 Paid Mode ENABLED przez API - użytkownik zaakceptował koszty"
            )
            return {
                "status": "success",
                "message": "Paid Mode (Pro) włączony - dostęp do Cloud API otwarty",
                "enabled": True,
            }

        state_manager.disable_paid_mode()
        logger.info("🔒 Paid Mode DISABLED przez API - tryb Eco aktywny")
        return {
            "status": "success",
            "message": "Paid Mode (Pro) wyłączony - tylko lokalne modele",
            "enabled": False,
        }

    except Exception as e:
        logger.exception("Błąd podczas zmiany trybu kosztowego")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


class AutonomyLevelRequest(BaseModel):
    """Request do zmiany poziomu autonomii."""

    level: int


class AutonomyLevelResponse(BaseModel):
    """Response z informacją o poziomie autonomii."""

    current_level: int
    current_level_name: str
    color: str
    color_name: str
    description: str
    permissions: dict
    risk_level: str


@router.get(
    "/system/autonomy",
    response_model=AutonomyLevelResponse,
    responses=AUTONOMY_GET_RESPONSES,
)
async def get_autonomy_level():
    """
    Zwraca aktualny poziom autonomii AutonomyGate.
    """
    try:
        current_level = permission_guard.get_current_level()
        level_info = permission_guard.get_level_info(current_level)

        if not level_info:
            raise HTTPException(
                status_code=500, detail="Nie można pobrać informacji o poziomie"
            )

        return AutonomyLevelResponse(
            current_level=current_level,
            current_level_name=level_info.name,
            color=level_info.color,
            color_name=level_info.color_name,
            description=level_info.description,
            permissions=level_info.permissions,
            risk_level=level_info.risk_level,
        )

    except Exception as e:
        logger.exception("Błąd podczas pobierania poziomu autonomii")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@router.post("/system/autonomy", responses=AUTONOMY_SET_RESPONSES)
async def set_autonomy_level(request: AutonomyLevelRequest):
    """
    Ustawia nowy poziom autonomii.
    """
    try:
        success = permission_guard.set_level(request.level)

        if not success:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Nieprawidłowy poziom: {request.level}. "
                    "Dostępne: 0, 10, 20, 30, 40"
                ),
            )

        level_info = permission_guard.get_level_info(request.level)

        if not level_info:
            raise HTTPException(
                status_code=500,
                detail="Nie można pobrać informacji o poziomie po zmianie",
            )

        return {
            "status": "success",
            "message": f"Poziom autonomii zmieniony na {level_info.name}",
            "level": request.level,
            "level_name": level_info.name,
            "color": level_info.color,
            "permissions": level_info.permissions,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Błąd podczas zmiany poziomu autonomii")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@router.get("/system/autonomy/levels", responses=AUTONOMY_LEVELS_RESPONSES)
async def get_all_autonomy_levels():
    """
    Zwraca listę wszystkich dostępnych poziomów autonomii.
    """
    try:
        levels = permission_guard.get_all_levels()

        levels_data = [
            {
                "id": level.id,
                "name": level.name,
                "description": level.description,
                "color": level.color,
                "color_name": level.color_name,
                "permissions": level.permissions,
                "risk_level": level.risk_level,
                "examples": level.examples,
            }
            for level in levels.values()
        ]

        return {"status": "success", "levels": levels_data, "count": len(levels_data)}

    except Exception as e:
        logger.exception("Błąd podczas pobierania listy poziomów")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e
