from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from venom_core.api.routes import models_dependencies, models_registry_ops


class DummyModelManager:
    def __init__(self, result):
        self._result = result

    def build_onnx_llm_model(self, **_kwargs):
        return self._result


class DummyRuntimeModelManager:
    def __init__(self, local_models):
        self._local_models = local_models

    async def list_local_models(self):
        return self._local_models


class DummyModelRegistry:
    def __init__(self, activate_result: bool = True):
        self.activate_result = activate_result
        self.calls: list[tuple[str, str]] = []

    async def activate_model(self, model_name: str, runtime: str):
        self.calls.append((model_name, runtime))
        return self.activate_result


def _create_client(model_manager, model_registry=None):
    app = FastAPI()
    models_dependencies.set_dependencies(
        model_manager=model_manager, model_registry=model_registry
    )
    app.include_router(models_registry_ops.router)
    return TestClient(app)


def test_build_onnx_model_success():
    client = _create_client(
        DummyModelManager(
            {
                "success": True,
                "message": "ok",
                "output_dir": "/tmp/model",
            }
        )
    )
    response = client.post(
        "/api/v1/models/onnx/build",
        json={
            "model_name": "microsoft/Phi-3.5-mini-instruct",
            "execution_provider": "cuda",
            "precision": "int4",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True


def test_build_onnx_model_returns_400_on_pipeline_error():
    client = _create_client(
        DummyModelManager(
            {
                "success": False,
                "message": "build failed",
            }
        )
    )
    response = client.post(
        "/api/v1/models/onnx/build",
        json={
            "model_name": "microsoft/Phi-3.5-mini-instruct",
            "execution_provider": "cuda",
            "precision": "int4",
        },
    )
    assert response.status_code == 400
    assert "build failed" in response.json()["detail"]


def test_activate_model_rejects_non_servable_runtime_model():
    registry = DummyModelRegistry()
    manager = DummyRuntimeModelManager(
        [
            {
                "name": "qwen2.5:7b",
                "provider": "vllm",
                "chat_compatible": True,
            }
        ]
    )
    client = _create_client(manager, registry)
    response = client.post(
        "/api/v1/models/activate",
        json={"name": "missing-model", "runtime": "vllm"},
    )
    assert response.status_code == 400
    assert "not available" in response.json()["detail"]
    assert registry.calls == []


def test_activate_model_returns_runtime_payload_when_successful():
    local_models = [
        {
            "name": "qwen2.5:7b",
            "provider": "vllm",
            "chat_compatible": True,
        }
    ]
    manager = DummyRuntimeModelManager(local_models)
    registry = DummyModelRegistry(activate_result=True)
    client = _create_client(manager, registry)
    runtime_info = SimpleNamespace(
        to_payload=lambda: {"runtime_id": "vllm", "active_model": "qwen2.5:7b"}
    )
    with (
        patch(
            "venom_core.utils.llm_runtime.get_active_llm_runtime",
            return_value=runtime_info,
        ),
        patch(
            "venom_core.utils.llm_runtime.probe_runtime_status",
            new=AsyncMock(return_value=("online", None)),
        ),
    ):
        response = client.post(
            "/api/v1/models/activate",
            json={"name": "qwen2.5:7b", "runtime": "vllm"},
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["runtime"]["status"] == "online"
    assert registry.calls == [("qwen2.5:7b", "vllm")]
