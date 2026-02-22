from fastapi import FastAPI
from fastapi.testclient import TestClient

from venom_core.api.routes import models_dependencies, models_registry_ops


class DummyModelManager:
    def __init__(self, result):
        self._result = result

    def build_onnx_llm_model(self, **_kwargs):
        return self._result


def _create_client(model_manager):
    app = FastAPI()
    models_dependencies.set_dependencies(
        model_manager=model_manager, model_registry=None
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
