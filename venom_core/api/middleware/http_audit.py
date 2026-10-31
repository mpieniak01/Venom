"""Shared HTTP audit mirror, independent of either application bootstrap."""

from fastapi import Request

from venom_core.core.permission_guard import permission_guard
from venom_core.services.audit_stream import get_audit_stream
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

_AUDIT_CHANNEL_BY_PATH_PREFIX: tuple[tuple[str, str], ...] = (
    ("/api/v1/system/status", "System Status API"),
    ("/api/v1/system/services", "System Services API"),
    ("/api/v1/system/runtime", "System Runtime API"),
    ("/api/v1/system/storage", "System Storage API"),
    ("/api/v1/system/iot", "System IoT API"),
    ("/api/v1/tasks", "Tasks API"),
    ("/api/v1/queue", "Queue API"),
    ("/api/v1/agents", "Agents API"),
    ("/api/roadmap", "Strategy API"),
    ("/api/v1/governance", "Governance API"),
    ("/api/v1/providers", "Governance API"),
    ("/api/v1/memory", "Memory API"),
    ("/api/v1/nodes", "Nodes API"),
    ("/api/v1/feedback", "Feedback API"),
    ("/api/v1/chat", "Frontend (Next.js)"),
    ("/api/v1/models", "Frontend (Next.js)"),
)


def _resolve_audit_channel_for_path(path: str) -> str:
    for prefix, channel in _AUDIT_CHANNEL_BY_PATH_PREFIX:
        if path.startswith(prefix):
            return channel
    return "System Services API"


def _resolve_audit_actor(request: Request) -> str:
    for header_name in ("X-Authenticated-User", "X-User", "X-Admin-User"):
        header_value = (request.headers.get(header_name) or "").strip()
        if header_value:
            return header_value
    if hasattr(request, "state") and hasattr(request.state, "user"):
        state_user = str(getattr(request.state, "user", "")).strip()
        if state_user:
            return state_user
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _resolve_audit_status(status_code: int) -> str:
    if status_code >= 500:
        return "failure"
    if status_code >= 400:
        return "warning"
    return "success"


def _resolve_audit_autonomy_snapshot() -> tuple[int, str]:
    try:
        return (
            permission_guard.get_current_level(),
            permission_guard.get_current_level_name(),
        )
    except Exception:
        return (-1, "UNKNOWN")


def _resolve_http_autonomy_policy(
    method: str, status_code: int
) -> tuple[str, bool | None]:
    read_only_methods = {"GET"}
    mutating_methods = {"POST", "PUT", "PATCH", "DELETE"}
    normalized_method = method.upper()

    if normalized_method in read_only_methods:
        return ("not_applicable_read_only", True)
    if normalized_method in mutating_methods and status_code in {401, 403}:
        return ("blocked", False)
    if normalized_method in mutating_methods and 200 <= status_code < 400:
        return ("allowed", True)
    return ("unknown", None)


async def audit_http_requests(
    request: Request, call_next, *, stream_factory=get_audit_stream
):
    response = await call_next(request)

    try:
        path = request.url.path or ""
        if not path.startswith("/api/"):
            return response
        if path.startswith("/api/v1/audit/stream"):
            return response
        if request.method.upper() in {"OPTIONS", "HEAD"}:
            return response

        api_channel = _resolve_audit_channel_for_path(path)
        method = request.method.upper()
        status = _resolve_audit_status(response.status_code)
        current_level, current_level_name = _resolve_audit_autonomy_snapshot()
        autonomy_policy_check, autonomy_policy_compliant = (
            _resolve_http_autonomy_policy(method, response.status_code)
        )
        stream_factory().publish(
            source="core.http",
            action=f"http.{method.lower()}",
            actor=_resolve_audit_actor(request),
            status=status,
            context=path,
            details={
                "api_channel": api_channel,
                "http_method": method,
                "http_path": path,
                "status_code": response.status_code,
                "current_autonomy_level": current_level,
                "current_autonomy_level_name": current_level_name,
                "autonomy_policy_check": autonomy_policy_check,
                "autonomy_policy_compliant": autonomy_policy_compliant,
            },
        )
    except Exception:
        logger.debug("HTTP audit mirror skipped due to runtime error", exc_info=True)

    return response
