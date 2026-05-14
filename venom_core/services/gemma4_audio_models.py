"""Compatibility shim — implementation moved to multi_runtime_models.

Legacy function names re-exported for backward compatibility during 217B transition.
Will be removed in Phase 7 (Faza 7 cleanup).
"""

from __future__ import annotations

from venom_core.services.multi_runtime_models import (
    multi_runtime_available_models as gemma4_audio_available_models,
)
from venom_core.services.multi_runtime_models import (
    multi_runtime_model_has_snapshot as gemma4_audio_model_has_snapshot,
)

__all__ = [
    "gemma4_audio_available_models",
    "gemma4_audio_model_has_snapshot",
]
