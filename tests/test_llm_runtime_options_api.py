"""Testy kontraktu endpointu /api/v1/system/llm-runtime/options."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from venom_core.api.routes import system_llm


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(system_llm.router)
    return TestClient(app)


def _runtime_vllm_dir(tmp_path: Path, name: str) -> Path:
    model_dir = tmp_path / name
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "config.json").write_text("{}", encoding="utf-8")
    (model_dir / "model.safetensors").write_text("x", encoding="utf-8")
    return model_dir


def _local_model_entry(
    *,
    name: str,
    provider: str,
    path: Path,
    source: str,
    chat_compatible: bool = True,
) -> dict[str, object]:
    return {
        "name": name,
        "provider": provider,
        "path": str(path),
        "source": source,
        "chat_compatible": chat_compatible,
    }


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
    service_monitor = SimpleNamespace(get_all_services=lambda: [])
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
            system_llm.system_deps, "get_service_monitor", return_value=service_monitor
        ),
        patch.object(
            system_llm.system_deps, "get_model_manager", return_value=object()
        ),
        patch.object(
            system_llm,
            "_local_models_by_runtime",
            new=AsyncMock(return_value=({"vllm": [], "ollama": [], "onnx": []}, [])),
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
    assert payload["model_audit"]["issues_count"] == 0
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
    assert payload["model_kind"] == "base_model"
    assert payload["is_adapter_artifact"] is False


def test_runtime_model_payload_marks_adapter_artifact() -> None:
    payload = system_llm._runtime_model_payload(  # noqa: SLF001
        runtime_id="ollama",
        model_id="venom-adapter-self_learning_123:latest",
        name="venom-adapter-self_learning_123:latest",
        provider="ollama",
        active=False,
        source_type="local-runtime",
    )
    assert payload["model_kind"] == "adapter_artifact"
    assert payload["is_adapter_artifact"] is True


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


def test_build_model_catalog_inference_artifacts_come_from_explicit_flag() -> None:
    runtime_targets = [
        {
            "runtime_id": "ollama",
            "models": [
                {
                    "name": "gemma3:4b",
                    "is_adapter_artifact": False,
                    "chat_compatible": True,
                },
                {
                    "name": "venom-adapter-self_learning_abc:latest",
                    "is_adapter_artifact": True,
                    "chat_compatible": True,
                },
            ],
        }
    ]
    catalog = system_llm._build_model_catalog(  # noqa: SLF001
        runtime_targets=runtime_targets,
        trainable_models=[],
    )
    assert [item["name"] for item in catalog["inference_only_artifacts"]] == [
        "venom-adapter-self_learning_abc:latest"
    ]


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
    assert payload["supports_native_training"] is False
    assert payload["supports_adapter_import_safetensors"] is False
    assert payload["supports_adapter_import_gguf"] is False
    assert payload["supports_adapter_runtime_apply"] is True


def test_runtime_target_payload_contains_onnx_adapter_deploy_capability() -> None:
    active_runtime = SimpleNamespace(provider="onnx")
    payload = system_llm._runtime_target_payload(  # noqa: SLF001
        runtime_id="onnx",
        source_type="local-runtime",
        configured=True,
        available=True,
        status="online",
        reason=None,
        models=[],
        active_runtime=active_runtime,
    )
    assert payload["adapter_deploy_supported"] is True
    assert payload["adapter_deploy_mode"] == "onnx_merge_export_runtime_model"
    assert payload["supports_native_training"] is False
    assert payload["supports_adapter_import_safetensors"] is False
    assert payload["supports_adapter_import_gguf"] is False
    assert payload["supports_adapter_runtime_apply"] is True


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


@pytest.mark.asyncio
async def test_local_models_by_runtime_skips_non_runtime_vllm_entries(
    tmp_path: Path,
) -> None:
    valid_runtime_dir = _runtime_vllm_dir(tmp_path, "runtime-vllm")
    plain_dir = tmp_path / "plain-folder"
    plain_dir.mkdir(parents=True)

    settings = SimpleNamespace(REPO_ROOT=str(tmp_path))
    active_runtime = SimpleNamespace(provider="vllm", model_name="good-model")
    local_models = [
        _local_model_entry(
            name="good-model",
            provider="vllm",
            path=valid_runtime_dir,
            source="vllm",
        ),
        _local_model_entry(
            name="plain-folder",
            provider="vllm",
            path=plain_dir,
            source="models",
        ),
    ]

    with (
        patch.object(system_llm, "SETTINGS", settings),
        patch.object(system_llm, "get_active_llm_runtime", return_value=active_runtime),
    ):
        grouped, audit = await system_llm._local_models_by_runtime(  # noqa: SLF001
            model_manager=object(),
            local_models=local_models,
        )

    assert [model["name"] for model in grouped["vllm"]] == ["good-model"]
    assert any(
        item.get("name") == "plain-folder"
        and item.get("reason") == "not_runtime_loadable_for_vllm"
        for item in audit
    )


@pytest.mark.asyncio
async def test_local_models_by_runtime_reports_unknown_provider_issue(
    tmp_path: Path,
) -> None:
    weird_dir = tmp_path / "weird-model"
    weird_dir.mkdir(parents=True)
    settings = SimpleNamespace(REPO_ROOT=str(tmp_path))
    active_runtime = SimpleNamespace(provider="vllm", model_name="")
    local_models = [
        _local_model_entry(
            name="mystery-model",
            provider="custom-provider",
            path=weird_dir,
            source="custom-source",
        )
    ]

    with (
        patch.object(system_llm, "SETTINGS", settings),
        patch.object(system_llm, "get_active_llm_runtime", return_value=active_runtime),
    ):
        grouped, audit = await system_llm._local_models_by_runtime(  # noqa: SLF001
            model_manager=object(),
            local_models=local_models,
        )

    assert grouped == {"ollama": [], "vllm": [], "onnx": []}
    assert audit == [
        {
            "name": "mystery-model",
            "path": str(weird_dir),
            "source": "custom-source",
            "reason": "provider_unknown",
        }
    ]
