"""Error code to message mapping with runbook links for admin UX."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class ErrorMapping:
    """Maps reason_code to user/admin messages and runbook links."""

    reason_code: str
    user_message_key: str  # i18n key for user-facing message
    admin_message_key: str  # i18n key for admin-facing message
    runbook_path: Optional[str] = None  # Path to runbook doc
    recovery_hint_key: Optional[str] = None  # i18n key for recovery hint
    severity: str = "warning"  # info, warning, critical


# Provider error mappings
RUNBOOK_PROVIDER_OFFLINE = "/docs/runbooks/provider-offline.md"
RUNBOOK_AUTH_FAILURES = "/docs/runbooks/auth-failures.md"
RUNBOOK_LATENCY_SPIKE = "/docs/runbooks/latency-spike.md"


PROVIDER_ERROR_MAPPINGS: Dict[str, ErrorMapping] = {
    # Connection errors
    "connection_failed": ErrorMapping(
        reason_code="connection_failed",
        user_message_key="errors.provider.connection_failed.user",
        admin_message_key="errors.provider.connection_failed.admin",
        runbook_path=RUNBOOK_PROVIDER_OFFLINE,
        recovery_hint_key="errors.provider.connection_failed.hint",
        severity="critical",
    ),
    "offline": ErrorMapping(
        reason_code="offline",
        user_message_key="errors.provider.offline.user",
        admin_message_key="errors.provider.offline.admin",
        runbook_path=RUNBOOK_PROVIDER_OFFLINE,
        recovery_hint_key="errors.provider.offline.hint",
        severity="critical",
    ),
    "PROVIDER_OFFLINE": ErrorMapping(
        reason_code="PROVIDER_OFFLINE",
        user_message_key="errors.provider.offline.user",
        admin_message_key="errors.provider.offline.admin",
        runbook_path=RUNBOOK_PROVIDER_OFFLINE,
        recovery_hint_key="errors.provider.offline.hint",
        severity="critical",
    ),
    # Authentication errors
    "missing_api_key": ErrorMapping(
        reason_code="missing_api_key",
        user_message_key="errors.provider.missing_api_key.user",
        admin_message_key="errors.provider.missing_api_key.admin",
        runbook_path=RUNBOOK_AUTH_FAILURES,
        recovery_hint_key="errors.provider.missing_api_key.hint",
        severity="warning",
    ),
    "AUTH_ERROR": ErrorMapping(
        reason_code="AUTH_ERROR",
        user_message_key="errors.provider.auth_error.user",
        admin_message_key="errors.provider.auth_error.admin",
        runbook_path=RUNBOOK_AUTH_FAILURES,
        recovery_hint_key="errors.provider.auth_error.hint",
        severity="critical",
    ),
    "invalid_credentials": ErrorMapping(
        reason_code="invalid_credentials",
        user_message_key="errors.provider.invalid_credentials.user",
        admin_message_key="errors.provider.invalid_credentials.admin",
        runbook_path=RUNBOOK_AUTH_FAILURES,
        recovery_hint_key="errors.provider.invalid_credentials.hint",
        severity="critical",
    ),
    # Endpoint errors
    "no_endpoint": ErrorMapping(
        reason_code="no_endpoint",
        user_message_key="errors.provider.no_endpoint.user",
        admin_message_key="errors.provider.no_endpoint.admin",
        runbook_path=RUNBOOK_PROVIDER_OFFLINE,
        recovery_hint_key="errors.provider.no_endpoint.hint",
        severity="warning",
    ),
    "http_error": ErrorMapping(
        reason_code="http_error",
        user_message_key="errors.provider.http_error.user",
        admin_message_key="errors.provider.http_error.admin",
        runbook_path=RUNBOOK_PROVIDER_OFFLINE,
        recovery_hint_key="errors.provider.http_error.hint",
        severity="warning",
    ),
    # Performance errors
    "TIMEOUT": ErrorMapping(
        reason_code="TIMEOUT",
        user_message_key="errors.provider.timeout.user",
        admin_message_key="errors.provider.timeout.admin",
        runbook_path=RUNBOOK_LATENCY_SPIKE,
        recovery_hint_key="errors.provider.timeout.hint",
        severity="warning",
    ),
    "PROVIDER_DEGRADED": ErrorMapping(
        reason_code="PROVIDER_DEGRADED",
        user_message_key="errors.provider.degraded.user",
        admin_message_key="errors.provider.degraded.admin",
        runbook_path=RUNBOOK_LATENCY_SPIKE,
        recovery_hint_key="errors.provider.degraded.hint",
        severity="warning",
    ),
    # Budget and rate limit errors
    "BUDGET_EXCEEDED": ErrorMapping(
        reason_code="BUDGET_EXCEEDED",
        user_message_key="errors.provider.budget_exceeded.user",
        admin_message_key="errors.provider.budget_exceeded.admin",
        runbook_path="/docs/runbooks/budget-exhaustion.md",
        recovery_hint_key="errors.provider.budget_exceeded.hint",
        severity="critical",
    ),
    "RATE_LIMIT_EXCEEDED": ErrorMapping(
        reason_code="RATE_LIMIT_EXCEEDED",
        user_message_key="errors.provider.rate_limit.user",
        admin_message_key="errors.provider.rate_limit.admin",
        runbook_path=RUNBOOK_LATENCY_SPIKE,
        recovery_hint_key="errors.provider.rate_limit.hint",
        severity="warning",
    ),
    # Unknown errors
    "unsupported_provider": ErrorMapping(
        reason_code="unsupported_provider",
        user_message_key="errors.provider.unsupported.user",
        admin_message_key="errors.provider.unsupported.admin",
        runbook_path=None,
        recovery_hint_key="errors.provider.unsupported.hint",
        severity="info",
    ),
}


def get_error_mapping(reason_code: str) -> Optional[ErrorMapping]:
    """
    Get error mapping for a given reason code.

    Args:
        reason_code: The reason code from provider status

    Returns:
        ErrorMapping if found, None otherwise
    """
    return PROVIDER_ERROR_MAPPINGS.get(reason_code)


def get_user_message_key(reason_code: str) -> str:
    """Get i18n key for user message."""
    mapping = get_error_mapping(reason_code)
    return mapping.user_message_key if mapping else "errors.provider.unknown.user"


def get_admin_message_key(reason_code: str) -> str:
    """Get i18n key for admin message."""
    mapping = get_error_mapping(reason_code)
    return mapping.admin_message_key if mapping else "errors.provider.unknown.admin"


def get_runbook_path(reason_code: str) -> Optional[str]:
    """Get runbook path for a reason code."""
    mapping = get_error_mapping(reason_code)
    return mapping.runbook_path if mapping else None


def get_recovery_hint_key(reason_code: str) -> Optional[str]:
    """Get i18n key for recovery hint."""
    mapping = get_error_mapping(reason_code)
    return mapping.recovery_hint_key if mapping else None


def get_severity(reason_code: str) -> str:
    """Get severity level for a reason code."""
    mapping = get_error_mapping(reason_code)
    return mapping.severity if mapping else "info"
