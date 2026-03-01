"""Moduł: routes/governance - API endpointy dla Provider Governance."""

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException

from venom_core.api.schemas.governance import (
    GovernanceStatusResponse,
    LimitsConfigResponse,
    ProviderCredentialStatusResponse,
    UpdateLimitRequest,
)
from venom_core.services import governance_service
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["governance"])
INTERNAL_SERVER_ERROR_DETAIL = "Internal server error"

RESP_400_INVALID_LIMIT = {"description": "Invalid governance limit request."}
RESP_500_INTERNAL = {"description": INTERNAL_SERVER_ERROR_DETAIL}

# Compatibility alias for tests that monkeypatch mutation guard at route-level.
ensure_data_mutation_allowed = governance_service.ensure_data_mutation_allowed


@router.get(
    "/governance/status",
    summary="Pobierz status governance",
    description="Zwraca aktywne limity, zużycie i ostatnie zdarzenia fallback",
    responses={500: RESP_500_INTERNAL},
)
def get_governance_status() -> GovernanceStatusResponse:
    """
    Endpoint statusu governance.

    Zwraca:
    - aktywne limity kosztowe i rate
    - aktualne zużycie
    - ostatnie zdarzenia fallback
    - konfigurację fallback policy
    """
    try:
        status_data = governance_service.get_governance_status_payload()

        return GovernanceStatusResponse(
            status="success",
            cost_limits=status_data["cost_limits"],
            rate_limits=status_data["rate_limits"],
            recent_fallbacks=status_data["recent_fallbacks"],
            fallback_policy=status_data["fallback_policy"],
        )

    except Exception as e:
        logger.exception("Błąd podczas pobierania statusu governance")
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR_DETAIL) from e


@router.get(
    "/governance/limits",
    summary="Pobierz konfigurację limitów",
    description="Zwraca aktualne ustawienia limitów kosztowych i rate",
    responses={500: RESP_500_INTERNAL},
)
def get_limits_config() -> LimitsConfigResponse:
    """
    Endpoint konfiguracji limitów.

    Zwraca aktualne limity bez wrażliwych danych.
    """
    try:
        payload = governance_service.get_limits_config_payload()

        return LimitsConfigResponse(
            status="success",
            cost_limits=payload["cost_limits"],
            rate_limits=payload["rate_limits"],
        )

    except Exception as e:
        logger.exception("Błąd podczas pobierania konfiguracji limitów")
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR_DETAIL) from e


@router.get(
    "/governance/providers/{provider_name}/credentials",
    summary="Sprawdź status credentiali providera",
    description="Waliduje konfigurację credentiali providera bez ujawniania sekretów",
    responses={500: RESP_500_INTERNAL},
)
def get_provider_credential_status(
    provider_name: str,
) -> ProviderCredentialStatusResponse:
    """
    Endpoint walidacji credentiali.

    Sprawdza status konfiguracji bez ujawniania kluczy API.

    Args:
        provider_name: Nazwa providera

    Returns:
        Status: configured, missing_credentials, invalid_credentials
    """
    try:
        payload = governance_service.get_provider_credential_status_payload(
            provider_name
        )

        return ProviderCredentialStatusResponse(
            provider=payload["provider"],
            credential_status=payload["credential_status"],
            message=payload["message"],
        )

    except Exception as e:
        logger.exception(
            f"Błąd podczas walidacji credentiali dla providera {provider_name}"
        )
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR_DETAIL) from e


@router.post(
    "/governance/limits",
    summary="Aktualizuj limity",
    description="Aktualizuje limity kosztowe lub rate dla danego scope",
    responses={
        400: RESP_400_INVALID_LIMIT,
        500: RESP_500_INTERNAL,
    },
)
def update_limit(request: UpdateLimitRequest) -> Dict[str, Any]:
    """
    Endpoint aktualizacji limitów.

    Pozwala na dynamiczną zmianę limitów kosztowych i rate.

    Args:
        request: Konfiguracja limitu do aktualizacji

    Returns:
        Potwierdzenie aktualizacji
    """
    try:
        return governance_service.update_limit(
            governance_service.LimitUpdateInput(
                limit_type=request.limit_type,
                scope=request.scope,
                soft_limit_usd=request.soft_limit_usd,
                hard_limit_usd=request.hard_limit_usd,
                max_requests_per_minute=request.max_requests_per_minute,
                max_tokens_per_minute=request.max_tokens_per_minute,
            )
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception("Błąd podczas aktualizacji limitu")
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR_DETAIL) from e


@router.post(
    "/governance/reset-usage",
    summary="Resetuj liczniki zużycia",
    description="Resetuje liczniki zużycia dla wszystkich lub wybranego scope",
    responses={
        403: {"description": "Brak uprawnień do mutacji danych"},
        500: RESP_500_INTERNAL,
    },
)
def reset_usage(scope: Optional[str] = None) -> Dict[str, Any]:
    """
    Endpoint resetowania liczników zużycia.

    Args:
        scope: Opcjonalny scope do zresetowania (None = wszystko)

    Returns:
        Potwierdzenie resetu
    """
    try:
        return governance_service.reset_usage(
            scope=scope,
            mutation_guard=ensure_data_mutation_allowed,
        )

    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except Exception as e:
        logger.exception("Błąd podczas resetowania liczników")
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR_DETAIL) from e
