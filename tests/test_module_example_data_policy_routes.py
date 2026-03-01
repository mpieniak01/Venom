from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from venom_core.config import SETTINGS as CORE_SETTINGS

MODULE_EXAMPLE_ROOT = (
    Path(__file__).resolve().parents[1] / "modules" / "venom-module-example"
)
if str(MODULE_EXAMPLE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_EXAMPLE_ROOT))


def _load_module_example():
    routes_mod = importlib.import_module("venom_module_example.api.routes")
    provider_mod = importlib.import_module("venom_module_example.services.provider")
    return routes_mod.router, provider_mod.reset_module_example_provider_cache


def _client() -> TestClient:
    router, _ = _load_module_example()
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.fixture(autouse=True)
def _module_example_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    _, reset_provider_cache = _load_module_example()
    monkeypatch.setattr(CORE_SETTINGS, "FEATURE_MODULE_EXAMPLE", True)
    monkeypatch.setattr(CORE_SETTINGS, "MODULE_EXAMPLE_MODE", "stub")
    monkeypatch.setattr(CORE_SETTINGS, "MODULE_EXAMPLE_ALLOWED_USERS", "")
    monkeypatch.setattr(CORE_SETTINGS, "ENVIRONMENT_ROLE", "dev")
    monkeypatch.setattr(CORE_SETTINGS, "ALLOW_DATA_MUTATION", True)
    reset_provider_cache()
    yield
    reset_provider_cache()


def test_module_example_mutation_blocked_on_preprod(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(CORE_SETTINGS, "ENVIRONMENT_ROLE", "preprod")
    monkeypatch.setattr(CORE_SETTINGS, "ALLOW_DATA_MUTATION", False)
    response = _client().post(
        "/api/v1/module-example/drafts/generate",
        json={"candidate_id": "c-001", "channels": ["x"], "languages": ["pl"]},
    )
    assert response.status_code == 403
    assert "ALLOW_DATA_MUTATION=0" in response.json()["detail"]


def test_module_example_mutation_allowed_on_dev() -> None:
    response = _client().post(
        "/api/v1/module-example/drafts/generate",
        json={"candidate_id": "c-001", "channels": ["x"], "languages": ["pl"]},
    )
    assert response.status_code == 200
    assert response.json()["candidate_id"] == "c-001"
