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
    retrieval_context_items: int = 0
    retrieval_route: str | None = None
    assistant_used: bool = False
    economy_mode_activated: bool = False
    degradation_reasons: list[str] = field(default_factory=list)
    component_snapshot: list[dict[str, object]] = field(default_factory=list)
    component_snapshot_timestamp_ms: int | None = None
    component_snapshot_version: str | None = None

    def push_trace(
        self, stage_name: str, started_at: float, outcome: str = "ok"
    ) -> None:
        duration_ms = int((perf_counter() - started_at) * 1000)
        self.execution_trace.append(
            StageTrace(name=stage_name, duration_ms=duration_ms, outcome=outcome)
        )

    def trace_names(self) -> list[str]:
        return [item.name for item in self.execution_trace]

    def add_degradation(self, reason: str) -> None:
        normalized = str(reason or "").strip()
        if normalized and normalized not in self.degradation_reasons:
            self.degradation_reasons.append(normalized)
