"""Moduł: routes/system_governance - Cost Guard i AutonomyGate."""

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from venom_core.api.routes import system_deps
from venom_core.api.schemas.governance import (
    AutonomyLevelRequest,
    AutonomyLevelResponse,
    AutonomyLevelSetResponse,
    AutonomyLevelsResponse,
    CostModeRequest,
    CostModeResponse,
    CostModeSetResponse,
)
from venom_core.config import SETTINGS
from venom_core.core.permission_guard import permission_guard
from venom_core.services.audit_stream import get_audit_stream
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["system"])

STATE_MANAGER_COST_GUARD_UNAVAILABLE = "StateManager nie jest dostępny (Cost Guard)"

COST_MODE_RESPONSES: dict[int | str, dict[str, Any]] = {
    503: {"description": STATE_MANAGER_COST_GUARD_UNAVAILABLE},
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


def _extract_actor_from_request(request: Request) -> str:
    try:
        if hasattr(request, "state") and hasattr(request.state, "user"):
            user = request.state.user
            if user:
                return str(user)
        actor = request.headers.get("X-Actor") or request.headers.get("X-User-Id")
        if actor:
            return actor
    except Exception:
        logger.warning("Nie udało się wyekstrahować aktora dla audytu autonomii")
    return "unknown"


@router.get(
    "/system/cost-mode",
    response_model=CostModeResponse,
    responses=COST_MODE_RESPONSES,
)
def get_cost_mode():
    """
    Zwraca aktualny stan Global Cost Guard.
    """
    state_manager = system_deps.get_state_manager()
    if state_manager is None:
        raise HTTPException(
            status_code=503, detail=STATE_MANAGER_COST_GUARD_UNAVAILABLE
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


@router.post(
    "/system/cost-mode",
    responses=COST_MODE_RESPONSES,
)
def set_cost_mode(request: CostModeRequest) -> CostModeSetResponse:
    """
    Ustawia tryb kosztowy (Eco/Pro).
    """
    state_manager = system_deps.get_state_manager()
    if state_manager is None:
        raise HTTPException(
            status_code=503, detail=STATE_MANAGER_COST_GUARD_UNAVAILABLE
        )

    try:
        if request.enable:
            state_manager.enable_paid_mode()
            logger.warning(
                "🔓 Paid Mode ENABLED przez API - użytkownik zaakceptował koszty"
            )
            return CostModeSetResponse(
                status="success",
                message="Paid Mode (Pro) włączony - dostęp do Cloud API otwarty",
                enabled=True,
            )

        state_manager.disable_paid_mode()
        logger.info("🔒 Paid Mode DISABLED przez API - tryb Eco aktywny")
        return CostModeSetResponse(
            status="success",
            message="Paid Mode (Pro) wyłączony - tylko lokalne modele",
            enabled=False,
        )

    except Exception as e:
        logger.exception("Błąd podczas zmiany trybu kosztowego")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@router.get(
    "/system/autonomy",
    response_model=AutonomyLevelResponse,
    responses=AUTONOMY_GET_RESPONSES,
)
def get_autonomy_level():
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


@router.post(
    "/system/autonomy",
    responses=AUTONOMY_SET_RESPONSES,
)
def set_autonomy_level(
    request: Request, payload: AutonomyLevelRequest
) -> AutonomyLevelSetResponse:
    """
    Ustawia nowy poziom autonomii.
    """
    try:
        actor = _extract_actor_from_request(request)
        old_level = permission_guard.get_current_level()
        old_level_info = permission_guard.get_level_info(old_level)
        success = permission_guard.set_level(payload.level)

        if not success:
            get_audit_stream().publish(
                source="core.governance",
                action="autonomy.level_changed",
                actor=actor,
                status="failure",
                details={
                    "old_level": old_level,
                    "old_level_name": old_level_info.name
                    if old_level_info
                    else "UNKNOWN",
                    "new_level": payload.level,
                    "new_level_name": "UNKNOWN",
                    "actor": actor,
                    "request_path": "/api/v1/system/autonomy",
                },
            )
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Nieprawidłowy poziom: {payload.level}. "
                    "Dostępne: 0, 10, 20, 30, 40"
                ),
            )

        level_info = permission_guard.get_level_info(payload.level)

        if not level_info:
            raise HTTPException(
                status_code=500,
                detail="Nie można pobrać informacji o poziomie po zmianie",
            )

        get_audit_stream().publish(
            source="core.governance",
            action="autonomy.level_changed",
            actor=actor,
            status="success",
            details={
                "old_level": old_level,
                "old_level_name": old_level_info.name if old_level_info else "UNKNOWN",
                "new_level": payload.level,
                "new_level_name": level_info.name,
                "actor": actor,
                "request_path": "/api/v1/system/autonomy",
            },
        )

        return AutonomyLevelSetResponse(
            status="success",
            message=f"Poziom autonomii zmieniony na {level_info.name}",
            level=payload.level,
            level_name=level_info.name,
            color=level_info.color,
            permissions=level_info.permissions,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Błąd podczas zmiany poziomu autonomii")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@router.get(
    "/system/autonomy/levels",
    responses=AUTONOMY_LEVELS_RESPONSES,
)
def get_all_autonomy_levels() -> AutonomyLevelsResponse:
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

        return AutonomyLevelsResponse(
            status="success", levels=levels_data, count=len(levels_data)
        )

    except Exception as e:
        logger.exception("Błąd podczas pobierania listy poziomów")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e
