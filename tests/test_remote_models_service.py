from __future__ import annotations

from threading import Lock

import pytest

from venom_core.services import remote_models_service as svc


def test_env_ttl_and_timeout_helpers(monkeypatch):
    monkeypatch.delenv("VENOM_REMOTE_MODELS_CATALOG_TTL_SECONDS", raising=False)
    assert svc.env_int("VENOM_REMOTE_MODELS_CATALOG_TTL_SECONDS", 7) == 7

    monkeypatch.setenv("VENOM_REMOTE_MODELS_PROVIDER_PROBE_TTL_SECONDS", "2")
    assert svc.provider_probe_ttl_seconds() == 10

    assert svc.remote_timeout_seconds(openai_api_timeout=1000) == 20.0
    assert svc.remote_timeout_seconds(openai_api_timeout=0.1) == 1.0


def test_url_and_capability_helpers():
    assert (
        svc.openai_models_url(chat_completions_endpoint="")
        == "https://api.openai.com/v1/models"
    )
    assert svc.openai_model_url(
        models_url="https://api.openai.com/v1/models", model_id="gpt-x"
    ).endswith("/gpt-x")
    assert svc.google_models_url().endswith("/v1beta/models")
    assert svc.google_model_url("gemini-1.5-pro").endswith("/models/gemini-1.5-pro")

    assert "function-calling" in svc.map_openai_capabilities("gpt-4.1")
    assert "vision" in svc.map_openai_capabilities("gpt-4o")

    caps = svc.map_google_capabilities(
        {
            "name": "models/gemini-1.5-pro",
            "supportedGenerationMethods": ["generateContent", "countTokens"],
        }
    )
    assert "chat" in caps
    assert "token-counting" in caps


def test_cache_helpers_roundtrip_and_ttl():
    cache: dict[str, dict[str, object]] = {}
    lock = Lock()

    svc.cache_put(cache, lock, "foo", payload={"status": "ok"})
    out = svc.cache_get(cache, lock, "foo", 10)
    assert out is not None
    assert out["status"] == "ok"

    expired = svc.cache_get(cache, lock, "foo", 0)
    assert expired is None


class _Logger:
    def __init__(self) -> None:
        self.warnings: list[str] = []

    def warning(self, msg: str, *args: object, **_kwargs: object) -> None:
        self.warnings.append(msg % args if args else msg)


def _deps(
    *,
    logger: _Logger,
    fetch_openai,
    fetch_google,
    check_openai=lambda: True,  # noqa: E731
    check_google=lambda: True,  # noqa: E731
):
    return svc.CatalogProviderDeps(
        cache_get_fn=svc.cache_get,
        cache_put_fn=svc.cache_put,
        fetch_openai_models_catalog_live_fn=fetch_openai,
        fetch_google_models_catalog_live_fn=fetch_google,
        openai_static_catalog_payload_fn=svc.openai_static_catalog_payload,
        google_static_catalog_payload_fn=svc.google_static_catalog_payload,
        check_openai_configured_fn=check_openai,
        check_google_configured_fn=check_google,
        now_iso_fn=lambda: "2026-03-01T12:00:00",
        logger=logger,
    )


@pytest.mark.asyncio
async def test_catalog_for_provider_cached_hit() -> None:
    cache: dict[str, dict[str, object]] = {}
    lock = Lock()
    svc.cache_put(
        cache,
        lock,
        "openai",
        payload={"models": [{"id": "x"}], "source": "cache", "error": None},
    )
    models, source, error = await svc.catalog_for_provider(
        provider="openai",
        cache=cache,
        lock=lock,
        catalog_ttl_seconds=60,
        deps=_deps(
            logger=_Logger(),
            fetch_openai=lambda: _async_result([]),
            fetch_google=lambda: _async_result([]),
        ),
    )
    assert models == [{"id": "x"}]
    assert source == "cache"
    assert error is None


@pytest.mark.asyncio
async def test_catalog_for_provider_openai_live_paths() -> None:
    cache: dict[str, dict[str, object]] = {}
    lock = Lock()
    logger = _Logger()

    models, source, error = await svc.catalog_for_provider(
        provider="openai",
        cache=cache,
        lock=lock,
        catalog_ttl_seconds=60,
        deps=_deps(
            logger=logger,
            fetch_openai=lambda: _async_result([{"id": "gpt-live"}]),
            fetch_google=lambda: _async_result([]),
        ),
    )
    assert models == [{"id": "gpt-live"}]
    assert source == "openai_api"
    assert error is None

    cache.clear()
    models, source, error = await svc.catalog_for_provider(
        provider="openai",
        cache=cache,
        lock=lock,
        catalog_ttl_seconds=60,
        deps=_deps(
            logger=logger,
            fetch_openai=lambda: _async_result([]),
            fetch_google=lambda: _async_result([]),
        ),
    )
    assert source == "static_fallback_empty_live"
    assert error == "live catalog empty"
    assert any(item.get("provider") == "openai" for item in models)

    cache.clear()
    models, source, error = await svc.catalog_for_provider(
        provider="openai",
        cache=cache,
        lock=lock,
        catalog_ttl_seconds=60,
        deps=_deps(
            logger=logger,
            fetch_openai=_async_raise,
            fetch_google=lambda: _async_result([]),
        ),
    )
    assert source == "static_fallback_error"
    assert error == "boom"
    assert logger.warnings


@pytest.mark.asyncio
async def test_catalog_for_provider_google_unconfigured_path() -> None:
    cache: dict[str, dict[str, object]] = {}
    lock = Lock()
    models, source, error = await svc.catalog_for_provider(
        provider="google",
        cache=cache,
        lock=lock,
        catalog_ttl_seconds=60,
        deps=_deps(
            logger=_Logger(),
            fetch_openai=lambda: _async_result([]),
            fetch_google=lambda: _async_result([]),
            check_openai=lambda: False,
            check_google=lambda: False,
        ),
    )
    assert source == "static_fallback_unconfigured"
    assert error == "GOOGLE_API_KEY not configured"
    assert any(item.get("provider") == "google" for item in models)


async def _async_result(value):
    return value


async def _async_raise():
    raise RuntimeError("boom")
