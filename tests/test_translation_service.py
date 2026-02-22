"""Tests for translation_service."""

import asyncio

import httpx
import pytest

from venom_core.services import translation_service as translation_module


class DummyRuntime:
    service_type = "local"


class DummyResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _configure_settings(monkeypatch):
    monkeypatch.setattr(
        translation_module.SETTINGS, "LLM_MODEL_NAME", "test-model", raising=False
    )
    monkeypatch.setattr(
        translation_module.SETTINGS,
        "LLM_LOCAL_ENDPOINT",
        "http://localhost:8000/v1",
        raising=False,
    )
    monkeypatch.setattr(
        translation_module.SETTINGS, "LLM_LOCAL_API_KEY", "local-key", raising=False
    )
    monkeypatch.setattr(
        translation_module.SETTINGS, "OPENAI_API_TIMEOUT", 1.0, raising=False
    )


@pytest.mark.asyncio
async def test_translate_text_uses_cache(monkeypatch):
    _configure_settings(monkeypatch)
    monkeypatch.setattr(translation_module, "get_active_llm_runtime", DummyRuntime)

    call_count = {"value": 0}
    payload = {"choices": [{"message": {"content": "Czesc"}}]}

    class DummyClient:
        def __init__(self, *args, **kwargs):
            # No-op: konstruktor tylko dla kompatybilności z TrafficControlledHttpClient
            return None

        async def __aenter__(self):
            await asyncio.sleep(0)
            return self

        async def __aexit__(self, exc_type, exc, tb):
            await asyncio.sleep(0)
            return False

        async def apost(self, *args, **kwargs):
            await asyncio.sleep(0)
            call_count["value"] += 1
            return DummyResponse(payload)

    monkeypatch.setattr(
        translation_module,
        "TrafficControlledHttpClient",
        DummyClient,
    )

    service = translation_module.TranslationService(cache_ttl_seconds=60)
    result_first = await service.translate_text("Hello", target_lang="pl")
    result_cached = await service.translate_text("Hello", target_lang="pl")

    assert result_first == "Czesc"
    assert result_cached == "Czesc"
    assert call_count["value"] == 1


@pytest.mark.asyncio
async def test_translate_text_falls_back_on_error(monkeypatch):
    _configure_settings(monkeypatch)
    monkeypatch.setattr(translation_module, "get_active_llm_runtime", DummyRuntime)

    class DummyClient:
        def __init__(self, *args, **kwargs):
            # No-op: konstruktor tylko dla kompatybilności z TrafficControlledHttpClient
            return None

        async def __aenter__(self):
            await asyncio.sleep(0)
            return self

        async def __aexit__(self, exc_type, exc, tb):
            await asyncio.sleep(0)
            return False

        async def apost(self, *args, **kwargs):
            await asyncio.sleep(0)
            raise httpx.HTTPError("boom")

    monkeypatch.setattr(
        translation_module,
        "TrafficControlledHttpClient",
        DummyClient,
    )

    service = translation_module.TranslationService(cache_ttl_seconds=60)
    result = await service.translate_text("Hello", target_lang="pl")
    assert result == "Hello"


@pytest.mark.asyncio
async def test_translate_text_raises_on_http_error_without_fallback(monkeypatch):
    _configure_settings(monkeypatch)
    monkeypatch.setattr(translation_module, "get_active_llm_runtime", DummyRuntime)

    class DummyClient:
        def __init__(self, *args, **kwargs):
            return None

        async def __aenter__(self):
            await asyncio.sleep(0)
            return self

        async def __aexit__(self, exc_type, exc, tb):
            await asyncio.sleep(0)
            return False

        async def apost(self, *args, **kwargs):
            await asyncio.sleep(0)
            raise httpx.HTTPError("boom-no-fallback")

    monkeypatch.setattr(
        translation_module,
        "TrafficControlledHttpClient",
        DummyClient,
    )

    service = translation_module.TranslationService(cache_ttl_seconds=60)
    with pytest.raises(httpx.HTTPError, match="boom-no-fallback"):
        await service.translate_text(
            "Hello",
            target_lang="pl",
            allow_fallback=False,
        )


@pytest.mark.asyncio
async def test_translate_text_rejects_invalid_lang():
    service = translation_module.TranslationService()
    with pytest.raises(ValueError):
        await service.translate_text("Hello", target_lang="fr")
