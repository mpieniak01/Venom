"""Canonical HTTP detail mapping for permission/autonomy denials."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from venom_core.core.autonomy_enforcement import AutonomyPermissionDenied


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
    raise HTTPException(
        status_code=403,
        detail=build_permission_denied_detail(exc, operation=operation),
    ) from exc
