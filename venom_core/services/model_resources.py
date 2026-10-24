"""Process-wide inventory and drain barrier for local in-process model owners."""

from __future__ import annotations

import gc
import inspect
import threading
import time
import weakref
from contextlib import contextmanager
from functools import wraps
from typing import Any

from fastapi import HTTPException

_CONDITION = threading.Condition(threading.RLock())
_LOCAL = threading.local()
_OWNERS: weakref.WeakKeyDictionary[Any, tuple[str, str]] = weakref.WeakKeyDictionary()
_RELEASING = False
_ACTIVE = 0


def register_model_resource(owner: Any, category: str, release_method: str) -> None:
    """Register a weak owner reference, not another copy of its model."""
    with _CONDITION:
        _OWNERS[owner] = (category, release_method)


@contextmanager
def _model_work():
    global _ACTIVE
    with _CONDITION:
        depth = getattr(_LOCAL, "depth", 0)
        if _RELEASING and not depth:
            raise HTTPException(
                status_code=409, detail={"code": "model_resources_releasing"}
            )
        _LOCAL.depth = depth + 1
        _ACTIVE += 1
    try:
        yield
    finally:
        with _CONDITION:
            _ACTIVE -= 1
            _LOCAL.depth -= 1
            _CONDITION.notify_all()


def model_operation(function):
    """Track actual synchronous model work, including cancelled callers' threads."""
    if inspect.iscoroutinefunction(function):
        # Async tasks share threads: do not treat another task as nested work.
        @wraps(function)
        async def asynchronous(*args, **kwargs):
            global _ACTIVE
            with _CONDITION:
                if _RELEASING:
                    raise HTTPException(
                        status_code=409, detail={"code": "model_resources_releasing"}
                    )
                _ACTIVE += 1
            try:
                return await function(*args, **kwargs)
            finally:
                with _CONDITION:
                    _ACTIVE -= 1
                    _CONDITION.notify_all()

        return asynchronous

    @wraps(function)
    def invoke(*args, **kwargs):
        with _model_work():
            return function(*args, **kwargs)

    return invoke


@contextmanager
def release_barrier():
    global _RELEASING
    with _CONDITION:
        if _RELEASING:
            raise HTTPException(
                status_code=409, detail={"code": "model_resources_releasing"}
            )
        _RELEASING = True
    try:
        yield
    finally:
        with _CONDITION:
            _RELEASING = False
            _CONDITION.notify_all()


def wait_for_model_work(timeout: float = 30) -> None:
    deadline = time.monotonic() + timeout
    with _CONDITION:
        while _ACTIVE:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise HTTPException(
                    status_code=409, detail={"code": "model_resources_work_not_drained"}
                )
            _CONDITION.wait(remaining)


def resource_snapshot() -> list[dict[str, Any]]:
    with _CONDITION:
        owners = tuple(_OWNERS.items())
    return [
        {"category": category, "owner": type(owner).__name__}
        for owner, (category, _) in owners
    ]


def release_registered_models() -> list[dict[str, Any]]:
    with _CONDITION:
        if not _RELEASING or _ACTIVE:
            raise RuntimeError("model_resources_not_exclusive")
        owners = list(_OWNERS.items())
    results = []
    for owner, (category, method) in owners:
        try:
            verified = getattr(owner, method)() is True
        except Exception:
            verified = False
        results.append(
            {"category": category, "owner": type(owner).__name__, "verified": verified}
        )
    gc.collect()
    # Do not initialize CUDA merely to release CPU-only resources.
    import sys

    torch = sys.modules.get("torch")
    if torch is not None and torch.cuda.is_initialized():
        torch.cuda.synchronize()
        torch.cuda.empty_cache()
    return results


async def prepare_registered_models() -> list[dict[str, Any]]:
    with _CONDITION:
        owners = list(_OWNERS.items())
    failures = []
    for owner, (category, _) in owners:
        prepare = getattr(owner, "prepare_model_release", None)
        if prepare is not None:
            try:
                await prepare()
            except Exception:
                failures.append(
                    {
                        "category": category,
                        "owner": type(owner).__name__,
                        "verified": False,
                    }
                )
    return failures
