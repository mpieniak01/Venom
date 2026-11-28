"""A Studio calculation verified by the shared calculator before rendering."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from venom_core.services.chat_policy.direct_calculator import (
    CalculatorRequest,
    execute_calculator,
)


@dataclass(frozen=True)
class StudioCalculation:
    expression: str
    unit: str | None
    render: Callable[[str], str]

    def publish(self) -> dict[str, Any]:
        reply = execute_calculator(CalculatorRequest(self.expression, self.unit))
        if reply["tool_result"]["status"] == "succeeded":
            reply["text"] = self.render(reply["text"])
        return reply
