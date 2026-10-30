"""Regression tests for nonblocking model telemetry and refresh ownership."""

import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from venom_core.api.routes import models_usage
from venom_core.core.model_manager import ModelManager
from venom_core.utils import async_snapshot_cache as cache_module
from venom_core.utils.async_snapshot_cache import AsyncSnapshotCache


@pytest.mark.asyncio
async def test_slow_host_sample_keeps_http_loop_available(tmp_path, monkeypatch):
    manager = ModelManager(str(tmp_path))
    loop_thread = threading.get_ident()
    started = threading.Event()
    release = threading.Event()

    def collect():
        assert threading.get_ident() != loop_thread
        started.set()
        assert release.wait(3)
        return {"disk_usage_gb": 1.0}

    monkeypatch.setattr(manager, "_collect_host_usage_metrics", collect)
    monkeypatch.setattr(manager, "list_local_models", AsyncMock(return_value=[]))
    monkeypatch.setattr(manager, "_collect_gpu_metrics", AsyncMock(return_value={}))
    monkeypatch.setattr(models_usage, "get_model_manager", lambda: manager)
    monkeypatch.setattr(
        models_usage, "_models_usage_cache", AsyncSnapshotCache(5.0, 4.0)
    )
    app = FastAPI()
    app.include_router(models_usage.router)

    @app.get("/queue")
    async def queue():
        return {"available": True}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        usage = asyncio.create_task(client.get("/api/v1/models/usage"))
        try:
            assert await asyncio.to_thread(started.wait, 1)
            assert (await client.get("/queue")).json() == {"available": True}
            assert not usage.done()
        finally:
            release.set()
        response = await usage

    assert response.status_code == 200
    assert response.json()["usage"]["models_count"] == 0
    assert response.json()["telemetry"]["stale"] is False


@pytest.mark.asyncio
async def test_filesystem_discovery_does_not_run_on_event_loop(tmp_path, monkeypatch):
    manager = ModelManager(str(tmp_path))
    loop_thread = threading.get_ident()

    def discover():
        assert threading.get_ident() != loop_thread
        return {"local": {"name": "local", "runtime": "ollama"}}

    monkeypatch.setattr(manager, "_discover_local_models", discover)
    monkeypatch.setattr(manager, "_should_query_ollama_runtime", lambda: False)
    assert (await manager.list_local_models())[0]["name"] == "local"


@pytest.mark.asyncio
async def test_concurrent_requests_share_refresh_and_disconnect_does_not_cancel_it():
    cache = AsyncSnapshotCache[dict](5.0, 1.0)
    owner = object()
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def collect():
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return {"sample": 1}

    first = asyncio.create_task(cache.get_or_refresh(collect, owner=owner))
    await started.wait()
    others = [
        asyncio.create_task(cache.get_or_refresh(collect, owner=owner))
        for _ in range(5)
    ]
    await asyncio.sleep(0)
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    release.set()
    samples = await asyncio.gather(*others)
    assert calls == 1
    assert all(sample.value == {"sample": 1} for sample in samples)
    assert (await cache.get_or_refresh(collect, owner=owner)).stale is False
    assert calls == 1


@pytest.mark.asyncio
async def test_timeout_retains_one_inflight_collector_and_can_recover():
    cache = AsyncSnapshotCache[int](5.0, 0.001)
    owner = object()
    release = asyncio.Event()
    calls = 0

    async def collect():
        nonlocal calls
        calls += 1
        await release.wait()
        return 7

    for _ in range(3):
        with pytest.raises(TimeoutError):
            await cache.get_or_refresh(collect, owner=owner)
    assert calls == 1
    assert len(cache._pending) == 1
    release.set()
    await asyncio.gather(*cache._pending)
    assert (await cache.get_or_refresh(collect, owner=owner)).value == 7
    assert calls == 1


@pytest.mark.asyncio
async def test_failed_first_refresh_is_not_negative_cached():
    cache = AsyncSnapshotCache[int](5.0, 1.0)
    owner = object()
    collect = AsyncMock(side_effect=[RuntimeError("disk unavailable"), 9])

    with pytest.raises(RuntimeError, match="disk unavailable"):
        await cache.get_or_refresh(collect, owner=owner)
    assert cache.get() is None
    snapshot = await cache.get_or_refresh(collect, owner=owner)
    assert snapshot.value == 9
    assert snapshot.refresh_failed is False
    assert collect.await_count == 2


@pytest.mark.asyncio
async def test_stale_read_returns_last_good_sample_and_refreshes_once(monkeypatch):
    clock = [10.0]
    monkeypatch.setattr(
        cache_module, "time", SimpleNamespace(monotonic=lambda: clock[0])
    )
    cache = AsyncSnapshotCache[int](5.0, 1.0)
    owner = object()
    assert (
        await cache.get_or_refresh(AsyncMock(return_value=1), owner=owner)
    ).value == 1
    clock[0] = 16.0
    release = asyncio.Event()
    calls = 0

    async def collect():
        nonlocal calls
        calls += 1
        await release.wait()
        return 2

    snapshots = await asyncio.gather(
        *(cache.get_or_refresh(collect, owner=owner) for _ in range(5))
    )
    assert all(sample.value == 1 and sample.stale for sample in snapshots)
    assert all(sample.age_seconds == 6.0 and sample.refreshing for sample in snapshots)
    assert calls == 1
    release.set()
    await asyncio.gather(*cache._pending)
    snapshot = await cache.get_or_refresh(collect, owner=owner)
    assert snapshot.value == 2
    assert not snapshot.stale
    assert snapshot.age_seconds == 0


@pytest.mark.asyncio
async def test_failed_stale_refresh_keeps_good_sample_and_retries(monkeypatch):
    clock = [10.0]
    monkeypatch.setattr(
        cache_module, "time", SimpleNamespace(monotonic=lambda: clock[0])
    )
    cache = AsyncSnapshotCache[int](5.0, 1.0)
    owner = object()
    await cache.get_or_refresh(AsyncMock(return_value=1), owner=owner)
    clock[0] = 16.0
    failing = AsyncMock(side_effect=RuntimeError("temporary"))
    assert (await cache.get_or_refresh(failing, owner=owner)).value == 1
    await asyncio.gather(*cache._pending, return_exceptions=True)
    retry = AsyncMock(return_value=3)
    stale = await cache.get_or_refresh(retry, owner=owner)
    assert stale.value == 1
    assert stale.stale and stale.refresh_failed
    await asyncio.gather(*cache._pending)
    assert (await cache.get_or_refresh(retry, owner=owner)).value == 3


@pytest.mark.asyncio
async def test_owner_change_cannot_reuse_previous_manager_sample():
    cache = AsyncSnapshotCache[int](5.0, 1.0)
    first, second = object(), object()
    await cache.get_or_refresh(AsyncMock(return_value=1), owner=first)
    other = AsyncMock(return_value=2)
    assert (await cache.get_or_refresh(other, owner=second)).value == 2
    other.assert_awaited_once()


@pytest.mark.asyncio
async def test_invalidation_prevents_old_refresh_repopulating_cache():
    cache = AsyncSnapshotCache[int](5.0, 1.0)
    owner = object()
    started = asyncio.Event()
    release = asyncio.Event()

    async def old_collect():
        started.set()
        await release.wait()
        return 1

    old = asyncio.create_task(cache.get_or_refresh(old_collect, owner=owner))
    await started.wait()
    cache.clear()
    new = await cache.get_or_refresh(AsyncMock(return_value=2), owner=owner)
    assert new.value == 2
    release.set()
    assert (await old).value == 1
    assert cache.get() == 2
    await asyncio.sleep(0)
    assert not cache._pending


def test_explicit_cache_reset_is_compatible_with_ttl_callers():
    cache = AsyncSnapshotCache[dict](5.0, 1.0)
    cache.set({"sample": 1})
    assert cache.get() == {"sample": 1}
    cache.set(None)
    assert cache.get() is None
    cache.clear()
    assert cache.get() is None


@pytest.mark.asyncio
async def test_unavailable_manager_never_returns_a_previous_sample(monkeypatch):
    cache = AsyncSnapshotCache[dict](5.0, 1.0)
    cache.set({"success": True, "usage": {"sample": 1}})
    monkeypatch.setattr(models_usage, "_models_usage_cache", cache)
    monkeypatch.setattr(models_usage, "get_model_manager", lambda: None)
    with pytest.raises(models_usage.HTTPException) as error:
        await models_usage.get_models_usage()
    assert error.value.status_code == 503


@pytest.mark.asyncio
async def test_route_timeout_reports_unavailable_not_zero_metrics(monkeypatch):
    cache = AsyncSnapshotCache[dict](5.0, 0.001)
    release = asyncio.Event()
    calls = 0

    async def collect():
        nonlocal calls
        calls += 1
        await release.wait()
        return {"models_count": 0}

    manager = SimpleNamespace(get_usage_metrics=collect)
    monkeypatch.setattr(models_usage, "_models_usage_cache", cache)
    monkeypatch.setattr(models_usage, "get_model_manager", lambda: manager)
    try:
        with pytest.raises(models_usage.HTTPException) as error:
            await models_usage.get_models_usage()
        assert error.value.status_code == 503
        assert error.value.detail == {"reason_code": "MODELS_USAGE_TIMEOUT"}
        assert calls == 1
    finally:
        release.set()
        await asyncio.gather(*cache._pending)


def test_quota_checks_do_not_use_telemetry_snapshot(tmp_path, monkeypatch):
    manager = ModelManager(str(tmp_path))
    actual_size = iter([1.0, 60.0])
    monkeypatch.setattr(manager, "get_models_size_gb", lambda: next(actual_size))
    assert manager.check_storage_quota() is True
    assert manager.check_storage_quota() is False
