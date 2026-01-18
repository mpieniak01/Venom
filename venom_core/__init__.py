"""
Venom core package initialization.

Includes a small compatibility shim for Pydantic so that libraries expecting
`pydantic.networks.Url` (e.g., older Semantic Kernel imports) work with
Pydantic 2.12+ where `Url` is no longer exported from that module.
"""

import importlib

# Compat: ensure pydantic.networks.Url exists for dependencies expecting it.
try:
    networks = importlib.import_module("pydantic.networks")
    if not hasattr(networks, "Url"):
        from pydantic import AnyUrl

        networks.Url = AnyUrl  # type: ignore[attr-defined]
except Exception:
    # Best-effort compatibility; avoid breaking import chain.
    pass
