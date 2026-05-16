"""
Venom core package initialization.

Includes a small compatibility shim for Pydantic so that libraries expecting
`pydantic.networks.Url` (e.g., older Semantic Kernel imports) work with
Pydantic 2.12+ where `Url` is no longer exported from that module.
"""

import importlib
import warnings

# Compat: ensure pydantic.networks.Url exists for dependencies expecting it.
try:
    networks = importlib.import_module("pydantic.networks")
    if not hasattr(networks, "Url"):
        from pydantic import AnyUrl

        networks.Url = AnyUrl  # type: ignore[attr-defined]
except (ModuleNotFoundError, AttributeError) as exc:
    # Best-effort compatibility; avoid breaking import chain.
    warnings.warn(
        f"pydantic Url compatibility patch skipped: {exc}",
        RuntimeWarning,
        stacklevel=2,
    )

# Compat: Semantic Kernel 1.39.x still imports `openai._types.omit`, but the
# symbol was removed from newer OpenAI SDK releases. Re-create it lazily so
# imports continue to work without pinning the whole stack back.
try:
    openai_types = importlib.import_module("openai._types")
    if not hasattr(openai_types, "omit") and hasattr(openai_types, "Omit"):
        openai_types.omit = openai_types.Omit()  # type: ignore[attr-defined]
except (ModuleNotFoundError, AttributeError) as exc:
    # Best-effort compatibility; avoid breaking import chain.
    warnings.warn(
        f"openai omit compatibility patch skipped: {exc}",
        RuntimeWarning,
        stacklevel=2,
    )
