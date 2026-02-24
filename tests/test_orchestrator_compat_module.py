"""Coverage tests for backward-compatible orchestrator module re-export."""

import importlib
import runpy
from pathlib import Path


def test_orchestrator_module_reexports_package_symbols():
    module = importlib.import_module("venom_core.core.orchestrator")

    assert "Orchestrator" in module.__all__
    assert "MAX_CONTEXT_CHARS" in module.__all__
    assert module.Orchestrator is not None


def test_orchestrator_compat_file_executes_reexports():
    orchestrator_py = Path("venom_core/core/orchestrator.py")
    globals_after_exec = runpy.run_path(str(orchestrator_py))
    assert "Orchestrator" in globals_after_exec["__all__"]
