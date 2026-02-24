"""Tests for translation_service."""

import asyncio
from types import SimpleNamespace

import httpx
import pytest

from venom_core.services import translation_service as translation_module


class DummyRuntime:
    service_type = "local"


class DummyOpenAIRuntime:
    service_type = "openai"


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


def test_resolve_chat_endpoint_variants(monkeypatch):
    _configure_settings(monkeypatch)

    service = translation_module.TranslationService()

    monkeypatch.setattr(
        translation_module,
        "get_active_llm_runtime",
        lambda: DummyOpenAIRuntime(),
    )
    assert (
        service._resolve_chat_endpoint()
        == translation_module.SETTINGS.OPENAI_CHAT_COMPLETIONS_ENDPOINT
    )

    monkeypatch.setattr(
        translation_module,
        "get_active_llm_runtime",
        lambda: DummyRuntime(),
    )
    monkeypatch.setattr(
        translation_module.SETTINGS, "LLM_LOCAL_ENDPOINT", "http://localhost:11434"
    )
    assert (
        service._resolve_chat_endpoint() == "http://localhost:11434/v1/chat/completions"
    )

    monkeypatch.setattr(translation_module.SETTINGS, "LLM_LOCAL_ENDPOINT", "")
    with pytest.raises(RuntimeError, match="Brak skonfigurowanego endpointu"):
        service._resolve_chat_endpoint()


def test_resolve_chat_endpoint_accepts_full_chat_completions(monkeypatch):
    _configure_settings(monkeypatch)
    service = translation_module.TranslationService()
    monkeypatch.setattr(
        translation_module,
        "get_active_llm_runtime",
        lambda: DummyRuntime(),
    )
    monkeypatch.setattr(
        translation_module.SETTINGS,
        "LLM_LOCAL_ENDPOINT",
        "http://localhost:11434/v1/chat/completions",
    )
    assert (
        service._resolve_chat_endpoint() == "http://localhost:11434/v1/chat/completions"
    )


def test_resolve_headers_openai_local_and_empty(monkeypatch):
    _configure_settings(monkeypatch)
    service = translation_module.TranslationService()

    monkeypatch.setattr(translation_module.SETTINGS, "OPENAI_API_KEY", "openai-key")
    assert service._resolve_headers(DummyOpenAIRuntime()) == {
        "Authorization": "Bearer openai-key"
    }

    monkeypatch.setattr(translation_module.SETTINGS, "OPENAI_API_KEY", "")
    monkeypatch.setattr(translation_module.SETTINGS, "LLM_LOCAL_API_KEY", "local-key")
    assert service._resolve_headers(DummyRuntime()) == {
        "Authorization": "Bearer local-key"
    }

    monkeypatch.setattr(translation_module.SETTINGS, "LLM_LOCAL_API_KEY", "")
    assert service._resolve_headers(DummyRuntime()) == {}


@pytest.mark.asyncio
async def test_translate_text_returns_early_on_empty_text():
    service = translation_module.TranslationService()
    assert await service.translate_text("", target_lang="pl") == ""


def test_extract_message_content_fallback_variants():
    text = "fallback"
    assert (
        translation_module.TranslationService._extract_message_content(
            data={"choices": "not-list"},
            fallback_text=text,
        )
        == text
    )
    assert (
        translation_module.TranslationService._extract_message_content(
            data={"choices": [123]},
            fallback_text=text,
        )
        == text
    )
    assert (
        translation_module.TranslationService._extract_message_content(
            data={"choices": [{"message": "not-dict"}]},
            fallback_text=text,
        )
        == text
    )
    assert (
        translation_module.TranslationService._extract_message_content(
            data={"choices": [{"message": {"content": 7}}]},
            fallback_text=text,
        )
        == text
    )


def test_get_cached_value_expired_entry_returns_none():
    service = translation_module.TranslationService(cache_ttl_seconds=1)
    key = service._build_cache_key("hello", None, "pl", "m")
    service._cache[key] = {"value": "cached", "timestamp": 1.0}
    assert service._get_cached_value(cache_key=key, now=2.0) is None


@pytest.mark.asyncio
async def test_translate_text_without_cache_handles_non_dict_payload(monkeypatch):
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
            return DummyResponse(["not-a-dict"])

    monkeypatch.setattr(translation_module, "TrafficControlledHttpClient", DummyClient)
    service = translation_module.TranslationService(cache_ttl_seconds=60)
    result = await service.translate_text("Hello", target_lang="pl", use_cache=False)
    assert result == "Hello"
    assert service._cache == {}


@pytest.mark.asyncio
async def test_translate_text_model_name_missing_raises_without_fallback(monkeypatch):
    _configure_settings(monkeypatch)
    monkeypatch.setattr(
        translation_module.SETTINGS, "LLM_MODEL_NAME", "", raising=False
    )
    service = translation_module.TranslationService()
    with pytest.raises(RuntimeError, match="Brak ustawionego modelu"):
        await service.translate_text("Hello", target_lang="pl", allow_fallback=False)


@pytest.mark.asyncio
async def test_translate_text_raises_generic_exception_without_fallback(monkeypatch):
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
            raise RuntimeError("generic-boom")

    monkeypatch.setattr(translation_module, "TrafficControlledHttpClient", DummyClient)
    service = translation_module.TranslationService()
    with pytest.raises(RuntimeError, match="generic-boom"):
        await service.translate_text("Hello", target_lang="pl", allow_fallback=False)


@pytest.mark.asyncio
async def test_translate_text_falls_back_on_generic_exception(monkeypatch):
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
            raise RuntimeError("generic-boom-fallback")

    monkeypatch.setattr(translation_module, "TrafficControlledHttpClient", DummyClient)
    service = translation_module.TranslationService()
    result = await service.translate_text("Hello", target_lang="pl")
    assert result == "Hello"


def test_get_cached_value_missing_and_valid_entry():
    service = translation_module.TranslationService(cache_ttl_seconds=100)
    key = service._build_cache_key("hello", "en", "pl", "m")
    assert service._get_cached_value(cache_key=key, now=1.0) is None

    service._cache[key] = {"value": "cached-ok", "timestamp": 1.0}
    assert service._get_cached_value(cache_key=key, now=50.0) == "cached-ok"


def test_extract_message_content_blank_string_falls_back():
    assert (
        translation_module.TranslationService._extract_message_content(
            data={"choices": [{"message": {"content": "   "}}]},
            fallback_text="fallback",
        )
        == "fallback"
    )


def test_build_translation_payload_uses_source_and_target_labels():
    payload = translation_module.TranslationService._build_translation_payload(
        text="Hello",
        source_lang="en",
        target_lang="pl",
        model_name="test-model",
    )
    messages = payload["messages"]
    assert payload["model"] == "test-model"
    assert "Translate from English to Polish." in messages[1]["content"]


def test_build_translation_payload_uses_source_language_fallback():
    payload = translation_module.TranslationService._build_translation_payload(
        text="Hallo",
        source_lang=None,
        target_lang="en",
        model_name="test-model",
    )
    assert (
        "Translate from the source language to English."
        in payload["messages"][1]["content"]
    )


def test_resolve_headers_runtime_without_keys_returns_empty(monkeypatch):
    _configure_settings(monkeypatch)
    monkeypatch.setattr(translation_module.SETTINGS, "OPENAI_API_KEY", "")
    monkeypatch.setattr(translation_module.SETTINGS, "LLM_LOCAL_API_KEY", "")
    service = translation_module.TranslationService()
    monkeypatch.setattr(
        translation_module,
        "get_active_llm_runtime",
        lambda: SimpleNamespace(service_type="local"),
    )
    assert service._resolve_headers() == {}


def test_resolve_chat_endpoint_appends_v1_path_for_plain_local_endpoint(monkeypatch):
    _configure_settings(monkeypatch)
    service = translation_module.TranslationService()
    monkeypatch.setattr(
        translation_module,
        "get_active_llm_runtime",
        lambda: DummyRuntime(),
    )
    monkeypatch.setattr(
        translation_module.SETTINGS,
        "LLM_LOCAL_ENDPOINT",
        "http://localhost:11434/",
    )
    assert (
        service._resolve_chat_endpoint() == "http://localhost:11434/v1/chat/completions"
    )


def test_resolve_headers_unknown_runtime_type_returns_empty():
    service = translation_module.TranslationService()
    headers = service._resolve_headers(SimpleNamespace(service_type="custom"))
    assert headers == {}


def test_normalize_target_lang_accepts_uppercase():
    assert translation_module.TranslationService._normalize_target_lang("PL") == "pl"


def test_build_cache_key_depends_on_source_language():
    service = translation_module.TranslationService()
    key_en = service._build_cache_key("Hello", "en", "pl", "model")
    key_auto = service._build_cache_key("Hello", None, "pl", "model")
    assert key_en != key_auto


@pytest.mark.asyncio
async def test_translate_text_uses_llm_provider_when_runtime_has_no_markers(
    monkeypatch,
):
    _configure_settings(monkeypatch)
    runtime = SimpleNamespace(provider=None, service_type=None)
    monkeypatch.setattr(translation_module, "get_active_llm_runtime", lambda: runtime)

    observed_provider = {"value": None}

    class DummyClient:
        def __init__(self, *args, **kwargs):
            observed_provider["value"] = kwargs.get("provider")

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def apost(self, *args, **kwargs):
            return DummyResponse({"choices": [{"message": {"content": "Czesc"}}]})

    monkeypatch.setattr(translation_module, "TrafficControlledHttpClient", DummyClient)
    service = translation_module.TranslationService(cache_ttl_seconds=0)
    result = await service.translate_text("Hello", target_lang="pl", use_cache=False)
    assert result == "Czesc"
    assert observed_provider["value"] == "llm"
