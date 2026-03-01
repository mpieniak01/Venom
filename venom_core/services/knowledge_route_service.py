"""Route-facing helpers for knowledge endpoints (contracts + mutation guard)."""

from __future__ import annotations

from venom_core.core.environment_policy import ensure_data_mutation_allowed
from venom_core.core.knowledge_contract import KnowledgeContextMapV1

__all__ = [
    "KnowledgeContextMapV1",
    "ensure_data_mutation_allowed",
]
