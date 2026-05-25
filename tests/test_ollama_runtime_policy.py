from __future__ import annotations

import pytest

from venom_core.services import ollama_runtime_policy as policy


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}
        self.content = b"{}"

    def json(self):
        return self._payload


class _FakeAsyncClient:
    def __init__(self, get_responses: list[_FakeResponse], post_statuses: list[int]):
        self._get = list(get_responses)
        self._post = list(post_statuses)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, _url: str):
        if self._get:
            return self._get.pop(0)
        return _FakeResponse(200, {"models": []})

    async def post(self, _url: str, json: dict):
        if self._post:
            return _FakeResponse(self._post.pop(0), {})
        return _FakeResponse(200, {})


@pytest.mark.asyncio
async def test_enforce_single_loaded_ollama_model_unloads_other_models(monkeypatch):
    before = _FakeResponse(
        200,
        {"models": [{"name": "qwen3.5:latest"}, {"name": "qwen2.5-coder:3b"}]},
    )
    after = _FakeResponse(200, {"models": [{"name": "qwen2.5-coder:3b"}]})

    monkeypatch.setattr(
        policy.httpx,
        "AsyncClient",
        lambda timeout=10.0: _FakeAsyncClient([before, after], [200]),
    )

    result = await policy.enforce_single_loaded_ollama_model(
        endpoint="http://localhost:11434/v1",
        selected_model="qwen2.5-coder:3b",
    )

    assert result["unloaded"] == ["qwen3.5:latest"]
    assert result["after"] == ["qwen2.5-coder:3b"]


@pytest.mark.asyncio
async def test_enforce_single_loaded_ollama_model_raises_when_extra_models_remain(
    monkeypatch,
):
    before = _FakeResponse(200, {"models": [{"name": "qwen3.5:latest"}]})
    after = _FakeResponse(200, {"models": [{"name": "qwen3.5:latest"}]})

    monkeypatch.setattr(
        policy.httpx,
        "AsyncClient",
        lambda timeout=10.0: _FakeAsyncClient([before, after], [200]),
    )

    with pytest.raises(RuntimeError, match="single-model policy violation"):
        await policy.enforce_single_loaded_ollama_model(
            endpoint="http://localhost:11434/v1",
            selected_model="qwen2.5-coder:3b",
        )


def test_resolve_ollama_base_url_defaults_and_trims():
    assert policy._resolve_ollama_base_url(None) == "http://localhost:11434"  # noqa: SLF001
    assert (
        policy._resolve_ollama_base_url("http://localhost:11434/v1/")
        == "http://localhost:11434"
    )  # noqa: SLF001


def test_extract_loaded_model_names_handles_invalid_payload_shape():
    assert policy._extract_loaded_model_names(None) == []  # noqa: SLF001
    assert policy._extract_loaded_model_names({"models": {}}) == []  # noqa: SLF001
    assert policy._extract_loaded_model_names({"models": [None, {"name": "a"}]}) == [
        "a"
    ]  # noqa: SLF001
