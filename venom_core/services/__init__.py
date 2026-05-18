"""Moduł: services - logika biznesowa i serwisy."""

from __future__ import annotations

from typing import Any

__all__ = ["MemoryConsolidator"]


def __getattr__(name: str) -> Any:
    if name == "MemoryConsolidator":
        from venom_core.services.memory_service import MemoryConsolidator

        return MemoryConsolidator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# BenchmarkService dostępny przez import bezpośredni:
# from venom_core.services.benchmark import BenchmarkService
