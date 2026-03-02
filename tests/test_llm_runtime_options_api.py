"""Testy kontraktu endpointu /api/v1/system/llm-runtime/options."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from venom_core.api.routes import system_llm


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(system_llm.router)
    return TestClient(app)


def test_runtime_options_endpoint_returns_contract_snapshot() -> None:
    payload = {
        "status": "success",
        "active": {
            "runtime_id": "openai",
            "active_server": "openai",
            "active_model": "gpt-4o-mini",
            "active_endpoint": "https://api.openai.com/v1",
            "config_hash": "cfg-hash",
            "source_type": "cloud-api",
        },
        "runtimes": [
            {
                "runtime_id": "openai",
                "source_type": "cloud-api",
                "configured": True,
                "available": True,
                "status": "configured",
                "reason": None,
                "active": True,
                "models": [
                    {
                        "id": "gpt-4o-mini",
                        "name": "gpt-4o-mini",
                        "provider": "openai",
                        "runtime_id": "openai",
                        "source_type": "cloud-api",
                        "active": True,
                        "chat_compatible": True,
                    }
                ],
            }
        ],
    }

    with patch.object(
        system_llm,
        "_resolve_runtime_options_payload",
        new=AsyncMock(return_value=payload),
    ):
        response = _client().get("/api/v1/system/llm-runtime/options")
        assert response.status_code == 200
        assert response.json() == payload


def test_resolve_runtime_options_payload_mixed_modes() -> None:
    active_runtime = SimpleNamespace(
        provider="vllm",
        model_name="Qwen2.5-7B-Instruct",
        endpoint="http://127.0.0.1:8000/v1",
        config_hash="hash-local",
    )
    llm_controller = SimpleNamespace(
        list_servers=lambda: [
            {"name": "vllm", "status": "online"},
            {"name": "ollama", "status": "offline"},
        ]
    )
    local_targets = [
        {
            "runtime_id": "vllm",
            "source_type": "local-runtime",
            "configured": True,
            "available": True,
            "status": "online",
            "reason": None,
            "active": True,
            "models": [],
        }
    ]

    with (
        patch.object(system_llm, "get_active_llm_runtime", return_value=active_runtime),
        patch.object(
            system_llm.system_deps, "get_llm_controller", return_value=llm_controller
        ),
        patch.object(
            system_llm.system_deps, "get_model_manager", return_value=object()
        ),
        patch.object(
            system_llm,
            "_local_models_by_runtime",
            new=AsyncMock(return_value={"vllm": [], "ollama": [], "onnx": []}),
        ),
        patch.object(system_llm, "_local_runtime_targets", return_value=local_targets),
        patch.object(
            system_llm,
            "_cloud_runtime_target",
            new=AsyncMock(
                side_effect=[
                    {
                        "runtime_id": "openai",
                        "source_type": "cloud-api",
                        "configured": True,
                        "available": True,
                        "status": "configured",
                        "reason": None,
                        "active": False,
                        "models": [{"id": "gpt-4o-mini", "name": "gpt-4o-mini"}],
                    },
                    {
                        "runtime_id": "google",
                        "source_type": "cloud-api",
                        "configured": False,
                        "available": False,
                        "status": "disabled",
                        "reason": "GOOGLE_API_KEY not configured",
                        "active": False,
                        "models": [{"id": "gemini-1.5-pro", "name": "gemini-1.5-pro"}],
                    },
                ]
            ),
        ),
    ):
        payload = _client().get("/api/v1/system/llm-runtime/options").json()

    assert payload["status"] == "success"
    assert payload["active"]["runtime_id"] == "vllm"
    runtimes = {item["runtime_id"]: item for item in payload["runtimes"]}
    assert runtimes["vllm"]["source_type"] == "local-runtime"
    assert runtimes["openai"]["configured"] is True
    assert runtimes["google"]["configured"] is False
    assert runtimes["google"]["reason"] == "GOOGLE_API_KEY not configured"
    assert (
        payload["feedback_loop"]["requested_alias"] == "OpenCodeInterpreter-Qwen2.5-7B"
    )


def test_runtime_options_returns_503_when_llm_controller_missing() -> None:
    with patch.object(system_llm.system_deps, "get_llm_controller", return_value=None):
        response = _client().get("/api/v1/system/llm-runtime/options")

    assert response.status_code == 503
    assert "LLMController" in response.json().get("detail", "")


def test_runtime_options_returns_503_when_model_manager_missing() -> None:
    llm_controller = SimpleNamespace(list_servers=lambda: [])
    with (
        patch.object(
            system_llm.system_deps, "get_llm_controller", return_value=llm_controller
        ),
        patch.object(system_llm.system_deps, "get_model_manager", return_value=None),
    ):
        response = _client().get("/api/v1/system/llm-runtime/options")

    assert response.status_code == 503
    assert "ModelManager" in response.json().get("detail", "")


def test_runtime_model_payload_contains_feedback_loop_metadata() -> None:
    payload = system_llm._runtime_model_payload(  # noqa: SLF001
        runtime_id="ollama",
        model_id="qwen2.5-coder:7b",
        name="qwen2.5-coder:7b",
        provider="ollama",
        active=False,
        source_type="local-runtime",
    )
    assert payload["feedback_loop_ready"] is True
    assert payload["feedback_loop_tier"] == "primary"
