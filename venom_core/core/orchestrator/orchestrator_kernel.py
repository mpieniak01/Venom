"""Helpers for kernel lifecycle operations in Orchestrator."""

from __future__ import annotations

from typing import Any

from venom_core.config import SETTINGS

from .constants import MAX_CONTEXT_CHARS


def get_runtime_context_char_limit(runtime_info: Any) -> int:
    """Wyznacza przybliżony limit znaków dla promptu na podstawie runtime."""
    if runtime_info.provider != "vllm":
        return MAX_CONTEXT_CHARS
    max_ctx_raw = getattr(SETTINGS, "VLLM_MAX_MODEL_LEN", None)
    max_ctx = int(max_ctx_raw) if isinstance(max_ctx_raw, int) else 0
    if max_ctx <= 0:
        return MAX_CONTEXT_CHARS
    reserve = max(64, max_ctx // 4)
    input_tokens = max(32, max_ctx - reserve)
    return min(MAX_CONTEXT_CHARS, input_tokens * 4)


def refresh_kernel(kernel_manager, flow_coordinator, runtime_info: Any = None):
    """Odtwarza kernel i agentów po zmianie konfiguracji LLM."""
    task_dispatcher = kernel_manager.refresh_kernel(runtime_info)
    flow_coordinator.task_dispatcher = task_dispatcher
    flow_coordinator.reset_flows()
    return task_dispatcher


def refresh_kernel_if_needed(kernel_manager, flow_coordinator):
    """Sprawdza drift konfiguracji i odświeża kernel przy zmianie."""
    if kernel_manager.refresh_kernel_if_needed():
        task_dispatcher = kernel_manager.task_dispatcher
        flow_coordinator.task_dispatcher = task_dispatcher
        flow_coordinator.reset_flows()
        return task_dispatcher
    return None
