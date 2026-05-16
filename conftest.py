"""Repo-wide pytest bootstrap compatibility shims."""

from __future__ import annotations

import importlib
import warnings


def _patch_pydantic_url() -> None:
    """Restore `pydantic.networks.Url` for dependencies expecting the legacy export."""
    try:
        networks = importlib.import_module("pydantic.networks")
        if not hasattr(networks, "Url"):
            from pydantic import AnyUrl

            networks.Url = AnyUrl  # type: ignore[attr-defined]
    except (ImportError, AttributeError) as exc:
        # Best-effort compatibility; never block test collection.
        warnings.warn(
            f"pydantic Url compatibility patch failed: {exc}",
            RuntimeWarning,
            stacklevel=2,
        )


def _patch_openai_omit() -> None:
    """Restore `openai._types.omit` for Semantic Kernel imports during test collection."""
    try:
        openai_types = importlib.import_module("openai._types")
        if not hasattr(openai_types, "omit") and hasattr(openai_types, "Omit"):
            openai_types.omit = openai_types.Omit()  # type: ignore[attr-defined]
    except (ImportError, AttributeError) as exc:
        # Best-effort compatibility; never block test collection.
        warnings.warn(
            f"openai omit compatibility patch failed: {exc}",
            RuntimeWarning,
            stacklevel=2,
        )


_patch_pydantic_url()
_patch_openai_omit()
