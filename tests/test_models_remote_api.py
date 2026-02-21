"""Tests for remote models API endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient

from venom_core.api.routes import models_remote
from venom_core.config import SETTINGS
from venom_core.main import app


@pytest.mark.asyncio
async def test_get_remote_providers():
    """Test getting remote provider status."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/api/v1/models/remote/providers")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "providers" in data
    assert "count" in data
    assert data["count"] == 2  # OpenAI and Google

    # Check provider structure
    provider_names = {p["provider"] for p in data["providers"]}
    assert "openai" in provider_names
    assert "google" in provider_names

    # Check that each provider has required fields
    for provider in data["providers"]:
        assert "provider" in provider
        assert "status" in provider
        assert "last_check" in provider
        assert provider["status"] in ["configured", "disabled", "reachable", "degraded"]


@pytest.mark.asyncio
async def test_get_remote_catalog_openai():
    """Test getting OpenAI models catalog."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/api/v1/models/remote/catalog?provider=openai")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["provider"] == "openai"
    assert "models" in data
    assert "count" in data
    assert "refreshed_at" in data
    assert "source" in data
    assert "source" in data
    assert isinstance(data["source"], str)
    assert data["count"] > 0

    # Check model structure
    for model in data["models"]:
        assert "id" in model
        assert "name" in model
        assert "provider" in model
        assert model["provider"] == "openai"
        assert "capabilities" in model
        assert isinstance(model["capabilities"], list)


@pytest.mark.asyncio
async def test_get_remote_catalog_google():
    """Test getting Google models catalog."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/api/v1/models/remote/catalog?provider=google")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["provider"] == "google"
    assert "models" in data
    assert data["count"] > 0

    # Check model structure
    for model in data["models"]:
        assert model["provider"] == "google"
        assert "capabilities" in model


@pytest.mark.asyncio
async def test_get_remote_catalog_invalid_provider():
    """Test getting catalog with invalid provider."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/api/v1/models/remote/catalog?provider=invalid")

    assert response.status_code == 400
    data = response.json()
    assert "detail" in data
    assert "invalid" in data["detail"].lower()


@pytest.mark.asyncio
async def test_get_connectivity_map():
    """Test getting service-to-model connectivity map."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/api/v1/models/remote/connectivity")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "bindings" in data
    assert "count" in data
    assert isinstance(data["bindings"], list)

    # Check binding structure if any exist
    for binding in data["bindings"]:
        assert "service_id" in binding
        assert "endpoint" in binding
        assert "http_method" in binding
        assert "provider" in binding
        assert "model" in binding
        assert "routing_mode" in binding
        assert "status" in binding


@pytest.mark.asyncio
async def test_validate_provider_openai():
    """Test validating OpenAI provider."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.post(
            "/api/v1/models/remote/validate",
            json={"provider": "openai"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "validation" in data

    validation = data["validation"]
    assert validation["provider"] == "openai"
    assert "valid" in validation
    assert "message" in validation
    assert isinstance(validation["valid"], bool)


@pytest.mark.asyncio
async def test_validate_provider_google():
    """Test validating Google provider."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.post(
            "/api/v1/models/remote/validate",
            json={"provider": "google"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "validation" in data

    validation = data["validation"]
    assert validation["provider"] == "google"
    assert "valid" in validation
    assert "message" in validation


@pytest.mark.asyncio
async def test_validate_provider_invalid():
    """Test validating invalid provider."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.post(
            "/api/v1/models/remote/validate",
            json={"provider": "invalid"},
        )

    assert response.status_code == 400
    data = response.json()
    assert "detail" in data
    assert "invalid" in data["detail"].lower()


@pytest.mark.asyncio
async def test_validate_provider_with_model():
    """Test validating provider with specific model."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.post(
            "/api/v1/models/remote/validate",
            json={"provider": "openai", "model": "gpt-4o"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "validation" in data


@pytest.mark.asyncio
async def test_get_remote_catalog_openai_live_path(monkeypatch):
    """Uses live fetch path when provider is configured."""
    monkeypatch.setattr(models_remote, "_check_openai_configured", lambda: True)

    async def _fake_live():
        return [
            models_remote.RemoteModelInfo(
                id="gpt-test-live",
                name="gpt-test-live",
                provider="openai",
                capabilities=["chat"],
                model_alias=None,
            )
        ]

    monkeypatch.setattr(models_remote, "_fetch_openai_models_catalog_live", _fake_live)
    models_remote._catalog_cache.clear()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/api/v1/models/remote/catalog?provider=openai")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["provider"] == "openai"
    assert data["source"] == "openai_api"
    assert data["count"] == 1
    assert data["models"][0]["id"] == "gpt-test-live"


@pytest.mark.asyncio
async def test_get_remote_catalog_openai_live_error_falls_back_to_static(monkeypatch):
    """Falls back to static catalog if live fetch fails."""
    monkeypatch.setattr(models_remote, "_check_openai_configured", lambda: True)

    async def _fake_live_error():
        raise RuntimeError("boom")

    monkeypatch.setattr(
        models_remote, "_fetch_openai_models_catalog_live", _fake_live_error
    )
    models_remote._catalog_cache.clear()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/api/v1/models/remote/catalog?provider=openai")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["provider"] == "openai"
    assert data["source"] == "static_fallback_error"
    assert data["count"] > 0


@pytest.mark.asyncio
async def test_validate_provider_uses_live_validation_path(monkeypatch):
    """Validate endpoint uses live API validation helper."""

    async def _fake_validate(*, model=None):
        assert model == "gpt-4o"
        return True, "OpenAI API reachable", 42.0

    monkeypatch.setattr(models_remote, "_validate_openai_connection", _fake_validate)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.post(
            "/api/v1/models/remote/validate",
            json={"provider": "openai", "model": "gpt-4o"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    validation = data["validation"]
    assert validation["provider"] == "openai"
    assert validation["valid"] is True
    assert validation["details"]["validation_mode"] == "live_api_call"


def test_models_remote_helpers_and_mapping_branches(monkeypatch):
    monkeypatch.setenv("VENOM_REMOTE_MODELS_CATALOG_TTL_SECONDS", "bad")
    assert models_remote._env_int("VENOM_REMOTE_MODELS_CATALOG_TTL_SECONDS", 123) == 123
    monkeypatch.setenv("VENOM_REMOTE_MODELS_PROVIDER_PROBE_TTL_SECONDS", "1")
    assert models_remote._provider_probe_ttl_seconds() >= 10

    monkeypatch.setattr(SETTINGS, "OPENAI_API_TIMEOUT", 99.0, raising=False)
    assert models_remote._remote_timeout_seconds() == 20.0
    monkeypatch.setattr(SETTINGS, "OPENAI_API_TIMEOUT", 0.2, raising=False)
    assert models_remote._remote_timeout_seconds() == 1.0

    monkeypatch.setattr(
        SETTINGS,
        "OPENAI_CHAT_COMPLETIONS_ENDPOINT",
        "https://api.openai.com/v1/chat/completions",
        raising=False,
    )
    assert models_remote._openai_models_url() == "https://api.openai.com/v1/models"
    monkeypatch.setattr(
        SETTINGS,
        "OPENAI_CHAT_COMPLETIONS_ENDPOINT",
        "https://api.openai.com/v1",
        raising=False,
    )
    assert models_remote._openai_models_url() == "https://api.openai.com/v1/models"
    monkeypatch.setattr(
        SETTINGS,
        "OPENAI_CHAT_COMPLETIONS_ENDPOINT",
        "https://proxy.example.local/x/v1/router",
        raising=False,
    )
    assert (
        models_remote._openai_models_url() == "https://proxy.example.local/x/v1/models"
    )
    monkeypatch.setattr(SETTINGS, "OPENAI_CHAT_COMPLETIONS_ENDPOINT", "", raising=False)
    assert models_remote._openai_models_url() == "https://api.openai.com/v1/models"

    assert models_remote._openai_model_url("gpt-x").endswith("/gpt-x")
    assert models_remote._google_models_url().endswith("/v1beta/models")
    assert models_remote._google_model_url("gemini-1.5-pro").endswith(
        "/v1beta/models/gemini-1.5-pro"
    )
    assert models_remote._google_model_url("models/gemini-1.5-pro").endswith(
        "/v1beta/models/gemini-1.5-pro"
    )

    assert "function-calling" in models_remote._map_openai_capabilities("gpt-4.1")
    assert "vision" in models_remote._map_openai_capabilities("gpt-4o")
    assert models_remote._map_openai_capabilities("gpt-3.5-turbo") == [
        "chat",
        "text-generation",
    ]

    caps = models_remote._map_google_capabilities(
        {
            "name": "models/gemini-1.5-pro",
            "supportedGenerationMethods": [
                "generateContent",
                "streamGenerateContent",
                "countTokens",
                "embedContent",
            ],
        }
    )
    assert (
        "chat" in caps
        and "embeddings" in caps
        and "token-counting" in caps
        and "vision" in caps
    )
    assert models_remote._map_google_capabilities(
        {"name": "models/foo", "supportedGenerationMethods": []}
    ) == [
        "chat",
        "text-generation",
    ]


def test_models_remote_cache_get_expired_path():
    lock = models_remote.Lock()
    cache: dict[str, dict[str, object]] = {
        "foo": {"value": 1, "ts_monotonic": 0.0},
    }
    assert models_remote._cache_get(cache, lock, "missing", 10) is None
    out = models_remote._cache_get(cache, lock, "foo", 0)
    assert out is None
    assert "foo" not in cache


@pytest.mark.asyncio
async def test_fetch_live_catalog_and_validate_branches(monkeypatch):
    class _Resp:
        def __init__(self, status_code: int, payload: dict):
            self.status_code = status_code
            self._payload = payload

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(f"http {self.status_code}")

        def json(self):
            return self._payload

    class _Client:
        def __init__(self, responses):
            self._responses = responses
            self._idx = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, **kwargs):
            response = self._responses[self._idx]
            self._idx += 1
            return response

    monkeypatch.setattr(SETTINGS, "OPENAI_API_KEY", "test-openai-key", raising=False)
    monkeypatch.setattr(SETTINGS, "GOOGLE_API_KEY", "test-google-key", raising=False)

    # OpenAI list models
    monkeypatch.setattr(
        models_remote.httpx,
        "AsyncClient",
        lambda timeout: _Client([_Resp(200, {"data": [{"id": "gpt-4o"}, {"id": ""}]})]),
    )
    openai_models = await models_remote._fetch_openai_models_catalog_live()
    assert [m.id for m in openai_models] == ["gpt-4o"]

    # Google list models
    monkeypatch.setattr(
        models_remote.httpx,
        "AsyncClient",
        lambda timeout: _Client(
            [
                _Resp(
                    200,
                    {
                        "models": [
                            {
                                "name": "models/gemini-1.5-flash",
                                "supportedGenerationMethods": ["generateContent"],
                            },
                            {"name": ""},
                        ]
                    },
                )
            ]
        ),
    )
    google_models = await models_remote._fetch_google_models_catalog_live()
    assert [m.id for m in google_models] == ["gemini-1.5-flash"]

    # Validation success / unauthorized / not found / generic
    monkeypatch.setattr(
        models_remote.httpx,
        "AsyncClient",
        lambda timeout: _Client([_Resp(200, {})]),
    )
    valid, _, _ = await models_remote._validate_openai_connection()
    assert valid is True

    monkeypatch.setattr(
        models_remote.httpx,
        "AsyncClient",
        lambda timeout: _Client([_Resp(401, {})]),
    )
    valid, msg, _ = await models_remote._validate_openai_connection()
    assert valid is False and "unauthorized" in msg.lower()

    monkeypatch.setattr(
        models_remote.httpx,
        "AsyncClient",
        lambda timeout: _Client([_Resp(404, {})]),
    )
    valid, msg, _ = await models_remote._validate_openai_connection(
        model="missing-model"
    )
    assert valid is False and "not found" in msg.lower()

    monkeypatch.setattr(
        models_remote.httpx,
        "AsyncClient",
        lambda timeout: _Client([_Resp(500, {})]),
    )
    valid, msg, _ = await models_remote._validate_openai_connection()
    assert valid is False and "http 500" in msg.lower()

    # Exception path
    class _ErrClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, **kwargs):
            raise RuntimeError("network-down")

    monkeypatch.setattr(
        models_remote.httpx, "AsyncClient", lambda timeout: _ErrClient()
    )
    valid, msg, _ = await models_remote._validate_openai_connection()
    assert valid is False and "network-down" in msg

    # Google validation branches
    monkeypatch.setattr(
        models_remote.httpx,
        "AsyncClient",
        lambda timeout: _Client([_Resp(403, {})]),
    )
    valid, msg, _ = await models_remote._validate_google_connection()
    assert valid is False and "unauthorized" in msg.lower()

    monkeypatch.setattr(
        models_remote.httpx,
        "AsyncClient",
        lambda timeout: _Client([_Resp(404, {})]),
    )
    valid, msg, _ = await models_remote._validate_google_connection(
        model="gemini-missing"
    )
    assert valid is False and "not found" in msg.lower()
