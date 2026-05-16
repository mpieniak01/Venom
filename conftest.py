"""Repo-wide pytest bootstrap compatibility shims."""

from __future__ import annotations

import importlib


def _patch_pydantic_url() -> None:
    """Restore `pydantic.networks.Url` for dependencies expecting the legacy export."""
    try:
        networks = importlib.import_module("pydantic.networks")
        if not hasattr(networks, "Url"):
            from pydantic import AnyUrl

            networks.Url = AnyUrl  # type: ignore[attr-defined]
    except Exception:
        # Best-effort compatibility; never block test collection.
        pass


def _patch_openai_omit() -> None:
    """Restore `openai._types.omit` for Semantic Kernel imports during test collection."""
    try:
        openai_types = importlib.import_module("openai._types")
        if not hasattr(openai_types, "omit") and hasattr(openai_types, "Omit"):
            openai_types.omit = openai_types.Omit()  # type: ignore[attr-defined]
    except Exception:
        # Best-effort compatibility; never block test collection.
        pass


_patch_pydantic_url()
_patch_openai_omit()
