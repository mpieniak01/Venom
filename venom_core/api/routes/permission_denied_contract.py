"""Canonical HTTP detail mapping for permission/autonomy denials."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import HTTPException
from starlette.requests import Request

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


def _resolve_audit_actor(actor: str | None) -> str:
    value = str(actor or "").strip()
    if value:
        return value
    return "api.route"


def resolve_actor_from_request(request: Request | None) -> str:
    """Resolve audit actor from request metadata (user headers first, then client host)."""
    if request is None:
        return "api.route"
    try:
        headers = getattr(request, "headers", None)
        for header in ("x-authenticated-user", "x-user"):
            raw_value: Any = None
            if isinstance(headers, Mapping):
                raw_value = headers.get(header)
            elif hasattr(headers, "get"):
                raw_value = headers.get(header)
            header_value = raw_value.strip() if isinstance(raw_value, str) else ""
            if header_value:
                return header_value
    except Exception:
        # Defensive fallback for non-standard request test doubles.
        pass

    client_host = str(getattr(getattr(request, "client", None), "host", "")).strip()
    if client_host:
        return f"client:{client_host}"
    return "api.route"


def publish_permission_denied_audit(
    detail: dict[str, Any],
    *,
    actor: str | None = None,
) -> None:
    """Publish canonical deny audit event for API route-level guard blocks."""
    reason_code = str(detail.get("reason_code") or "PERMISSION_DENIED")
    technical_context = detail.get("technical_context") or {}
    operation = str(technical_context.get("operation") or "permission.denied")
    action = (
        "autonomy.blocked"
        if reason_code.startswith("AUTONOMY_")
        else "policy.blocked.route"
    )
    get_audit_stream().publish(
        source="api.permission",
        action=action,
        actor=_resolve_audit_actor(actor),
        status="blocked",
        context=operation,
        details=detail,
    )


def raise_permission_denied_http(
    exc: PermissionError,
    *,
    operation: str | None = None,
    actor: str | None = None,
) -> None:
    """Raise HTTP 403 with canonical deny payload."""
    detail = build_permission_denied_detail(exc, operation=operation)
    try:
        publish_permission_denied_audit(detail, actor=actor)
    except Exception as audit_exc:  # pragma: no cover - defensive path
        logger.warning("Nie udało się opublikować audytu deny: %s", audit_exc)
    raise HTTPException(
        status_code=403,
        detail=detail,
    ) from exc
