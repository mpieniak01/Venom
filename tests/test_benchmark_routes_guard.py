"""Testy kontraktowe guarda dla routera benchmark."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from venom_core.api.routes import benchmark as benchmark_routes
from venom_core.services.runtime_exclusive_guard import RuntimeExclusiveConflictError


class _ConflictGuard:
    def acquire_lock(self, _owner):
        raise RuntimeExclusiveConflictError("lock busy")

    def release_lock(self, _owner):
        return None


class _PassGuard:
    def acquire_lock(self, _owner):
        return None

    def release_lock(self, _owner):
        return None

    async def preflight_for_benchmark(self, **_kwargs):
        return None


def _build_client(service, guard):
    benchmark_routes.set_dependencies(service, runtime_exclusive_guard=guard)
    app = FastAPI()
    app.include_router(benchmark_routes.router)
    return TestClient(app)


def test_benchmark_start_returns_409_when_guard_lock_busy():
    service = MagicMock()
    service.start_benchmark = AsyncMock(return_value="id")
    client = _build_client(service, _ConflictGuard())
    response = client.post(
        "/api/v1/benchmark/start",
        json={"models": ["llama3:latest"], "num_questions": 1},
    )
    assert response.status_code == 409


def test_benchmark_start_runs_when_guard_preflight_passes():
    service = MagicMock()
    service.start_benchmark = AsyncMock(return_value="id-123")
    client = _build_client(service, _PassGuard())
    response = client.post(
        "/api/v1/benchmark/start",
        json={"models": ["llama3:latest"], "num_questions": 1},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["benchmark_id"] == "id-123"
