from types import SimpleNamespace

import pytest

import venom_core.main as main_module
from venom_core.config import SETTINGS
from venom_core.core.service_monitor import ServiceRegistry
from venom_core.infrastructure.docker_habitat import CONTAINER_WORKDIR, DockerHabitat
from venom_core.main import (
    _extract_available_local_models,
    _get_orchestrator_kernel,
    _get_piper_models_root,
    _list_available_tts_models,
    _resolve_tts_model_path,
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


def test_tts_helpers_resolve_list_and_root(monkeypatch, tmp_path):
    storage_prefix = tmp_path / "storage"
    storage_piper = storage_prefix / "data" / "models" / "piper"
    storage_piper.mkdir(parents=True)
    model_file = storage_piper / "pl_PL-test.onnx"
    model_file.write_text("fake")

    monkeypatch.setattr(SETTINGS, "STORAGE_PREFIX", str(storage_prefix))
    monkeypatch.setattr(SETTINGS, "REPO_ROOT", str(tmp_path / "repo-root"))

    root = _get_piper_models_root()
    assert root == storage_piper

    listed = _list_available_tts_models()
    assert listed and listed[0]["id"] == "pl_PL-test.onnx"

    assert _resolve_tts_model_path("pl_PL-test.onnx") == model_file.resolve()


def test_tts_helpers_reject_outside_or_invalid_model(monkeypatch, tmp_path):
    piper_root = tmp_path / "data" / "models" / "piper"
    piper_root.mkdir(parents=True)
    wrong_ext = piper_root / "voice.bin"
    wrong_ext.write_text("fake")
    outside = tmp_path / "outside.onnx"
    outside.write_text("fake")

    monkeypatch.setattr(main_module, "_get_piper_models_root", lambda: piper_root)

    with pytest.raises(main_module.HTTPException) as exc_ext:
        _resolve_tts_model_path("voice.bin")
    assert exc_ext.value.status_code == 400

    with pytest.raises(main_module.HTTPException) as exc_outside:
        _resolve_tts_model_path(str(outside.resolve()))
    assert exc_outside.value.status_code == 400


@pytest.mark.asyncio
async def test_tts_models_list_and_update_endpoint_runtime_paths(monkeypatch, tmp_path):
    model_file = tmp_path / "pl_PL-gosia-medium.onnx"
    model_file.write_text("fake")

    monkeypatch.setattr(main_module, "_resolve_tts_model_path", lambda _m: model_file)
    monkeypatch.setattr(
        main_module,
        "_list_available_tts_models",
        lambda: [
            {"id": model_file.name, "label": model_file.stem, "path": str(model_file)}
        ],
    )

    updates: list[dict[str, str]] = []
    import venom_core.services.config_manager as config_manager_module

    monkeypatch.setattr(
        config_manager_module,
        "config_manager",
        SimpleNamespace(update_config=lambda payload: updates.append(payload)),
    )

    async def _reload(path: str):
        return {"tts_loaded": True, "tts_fallback": False, "path": path}

    global_engine = SimpleNamespace(
        set_tts_model_path=_reload,
        voice=SimpleNamespace(model_path=str(model_file)),
    )
    handler = SimpleNamespace(audio_engine=None)

    monkeypatch.setattr(main_module, "audio_engine", global_engine)
    monkeypatch.setattr(main_module, "audio_stream_handler", handler)
    monkeypatch.setattr(SETTINGS, "TTS_MODEL_PATH", str(model_file))

    request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))
    listed = await main_module.list_audio_tts_models(request)
    assert listed["current_model_path"] == str(model_file)
    assert listed["models"][0]["id"] == model_file.name

    request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))
    payload = main_module.AudioTtsModelUpdateRequest(model=model_file.name)
    result = await main_module.update_audio_tts_model(payload, request)

    assert updates == [{"TTS_MODEL_PATH": str(model_file)}]
    assert handler.audio_engine is global_engine
    assert result["status"] == "success"
    assert result["effective_tts_model_path"] == str(model_file)
