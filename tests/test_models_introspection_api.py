"""Tests for the model introspection snapshot endpoint."""

from __future__ import annotations

import json
from pathlib import Path

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
    def __init__(
        self,
        metrics: dict[str, object] | None = None,
        models_dir: Path | None = None,
    ) -> None:
        self._metrics = metrics or {
            "models_count": 2,
            "memory_usage_mb": 512.0,
            "vram_usage_mb": 2048.0,
        }
        self.models_dir = models_dir or Path("./data/models")
        self.calls = 0

    async def get_usage_metrics(self) -> dict[str, object]:
        self.calls += 1
        return self._metrics


def _write_native_architecture_fixture(models_dir: Path) -> None:
    runtime_dir = models_dir / "self_learning_test" / "runtime_vllm"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    (runtime_dir / "config.json").write_text(
        json.dumps(
            {
                "architectures": ["Gemma3ForConditionalGeneration"],
                "model_type": "gemma3",
                "hidden_size": 2304,
                "intermediate_size": 9216,
                "num_attention_heads": 8,
                "num_key_value_heads": 4,
                "num_hidden_layers": 3,
                "head_dim": 256,
                "sliding_window": 4096,
                "layer_types": [
                    "sliding_attention",
                    "full_attention",
                    "sliding_attention",
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (runtime_dir / "venom_runtime_vllm.json").write_text(
        json.dumps(
            {
                "base_model": "google/gemma-3-4b-it",
                "adapter_path": str(models_dir / "self_learning_test" / "adapter"),
                "runtime": "vllm",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(models_routes.router)
    return TestClient(app)


def test_model_introspection_includes_runtime_packages() -> None:
    models_dir = Path("tests/.tmp-model-introspection-models")
    models_dir.mkdir(parents=True, exist_ok=True)
    _write_native_architecture_fixture(models_dir)
    dummy_manager = DummyModelManager(models_dir=models_dir)
    models_dependencies.set_dependencies(model_manager=dummy_manager)

    class _DummyRuntime:
        def to_payload(self) -> dict[str, object]:
            return {
                "provider": "multi_runtime",
                "model": "google/gemma-3-4b-it",
                "endpoint": "http://localhost:8014/v1",
                "service_type": "local",
                "mode": "LOCAL",
                "label": "local-test-model · multi_runtime @ localhost:8014",
                "config_hash": "local-test",
                "runtime_id": "multi_runtime@http://localhost:8014/v1",
            }

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        snapshot_service,
        "get_active_llm_runtime",
        lambda _settings=None: _DummyRuntime(),
    )
    monkeypatch.setattr(
        snapshot_service,
        "detect_runtime_drift",
        lambda _settings=None: {
            "drift_detected": False,
            "active_server": "multi_runtime",
            "inferred_provider": "multi_runtime",
            "model_name": "google/gemma-3-4b-it",
            "endpoint": "http://localhost:8014/v1",
            "issues": [],
        },
    )

    client = _client()
    try:
        response = client.get("/api/v1/models/introspection")
    finally:
        monkeypatch.undo()

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
    assert snapshot["architecture_graph"]["meta"]["fidelity"] == "native"
    assert snapshot["architecture_graph"]["meta"]["source"] == "native runtime config"
    assert snapshot["architecture_graph"]["summary"]["layer_count"] == 3
    assert snapshot["architecture_graph"]["summary"]["block_count"] == 3


def test_model_introspection_falls_back_to_derived_for_model_mismatch() -> None:
    models_dir = Path("tests/.tmp-model-introspection-models")
    models_dir.mkdir(parents=True, exist_ok=True)
    _write_native_architecture_fixture(models_dir)
    dummy_manager = DummyModelManager(models_dir=models_dir)
    models_dependencies.set_dependencies(model_manager=dummy_manager)

    class _DummyRuntime:
        def to_payload(self) -> dict[str, object]:
            return {
                "provider": "multi_runtime",
                "model": "google/local-test-model",
                "endpoint": "http://localhost:8014/v1",
                "service_type": "local",
                "mode": "LOCAL",
                "label": "local-test-model · multi_runtime @ localhost:8014",
                "config_hash": "local-test",
                "runtime_id": "multi_runtime@http://localhost:8014/v1",
            }

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        snapshot_service,
        "get_active_llm_runtime",
        lambda _settings=None: _DummyRuntime(),
    )
    monkeypatch.setattr(
        snapshot_service,
        "detect_runtime_drift",
        lambda _settings=None: {
            "drift_detected": False,
            "active_server": "multi_runtime",
            "inferred_provider": "multi_runtime",
            "model_name": "google/local-test-model",
            "endpoint": "http://localhost:8014/v1",
            "issues": [],
        },
    )

    client = _client()
    try:
        response = client.get("/api/v1/models/introspection")
    finally:
        monkeypatch.undo()

    assert response.status_code == 200
    payload = response.json()
    snapshot = payload["snapshot"]
    assert payload["success"] is True
    assert snapshot["architecture_graph"]["meta"]["fidelity"] == "derived"
    assert any(
        node["id"] == "input" for node in snapshot["architecture_graph"]["nodes"]
    )
    assert any(
        node["id"] == "output" for node in snapshot["architecture_graph"]["nodes"]
    )
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
