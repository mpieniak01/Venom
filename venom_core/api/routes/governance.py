"""Moduł: routes/governance - API endpointy dla Provider Governance."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from venom_core.core.provider_governance import (
    CredentialStatus,
    FallbackPolicy,
    get_provider_governance,
)
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["governance"])


class GovernanceStatusResponse(BaseModel):
    """Response dla statusu governance."""

    status: str = "success"
    cost_limits: Dict[str, Dict[str, Any]]
    rate_limits: Dict[str, Dict[str, Any]]
    recent_fallbacks: List[Dict[str, Any]]
    fallback_policy: Dict[str, Any]


class LimitsConfigResponse(BaseModel):
    """Response dla konfiguracji limitów."""

    status: str = "success"
    cost_limits: Dict[str, Dict[str, float]]
    rate_limits: Dict[str, Dict[str, int]]


class ProviderCredentialStatusResponse(BaseModel):
    """Response dla statusu credentiali providera."""

    provider: str
    credential_status: str
    message: str


class UpdateLimitRequest(BaseModel):
    """Request do aktualizacji limitu."""

    limit_type: str = Field(
        ..., description="Typ limitu: 'cost' lub 'rate'"
    )
    scope: str = Field(
        ..., description="Zakres: 'global', nazwa providera lub modelu"
    )
    soft_limit_usd: Optional[float] = Field(
        None, description="Soft limit w USD (dla cost)", gt=0
    )
    hard_limit_usd: Optional[float] = Field(
        None, description="Hard limit w USD (dla cost)", gt=0
    )
    max_requests_per_minute: Optional[int] = Field(
        None, description="Max requestów na minutę (dla rate)", gt=0
    )
    max_tokens_per_minute: Optional[int] = Field(
        None, description="Max tokenów na minutę (dla rate)", gt=0
    )


@router.get(
    "/governance/status",
    response_model=GovernanceStatusResponse,
    summary="Pobierz status governance",
    description="Zwraca aktywne limity, zużycie i ostatnie zdarzenia fallback",
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
        governance = get_provider_governance()
        status_data = governance.get_governance_status()

        return GovernanceStatusResponse(
            status="success",
            cost_limits=status_data["cost_limits"],
            rate_limits=status_data["rate_limits"],
            recent_fallbacks=status_data["recent_fallbacks"],
            fallback_policy=status_data["fallback_policy"],
        )

    except Exception as e:
        logger.exception("Błąd podczas pobierania statusu governance")
        raise HTTPException(
            status_code=500, detail="Internal server error"
        ) from e


@router.get(
    "/governance/limits",
    response_model=LimitsConfigResponse,
    summary="Pobierz konfigurację limitów",
    description="Zwraca aktualne ustawienia limitów kosztowych i rate",
)
def get_limits_config() -> LimitsConfigResponse:
    """
    Endpoint konfiguracji limitów.

    Zwraca aktualne limity bez wrażliwych danych.
    """
    try:
        governance = get_provider_governance()

        cost_limits = {
            scope: {
                "soft_limit_usd": limit.soft_limit_usd,
                "hard_limit_usd": limit.hard_limit_usd,
            }
            for scope, limit in governance.cost_limits.items()
        }

        rate_limits = {
            scope: {
                "max_requests_per_minute": limit.max_requests_per_minute,
                "max_tokens_per_minute": limit.max_tokens_per_minute,
            }
            for scope, limit in governance.rate_limits.items()
        }

        return LimitsConfigResponse(
            status="success",
            cost_limits=cost_limits,
            rate_limits=rate_limits,
        )

    except Exception as e:
        logger.exception("Błąd podczas pobierania konfiguracji limitów")
        raise HTTPException(
            status_code=500, detail="Internal server error"
        ) from e


@router.get(
    "/governance/providers/{provider_name}/credentials",
    response_model=ProviderCredentialStatusResponse,
    summary="Sprawdź status credentiali providera",
    description="Waliduje konfigurację credentiali providera bez ujawniania sekretów",
)
def get_provider_credential_status(provider_name: str) -> ProviderCredentialStatusResponse:
    """
    Endpoint walidacji credentiali.

    Sprawdza status konfiguracji bez ujawniania kluczy API.

    Args:
        provider_name: Nazwa providera

    Returns:
        Status: configured, missing_credentials, invalid_credentials
    """
    try:
        governance = get_provider_governance()
        status = governance.validate_credentials(provider_name)

        message_map = {
            CredentialStatus.CONFIGURED: "governance.messages.credentialsConfigured",
            CredentialStatus.MISSING_CREDENTIALS: "governance.messages.credentialsMissing",
            CredentialStatus.INVALID_CREDENTIALS: "governance.messages.credentialsInvalid",
        }

        return ProviderCredentialStatusResponse(
            provider=provider_name,
            credential_status=status.value,
            message=message_map.get(status, "governance.messages.credentialsConfigured"),
        )

    except Exception as e:
        logger.exception(
            f"Błąd podczas walidacji credentiali dla providera {provider_name}"
        )
        raise HTTPException(
            status_code=500, detail="Internal server error"
        ) from e


@router.post(
    "/governance/limits",
    summary="Aktualizuj limity",
    description="Aktualizuje limity kosztowe lub rate dla danego scope",
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
        governance = get_provider_governance()

        if request.limit_type == "cost":
            # Validate cost limits
            if request.soft_limit_usd is not None and request.hard_limit_usd is not None:
                if request.soft_limit_usd > request.hard_limit_usd:
                    raise HTTPException(
                        status_code=400,
                        detail="Soft limit cannot be greater than hard limit",
                    )
            
            # Update cost limit
            from venom_core.core.provider_governance import CostLimit, LimitType

            limit_type = (
                LimitType.GLOBAL
                if request.scope == "global"
                else LimitType.PER_PROVIDER
            )
            key = request.scope if request.scope == "global" else f"provider:{request.scope}"

            if key not in governance.cost_limits:
                governance.cost_limits[key] = CostLimit(
                    limit_type=limit_type,
                    scope=request.scope,
                    soft_limit_usd=request.soft_limit_usd or 10.0,
                    hard_limit_usd=request.hard_limit_usd or 50.0,
                )
            else:
                if request.soft_limit_usd is not None:
                    governance.cost_limits[key].soft_limit_usd = request.soft_limit_usd
                if request.hard_limit_usd is not None:
                    governance.cost_limits[key].hard_limit_usd = request.hard_limit_usd

            logger.info(
                f"Updated cost limit for {request.scope}: "
                f"soft=${governance.cost_limits[key].soft_limit_usd}, "
                f"hard=${governance.cost_limits[key].hard_limit_usd}"
            )

            return {
                "status": "success",
                "message": "governance.messages.limitUpdated",
                "limit": {
                    "soft_limit_usd": governance.cost_limits[key].soft_limit_usd,
                    "hard_limit_usd": governance.cost_limits[key].hard_limit_usd,
                },
            }

        elif request.limit_type == "rate":
            # Update rate limit
            from venom_core.core.provider_governance import RateLimit, LimitType

            limit_type = (
                LimitType.GLOBAL
                if request.scope == "global"
                else LimitType.PER_PROVIDER
            )
            key = request.scope if request.scope == "global" else f"provider:{request.scope}"

            if key not in governance.rate_limits:
                governance.rate_limits[key] = RateLimit(
                    limit_type=limit_type,
                    scope=request.scope,
                    max_requests_per_minute=request.max_requests_per_minute or 100,
                    max_tokens_per_minute=request.max_tokens_per_minute or 100000,
                )
            else:
                if request.max_requests_per_minute is not None:
                    governance.rate_limits[
                        key
                    ].max_requests_per_minute = request.max_requests_per_minute
                if request.max_tokens_per_minute is not None:
                    governance.rate_limits[
                        key
                    ].max_tokens_per_minute = request.max_tokens_per_minute

            logger.info(
                f"Updated rate limit for {request.scope}: "
                f"requests={governance.rate_limits[key].max_requests_per_minute}/min, "
                f"tokens={governance.rate_limits[key].max_tokens_per_minute}/min"
            )

            return {
                "status": "success",
                "message": "governance.messages.limitUpdated",
                "limit": {
                    "max_requests_per_minute": governance.rate_limits[
                        key
                    ].max_requests_per_minute,
                    "max_tokens_per_minute": governance.rate_limits[
                        key
                    ].max_tokens_per_minute,
                },
            }

        else:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid limit_type: {request.limit_type}. Use 'cost' or 'rate'",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Błąd podczas aktualizacji limitu")
        raise HTTPException(
            status_code=500, detail="Internal server error"
        ) from e


@router.post(
    "/governance/reset-usage",
    summary="Resetuj liczniki zużycia",
    description="Resetuje liczniki zużycia dla wszystkich lub wybranego scope",
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
        governance = get_provider_governance()

        if scope is None:
            # Reset all
            for limit in governance.cost_limits.values():
                limit.current_usage_usd = 0.0
            for limit in governance.rate_limits.values():
                limit.current_requests = 0
                limit.current_tokens = 0

            logger.info("Reset all usage counters")
            return {
                "status": "success",
                "message": "governance.messages.usageReset",
            }
        else:
            # Reset specific scope
            key = scope if scope == "global" else f"provider:{scope}"

            if key in governance.cost_limits:
                governance.cost_limits[key].current_usage_usd = 0.0

            if key in governance.rate_limits:
                governance.rate_limits[key].current_requests = 0
                governance.rate_limits[key].current_tokens = 0

            logger.info(f"Reset usage counters for {scope}")
            return {
                "status": "success",
                "message": "governance.messages.usageReset",
            }

    except Exception as e:
        logger.exception("Błąd podczas resetowania liczników")
        raise HTTPException(
            status_code=500, detail="Internal server error"
        ) from e
