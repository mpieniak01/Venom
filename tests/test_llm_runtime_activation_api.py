"""Testy API dla endpointu /api/v1/system/llm-runtime/active."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from venom_core.api.routes import system_llm
from venom_core.utils.mode_contracts import MODE_CONTRACTS


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
            patch.object(
                system_llm,
                "_resolve_validated_cloud_model",
                new=AsyncMock(return_value="gpt-4o-mini"),
            ),
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
            assert payload["source_type"] == "cloud-api"
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
            assert payload["source_type"] == "local-runtime"
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

    def test_get_active_server_includes_switch_policy_and_last_event(self, client):
        with (
            patch.object(system_llm, "get_active_llm_runtime") as mock_runtime,
            patch.object(system_llm, "config_manager") as mock_manager,
            patch.object(
                system_llm,
                "get_runtime_switch_guard_status",
                return_value={
                    "allowed_sources": ["make_start", "ui"],
                    "ownership_token_configured": True,
                },
            ),
            patch.object(
                system_llm,
                "get_last_runtime_switch_event",
                return_value={
                    "event": "runtime_model_selected",
                    "source": "ui",
                    "runtime": "multi_runtime",
                    "model": "google/gemma-4-E2B-it",
                    "at_utc": "2026-05-18T10:00:00+00:00",
                },
            ),
        ):
            mock_runtime.return_value = type(
                "Runtime",
                (),
                {
                    "provider": "multi_runtime",
                    "endpoint": "http://127.0.0.1:8014/v1",
                    "model_name": "google/gemma-4-E2B-it",
                    "config_hash": "hash-1",
                    "runtime_id": "multi_runtime@local",
                },
            )()
            mock_manager.get_config.return_value = {}

            response = client.get("/api/v1/system/llm-servers/active")
            assert response.status_code == 200
            payload = response.json()
            assert (
                payload["runtime_switch_policy"]["ownership_token_configured"] is True
            )
            assert payload["last_runtime_switch"]["runtime"] == "multi_runtime"
            assert payload["mode_contracts"] == MODE_CONTRACTS

    def test_get_active_runtime_info_includes_switch_policy_and_last_event(
        self, client
    ):
        with (
            patch.object(system_llm, "get_active_llm_runtime") as mock_runtime,
            patch.object(
                system_llm, "detect_runtime_drift", return_value={"drift": "no"}
            ),
            patch.object(
                system_llm,
                "get_runtime_switch_guard_status",
                return_value={
                    "allowed_sources": ["make_start", "ui"],
                    "ownership_token_configured": False,
                },
            ),
            patch.object(
                system_llm,
                "get_last_runtime_switch_event",
                return_value=None,
            ),
        ):
            mock_runtime.return_value = type(
                "Runtime",
                (),
                {
                    "to_payload": lambda self: {"runtime_id": "multi_runtime@local"},
                },
            )()

            response = client.get("/api/v1/system/llm-runtime/active")
            assert response.status_code == 200
            assert response.json()["mode_contracts"] == MODE_CONTRACTS
            payload = response.json()
            assert payload["runtime_switch_policy"]["allowed_sources"] == [
                "make_start",
                "ui",
            ]
            assert payload["last_runtime_switch"] is None


def test_previous_model_key_for_server():
    assert (
        system_llm._previous_model_key_for_server("ollama") == "PREVIOUS_MODEL_OLLAMA"
    )  # noqa: SLF001
    assert system_llm._previous_model_key_for_server("vllm") == "PREVIOUS_MODEL_VLLM"  # noqa: SLF001
    assert system_llm._previous_model_key_for_server("onnx") == "PREVIOUS_MODEL_ONNX"  # noqa: SLF001


def test_rejects_cloud_model_not_in_catalog(client):
    with (
        patch.object(system_llm, "SETTINGS") as settings,
        patch.object(system_llm, "_release_onnx_runtime_caches"),
        patch.object(
            system_llm,
            "_catalog_for_cloud_provider",
            new=AsyncMock(
                return_value=(
                    [
                        {
                            "id": "gpt-4o-mini",
                            "name": "gpt-4o-mini",
                            "model_alias": "gpt-4o-mini",
                        }
                    ],
                    "static",
                    None,
                )
            ),
        ),
    ):
        settings.OPENAI_API_KEY = "sk-test"
        settings.GOOGLE_API_KEY = ""
        settings.OPENAI_GPT4O_MODEL = "gpt-4o-mini"
        settings.GOOGLE_GEMINI_PRO_MODEL = "gemini-1.5-pro"

        response = client.post(
            "/api/v1/system/llm-runtime/active",
            json={"provider": "openai", "model": "non-existent-model"},
        )
        assert response.status_code == 400
        assert "katalogu providera 'openai'" in response.json()["detail"]


def test_runtime_queue_snapshot_includes_queue_and_scope_metrics(client):
    runtime = type(
        "Runtime",
        (),
        {
            "provider": "ollama",
            "to_payload": lambda self: {
                "provider": "ollama",
                "runtime_id": "ollama@local",
            },
        },
    )()
    orchestrator = type(
        "Orchestrator",
        (),
        {"get_queue_status": lambda self: {"paused": False, "pending": 2, "active": 1}},
    )()
    controller = type(
        "Controller",
        (),
        {"get_metrics": lambda self, scope=None: {"scope": scope, "requests": 3}},
    )()

    with (
        patch.object(system_llm, "get_active_llm_runtime", return_value=runtime),
        patch.object(
            system_llm.system_deps, "get_orchestrator", return_value=orchestrator
        ),
        patch.object(
            system_llm.traffic_control_service,
            "get_traffic_controller",
            return_value=controller,
        ),
    ):
        response = client.get("/api/v1/system/llm-runtime/queue-snapshot")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["runtime"]["provider"] == "ollama"
    assert payload["queue"]["status"]["pending"] == 2
    assert payload["queue"]["error"] is None
    assert "outbound:ollama" in payload["traffic"]["scopes"]
    assert payload["traffic"]["error"] is None


def test_runtime_queue_snapshot_reports_missing_orchestrator(client):
    runtime = type(
        "Runtime",
        (),
        {
            "provider": "multi_runtime",
            "to_payload": lambda self: {
                "provider": "multi_runtime",
                "runtime_id": "multi_runtime@local",
            },
        },
    )()
    controller = type(
        "Controller",
        (),
        {"get_metrics": lambda self, scope=None: {"scope": scope}},
    )()

    with (
        patch.object(system_llm, "get_active_llm_runtime", return_value=runtime),
        patch.object(system_llm.system_deps, "get_orchestrator", return_value=None),
        patch.object(
            system_llm.traffic_control_service,
            "get_traffic_controller",
            return_value=controller,
        ),
    ):
        response = client.get("/api/v1/system/llm-runtime/queue-snapshot")

    assert response.status_code == 200
    payload = response.json()
    assert payload["queue"]["status"] is None
    assert payload["queue"]["error"] == "Orchestrator not available"
