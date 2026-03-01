from __future__ import annotations

import asyncio
from types import SimpleNamespace

from venom_core.core import model_registry_providers as providers
from venom_core.core.model_registry_types import ModelProvider, ModelStatus


def test_resolve_hf_token_from_secret_like_object(monkeypatch) -> None:
    class _SecretLike:
        def get_secret_value(self) -> str:
            return "hf_secret"

    monkeypatch.setattr(providers, "SETTINGS", SimpleNamespace(HF_TOKEN=_SecretLike()))
    assert providers.resolve_hf_token() == "hf_secret"


def test_resolve_hf_token_from_plain_value(monkeypatch) -> None:
    monkeypatch.setattr(providers, "SETTINGS", SimpleNamespace(HF_TOKEN="hf_plain"))
    assert providers.resolve_hf_token() == "hf_plain"


def test_create_default_generation_schema_contains_core_keys() -> None:
    schema = providers.create_default_generation_schema()
    assert {"temperature", "max_tokens", "top_p", "top_k", "repeat_penalty"} <= set(
        schema
    )
    assert schema["temperature"].max == 2.0


def test_ollama_provider_list_available_models_adjusts_llama_temperature(
    monkeypatch,
) -> None:
    class _FakeOllamaClient:
        def __init__(self, endpoint: str):
            self.endpoint = endpoint

        async def list_tags(self):
            return {"models": [{"name": "llama3:8b", "size": 1024}]}

    monkeypatch.setattr(providers, "OllamaClient", _FakeOllamaClient)
    provider = providers.OllamaModelProvider(endpoint="http://localhost:11434")
    models = asyncio.run(provider.list_available_models())

    assert len(models) == 1
    assert models[0].provider == ModelProvider.OLLAMA
    assert models[0].status == ModelStatus.INSTALLED
    assert models[0].capabilities.generation_schema["temperature"].max == 1.0


def test_ollama_provider_install_model_rejects_invalid_name(monkeypatch) -> None:
    class _FakeOllamaClient:
        def __init__(self, endpoint: str):
            self.endpoint = endpoint

        async def pull_model(self, model_name: str, progress_callback=None):
            return True

    monkeypatch.setattr(providers, "OllamaClient", _FakeOllamaClient)
    provider = providers.OllamaModelProvider(endpoint="http://localhost:11434")
    assert asyncio.run(provider.install_model("bad name!")) is False


def test_hf_provider_list_available_models_uses_fallback_when_empty(
    monkeypatch,
) -> None:
    class _FakeHfClient:
        def __init__(self, token=None):
            self.token = token

        async def list_models(self, sort: str, limit: int):
            return []

    monkeypatch.setattr(providers, "HuggingFaceClient", _FakeHfClient)
    provider = providers.HuggingFaceModelProvider(cache_dir="./tmp/test-hf")
    models = asyncio.run(provider.list_available_models())

    assert len(models) >= 2
    assert all(model.provider == ModelProvider.HUGGINGFACE for model in models)
    assert all(model.status == ModelStatus.AVAILABLE for model in models)
