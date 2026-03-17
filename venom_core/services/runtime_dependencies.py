"""Runtime-scoped shared dependencies for services layer.

This module is intentionally service-layer only so other services can access
runtime objects (e.g. request tracer) without importing API route modules.
"""

from __future__ import annotations

from typing import Any

_request_tracer: Any = None


def set_request_tracer(request_tracer: Any) -> None:
    """Register request tracer instance for service-layer consumers."""
    global _request_tracer
    _request_tracer = request_tracer


def get_request_tracer() -> Any:
    """Return registered request tracer instance or None."""
    return _request_tracer
