"""Canonical HTTP detail mapping for permission/autonomy denials."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from venom_core.core.autonomy_enforcement import AutonomyPermissionDenied
from venom_core.services.audit_stream import get_audit_stream
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


def build_permission_denied_detail(
    exc: PermissionError,
    *,
    operation: str | None = None,
) -> dict[str, Any]:
    """Build canonical deny detail payload for HTTP 403 responses."""
    if isinstance(exc, AutonomyPermissionDenied):
        return {
            "decision": exc.decision,
            "reason_code": exc.reason_code,
            "user_message": exc.user_message,
            "technical_context": dict(exc.technical_context),
            "tags": list(exc.tags),
        }

    technical_context: dict[str, Any] = {}
    if operation:
        technical_context["operation"] = operation

    return {
        "decision": "block",
        "reason_code": "PERMISSION_DENIED",
        "user_message": str(exc),
        "technical_context": technical_context,
        "tags": ["permission", "blocked"],
    }


def raise_permission_denied_http(
    exc: PermissionError,
    *,
    operation: str | None = None,
) -> None:
    """Raise HTTP 403 with canonical deny payload."""
    detail = build_permission_denied_detail(exc, operation=operation)
    reason_code = str(detail.get("reason_code") or "PERMISSION_DENIED")
    action = (
        "autonomy.blocked"
        if reason_code.startswith("AUTONOMY_")
        else "policy.blocked.route"
    )
    try:
        get_audit_stream().publish(
            source="api.permission",
            action=action,
            actor="unknown",
            status="blocked",
            details=detail,
        )
    except Exception as audit_exc:  # pragma: no cover - defensive path
        logger.warning("Nie udało się opublikować audytu deny: %s", audit_exc)
    raise HTTPException(
        status_code=403,
        detail=detail,
    ) from exc
