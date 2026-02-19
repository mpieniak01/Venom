"""Moduł: routes/traffic_control - API endpointy dla Traffic Control status."""

from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from venom_core.infrastructure.traffic_control import get_traffic_controller
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/traffic-control", tags=["traffic-control"])


@router.get(
    "/status",
    summary="Pobierz status traffic control",
    description="Zwraca metryki i status throttlingu dla API (read-only, bez sekretów)",
    responses={
        200: {"description": "Status traffic control"},
        500: {"description": "Internal server error"},
    },
)
def get_traffic_control_status() -> Dict[str, Any]:
    """
    Endpoint statusu traffic control.

    Zwraca:
    - globalne metryki
    - liste active scopes (providers + endpoint groups)
    - status rate limitów i circuit breakers

    UWAGA: Endpoint jest read-only i nie ekspozuje sekretów.
    """
    try:
        controller = get_traffic_controller()

        # Global metrics
        global_metrics = controller.get_metrics()

        # Get metrics dla wszystkich active scopes
        scope_metrics = {}

        # Outbound scopes (providers)
        for scope in global_metrics.get("outbound_scopes", []):
            scope_metrics[f"outbound:{scope}"] = controller.get_metrics(scope)

        # Inbound scopes (endpoint groups)
        for scope in global_metrics.get("inbound_scopes", []):
            scope_metrics[f"inbound:{scope}"] = controller.get_metrics(scope)

        return {
            "status": "success",
            "global": global_metrics,
            "scopes": scope_metrics,
        }

    except Exception as e:
        logger.exception("Błąd podczas pobierania statusu traffic control")
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get(
    "/metrics/{scope}",
    summary="Pobierz metryki dla konkretnego scope",
    description="Zwraca szczegółowe metryki dla providera lub endpoint group",
    responses={
        200: {"description": "Metryki scope"},
        404: {"description": "Scope not found"},
        500: {"description": "Internal server error"},
    },
)
def get_scope_metrics(scope: str) -> Dict[str, Any]:
    """
    Endpoint metryk dla konkretnego scope.

    Args:
        scope: Nazwa scope (np. 'openai', 'github', 'chat', 'memory')

    Returns:
        Metryki dla scope (rate limit, circuit breaker, counters)
    """
    try:
        controller = get_traffic_controller()
        metrics = controller.get_metrics(scope)

        if "error" in metrics:
            raise HTTPException(status_code=404, detail=metrics["error"])

        return {
            "status": "success",
            "scope": scope,
            "metrics": metrics,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Błąd podczas pobierania metryk dla scope '{scope}'")
        raise HTTPException(status_code=500, detail="Internal server error") from e
