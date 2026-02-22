"""Testy API dla endpointu /api/v1/system/llm-runtime/active."""

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from venom_core.api.routes import system_llm


@pytest.fixture
def test_app():
    app = FastAPI()
    app.include_router(system_llm.router)
    return app


@pytest.fixture
def client(test_app):
    return TestClient(test_app)


class TestLlmRuntimeActivationAPI:
    def test_activate_openai_runtime(self, client):
        with (
            patch.object(system_llm, "SETTINGS") as settings,
            patch.object(system_llm, "config_manager") as mock_manager,
            patch.object(system_llm, "get_active_llm_runtime") as mock_runtime,
            patch.object(system_llm, "_release_onnx_runtime_caches") as mock_release,
        ):
            settings.OPENAI_API_KEY = "sk-test"
            settings.GOOGLE_API_KEY = ""
            settings.OPENAI_GPT4O_MODEL = "gpt-4o"
            settings.GOOGLE_GEMINI_PRO_MODEL = "gemini-1.5-pro"
            settings.LLM_SERVICE_TYPE = "local"
            settings.LLM_MODEL_NAME = "phi3:latest"
            settings.LLM_LOCAL_ENDPOINT = "http://localhost:11434/v1"
            settings.LLM_LOCAL_API_KEY = "local"
            settings.AI_MODE = "HYBRID"
            settings.LLM_CONFIG_HASH = ""
            settings.ACTIVE_LLM_SERVER = ""

            mock_runtime.return_value = type(
                "Runtime",
                (),
                {
                    "provider": "openai",
                    "endpoint": "https://api.openai.com/v1",
                    "model_name": "gpt-4o-mini",
                    "config_hash": "hash-openai",
                    "runtime_id": "openai@cloud",
                },
            )()

            response = client.post(
                "/api/v1/system/llm-runtime/active",
                json={"provider": "openai", "model": "gpt-4o-mini"},
            )

            assert response.status_code == 200
            payload = response.json()
            assert payload["status"] == "success"
            assert payload["active_server"] == "openai"
            assert payload["active_model"] == "gpt-4o-mini"
            mock_manager.update_config.assert_called_once()
            mock_release.assert_called_once()

    def test_activate_google_missing_key(self, client):
        with patch.object(system_llm, "SETTINGS") as settings:
            settings.GOOGLE_API_KEY = ""
            response = client.post(
                "/api/v1/system/llm-runtime/active",
                json={"provider": "google"},
            )
            assert response.status_code == 400
            assert "GOOGLE_API_KEY" in response.json()["detail"]

    def test_activate_unknown_provider(self, client):
        response = client.post(
            "/api/v1/system/llm-runtime/active",
            json={"provider": "unknown"},
        )
        assert response.status_code == 400

    def test_activate_onnx_runtime(self, client):
        with (
            patch.object(system_llm, "SETTINGS") as settings,
            patch.object(system_llm, "config_manager") as mock_manager,
            patch.object(system_llm, "get_active_llm_runtime") as mock_runtime,
            patch.object(system_llm, "OnnxLlmClient") as mock_onnx_client,
        ):
            settings.LLM_SERVICE_TYPE = "local"
            settings.LLM_MODEL_NAME = "phi3:latest"
            settings.LLM_CONFIG_HASH = ""
            settings.ACTIVE_LLM_SERVER = ""
            settings.OPENAI_API_KEY = ""
            settings.GOOGLE_API_KEY = ""

            client_instance = mock_onnx_client.return_value
            client_instance.ensure_ready.return_value = None
            client_instance.config.model_path = "models/phi35-onnx"

            mock_runtime.return_value = type(
                "Runtime",
                (),
                {
                    "provider": "onnx",
                    "endpoint": None,
                    "model_name": "models/phi35-onnx",
                    "config_hash": "hash-onnx",
                    "runtime_id": "onnx@local",
                },
            )()

            response = client.post(
                "/api/v1/system/llm-runtime/active",
                json={"provider": "onnx"},
            )
            assert response.status_code == 200
            payload = response.json()
            assert payload["active_server"] == "onnx"
            mock_manager.update_config.assert_called_once()

    def test_activate_onnx_runtime_not_ready(self, client):
        with patch.object(system_llm, "OnnxLlmClient") as mock_onnx_client:
            mock_onnx_client.return_value.ensure_ready.side_effect = RuntimeError(
                "boom"
            )
            response = client.post(
                "/api/v1/system/llm-runtime/active",
                json={"provider": "onnx"},
            )
            assert response.status_code == 400
            assert "boom" in response.json()["detail"]
