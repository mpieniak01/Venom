from types import SimpleNamespace

import pytest

from venom_core.config import SETTINGS
from venom_core.core.service_monitor import ServiceRegistry
from venom_core.infrastructure.docker_habitat import CONTAINER_WORKDIR, DockerHabitat
from venom_core.main import (
    _extract_available_local_models,
    _get_orchestrator_kernel,
    _select_startup_model,
)
from venom_core.services.translation_service import TranslationService


def test_service_registry_registers_expected_defaults(monkeypatch):
    monkeypatch.setattr(SETTINGS, "OPENAI_API_KEY", "apikey")
    monkeypatch.setattr(SETTINGS, "LLM_SERVICE_TYPE", "openai")
    monkeypatch.setattr(SETTINGS, "ENABLE_SANDBOX", True)
    monkeypatch.setattr(SETTINGS, "REDIS_HOST", "localhost")
    monkeypatch.setattr(SETTINGS, "REDIS_PORT", 6379)
    monkeypatch.setattr(SETTINGS, "REDIS_DB", 0)
    registry = ServiceRegistry()
    assert "LanceDB" in registry.services
    assert registry.get_service("OpenAI API") is not None
    assert "Redis" in {svc.name for svc in registry.get_all_services()}
    assert any(svc.is_critical for svc in registry.get_all_services())


def test_translation_normalize_and_extract():
    service = TranslationService()
    assert service._normalize_target_lang("Pl") == "pl"
    with pytest.raises(ValueError):
        service._normalize_target_lang("xx")


def test_translation_headers_and_promotion(monkeypatch):
    runtimes = SimpleNamespace(service_type="openai", provider="openai")
    monkeypatch.setattr(
        "venom_core.services.translation_service.get_active_llm_runtime",
        lambda: runtimes,
    )
    monkeypatch.setattr(SETTINGS, "OPENAI_API_KEY", "secret")
    monkeypatch.setattr(SETTINGS, "LLM_MODEL_NAME", "test-model")
    monkeypatch.setattr(SETTINGS, "OPENAI_CHAT_COMPLETIONS_ENDPOINT", "https://api")

    service = TranslationService()
    headers = service._resolve_headers(runtimes)
    assert "Authorization" in headers
    payload = service._build_translation_payload(
        text="Hello", source_lang="en", target_lang="pl", model_name="test-model"
    )
    assert payload["model"] == "test-model"


def test_translation_extract_message_fallback():
    service = TranslationService()
    assert (
        service._extract_message_content({"choices": []}, fallback_text="fallback")
        == "fallback"
    )
    assert (
        service._extract_message_content(
            {"choices": [{"message": {"content": " ok "}}]}, fallback_text="fallback"
        )
        == "ok"
    )


def test_select_startup_model_with_fallbacks():
    result = _select_startup_model(
        {"alpha", "beta"}, desired_model="cuda", previous_model="alpha"
    )
    assert result == "alpha"
    result = _select_startup_model(
        {"alpha", "beta"}, desired_model="beta", previous_model="alpha"
    )
    assert result == "beta"


def test_extract_available_local_models():
    models = [
        {"provider": "local", "name": "model-a"},
        {"provider": "remote", "name": "model-b"},
        {"provider": "local", "name": ""},
    ]
    available = _extract_available_local_models(models, "local")
    assert available == {"model-a"}


def test_get_orchestrator_kernel_none(monkeypatch):
    monkeypatch.setattr("venom_core.main.orchestrator", None)
    assert _get_orchestrator_kernel() is None
    dummy_kernel = object()

    class Dispatcher:
        kernel = dummy_kernel

    class Orchestrator:
        task_dispatcher = Dispatcher()

    monkeypatch.setattr("venom_core.main.orchestrator", Orchestrator())
    assert _get_orchestrator_kernel() is dummy_kernel


def test_docker_habitat_workspace_mount_helpers(tmp_path, monkeypatch):
    monkeypatch.setattr(SETTINGS, "WORKSPACE_ROOT", str(tmp_path / "workspace"))
    habitat = DockerHabitat.__new__(DockerHabitat)
    workspace = habitat._resolve_workspace_path()
    assert workspace.exists()

    class FakeContainer:
        def __init__(self, source):
            self.attrs = {
                "Mounts": [{"Destination": CONTAINER_WORKDIR, "Source": source}]
            }

        def reload(self):
            pass

    container = FakeContainer(str(workspace))
    assert habitat._container_workspace_mount(container) == workspace
    assert habitat._has_expected_workspace_mount(container, workspace)
