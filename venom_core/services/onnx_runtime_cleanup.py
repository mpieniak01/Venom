"""Best-effort ONNX runtime cleanup helpers used outside API layer."""

from __future__ import annotations

import sys
from typing import Any

from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


def _safe_call(module_name: str, function_name: str, **kwargs: Any) -> bool:
    try:
        # Cleanup must never initialize a route/service merely to free it.
        module = sys.modules.get(module_name)
        if module is None:
            return False
        func = getattr(module, function_name, None)
        if not callable(func):
            return False
        func(**kwargs)
        return True
    except Exception:
        logger.exception(
            "Failed to run ONNX cleanup hook: {}.{}",
            module_name,
            function_name,
        )
        return False


def release_onnx_runtime_best_effort(*, wait: bool = False) -> bool:
    """Release ONNX runtime resources across known entrypoints."""
    released = False
    if _safe_call(
        "venom_core.api.routes.tasks",
        "release_onnx_task_runtime",
        wait=wait,
    ):
        released = True
    if _safe_call(
        "venom_core.api.routes.llm_simple",
        "release_onnx_simple_client",
    ):
        released = True
    return released
