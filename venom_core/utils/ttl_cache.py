"""Prosty cache w pamięci z TTL (bez zależności zewnętrznych)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Generic, Optional, TypeVar

T = TypeVar("T")


@dataclass
class _CacheEntry(Generic[T]):
    value: T
    expires_at: float


class TTLCache(Generic[T]):
    """Lekki cache w pamięci z TTL (sekundy)."""

    def __init__(self, ttl_seconds: float) -> None:
        self.ttl_seconds = ttl_seconds
        self._entry: Optional[_CacheEntry[T]] = None

    def get(self) -> Optional[T]:
        entry = self._entry
        if entry is None:
            return None
        if entry.expires_at <= time.monotonic():
            self._entry = None
            return None
        return entry.value

    def set(self, value: T) -> None:
        self._entry = _CacheEntry(
            value=value,
            expires_at=time.monotonic() + self.ttl_seconds,
        )

    def clear(self) -> None:
        self._entry = None
