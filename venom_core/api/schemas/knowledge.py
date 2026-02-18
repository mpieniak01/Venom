"""Schemas for knowledge API endpoints."""

from venom_core.api.schemas.memory import LearningToggleRequest

# Re-export the canonical LearningToggleRequest model from the memory schemas
__all__ = ["LearningToggleRequest"]
