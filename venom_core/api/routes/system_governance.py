"""Moduł: routes/system_governance - Cost Guard i AutonomyGate."""

import os
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from venom_core.api.routes import system_deps
from venom_core.api.schemas.governance import (
    AutonomyLevelRequest,
    AutonomyLevelResponse,
    AutonomyLevelSetResponse,
    AutonomyLevelsResponse,
    AutonomyObservabilityPayload,
    AutonomyObservabilityResponse,
    AutonomyRolloutStatusResponse,
    CostModeRequest,
    CostModeResponse,
    CostModeSetResponse,
    PolicyFalsePositiveTriage,
    PolicyReasonStat,
)
from venom_core.config import SETTINGS
from venom_core.core.permission_guard import permission_guard
from venom_core.services import tasks_service
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
AUTONOMY_OBSERVABILITY_RESPONSES: dict[int | str, dict[str, Any]] = {
    503: {"description": "Metrics collector nie jest dostępny"},
    500: {"description": "Błąd wewnętrzny podczas pobierania observability policy"},
}
AUTONOMY_ROLLOUT_STATUS_RESPONSES: dict[int | str, dict[str, Any]] = {
    500: {"description": "Błąd wewnętrzny podczas pobierania statusu rollout policy"},
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


def _normalize_reason_stats(items: Any) -> list[PolicyReasonStat]:
    if not isinstance(items, list):
        return []

    stats: list[PolicyReasonStat] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        reason_code = str(item.get("reason_code") or "").strip()
        if not reason_code:
            continue
        stats.append(
            PolicyReasonStat(
                reason_code=reason_code,
                count=int(item.get("count") or 0),
                share_rate=float(item.get("share_rate") or 0.0),
            )
        )
    return stats


def _normalize_policy_observability(policy_data: Any) -> AutonomyObservabilityPayload:
    raw = policy_data if isinstance(policy_data, dict) else {}
    blocked_count = int(raw.get("blocked_count") or 0)
    deny_rate = float(raw.get("deny_rate") or raw.get("block_rate") or 0.0)

    top_reason_codes = _normalize_reason_stats(raw.get("top_reason_codes"))

    triage_raw = raw.get("false_positive_triage")
    triage = triage_raw if isinstance(triage_raw, dict) else {}
    return AutonomyObservabilityPayload(
        blocked_count=blocked_count,
        deny_rate=round(deny_rate, 2),
        top_reason_codes=top_reason_codes,
        false_positive_triage=PolicyFalsePositiveTriage(
            candidate_count=int(triage.get("candidate_count") or 0),
            candidate_rate=float(triage.get("candidate_rate") or 0.0),
            top_candidate_reasons=_normalize_reason_stats(
                triage.get("top_candidate_reasons")
            ),
        ),
    )


def _build_rollout_next_actions(
    *, policy_enabled: bool, observability_ready: bool
) -> list[str]:
    actions: list[str] = []
    if not policy_enabled:
        actions.append("Enable runtime policy gate (set ENABLE_POLICY_GATE=true).")
    if not observability_ready:
        actions.append("Initialize metrics collector before rollout validation.")
    actions.append(
        "Validate rollout on staging/preprod/prod using /api/v1/system/autonomy/rollout-status."
    )
    return actions


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


@router.get(
    "/system/autonomy/observability",
    responses=AUTONOMY_OBSERVABILITY_RESPONSES,
)
def get_autonomy_observability() -> AutonomyObservabilityResponse:
    """
    Zwraca dedykowany snapshot observability policy/autonomy dla operacji (SRE/ops).
    """
    collector = tasks_service.get_metrics_collector()
    if collector is None:
        raise HTTPException(
            status_code=503, detail="Metrics collector nie jest dostępny"
        )

    try:
        metrics = collector.get_metrics()
        policy = _normalize_policy_observability(metrics.get("policy"))
        return AutonomyObservabilityResponse(policy=policy)
    except Exception as e:
        logger.exception("Błąd podczas pobierania observability policy")
        raise HTTPException(
            status_code=500,
            detail=f"Błąd wewnętrzny: {str(e)}",
        ) from e


@router.get(
    "/system/autonomy/rollout-status",
    responses=AUTONOMY_ROLLOUT_STATUS_RESPONSES,
)
def get_autonomy_rollout_status() -> AutonomyRolloutStatusResponse:
    """
    Zwraca status gotowości rollout runtime-only policy gate.
    """
    try:
        observability_ready = tasks_service.get_metrics_collector() is not None
        policy_enabled = os.getenv("ENABLE_POLICY_GATE", "false").lower() == "true"
        readiness = (
            "ready" if policy_enabled and observability_ready else "attention_required"
        )
        return AutonomyRolloutStatusResponse(
            readiness=readiness,
            runtime_only_architecture=True,
            policy_gate_enabled=policy_enabled,
            legacy_submit_stage_removed=True,
            observability_endpoint_available=observability_ready,
            required_next_actions=_build_rollout_next_actions(
                policy_enabled=policy_enabled,
                observability_ready=observability_ready,
            ),
        )
    except Exception as e:
        logger.exception("Błąd podczas pobierania statusu rollout policy")
        raise HTTPException(
            status_code=500,
            detail=f"Błąd wewnętrzny: {str(e)}",
        ) from e


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
