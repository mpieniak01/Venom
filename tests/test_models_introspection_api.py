"""Tests for the model introspection snapshot endpoint."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from venom_core.api.routes import models as models_routes
from venom_core.api.routes import models_dependencies


class DummyModelManager:
    def __init__(self, metrics: dict[str, object] | None = None) -> None:
        self._metrics = metrics or {
            "models_count": 2,
            "memory_usage_mb": 512.0,
            "vram_usage_mb": 2048.0,
        }
        self.calls = 0

    async def get_usage_metrics(self) -> dict[str, object]:
        self.calls += 1
        return self._metrics


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(models_routes.router)
    return TestClient(app)


def test_model_introspection_includes_runtime_packages() -> None:
    dummy_manager = DummyModelManager()
    models_dependencies.set_dependencies(model_manager=dummy_manager)

    client = _client()
    response = client.get("/api/v1/models/introspection")

    assert response.status_code == 200
    payload = response.json()
    snapshot = payload["snapshot"]
    assert payload["success"] is True
    assert snapshot["summary"]["introspection_ready"] is True
    assert snapshot["reuse"]["brain"]["path"] == "/brain"
    assert snapshot["reuse"]["diagnostics"][0]["id"] == "217da"
    assert snapshot["model_manager"]["available"] is True
    assert snapshot["model_manager"]["usage_metrics"]["models_count"] == 2
    assert snapshot["graph"]["summary"]["nodes"] >= 1
    assert snapshot["graph"]["summary"]["edges"] >= 1
    assert dummy_manager.calls == 1
    assert "transformer-lens" in snapshot["packages"]
    assert "captum" in snapshot["packages"]
    assert "circuitsvis" in snapshot["packages"]


def test_model_introspection_survives_missing_model_manager() -> None:
    models_dependencies.set_dependencies(model_manager=None)

    client = _client()
    response = client.get("/api/v1/models/introspection")

    assert response.status_code == 200
    snapshot = response.json()["snapshot"]
    assert snapshot["model_manager"]["available"] is False
    assert snapshot["model_manager"]["usage_metrics"] is None
