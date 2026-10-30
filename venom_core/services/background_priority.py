"""Defer optional maintenance while interactive host work owns resources."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

from venom_core.services.runtime_admission import get_runtime_admission


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
        runtime = await asyncio.to_thread(get_runtime_admission().snapshot)
        if runtime["status"] in {"available", "disabled"}:
            return
        await asyncio.sleep(1)
