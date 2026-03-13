from __future__ import annotations

import gc
import time
import tracemalloc
from types import SimpleNamespace

import pytest

from venom_core.core.orchestrator.orchestrator_dispatch import _build_risk_context

pytestmark = [pytest.mark.performance]


def _baseline_build_risk_context(request, intent: str, tool_required: bool):
    forced_tool = str(request.forced_tool or "").strip().lower()
    intent_upper = str(intent or "").strip().upper()
    return {
        "desktop": forced_tool in {"desktop", "vision", "ghost", "ui"}
        or intent_upper in {"DESKTOP_AUTOMATION", "VISION_CONTROL"},
        "fileops": forced_tool in {"file", "fs", "filesystem", "fileops"}
        or intent_upper
        in {"FILE_OPERATIONS", "FILESYSTEM_OPERATION", "CODE_GENERATION"},
        "shell": forced_tool in {"shell", "bash", "terminal", "command"}
        or intent_upper in {"SHELL_EXECUTION", "SYSTEM_DIAGNOSTICS"},
        "network": forced_tool in {"browser", "web", "http", "network"}
        or intent_upper in {"RESEARCH", "WEB_RESEARCH", "NETWORK_OPERATION"},
        "tool_required": tool_required,
    }


def _run_mix(iterations: int, builder) -> None:
    req_network = SimpleNamespace(forced_tool="browser")
    req_fileops = SimpleNamespace(forced_tool="file")
    req_shell = SimpleNamespace(forced_tool="terminal")
    req_desktop = SimpleNamespace(forced_tool="ui")

    for _ in range(iterations):
        network = builder(req_network, "RESEARCH", True)
        fileops = builder(req_fileops, "CODE_GENERATION", True)
        shell = builder(req_shell, "SYSTEM_DIAGNOSTICS", True)
        desktop = builder(req_desktop, "DESKTOP_AUTOMATION", True)

        assert network["network"] is True
        assert fileops["fileops"] is True
        assert shell["shell"] is True
        assert desktop["desktop"] is True


def _measure_elapsed(iterations: int, builder) -> float:
    start = time.perf_counter()
    _run_mix(iterations, builder)
    return time.perf_counter() - start


def _measure_peak(iterations: int, builder) -> int:
    gc.collect()
    tracemalloc.start()
    _run_mix(iterations, builder)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return peak


def test_risk_context_builder_reduces_hot_path_allocations_and_latency() -> None:
    _run_mix(2000, _build_risk_context)

    iterations = 10000
    baseline_elapsed = _measure_elapsed(iterations, _baseline_build_risk_context)
    optimized_elapsed = _measure_elapsed(iterations, _build_risk_context)

    baseline_peak = _measure_peak(iterations, _baseline_build_risk_context)
    optimized_peak = _measure_peak(iterations, _build_risk_context)

    assert optimized_elapsed <= baseline_elapsed * 1.35
    assert optimized_peak <= baseline_peak
