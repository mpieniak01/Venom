from __future__ import annotations

import importlib
from typing import Any

import httpx
import pytest

import venom_core.services.runtime_switch_service as switch_mod


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, Any] | None = None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload


class _FakeAsyncClient:
    def __init__(
        self,
        *,
        get_items: list[Any] | None = None,
        post_exception: bool = False,
    ):
        self._get_items = list(get_items or [])
        self._post_exception = post_exception

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, _url: str):
        if not self._get_items:
            return _FakeResponse(500, {"status": "error"})
        item = self._get_items.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def post(self, _url: str, json: dict[str, Any] | None = None):
        if self._post_exception:
            raise RuntimeError("post failed")
        return _FakeResponse(200, {"ok": True, "echo": json or {}})


@pytest.mark.asyncio
async def test_release_ollama_model_handles_empty_input():
    mod = importlib.reload(switch_mod)
    assert await mod._release_ollama_model("", "phi3:mini") is False
    assert await mod._release_ollama_model("http://localhost:11434", "") is False


@pytest.mark.asyncio
async def test_release_ollama_model_success_and_failure(monkeypatch):
    mod = importlib.reload(switch_mod)
    monkeypatch.setattr(mod.httpx, "AsyncClient", lambda timeout: _FakeAsyncClient())
    assert (
        await mod._release_ollama_model("http://localhost:11434/v1", "phi3:mini")
        is True
    )

    monkeypatch.setattr(
        mod.httpx,
        "AsyncClient",
        lambda timeout: _FakeAsyncClient(post_exception=True),
    )
    assert (
        await mod._release_ollama_model("http://localhost:11434/v1", "phi3:mini")
        is False
    )


@pytest.mark.asyncio
async def test_probe_health_ready_and_shutdown_branches(monkeypatch):
    mod = importlib.reload(switch_mod)

    async def _no_sleep(_seconds):
        return None

    monkeypatch.setattr(mod.asyncio, "sleep", _no_sleep)
    monkeypatch.setattr(mod, "_HEALTH_MAX_ATTEMPTS", 2)

    monkeypatch.setattr(
        mod.httpx,
        "AsyncClient",
        lambda timeout: _FakeAsyncClient(
            get_items=[_FakeResponse(200, {"status": "ok"})]
        ),
    )
    assert (
        await mod.probe_health_ready("multi_runtime", "http://localhost:8014/health")
        is True
    )

    monkeypatch.setattr(
        mod.httpx,
        "AsyncClient",
        lambda timeout: _FakeAsyncClient(
            get_items=[httpx.ConnectError("down"), httpx.ConnectError("down")]
        ),
    )
    assert (
        await mod.probe_health_ready("multi_runtime", "http://localhost:8014/health")
        is False
    )

    monkeypatch.setattr(
        mod.httpx,
        "AsyncClient",
        lambda timeout: _FakeAsyncClient(
            get_items=[_FakeResponse(503, {"status": "down"})]
        ),
    )
    assert (
        await mod.probe_until_shutdown("ollama", "http://localhost:11434/api/tags")
        is True
    )

    monkeypatch.setattr(
        mod.httpx,
        "AsyncClient",
        lambda timeout: _FakeAsyncClient(
            get_items=[
                _FakeResponse(200, {"status": "ok"}),
                _FakeResponse(200, {"status": "ok"}),
            ]
        ),
    )
    assert (
        await mod.probe_until_shutdown("multi_runtime", "http://localhost:8014/health")
        is False
    )


@pytest.mark.asyncio
async def test_probe_until_shutdown_returns_true_on_exception(monkeypatch):
    mod = importlib.reload(switch_mod)

    async def _no_sleep(_seconds):
        return None

    monkeypatch.setattr(mod.asyncio, "sleep", _no_sleep)
    monkeypatch.setattr(mod, "_HEALTH_MAX_ATTEMPTS", 1)
    monkeypatch.setattr(
        mod.httpx,
        "AsyncClient",
        lambda timeout: _FakeAsyncClient(get_items=[httpx.ConnectError("boom")]),
    )
    assert (
        await mod.probe_until_shutdown("ollama", "http://localhost:11434/api/tags")
        is True
    )
