from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from venom_core.api.routes import models_install
from venom_core.services.feedback_loop_policy import (
    FEEDBACK_LOOP_PRIMARY_MODEL,
    feedback_loop_policy,
)


class DummyManager:
    def check_storage_quota(self, additional_size_gb: float = 0.0) -> bool:
        return True

    async def list_local_models(self):
        return [{"name": "qwen2.5-coder:7b", "provider": "ollama"}]


class DummyMissingManager(DummyManager):
    async def list_local_models(self):
        return []

    async def pull_model(self, model_name: str):
        return True


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(models_install.router)
    return TestClient(app)


def test_models_install_feedback_loop_alias_resolves_to_installed_primary(monkeypatch):
    monkeypatch.setattr(models_install, "get_model_manager", lambda: DummyManager())

    response = _client().post(
        "/api/v1/models/install",
        json={"name": "OpenCodeInterpreter-Qwen2.5-7B"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["already_installed"] is True
    assert payload["requested_model_alias"] == "OpenCodeInterpreter-Qwen2.5-7B"
    assert payload["resolved_model_id"] == "qwen2.5-coder:7b"
    assert payload["feedback_loop_tier"] == "primary"


def test_models_install_feedback_loop_alias_returns_background_plan(monkeypatch):
    monkeypatch.setattr(
        models_install, "get_model_manager", lambda: DummyMissingManager()
    )

    async def _allow_primary(_manager):
        return True

    monkeypatch.setattr(
        models_install, "_feedback_loop_primary_allowed", _allow_primary
    )

    response = _client().post(
        "/api/v1/models/install",
        json={"name": "OpenCodeInterpreter-Qwen2.5-7B"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["requested_model_alias"] == "OpenCodeInterpreter-Qwen2.5-7B"
    assert payload["install_candidates"] == list(feedback_loop_policy().candidates)


def test_models_install_feedback_loop_alias_uses_fallbacks_on_resource_guard(
    monkeypatch,
):
    monkeypatch.setattr(
        models_install, "get_model_manager", lambda: DummyMissingManager()
    )

    async def _disallow_primary(_manager):
        return False

    monkeypatch.setattr(
        models_install,
        "_feedback_loop_primary_allowed",
        _disallow_primary,
    )

    response = _client().post(
        "/api/v1/models/install",
        json={"name": "OpenCodeInterpreter-Qwen2.5-7B"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["resolution_reason"] == "resource_guard"
    assert payload["resolved_model_id"] == feedback_loop_policy().fallbacks[0]
    assert payload["install_candidates"] == list(feedback_loop_policy().fallbacks)


def test_models_install_feedback_loop_alias_errors_when_no_fallbacks(monkeypatch):
    monkeypatch.setattr(
        models_install, "get_model_manager", lambda: DummyMissingManager()
    )

    async def _disallow_primary(_manager):
        return False

    monkeypatch.setattr(
        models_install,
        "_feedback_loop_primary_allowed",
        _disallow_primary,
    )
    monkeypatch.setattr(
        models_install,
        "feedback_loop_policy",
        lambda: SimpleNamespace(
            requested_alias="OpenCodeInterpreter-Qwen2.5-7B",
            primary=FEEDBACK_LOOP_PRIMARY_MODEL,
            fallbacks=(),
            candidates=(FEEDBACK_LOOP_PRIMARY_MODEL,),
        ),
    )

    response = _client().post(
        "/api/v1/models/install",
        json={"name": "OpenCodeInterpreter-Qwen2.5-7B"},
    )

    assert response.status_code == 400
    assert "Brak dostępnych modeli fallback" in str(response.json().get("detail", ""))
