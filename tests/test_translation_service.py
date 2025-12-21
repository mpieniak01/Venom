"""Tests for translation_service."""

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
    monkeypatch.setattr(
        translation_module, "get_active_llm_runtime", lambda: DummyRuntime()
    )

    call_count = {"value": 0}
    payload = {"choices": [{"message": {"content": "Czesc"}}]}

    class DummyClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, *args, **kwargs):
            call_count["value"] += 1
            return DummyResponse(payload)

    monkeypatch.setattr(translation_module.httpx, "AsyncClient", DummyClient)

    service = translation_module.TranslationService(cache_ttl_seconds=60)
    result_first = await service.translate_text("Hello", target_lang="pl")
    result_cached = await service.translate_text("Hello", target_lang="pl")

    assert result_first == "Czesc"
    assert result_cached == "Czesc"
    assert call_count["value"] == 1


@pytest.mark.asyncio
async def test_translate_text_falls_back_on_error(monkeypatch):
    _configure_settings(monkeypatch)
    monkeypatch.setattr(
        translation_module, "get_active_llm_runtime", lambda: DummyRuntime()
    )

    class DummyClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, *args, **kwargs):
            raise httpx.HTTPError("boom")

    monkeypatch.setattr(translation_module.httpx, "AsyncClient", DummyClient)

    service = translation_module.TranslationService(cache_ttl_seconds=60)
    result = await service.translate_text("Hello", target_lang="pl")
    assert result == "Hello"


@pytest.mark.asyncio
async def test_translate_text_rejects_invalid_lang():
    service = translation_module.TranslationService()
    with pytest.raises(ValueError):
        await service.translate_text("Hello", target_lang="fr")
