"""Diagnostics primitives for multi_runtime pipeline execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter


@dataclass(slots=True)
class StageTrace:
    name: str
    duration_ms: int
    outcome: str


@dataclass(slots=True)
class ExecutionDiagnostics:
    execution_trace: list[StageTrace] = field(default_factory=list)
    selected_policy: str | None = None
    selected_image_strategy: str | None = None
    retrieval_used: bool = False
    assistant_used: bool = False
    economy_mode_activated: bool = False
    component_snapshot: list[dict[str, object]] = field(default_factory=list)

    def push_trace(
        self, stage_name: str, started_at: float, outcome: str = "ok"
    ) -> None:
        duration_ms = int((perf_counter() - started_at) * 1000)
        self.execution_trace.append(
            StageTrace(name=stage_name, duration_ms=duration_ms, outcome=outcome)
        )

    def trace_names(self) -> list[str]:
        return [item.name for item in self.execution_trace]
