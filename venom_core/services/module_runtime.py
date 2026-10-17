"""Isolate optional-router lifecycle failures without swallowing core failures."""

import asyncio
import inspect
from contextlib import AsyncExitStack, asynccontextmanager
from copy import copy

from fastapi import APIRouter, Depends, HTTPException


async def _run_handlers(handlers):
    for handler in handlers:
        if inspect.iscoroutinefunction(handler):
            result = handler()
        else:
            result = await asyncio.to_thread(handler)
        if inspect.isawaitable(result):
            await result


async def _close_stack(stack, record, reason):
    try:
        await asyncio.wait_for(stack.aclose(), timeout=2.0)
    except Exception:
        record["state"], record["reason_code"] = "unavailable", reason


def include_isolated_router(app, router, record):
    # Include a host-owned copy. FastAPI would otherwise copy legacy event handlers
    # into the host lifespan, outside this module's exception/timeout boundary.
    isolated = copy(router)
    startup_handlers = tuple(router.on_startup)
    shutdown_handlers = tuple(router.on_shutdown)
    isolated.on_startup, isolated.on_shutdown = [], []
    original = router.lifespan_context
    # FastAPI's default context is bound to its router. Reuse the default of an
    # event-free router so these handlers are executed exactly once below. Custom
    # contexts remain unchanged; the shared module router is never mutated.
    if getattr(original, "_router", None) is router:
        original = APIRouter().lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        stack = AsyncExitStack()
        try:
            state = await asyncio.wait_for(
                stack.enter_async_context(original(application)), timeout=2.0
            )
            await asyncio.wait_for(_run_handlers(startup_handlers), timeout=2.0)
        except asyncio.CancelledError:
            await _close_stack(stack, record, "module_initialization_failed")
            raise
        except Exception:
            record["state"], record["reason_code"] = (
                "unavailable",
                "module_initialization_failed",
            )
            await _close_stack(stack, record, "module_initialization_failed")
            yield None
            return
        try:
            yield state
        finally:
            try:
                await asyncio.wait_for(_run_handlers(shutdown_handlers), timeout=2.0)
            except Exception:
                record["state"], record["reason_code"] = (
                    "unavailable",
                    "module_cleanup_failed",
                )
            finally:
                await _close_stack(stack, record, "module_cleanup_failed")

    def require_available():
        if record["state"] != "loaded":
            raise HTTPException(
                status_code=503, detail={"reason_code": "optional_module_unavailable"}
            )

    isolated.lifespan_context = lifespan
    app.include_router(isolated, dependencies=[Depends(require_available)])
