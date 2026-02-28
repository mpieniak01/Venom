from __future__ import annotations

from threading import Lock

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
