from __future__ import annotations

import pytest

from venom_core.api.model_schemas.model_requests import ModelSwitchRequest
from venom_core.api.routes import models_install as routes


class _DummyManager:
    async def list_local_models(self):
        return [
            {
                "name": "qwen2.5-coder:3b",
                "provider": "ollama",
                "path": "/tmp/model.gguf",
            }
        ]

    def get_version(self, _name: str):
        return object()

    def activate_version(self, _name: str):
        return True


@pytest.mark.asyncio
async def test_switch_model_enforces_single_loaded_ollama_model(monkeypatch):
    monkeypatch.setattr(routes, "get_model_manager", lambda: _DummyManager())
    monkeypatch.setattr(
        routes, "_ensure_registered_version", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(routes, "_update_runtime_settings", lambda **_kwargs: None)
    monkeypatch.setattr(
        routes, "_update_config_for_active_model", lambda **_kwargs: None
    )
    monkeypatch.setattr(routes, "update_last_model", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        routes, "emit_runtime_model_event", lambda *_args, **_kwargs: None
    )

    class _Runtime:
        provider = "ollama"
        endpoint = "http://localhost:11434/v1"

    monkeypatch.setattr(routes, "get_active_llm_runtime", lambda: _Runtime())

    calls: list[tuple[str | None, str | None]] = []

    async def _enforce_single_model(
        *, endpoint: str | None, selected_model: str | None
    ):
        calls.append((endpoint, selected_model))
        return {"after": [selected_model]}

    monkeypatch.setattr(
        routes, "enforce_single_loaded_ollama_model", _enforce_single_model
    )

    response = await routes.switch_model(ModelSwitchRequest(name="qwen2.5-coder:3b"))

    assert response["success"] is True
    assert calls == [("http://localhost:11434/v1", "qwen2.5-coder:3b")]
