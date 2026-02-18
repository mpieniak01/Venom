"""Compatibility wrapper for moved Module Example provider."""

from venom_module_example.services import provider as _provider_module
from venom_module_example.services.provider import (
    ModuleExampleProvider,
    StubModuleExampleProvider,
    get_module_example_provider,
    reset_module_example_provider_cache,
)

# Compatibility surface for tests monkeypatching loader internals.
importlib = _provider_module.importlib

__all__ = [
    "ModuleExampleProvider",
    "StubModuleExampleProvider",
    "get_module_example_provider",
    "importlib",
    "reset_module_example_provider_cache",
]
