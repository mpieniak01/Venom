"""Edge-case tests for provider management API internals."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from venom_core.api.routes import providers as providers_route


class _DummyResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code


class _DummyAsyncClient:
    def __init__(
        self, response: _DummyResponse | None = None, exc: Exception | None = None
    ):
        self._response = response
        self._exc = exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, _url: str):
        if self._exc:
            raise self._exc
        return self._response


def test_get_provider_type_unknown() -> None:
    assert providers_route._get_provider_type("unknown") == "unknown"


def test_get_provider_capabilities_local_and_unknown() -> None:
    local_caps = providers_route._get_provider_capabilities("local")
    assert local_caps.activate is True
    assert local_caps.install is False
    assert local_caps.search is False

    unknown_caps = providers_route._get_provider_capabilities("not-real")
    assert unknown_caps.install is False
    assert unknown_caps.search is False
    assert unknown_caps.activate is False
    assert unknown_caps.inference is False
    assert unknown_caps.trainable is False


def test_get_provider_endpoint_vllm_and_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        providers_route.SETTINGS, "VLLM_ENDPOINT", "http://vllm:8000", raising=False
    )
    assert providers_route._get_provider_endpoint("vllm") == "http://vllm:8000"
    assert providers_route._get_provider_endpoint("unknown") is None


def test_check_openai_status_key_missing_and_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(providers_route.SETTINGS, "OPENAI_API_KEY", "", raising=False)
    missing = providers_route._check_openai_status()
    assert missing.status == "offline"
    assert missing.reason_code == "missing_api_key"

    monkeypatch.setattr(
        providers_route.SETTINGS, "OPENAI_API_KEY", "sk-test", raising=False
    )
    present = providers_route._check_openai_status()
    assert present.status == "connected"


def test_check_google_status_key_missing_and_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(providers_route.SETTINGS, "GOOGLE_API_KEY", "", raising=False)
    missing = providers_route._check_google_status()
    assert missing.status == "offline"
    assert missing.reason_code == "missing_api_key"

    monkeypatch.setattr(
        providers_route.SETTINGS, "GOOGLE_API_KEY", "g-test", raising=False
    )
    present = providers_route._check_google_status()
    assert present.status == "connected"


@pytest.mark.asyncio
async def test_check_provider_connection_unknown_provider() -> None:
    status = await providers_route._check_provider_connection("not-supported")
    assert status.status == "unknown"
    assert status.reason_code == "unsupported_provider"


@pytest.mark.asyncio
async def test_check_ollama_status_degraded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        providers_route.httpx,
        "AsyncClient",
        lambda timeout=5.0: _DummyAsyncClient(response=_DummyResponse(503)),
    )
    status = await providers_route._check_ollama_status()
    assert status.status == "degraded"
    assert status.reason_code == "http_error"


@pytest.mark.asyncio
async def test_check_ollama_status_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        providers_route.httpx,
        "AsyncClient",
        lambda timeout=5.0: _DummyAsyncClient(exc=RuntimeError("boom")),
    )
    status = await providers_route._check_ollama_status()
    assert status.status == "offline"
    assert status.reason_code == "connection_failed"


@pytest.mark.asyncio
async def test_check_vllm_status_no_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(providers_route.SETTINGS, "VLLM_ENDPOINT", "", raising=False)
    status = await providers_route._check_vllm_status()
    assert status.status == "offline"
    assert status.reason_code == "no_endpoint"


@pytest.mark.asyncio
async def test_check_vllm_status_degraded_and_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        providers_route.SETTINGS, "VLLM_ENDPOINT", "http://vllm:8000", raising=False
    )
    monkeypatch.setattr(
        providers_route.httpx,
        "AsyncClient",
        lambda timeout=5.0: _DummyAsyncClient(response=_DummyResponse(502)),
    )
    degraded = await providers_route._check_vllm_status()
    assert degraded.status == "degraded"
    assert degraded.reason_code == "http_error"

    monkeypatch.setattr(
        providers_route.httpx,
        "AsyncClient",
        lambda timeout=5.0: _DummyAsyncClient(exc=RuntimeError("fail")),
    )
    offline = await providers_route._check_vllm_status()
    assert offline.status == "offline"
    assert offline.reason_code == "connection_failed"


@pytest.mark.asyncio
async def test_activate_provider_offline_raises_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _offline(_provider: str):
        return providers_route.ProviderStatus(status="offline", message="down")

    monkeypatch.setattr(providers_route, "_check_provider_connection", _offline)

    with pytest.raises(HTTPException) as exc:
        await providers_route.activate_provider("openai", None)
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_activate_provider_openai_success_default_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _connected(_provider: str):
        return providers_route.ProviderStatus(status="connected")

    update_mock = MagicMock()
    monkeypatch.setattr(providers_route, "_check_provider_connection", _connected)
    monkeypatch.setattr(providers_route.config_manager, "update_config", update_mock)
    monkeypatch.setattr(
        providers_route.SETTINGS, "OPENAI_GPT4O_MODEL", "gpt-4o-default", raising=False
    )

    result = await providers_route.activate_provider("openai", None)
    assert result["status"] == "success"
    assert result["provider"] == "openai"
    assert result["model"] == "gpt-4o-default"
    update_mock.assert_called_once()


@pytest.mark.asyncio
async def test_activate_provider_google_success_with_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _connected(_provider: str):
        return providers_route.ProviderStatus(status="connected")

    update_mock = MagicMock()
    monkeypatch.setattr(providers_route, "_check_provider_connection", _connected)
    monkeypatch.setattr(providers_route.config_manager, "update_config", update_mock)
    request = providers_route.ProviderActivateRequest(model="gemini-2.0-pro")

    result = await providers_route.activate_provider("google", request)
    assert result["status"] == "success"
    assert result["provider"] == "google"
    assert result["model"] == "gemini-2.0-pro"
    update_mock.assert_called_once()


@pytest.mark.asyncio
async def test_activate_provider_openai_update_failure_raises_500(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _connected(_provider: str):
        return providers_route.ProviderStatus(status="connected")

    def _raise(_payload: dict[str, str]):
        raise RuntimeError("cannot-save")

    monkeypatch.setattr(providers_route, "_check_provider_connection", _connected)
    monkeypatch.setattr(providers_route.config_manager, "update_config", _raise)
    monkeypatch.setattr(
        providers_route.SETTINGS, "OPENAI_GPT4O_MODEL", "gpt-4o-default", raising=False
    )

    with pytest.raises(HTTPException) as exc:
        await providers_route.activate_provider("openai", None)
    assert exc.value.status_code == 500
    assert "Failed to activate provider" in exc.value.detail
