"""One owned telemetry refresh shared by callers, with a stale last-good sample."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Snapshot[T]:
    value: T
    age_seconds: float
    stale: bool
    refreshing: bool
    refresh_failed: bool


class AsyncSnapshotCache[T]:
    """Keep telemetry only; admission must use its own current resource checks.

    A caller timeout/cancellation never cancels a shared refresh or starts another
    physical collector. Failed refreshes do not replace the last good sample.
    """

    def __init__(self, ttl_seconds: float, timeout_seconds: float) -> None:
        self.ttl_seconds = ttl_seconds
        self.timeout_seconds = timeout_seconds
        self._value: T | None = None
        self._sampled_at = 0.0
        self._owner: object | None = None
        self._generation = 0
        self._refresh: asyncio.Task[T] | None = None
        self._pending: set[asyncio.Task[T]] = set()
        self._refresh_failed = False

    def get(self) -> T | None:
        if time.monotonic() - self._sampled_at >= self.ttl_seconds:
            return None
        return self._value

    def set(self, value: T | None) -> None:
        self.clear()
        self._value = value
        self._sampled_at = time.monotonic()

    def clear(self) -> None:
        # A pre-invalidation collector may finish, but must not republish its data.
        self._generation += 1
        self._value = None
        self._sampled_at = 0.0
        self._owner = None
        self._refresh = None
        self._refresh_failed = False

    def _snapshot(self, value: T) -> Snapshot[T]:
        age = max(0.0, time.monotonic() - self._sampled_at)
        return Snapshot(
            value=value,
            age_seconds=age,
            stale=age >= self.ttl_seconds,
            refreshing=self._refresh is not None and not self._refresh.done(),
            refresh_failed=self._refresh_failed,
        )

    def _retire(self, task: asyncio.Task[T]) -> None:
        self._pending.discard(task)
        # Stale readers may have returned without awaiting the refresh.
        if not task.cancelled():
            task.exception()

    async def _collect(self, collect: Callable[[], Awaitable[T]], generation: int) -> T:
        try:
            value = await collect()
        except Exception:
            if generation == self._generation:
                self._refresh_failed = True
            raise
        if generation == self._generation:
            self._value = value
            self._sampled_at = time.monotonic()
            self._refresh_failed = False
        return value

    async def get_or_refresh(
        self, collect: Callable[[], Awaitable[T]], *, owner: object
    ) -> Snapshot[T]:
        if self._owner is not None and self._owner is not owner:
            self.clear()
        self._owner = owner
        cached = self.get()
        if cached is not None:
            return self._snapshot(cached)

        if self._refresh is None or self._refresh.done():
            self._refresh = asyncio.create_task(
                self._collect(collect, self._generation)
            )
            self._pending.add(self._refresh)
            self._refresh.add_done_callback(self._retire)
        refresh = self._refresh
        generation = self._generation

        if self._value is not None:
            return self._snapshot(self._value)

        # Shielding is essential: one disconnected or timed-out HTTP request
        # must not cancel the work awaited by other requests.
        value = await asyncio.wait_for(
            asyncio.shield(refresh), timeout=self.timeout_seconds
        )
        if generation != self._generation:
            return Snapshot(value, 0.0, False, False, False)
        return self._snapshot(value)
