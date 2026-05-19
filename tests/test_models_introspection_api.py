"""Tests for the model introspection snapshot endpoint."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from venom_core.api.routes import models as models_routes
from venom_core.api.routes import models_dependencies
from venom_core.services import model_introspection_service as snapshot_service


@pytest.fixture(autouse=True)
def _cleanup_model_dependencies() -> None:
    yield
    models_dependencies.set_dependencies(model_manager=None)


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
    assert snapshot["summary"]["introspection_level"] in {"full", "lite", "none"}
    assert snapshot["introspection_level"] in {"full", "lite", "none"}
    assert snapshot["reuse"]["brain"]["path"] == "/brain"
    assert snapshot["reuse"]["diagnostics"][0]["id"] == "217da"
    assert snapshot["model_manager"]["available"] is True
    assert snapshot["model_manager"]["usage_metrics"]["models_count"] == 2
    assert snapshot["graph"]["summary"]["nodes"] >= 1
    assert snapshot["graph"]["summary"]["edges"] >= 1
    assert "probe" in snapshot
    assert "status" in snapshot["probe"]
    assert "profile" in snapshot["probe"]
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


@pytest.mark.asyncio
async def test_collect_model_manager_usage_captures_error() -> None:
    class _FailingModelManager:
        async def get_usage_metrics(self) -> dict[str, object]:
            raise RuntimeError("metrics unavailable")

    payload = await snapshot_service._collect_model_manager_usage(
        _FailingModelManager()
    )
    assert payload["available"] is True
    assert payload["usage_metrics"] is None
    assert "metrics unavailable" in str(payload["error"])


def test_probe_package_handles_version_lookup_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        snapshot_service.importlib.util, "find_spec", lambda _name: object()
    )

    def _raise_pkg_not_found(_pkg: str) -> str:
        raise snapshot_service.importlib.metadata.PackageNotFoundError

    monkeypatch.setattr(
        snapshot_service.importlib.metadata, "version", _raise_pkg_not_found
    )
    probe = snapshot_service._probe_package("x.module", "x-package")
    assert probe["available"] is True
    assert probe["version"] is None

    def _raise_generic(_pkg: str) -> str:
        raise RuntimeError("broken metadata")

    monkeypatch.setattr(snapshot_service.importlib.metadata, "version", _raise_generic)
    probe_generic = snapshot_service._probe_package("x.module", "x-package")
    assert probe_generic["available"] is True
    assert probe_generic["version"] is None


def test_resolve_snapshot_introspection_level_full_and_none() -> None:
    full = snapshot_service._resolve_snapshot_introspection_level(
        runtime_provider="multi_runtime",
        probe_health={
            "enabled": True,
            "runtime_supported": True,
            "endpoint_configured": True,
            "model_whitelisted": True,
            "healthy": True,
        },
    )
    assert full == "full"

    none = snapshot_service._resolve_snapshot_introspection_level(
        runtime_provider="multi_runtime",
        probe_health={
            "enabled": True,
            "runtime_supported": True,
            "endpoint_configured": True,
            "model_whitelisted": False,
            "healthy": True,
        },
    )
    assert none == "none"
