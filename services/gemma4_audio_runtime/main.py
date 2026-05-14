"""Compatibility shim — implementation moved to services.multi_runtime.main.

Import the FastAPI app and all public callables from the new package.
The old module path is kept alive only so that existing `pkill -f` patterns
and log references continue to work during the 217B transition.
Will be removed in Phase 7 (Faza 7 cleanup).
"""

from __future__ import annotations

from services.multi_runtime.main import (
    app,
    configure_logging,
    daemon_assistant_attach,
    daemon_assistant_detach,
    daemon_config,
    daemon_fallback,
    daemon_reload,
    daemon_restart,
    daemon_status,
    get_daemon,
    get_engine,
    health,
    initialize_daemon,
    list_models,
    respond,
    run_server,
    status,
    v1_health,
)

__all__ = [
    "app",
    "configure_logging",
    "daemon_assistant_attach",
    "daemon_assistant_detach",
    "daemon_config",
    "daemon_fallback",
    "daemon_reload",
    "daemon_restart",
    "daemon_status",
    "get_daemon",
    "get_engine",
    "health",
    "initialize_daemon",
    "list_models",
    "respond",
    "run_server",
    "status",
    "v1_health",
]
