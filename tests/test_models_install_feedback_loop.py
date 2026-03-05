from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from venom_core.api.routes import models_install
from venom_core.services.feedback_loop_policy import (
    FEEDBACK_LOOP_PRIMARY_MODEL,
    FEEDBACK_LOOP_REQUESTED_ALIAS,
    evaluate_feedback_loop_guard,
    feedback_loop_policy,
    is_feedback_loop_ready,
    resolve_feedback_loop_model,
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
    async def _allow_primary(_manager):
        return True

    monkeypatch.setattr(models_install, "_feedback_loop_primary_allowed", _allow_primary)

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


def test_feedback_loop_resolution_paths_and_ready_flags() -> None:
    exact = resolve_feedback_loop_model(
        requested_model=FEEDBACK_LOOP_REQUESTED_ALIAS,
        available_models={FEEDBACK_LOOP_PRIMARY_MODEL},
        prefer_feedback_loop_default=False,
        exact_only=False,
        primary_allowed=True,
    )
    assert exact.resolution_reason == "exact"
    assert exact.resolved_model_id == FEEDBACK_LOOP_PRIMARY_MODEL

    fallback = resolve_feedback_loop_model(
        requested_model=FEEDBACK_LOOP_REQUESTED_ALIAS,
        available_models={"qwen2.5-coder:3b"},
        prefer_feedback_loop_default=False,
        exact_only=False,
        primary_allowed=True,
    )
    assert fallback.resolution_reason == "fallback"
    assert fallback.resolved_model_id == "qwen2.5-coder:3b"

    exact_only_not_found = resolve_feedback_loop_model(
        requested_model=FEEDBACK_LOOP_REQUESTED_ALIAS,
        available_models={"phi3:mini"},
        prefer_feedback_loop_default=False,
        exact_only=True,
        primary_allowed=True,
    )
    assert exact_only_not_found.resolution_reason == "not_found"
    assert exact_only_not_found.resolved_model_id is None

    default_alias = resolve_feedback_loop_model(
        requested_model=None,
        available_models={FEEDBACK_LOOP_PRIMARY_MODEL},
        prefer_feedback_loop_default=True,
        exact_only=False,
        primary_allowed=True,
    )
    assert default_alias.requested_model_alias == FEEDBACK_LOOP_REQUESTED_ALIAS
    assert default_alias.resolution_reason == "exact"
    assert default_alias.resolved_model_id == FEEDBACK_LOOP_PRIMARY_MODEL

    no_request = resolve_feedback_loop_model(
        requested_model=None,
        available_models={"phi3:mini"},
        prefer_feedback_loop_default=False,
        exact_only=False,
        primary_allowed=True,
    )
    assert no_request.requested_model_alias is None
    assert no_request.resolved_model_id is None
    assert no_request.resolution_reason == "exact"

    preserved = resolve_feedback_loop_model(
        requested_model="qwen2.5-coder:3b",
        available_models=set(),
        prefer_feedback_loop_default=True,
        exact_only=False,
        primary_allowed=False,
    )
    assert preserved.requested_model_alias is None
    assert preserved.resolved_model_id == "qwen2.5-coder:3b"
    assert preserved.resolution_reason == "exact"
    assert is_feedback_loop_ready("qwen2.5-coder:3b") is True
    assert is_feedback_loop_ready("phi3:mini") is False


def test_feedback_loop_guard_block_reasons_and_allow_path() -> None:
    low_profile_settings = SimpleNamespace(
        VENOM_OLLAMA_PROFILE="low-vram-8-12gb",
        OLLAMA_CONTEXT_LENGTH=32768,
        OLLAMA_NUM_PARALLEL=0,
        OLLAMA_MAX_QUEUE=0,
        OLLAMA_KV_CACHE_TYPE="",
        OLLAMA_FLASH_ATTENTION=True,
        LLM_KEEP_ALIVE="30m",
    )
    blocked_profile = evaluate_feedback_loop_guard(
        model_id=FEEDBACK_LOOP_PRIMARY_MODEL,
        settings=low_profile_settings,
        ram_total_gb=32.0,
        vram_total_mb=24576.0,
    )
    assert blocked_profile.allowed is False
    assert blocked_profile.guard_reason == "resource_guard"

    high_context_settings = SimpleNamespace(
        VENOM_OLLAMA_PROFILE="balanced-12-24gb",
        OLLAMA_CONTEXT_LENGTH=131072,
        OLLAMA_NUM_PARALLEL=0,
        OLLAMA_MAX_QUEUE=0,
        OLLAMA_KV_CACHE_TYPE="",
        OLLAMA_FLASH_ATTENTION=True,
        LLM_KEEP_ALIVE="30m",
    )
    blocked_context = evaluate_feedback_loop_guard(
        model_id=FEEDBACK_LOOP_PRIMARY_MODEL,
        settings=high_context_settings,
        ram_total_gb=32.0,
        vram_total_mb=24576.0,
    )
    assert blocked_context.allowed is False
    assert blocked_context.guard_reason == "resource_guard"

    blocked_ram = evaluate_feedback_loop_guard(
        model_id=FEEDBACK_LOOP_PRIMARY_MODEL,
        settings=SimpleNamespace(
            VENOM_OLLAMA_PROFILE="balanced-12-24gb",
            OLLAMA_CONTEXT_LENGTH=32768,
            OLLAMA_NUM_PARALLEL=0,
            OLLAMA_MAX_QUEUE=0,
            OLLAMA_KV_CACHE_TYPE="",
            OLLAMA_FLASH_ATTENTION=True,
            LLM_KEEP_ALIVE="30m",
        ),
        ram_total_gb=8.0,
        vram_total_mb=8192.0,
    )
    assert blocked_ram.allowed is False
    assert blocked_ram.guard_reason == "resource_guard"

    blocked_vram = evaluate_feedback_loop_guard(
        model_id=FEEDBACK_LOOP_PRIMARY_MODEL,
        settings=SimpleNamespace(
            VENOM_OLLAMA_PROFILE="balanced-12-24gb",
            OLLAMA_CONTEXT_LENGTH=32768,
            OLLAMA_NUM_PARALLEL=0,
            OLLAMA_MAX_QUEUE=0,
            OLLAMA_KV_CACHE_TYPE="",
            OLLAMA_FLASH_ATTENTION=True,
            LLM_KEEP_ALIVE="30m",
        ),
        ram_total_gb=16.0,
        vram_total_mb=2048.0,
    )
    assert blocked_vram.allowed is False
    assert blocked_vram.guard_reason == "resource_guard"

    allowed_non_primary = evaluate_feedback_loop_guard(
        model_id="qwen2.5-coder:3b",
        settings=low_profile_settings,
        ram_total_gb=1.0,
        vram_total_mb=256.0,
    )
    assert allowed_non_primary.allowed is True
    assert allowed_non_primary.guard_reason is None
