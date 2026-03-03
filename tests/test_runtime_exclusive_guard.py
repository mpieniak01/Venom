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


class _RaisingClient(_FakeClient):
    async def get(self, _url):
        raise RuntimeError("boom")


def test_lock_conflict():
    guard = RuntimeExclusiveGuard()
    guard.acquire_lock("owner-a")
    with pytest.raises(RuntimeExclusiveConflictError):
        guard.acquire_lock("owner-b")
    guard.release_lock("owner-a")


def test_release_lock_when_not_locked_resets_state():
    guard = RuntimeExclusiveGuard()
    guard._owner = "owner-a"  # noqa: SLF001
    guard._acquired_at = 123.0  # noqa: SLF001
    guard.release_lock("owner-a")
    assert guard._owner is None  # noqa: SLF001
    assert guard._acquired_at is None  # noqa: SLF001


def test_release_lock_ignores_foreign_owner():
    guard = RuntimeExclusiveGuard()
    guard.acquire_lock("owner-a")
    guard.release_lock("owner-b")
    assert guard.status_snapshot()["lock_held"] is True
    guard.release_lock("owner-a")


def test_status_snapshot_contains_lock_fields():
    guard = RuntimeExclusiveGuard()
    snap = guard.status_snapshot()
    assert set(snap.keys()) == {"lock_owner", "lock_acquired_at", "lock_held"}


def test_resolve_runtime_from_endpoint_and_provider(monkeypatch):
    guard = RuntimeExclusiveGuard()
    assert guard._resolve_runtime(endpoint="http://localhost:8000/v1") == "vllm"  # noqa: SLF001
    assert guard._resolve_runtime(endpoint="http://localhost/onnx") == "onnx"  # noqa: SLF001
    assert guard._resolve_runtime(endpoint="http://localhost:11434") == "ollama"  # noqa: SLF001

    class _RuntimeInfo:
        provider = "vllm"

    monkeypatch.setattr(
        "venom_core.services.runtime_exclusive_guard.get_active_llm_runtime",
        lambda _settings: _RuntimeInfo(),
    )
    assert guard._resolve_runtime(endpoint=None) == "vllm"  # noqa: SLF001


@pytest.mark.asyncio
async def test_healthcheck_handles_onnx_without_requests():
    guard = RuntimeExclusiveGuard()
    await guard._healthcheck_runtime(runtime="onnx", endpoint=None)  # noqa: SLF001


@pytest.mark.asyncio
async def test_healthcheck_ollama_http_error(monkeypatch):
    guard = RuntimeExclusiveGuard()
    responses = [_FakeResponse(500, {"models": []}), _FakeResponse(200, {"models": []})]
    monkeypatch.setattr(
        "venom_core.services.runtime_exclusive_guard.httpx.AsyncClient",
        lambda timeout=5.0: _FakeClient(responses),  # noqa: ARG005
    )
    with pytest.raises(RuntimeExclusivePreflightError):
        await guard._healthcheck_runtime(
            runtime="ollama", endpoint="http://127.0.0.1:11434"
        )  # noqa: SLF001


@pytest.mark.asyncio
async def test_healthcheck_vllm_http_error(monkeypatch):
    guard = RuntimeExclusiveGuard()
    responses = [_FakeResponse(503, {"data": []})]
    monkeypatch.setattr(
        "venom_core.services.runtime_exclusive_guard.httpx.AsyncClient",
        lambda timeout=5.0: _FakeClient(responses),  # noqa: ARG005
    )
    with pytest.raises(RuntimeExclusivePreflightError):
        await guard._healthcheck_runtime(
            runtime="vllm", endpoint="http://127.0.0.1:8000"
        )  # noqa: SLF001


@pytest.mark.asyncio
async def test_healthcheck_wraps_unexpected_exception(monkeypatch):
    guard = RuntimeExclusiveGuard()
    monkeypatch.setattr(
        "venom_core.services.runtime_exclusive_guard.httpx.AsyncClient",
        lambda timeout=5.0: _RaisingClient([]),  # noqa: ARG005
    )
    with pytest.raises(RuntimeExclusivePreflightError):
        await guard._healthcheck_runtime(
            runtime="ollama", endpoint="http://127.0.0.1:11434"
        )  # noqa: SLF001


def test_ensure_no_other_runs_conflicts_for_source_paths(monkeypatch):
    guard = RuntimeExclusiveGuard()
    monkeypatch.setattr(guard, "_has_active_llm_runs", lambda _service: True)
    monkeypatch.setattr(guard, "_has_active_coding_runs", lambda _service: False)
    with pytest.raises(RuntimeExclusiveConflictError):
        guard._ensure_no_other_runs(
            source="llm", benchmark_service=object(), coding_benchmark_service=None
        )  # noqa: SLF001

    monkeypatch.setattr(guard, "_has_active_llm_runs", lambda _service: False)
    monkeypatch.setattr(guard, "_has_active_coding_runs", lambda _service: True)
    with pytest.raises(RuntimeExclusiveConflictError):
        guard._ensure_no_other_runs(
            source="coding", benchmark_service=None, coding_benchmark_service=object()
        )  # noqa: SLF001
    with pytest.raises(RuntimeExclusiveConflictError):
        guard._ensure_no_other_runs(
            source="other", benchmark_service=None, coding_benchmark_service=object()
        )  # noqa: SLF001


def test_has_active_runs_handle_service_exceptions():
    guard = RuntimeExclusiveGuard()

    class _BadLLMService:
        def list_benchmarks(self, limit=100):  # noqa: ARG002
            raise RuntimeError("llm fail")

    class _BadCodingService:
        def list_runs(self, limit=100):  # noqa: ARG002
            raise RuntimeError("coding fail")

    assert guard._has_active_llm_runs(_BadLLMService()) is False  # noqa: SLF001
    assert guard._has_active_coding_runs(_BadCodingService()) is False  # noqa: SLF001


@pytest.mark.asyncio
async def test_drain_loaded_model_shortcuts(monkeypatch):
    guard = RuntimeExclusiveGuard()
    assert await guard._drain_loaded_model(runtime="vllm", endpoint=None) == []  # noqa: SLF001

    async def _empty_models(_base):
        return []

    monkeypatch.setattr(guard, "_ollama_loaded_models", _empty_models)
    assert (
        await guard._drain_loaded_model(
            runtime="ollama", endpoint="http://127.0.0.1:11434"
        )
        == []
    )  # noqa: SLF001


@pytest.mark.asyncio
async def test_ollama_loaded_models_errors_and_filtering(monkeypatch):
    guard = RuntimeExclusiveGuard()
    responses = [_FakeResponse(500, {"models": []})]
    monkeypatch.setattr(
        "venom_core.services.runtime_exclusive_guard.httpx.AsyncClient",
        lambda timeout=5.0: _FakeClient(responses),  # noqa: ARG005
    )
    with pytest.raises(RuntimeExclusivePreflightError):
        await guard._ollama_loaded_models("http://127.0.0.1:11434")  # noqa: SLF001

    responses = [_FakeResponse(200, {"models": [{"name": "a"}, {"name": ""}, "x"]})]
    monkeypatch.setattr(
        "venom_core.services.runtime_exclusive_guard.httpx.AsyncClient",
        lambda timeout=5.0: _FakeClient(responses),  # noqa: ARG005
    )
    assert await guard._ollama_loaded_models("http://127.0.0.1:11434") == ["a"]  # noqa: SLF001

    monkeypatch.setattr(
        "venom_core.services.runtime_exclusive_guard.httpx.AsyncClient",
        lambda timeout=5.0: _RaisingClient([]),  # noqa: ARG005
    )
    with pytest.raises(RuntimeExclusivePreflightError):
        await guard._ollama_loaded_models("http://127.0.0.1:11434")  # noqa: SLF001


def test_resolve_base_url_variants(monkeypatch):
    guard = RuntimeExclusiveGuard()
    monkeypatch.setattr(
        "venom_core.services.runtime_exclusive_guard.SETTINGS.LLM_LOCAL_ENDPOINT",
        "http://127.0.0.1:11434/v1",
    )
    monkeypatch.setattr(
        "venom_core.services.runtime_exclusive_guard.SETTINGS.VLLM_ENDPOINT",
        "http://127.0.0.1:8000/",
    )
    assert (
        guard._resolve_base_url(runtime="ollama", endpoint=None)
        == "http://127.0.0.1:11434"
    )  # noqa: SLF001
    assert (
        guard._resolve_base_url(runtime="vllm", endpoint=None)
        == "http://127.0.0.1:8000"
    )  # noqa: SLF001
    assert (
        guard._resolve_base_url(runtime="custom", endpoint="http://x/y/")
        == "http://x/y"
    )  # noqa: SLF001


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
