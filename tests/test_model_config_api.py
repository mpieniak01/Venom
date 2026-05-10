"""Testy API dla endpointów konfiguracji parametrów generacji."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from venom_core.api.routes import models as models_routes
from venom_core.core.model_registry import GenerationParameter
from venom_core.core.model_registry_types import ModelProvider


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
        ollama_client = type("DummyOllamaClient", (), {})()
        ollama_client.get_model_show = AsyncMock(
            side_effect=lambda model_name: {
                "capabilities": [
                    "completion",
                    "vision",
                    "audio",
                    "tools",
                    "thinking",
                ]
                if model_name == "gemma4:latest"
                else [],
                "details": {
                    "family": "gemma4",
                    "parameter_size": "8.0B",
                    "quantization_level": "Q4_K_M",
                },
                "model_info": {"gemma4.context_length": 131072},
            }
        )

        async def _chat(payload):
            messages = payload.get("messages") or []
            content = (messages[-1].get("content") if messages else "") or ""
            if payload.get("think"):
                return {
                    "message": {
                        "role": "assistant",
                        "thinking": "r probe",
                        "content": "There are 2 r letters.",
                    }
                }
            if payload.get("tools"):
                return {
                    "message": {
                        "role": "assistant",
                        "tool_calls": [
                            {"function": {"name": "noop_status", "arguments": {}}}
                        ],
                        "content": "",
                    }
                }
            if messages and messages[-1].get("images"):
                return {
                    "message": {
                        "role": "assistant",
                        "content": "A tiny image.",
                    }
                }
            return {"message": {"role": "assistant", "content": content or "ok"}}

        ollama_client.chat = AsyncMock(side_effect=_chat)
        self.providers = {
            ModelProvider.OLLAMA: type(
                "DummyOllamaProvider",
                (),
                {"endpoint": "http://localhost:11434", "client": ollama_client},
            )()
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

    def test_get_model_runtime_capabilities(self, client):
        _set_registry(DummyRegistry())
        response = client.get("/api/v1/models/gemma4:latest/runtime-capabilities")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert (
            data["runtime_capabilities"]["compatibility_profile"] == "multimodal_audio"
        )
        assert data["runtime_capabilities"]["capabilities"]["audio_input"] is True
        assert data["runtime_capabilities"]["fallbacks"]["stt"] == "faster_whisper"
