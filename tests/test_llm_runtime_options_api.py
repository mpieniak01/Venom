"""Testy kontraktu endpointu /api/v1/system/llm-runtime/options."""

from __future__ import annotations

from pathlib import Path
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
            "_load_trainable_model_catalog",
            new=AsyncMock(
                return_value=[
                    {
                        "model_id": "unsloth/Phi-3-mini-4k-instruct",
                        "canonical_model_id": "unsloth/Phi-3-mini-4k-instruct",
                        "coding_eligible": False,
                        "trainable": True,
                    }
                ]
            ),
        ),
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
    assert "model_catalog" in payload
    assert "trainable_models" in payload["model_catalog"]
    assert "coding_models" in payload["model_catalog"]
    assert payload["model_catalog"]["trainable_models"][0]["model_id"] == (
        "unsloth/Phi-3-mini-4k-instruct"
    )
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


def test_runtime_model_payload_contains_alias_and_canonical_for_gemma() -> None:
    payload = system_llm._runtime_model_payload(  # noqa: SLF001
        runtime_id="ollama",
        model_id="gemma3:latest",
        name="gemma3:latest",
        provider="ollama",
        active=False,
        source_type="local-runtime",
    )
    assert payload["canonical_model_id"] == "gemma-3-4b-it"
    assert "gemma3:latest" in payload["aliases"]
    assert "gemma-3-4b-it" in payload["aliases"]
    assert payload["ownership_status"] == "unknown"
    assert payload["compatible_runtimes"] == []


def test_build_model_catalog_enriches_compatible_runtimes() -> None:
    runtime_targets = [
        {
            "runtime_id": "vllm",
            "models": [
                {
                    "name": "unsloth/Phi-3-mini-4k-instruct",
                    "chat_compatible": True,
                }
            ],
        }
    ]
    trainable_models = [
        {
            "model_id": "unsloth/Phi-3-mini-4k-instruct",
            "canonical_model_id": "unsloth/Phi-3-mini-4k-instruct",
            "runtime_compatibility": {"vllm": True, "ollama": False},
        }
    ]

    catalog = system_llm._build_model_catalog(  # noqa: SLF001
        runtime_targets=runtime_targets,
        trainable_models=trainable_models,
    )
    assert catalog["all_models"][0]["compatible_runtimes"] == ["vllm"]


def test_runtime_target_payload_contains_adapter_deploy_capability() -> None:
    active_runtime = SimpleNamespace(provider="vllm")
    payload = system_llm._runtime_target_payload(  # noqa: SLF001
        runtime_id="vllm",
        source_type="local-runtime",
        configured=True,
        available=True,
        status="online",
        reason=None,
        models=[],
        active_runtime=active_runtime,
    )
    assert payload["adapter_deploy_supported"] is True
    assert payload["adapter_deploy_mode"] == "vllm_exported_runtime_model"


def test_apply_vllm_runtime_autofix_updates_invalid_config(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtime-vllm"
    runtime_dir.mkdir(parents=True)
    (runtime_dir / "config.json").write_text("{}", encoding="utf-8")
    (runtime_dir / "model.safetensors").write_text("x", encoding="utf-8")
    settings = SimpleNamespace(
        REPO_ROOT=str(tmp_path),
        VLLM_ENDPOINT="http://127.0.0.1:8000/v1",
        LLM_SERVICE_TYPE="local",
        ACTIVE_LLM_SERVER="vllm",
        LLM_MODEL_NAME="broken-model",
        HYBRID_LOCAL_MODEL="broken-model",
        LAST_MODEL_VLLM="broken-model",
        VLLM_MODEL_PATH="/tmp/missing",
        VLLM_SERVED_MODEL_NAME="broken-model",
        LLM_CONFIG_HASH=None,
    )
    local_models = [
        {
            "name": "good-model",
            "provider": "vllm",
            "path": str(runtime_dir),
            "chat_compatible": True,
        }
    ]
    active_runtime = SimpleNamespace(provider="vllm", model_name="broken-model")
    config = {
        "ACTIVE_LLM_SERVER": "vllm",
        "LLM_MODEL_NAME": "broken-model",
        "LAST_MODEL_VLLM": "good-model",
        "VLLM_MODEL_PATH": "/tmp/missing",
    }

    with (
        patch.object(system_llm, "SETTINGS", settings),
        patch.object(system_llm, "get_active_llm_runtime", return_value=active_runtime),
        patch.object(system_llm.config_manager, "get_config", return_value=config),
        patch.object(system_llm.config_manager, "update_config") as update_cfg,
        patch.object(system_llm, "compute_llm_config_hash", return_value="cfg-healed"),
    ):
        result = system_llm._apply_vllm_runtime_autofix(local_models=local_models)  # noqa: SLF001

    assert result is not None
    assert result["healed"] is True
    assert result["selected_model"] == "good-model"
    update_cfg.assert_called_once()
