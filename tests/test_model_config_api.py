"""Testy API dla endpointów konfiguracji parametrów generacji."""

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from venom_core.api.routes import models as models_routes
from venom_core.core.model_registry import GenerationParameter


@pytest.fixture
def test_app():
    app = FastAPI()
    app.include_router(models_routes.router)
    return app


@pytest.fixture
def client(test_app):
    return TestClient(test_app)


class DummyCaps:
    def __init__(self, generation_schema):
        self.generation_schema = generation_schema


class DummyRegistry:
    def __init__(self):
        self._schema = {
            "temperature": GenerationParameter(
                type="float",
                default=0.7,
                min=0.0,
                max=2.0,
            ),
            "max_tokens": GenerationParameter(
                type="int",
                default=256,
                min=1,
                max=2048,
            ),
        }

    def get_model_capabilities(self, model_name):
        return DummyCaps(self._schema)


def _set_registry(registry):
    models_routes.set_dependencies(model_manager=None, model_registry=registry)


class TestModelConfigAPI:
    def test_get_model_config_includes_current_values(self, client):
        _set_registry(DummyRegistry())
        with patch(
            "venom_core.api.routes.models.config_manager.get_config",
            return_value={
                "MODEL_GENERATION_OVERRIDES": '{"ollama":{"phi4:latest":{"temperature":1.1}}}'
            },
        ):
            response = client.get("/api/v1/models/phi4:latest/config?runtime=ollama")

        assert response.status_code == 200
        data = response.json()
        assert data["current_values"]["temperature"] == pytest.approx(1.1)
        assert data["current_values"]["max_tokens"] == 256

    def test_update_model_config_success(self, client):
        _set_registry(DummyRegistry())
        with (
            patch(
                "venom_core.api.routes.models.config_manager.get_config",
                return_value={"MODEL_GENERATION_OVERRIDES": ""},
            ),
            patch(
                "venom_core.api.routes.models.config_manager.update_config",
                return_value={"success": True},
            ),
        ):
            response = client.post(
                "/api/v1/models/phi4:latest/config",
                json={
                    "runtime": "ollama",
                    "params": {"temperature": 0.9, "max_tokens": 512},
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["params"]["temperature"] == pytest.approx(0.9)

    def test_update_model_config_unknown_param(self, client):
        _set_registry(DummyRegistry())
        response = client.post(
            "/api/v1/models/phi4:latest/config",
            json={"runtime": "ollama", "params": {"unknown": 123}},
        )
        assert response.status_code == 400
