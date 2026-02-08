"""Testy API dla endpointów tłumaczeń i news/papers."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from venom_core.api.routes import models as models_routes


@pytest.fixture
def test_app():
    app = FastAPI()
    app.include_router(models_routes.router)
    return app


@pytest.fixture
def client(test_app):
    return TestClient(test_app)


class DummyRegistry:
    async def list_news(self, provider, limit=5, kind="blog", month=None):
        await asyncio.sleep(0)
        return {
            "items": [
                {
                    "title": "Hello",
                    "summary": "World",
                    "published_at": "2025-12-01T12:00:00Z",
                    "authors": ["Author"],
                    "url": "https://example.com",
                }
            ],
            "stale": False,
            "error": None,
        }


def _set_registry(registry):
    models_routes.set_dependencies(model_manager=None, model_registry=registry)


class TestModelsTranslationAPI:
    def test_models_news_translates_items(self, client):
        _set_registry(DummyRegistry())
        with patch(
            "venom_core.api.routes.models.translation_service.translate_text",
            new=AsyncMock(side_effect=["PL-Title", "PL-Summary"]),
        ):
            response = client.get("/api/v1/models/news?provider=huggingface&lang=pl")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["items"][0]["title"] == "PL-Title"
        assert data["items"][0]["summary"] == "PL-Summary"

    def test_models_news_invalid_lang(self, client):
        _set_registry(DummyRegistry())
        response = client.get("/api/v1/models/news?provider=huggingface&lang=fr")
        assert response.status_code == 400

    def test_models_news_registry_error_returns_payload(self, client):
        class FailingRegistry:
            async def list_news(self, provider, limit=5, kind="blog", month=None):
                await asyncio.sleep(0)
                raise RuntimeError("registry error")

        _set_registry(FailingRegistry())
        response = client.get("/api/v1/models/news?provider=huggingface&lang=en")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["items"] == []
        assert data["error"] == "registry error"

    def test_translate_endpoint_success(self, client):
        _set_registry(DummyRegistry())
        with patch(
            "venom_core.api.routes.models.translation_service.translate_text",
            new=AsyncMock(return_value="Witaj świecie"),
        ):
            response = client.post(
                "/api/v1/translate",
                json={
                    "text": "Hello world",
                    "source_lang": "en",
                    "target_lang": "pl",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["translated_text"] == "Witaj świecie"
        assert data["target_lang"] == "pl"

    def test_translate_endpoint_invalid_lang(self, client):
        _set_registry(DummyRegistry())
        response = client.post(
            "/api/v1/translate",
            json={"text": "Hello", "target_lang": "fr"},
        )
        assert response.status_code == 400
