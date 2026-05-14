"""Base pipeline stage contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..diagnostics import ExecutionDiagnostics


@dataclass(slots=True)
class StageContext:
    request_payload: Any
    daemon_status: dict[str, Any]
    text_content: str | None
    audio_array: Any
    sample_rate: int
    images: list[Any]
    diagnostics: ExecutionDiagnostics
    state: dict[str, Any] = field(default_factory=dict)
