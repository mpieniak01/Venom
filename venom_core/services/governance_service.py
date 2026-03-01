"""Use-case helpers for governance routes (limits, usage reset, credentials)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from venom_core.core.environment_policy import ensure_data_mutation_allowed
from venom_core.core.provider_governance import (
    CostLimit,
    CredentialStatus,
    LimitType,
    RateLimit,
    get_provider_governance,
)
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class LimitUpdateInput:
    limit_type: str
    scope: str
    soft_limit_usd: float | None = None
    hard_limit_usd: float | None = None
    max_requests_per_minute: int | None = None
    max_tokens_per_minute: int | None = None


def get_governance_status_payload() -> dict[str, Any]:
    governance = get_provider_governance()
    return governance.get_governance_status()


def get_limits_config_payload() -> dict[str, Any]:
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

    return {
        "cost_limits": cost_limits,
        "rate_limits": rate_limits,
    }


def get_provider_credential_status_payload(provider_name: str) -> dict[str, str]:
    governance = get_provider_governance()
    status = governance.validate_credentials(provider_name)

    message_map = {
        CredentialStatus.CONFIGURED: "governance.messages.credentialsConfigured",
        CredentialStatus.MISSING_CREDENTIALS: "governance.messages.credentialsMissing",
        CredentialStatus.INVALID_CREDENTIALS: "governance.messages.credentialsInvalid",
    }
    return {
        "provider": provider_name,
        "credential_status": status.value,
        "message": message_map.get(status, "governance.messages.credentialsConfigured"),
    }


def _resolve_scope_key(scope: str) -> tuple[LimitType, str]:
    limit_type = LimitType.GLOBAL if scope == "global" else LimitType.PER_PROVIDER
    key = scope if scope == "global" else f"provider:{scope}"
    return limit_type, key


def _resolve_cost_limit_values(
    request: LimitUpdateInput,
    current_limit: CostLimit | None,
) -> tuple[float, float]:
    if current_limit is None:
        return (
            request.soft_limit_usd if request.soft_limit_usd is not None else 10.0,
            request.hard_limit_usd if request.hard_limit_usd is not None else 50.0,
        )

    return (
        request.soft_limit_usd
        if request.soft_limit_usd is not None
        else current_limit.soft_limit_usd,
        request.hard_limit_usd
        if request.hard_limit_usd is not None
        else current_limit.hard_limit_usd,
    )


def _apply_cost_limit_values(
    governance: Any,
    key: str,
    request: LimitUpdateInput,
    limit_type: LimitType,
    current_limit: CostLimit | None,
    new_soft_limit: float,
    new_hard_limit: float,
) -> CostLimit:
    if current_limit is None:
        limit = CostLimit(
            limit_type=limit_type,
            scope=request.scope,
            soft_limit_usd=new_soft_limit,
            hard_limit_usd=new_hard_limit,
        )
        governance.cost_limits[key] = limit
        return limit

    if request.soft_limit_usd is not None:
        current_limit.soft_limit_usd = request.soft_limit_usd
    if request.hard_limit_usd is not None:
        current_limit.hard_limit_usd = request.hard_limit_usd
    return current_limit


def _update_cost_limit(governance: Any, request: LimitUpdateInput) -> dict[str, Any]:
    limit_type, key = _resolve_scope_key(request.scope)
    current_limit = governance.cost_limits.get(key)
    new_soft_limit, new_hard_limit = _resolve_cost_limit_values(request, current_limit)

    if new_soft_limit > new_hard_limit:
        raise ValueError("Soft limit cannot be greater than hard limit")

    limit = _apply_cost_limit_values(
        governance,
        key,
        request,
        limit_type,
        current_limit,
        new_soft_limit,
        new_hard_limit,
    )

    logger.info(
        "Updated cost limit for %s: soft=$%s, hard=$%s",
        request.scope,
        limit.soft_limit_usd,
        limit.hard_limit_usd,
    )
    return {
        "status": "success",
        "message": "governance.messages.limitUpdated",
        "limit": {
            "soft_limit_usd": limit.soft_limit_usd,
            "hard_limit_usd": limit.hard_limit_usd,
        },
    }


def _update_rate_limit(governance: Any, request: LimitUpdateInput) -> dict[str, Any]:
    limit_type, key = _resolve_scope_key(request.scope)
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
        "Updated rate limit for %s: requests=%s/min, tokens=%s/min",
        request.scope,
        governance.rate_limits[key].max_requests_per_minute,
        governance.rate_limits[key].max_tokens_per_minute,
    )
    return {
        "status": "success",
        "message": "governance.messages.limitUpdated",
        "limit": {
            "max_requests_per_minute": governance.rate_limits[
                key
            ].max_requests_per_minute,
            "max_tokens_per_minute": governance.rate_limits[key].max_tokens_per_minute,
        },
    }


def update_limit(request: LimitUpdateInput) -> dict[str, Any]:
    governance = get_provider_governance()
    if request.limit_type == "cost":
        return _update_cost_limit(governance, request)
    if request.limit_type == "rate":
        return _update_rate_limit(governance, request)
    raise ValueError(f"Invalid limit_type: {request.limit_type}. Use 'cost' or 'rate'")


def reset_usage(
    *,
    scope: str | None,
    mutation_guard: Callable[[str], None] = ensure_data_mutation_allowed,
) -> dict[str, Any]:
    mutation_guard("governance.reset_usage")
    governance = get_provider_governance()

    if scope is None:
        for cost_limit in governance.cost_limits.values():
            cost_limit.current_usage_usd = 0.0
        for rate_limit in governance.rate_limits.values():
            rate_limit.current_requests = 0
            rate_limit.current_tokens = 0

        logger.info("Reset all usage counters")
        return {
            "status": "success",
            "message": "governance.messages.usageReset",
        }

    key = scope if scope == "global" else f"provider:{scope}"

    if key in governance.cost_limits:
        governance.cost_limits[key].current_usage_usd = 0.0

    if key in governance.rate_limits:
        governance.rate_limits[key].current_requests = 0
        governance.rate_limits[key].current_tokens = 0

    logger.info("Reset usage counters for %s", scope)
    return {
        "status": "success",
        "message": "governance.messages.usageReset",
    }
