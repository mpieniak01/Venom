"""Defer optional maintenance while interactive host work owns resources."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from contextlib import suppress
from typing import Any

from venom_core.services.runtime_admission import get_runtime_admission


async def run_drainable_thread[T](
    function: Callable[..., T], *args: Any, **kwargs: Any
) -> T:
    """Finish the real worker before propagating caller cancellation.

    Cancelling to_thread only abandons its result; it does not stop the OS thread.
    Keep shielding through repeated cancellation so stop/restart cannot overlap
    an old filesystem worker with a new service instance.
    """
    worker = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
    try:
        return await asyncio.shield(worker)
    except asyncio.CancelledError:
        while not worker.done():
            # Only suppress additional cancellation while draining real I/O.
            # The original cancellation is re-raised after the worker retires.
            with suppress(asyncio.CancelledError):
                try:
                    await asyncio.shield(worker)
                except Exception:
                    break
        if not worker.cancelled():
            worker.exception()
        raise


async def wait_for_interactive_idle(orchestrator: Any = None) -> None:
    """Yield until queued host work and the shared runtime are idle.

    This is a scheduling hint, not an admission lease. Actual model work still
    rechecks admission atomically. Health checks and retention never use it.
    """
    while True:
        tasks = getattr(orchestrator, "active_tasks", None)
        if isinstance(tasks, Mapping) and tasks:
            await asyncio.sleep(1)
            continue
        # Reading a locked SQLite ledger may wait; never do that on the API loop.
        runtime = await run_drainable_thread(get_runtime_admission().snapshot)
        if runtime["status"] in {"available", "disabled"}:
            return
        await asyncio.sleep(1)
