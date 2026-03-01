"""Route-facing adapters for tasks endpoints (core type aggregation)."""

from __future__ import annotations

from typing import Any

from venom_core.core import metrics as metrics_module
from venom_core.core.models import TaskStatus, VenomTask
from venom_core.core.orchestrator import Orchestrator
from venom_core.core.state_manager import StateManager
from venom_core.core.tracer import RequestTracer, TraceStatus


def get_metrics_collector() -> Any:
    return metrics_module.metrics_collector


def trace_status_values() -> list[str]:
    return [status.value for status in TraceStatus]


__all__ = [
    "TaskStatus",
    "VenomTask",
    "Orchestrator",
    "StateManager",
    "RequestTracer",
    "TraceStatus",
    "get_metrics_collector",
    "trace_status_values",
]
