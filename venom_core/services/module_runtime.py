"""Isolate optional-router lifecycle failures without swallowing core failures."""

import asyncio
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import Depends, HTTPException


def include_isolated_router(app, router, record):
    original = router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        stack = AsyncExitStack()
        try:
            state = await asyncio.wait_for(
                stack.enter_async_context(original(application)), timeout=2.0
            )
        except Exception:
            record["state"], record["reason_code"] = (
                "unavailable",
                "module_initialization_failed",
            )
            yield None
            return
        try:
            yield state
        finally:
            try:
                await asyncio.wait_for(stack.aclose(), timeout=2.0)
            except Exception:
                record["state"], record["reason_code"] = (
                    "unavailable",
                    "module_cleanup_failed",
                )

    async def require_available():
        if record["state"] != "loaded":
            raise HTTPException(
                status_code=503, detail={"reason_code": "optional_module_unavailable"}
            )

    # FastAPI captures this context at inclusion. Do not mutate a shared module
    # router permanently: the same package can be included by another host app.
    router.lifespan_context = lifespan
    try:
        app.include_router(router, dependencies=[Depends(require_available)])
    finally:
        router.lifespan_context = original
