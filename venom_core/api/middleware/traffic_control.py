"""Middleware dla kontroli ruchu API - inbound (web-next -> venom_core)."""

from __future__ import annotations

import json
import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.status import HTTP_429_TOO_MANY_REQUESTS

from venom_core.infrastructure.traffic_control import get_traffic_controller
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


# Mapowanie ścieżek na grupy endpointów
ENDPOINT_GROUP_MAPPING = {
    "/api/v1/chat": "chat",
    "/api/v1/memory": "memory",
    "/api/v1/workflow": "workflow",
    "/api/v1/agents": "agents",
    "/api/v1/knowledge": "knowledge",
    "/api/v1/models": "models",
    "/api/v1/system": "system",
    "/api/v1/governance": "governance",
}


def _get_endpoint_group(path: str) -> str:
    """
    Mapuje ścieżkę requestu na grupę endpointów.

    Args:
        path: Ścieżka HTTP requestu

    Returns:
        Nazwa grupy endpointów (np. 'chat', 'memory', 'workflow')
    """
    for prefix, group in ENDPOINT_GROUP_MAPPING.items():
        if path.startswith(prefix):
            return group
    return "default"


class TrafficControlMiddleware(BaseHTTPMiddleware):
    """
    Middleware dla kontroli ruchu inbound (web-next -> venom_core).

    Zapewnia:
    1. Rate limiting per endpoint group
    2. Burst protection
    3. Proper 429 responses z Retry-After headers
    4. Telemetria requestów
    """

    def __init__(self, app):
        """Inicjalizacja middleware."""
        super().__init__(app)
        self.traffic_controller = get_traffic_controller()

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        """
        Przetwarzanie requestu z traffic control.

        Args:
            request: FastAPI Request
            call_next: Next middleware/handler

        Returns:
            Response
        """
        # Skip traffic control dla endpointów statusowych i health checks
        if request.url.path in ["/health", "/api/v1/status", "/docs", "/openapi.json"]:
            return await call_next(request)

        # Określ grupę endpointów
        endpoint_group = _get_endpoint_group(request.url.path)

        # Check traffic control
        allowed, reason, wait_seconds = self.traffic_controller.check_inbound_request(
            endpoint_group
        )

        if not allowed:
            # Rate limit exceeded
            if self.traffic_controller.config.enable_logging:
                logger.warning(
                    f"Rate limit exceeded for {endpoint_group}: {request.url.path}"
                )

            # Prepare 429 response z Retry-After header
            retry_after = int(wait_seconds) if wait_seconds else 60
            content_dict = {
                "error": "rate_limit_exceeded",
                "message": f"Rate limit exceeded for {endpoint_group}. "
                f"Please retry after {retry_after} seconds.",
                "retry_after_seconds": retry_after,
            }
            return Response(
                content=json.dumps(content_dict),
                status_code=HTTP_429_TOO_MANY_REQUESTS,
                headers={"Retry-After": str(retry_after)},
                media_type="application/json",
            )

        # Process request
        start_time = time.time()
        response = await call_next(request)
        elapsed = time.time() - start_time

        # Log slow requests (>5s) only if logging enabled
        if elapsed > 5.0 and self.traffic_controller.config.enable_logging:
            logger.warning(
                f"Slow request: {request.method} {request.url.path} took {elapsed:.2f}s"
            )

        return response
