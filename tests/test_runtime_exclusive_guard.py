"""Testy unit dla RuntimeExclusiveGuard."""

from __future__ import annotations

import pytest

from venom_core.services.runtime_exclusive_guard import (
    RuntimeExclusiveConflictError,
    RuntimeExclusiveGuard,
    RuntimeExclusivePreflightError,
)


class _FakeResponse:
    def __init__(self, status_code: int, payload=None):
        self.status_code = status_code
        self._payload = payload
        self.content = b"1"

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, responses):
        self._responses = responses

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, _url):
        return self._responses.pop(0)

    async def post(self, _url, json=None):  # noqa: A002
        return _FakeResponse(200, {"ok": True, "json": json or {}})


def test_lock_conflict():
    guard = RuntimeExclusiveGuard()
    guard.acquire_lock("owner-a")
    with pytest.raises(RuntimeExclusiveConflictError):
        guard.acquire_lock("owner-b")
    guard.release_lock("owner-a")


@pytest.mark.asyncio
async def test_preflight_conflict_when_llm_run_active(monkeypatch):
    guard = RuntimeExclusiveGuard()

    class _BenchmarkService:
        def list_benchmarks(self, limit=10):  # noqa: ARG002
            return [{"status": "running"}]

    with pytest.raises(RuntimeExclusiveConflictError):
        await guard.preflight_for_benchmark(
            source="coding",
            benchmark_service=_BenchmarkService(),
            coding_benchmark_service=None,
            endpoint="http://127.0.0.1:11434",
        )


@pytest.mark.asyncio
async def test_preflight_unloads_ollama_models(monkeypatch):
    guard = RuntimeExclusiveGuard()

    # Sequence:
    # 1) health /api/tags
    # 2) health /api/ps
    # 3) drain first /api/ps => loaded model
    # 4) drain verify /api/ps => empty
    responses = [
        _FakeResponse(200, {"models": []}),
        _FakeResponse(200, {"models": []}),
        _FakeResponse(200, {"models": [{"name": "gemma3:latest"}]}),
        _FakeResponse(200, {"models": []}),
    ]
    monkeypatch.setattr(
        "venom_core.services.runtime_exclusive_guard.httpx.AsyncClient",
        lambda timeout=5.0: _FakeClient(responses),  # noqa: ARG005
    )

    snapshot = await guard.preflight_for_benchmark(
        source="llm",
        benchmark_service=None,
        coding_benchmark_service=None,
        endpoint="http://127.0.0.1:11434",
    )
    assert snapshot.runtime == "ollama"
    assert snapshot.loaded_models == ["gemma3:latest"]


@pytest.mark.asyncio
async def test_preflight_fails_when_unload_not_effective(monkeypatch):
    guard = RuntimeExclusiveGuard()
    responses = [
        _FakeResponse(200, {"models": []}),
        _FakeResponse(200, {"models": []}),
        _FakeResponse(200, {"models": [{"name": "qwen2.5-coder:3b"}]}),
        _FakeResponse(200, {"models": [{"name": "qwen2.5-coder:3b"}]}),
    ]
    monkeypatch.setattr(
        "venom_core.services.runtime_exclusive_guard.httpx.AsyncClient",
        lambda timeout=5.0: _FakeClient(responses),  # noqa: ARG005
    )

    with pytest.raises(RuntimeExclusivePreflightError):
        await guard.preflight_for_benchmark(
            source="llm",
            benchmark_service=None,
            coding_benchmark_service=None,
            endpoint="http://127.0.0.1:11434",
        )
