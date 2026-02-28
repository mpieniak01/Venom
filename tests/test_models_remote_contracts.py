from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from venom_core.api.routes import models_remote


@pytest.mark.asyncio
async def test_models_remote_helpers_and_validate_publish(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("VENOM_REMOTE_MODELS_CATALOG_TTL_SECONDS", "not-int")
    assert models_remote._env_int("VENOM_REMOTE_MODELS_CATALOG_TTL_SECONDS", 7) == 7

    monkeypatch.setenv("VENOM_REMOTE_MODELS_PROVIDER_PROBE_TTL_SECONDS", "2")
    assert models_remote._provider_probe_ttl_seconds() == 10

    monkeypatch.setattr(
        models_remote.SETTINGS,
        "OPENAI_CHAT_COMPLETIONS_ENDPOINT",
        "https://example.org/v1/chat/completions",
        raising=False,
    )
    assert models_remote._openai_models_url() == "https://example.org/v1/models"

    caps = models_remote._map_google_capabilities(
        {
            "name": "models/gemini-1.5-pro",
            "supportedGenerationMethods": ["generateContent", "countTokens"],
        }
    )
    assert "token-counting" in caps
    assert "vision" in caps

    no_caps = models_remote._map_google_capabilities({"name": "models/other"})
    assert no_caps == ["chat", "text-generation"]

    published: list[dict[str, object]] = []

    class _Audit:
        def publish(self, **kwargs):
            published.append(kwargs)

    monkeypatch.setattr(models_remote, "get_audit_stream", lambda: _Audit())
    monkeypatch.setattr(
        models_remote,
        "_validate_openai_connection",
        AsyncMock(return_value=(True, "ok", 12.3)),
    )

    result = await models_remote.validate_provider(
        models_remote.ValidationRequest(provider="openai", model="gpt-4o")
    )
    assert result["status"] == "success"
    assert published and published[0]["action"] == "validate_provider"
