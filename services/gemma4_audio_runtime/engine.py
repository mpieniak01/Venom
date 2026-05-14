"""Compatibility shim — implementation moved to services.multi_runtime.engine.

All symbols re-exported under their legacy names for backward compat during
the 217B transition. Will be removed in Phase 7 (Faza 7 cleanup).
"""

from __future__ import annotations

from services.multi_runtime.engine import DaemonParams, InferenceError, ModelLoadError
from services.multi_runtime.engine import MultiRuntimeDaemon as Gemma4Daemon
from services.multi_runtime.engine import MultiRuntimeEngine as Gemma4AudioEngine
from services.multi_runtime.engine import (
    ReloadSignal,
    RuntimeMode,
    VRAMInfo,
    _free_vram,
    _get_vram_info,
)

__all__ = [
    "DaemonParams",
    "Gemma4AudioEngine",
    "Gemma4Daemon",
    "InferenceError",
    "ModelLoadError",
    "ReloadSignal",
    "RuntimeMode",
    "VRAMInfo",
    "_free_vram",
    "_get_vram_info",
]
