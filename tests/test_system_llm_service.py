from __future__ import annotations

from types import SimpleNamespace

from venom_core.services import system_llm_service as svc


def test_runtime_profile_name_and_allowed_servers():
    assert svc.runtime_profile_name("LIGHT") == "light"
    assert svc.runtime_profile_name("bad") == "full"

    assert svc.allowed_local_servers(profile="light", onnx_enabled=True) == {"ollama"}
    assert svc.allowed_local_servers(profile="llm_off", onnx_enabled=True) == set()
    assert svc.allowed_local_servers(profile="full", onnx_enabled=False) == {
        "ollama",
        "vllm",
    }
    assert svc.allowed_local_servers(profile="full", onnx_enabled=True) == {
        "ollama",
        "vllm",
        "onnx",
    }


def test_installed_local_servers_composition():
    assert svc.installed_local_servers(
        ollama_installed=True,
        vllm_installed=False,
        onnx_installed=True,
    ) == {"ollama", "onnx"}


def test_provider_and_model_key_helpers():
    assert svc.normalize_runtime_provider("gem") == "google"
    assert svc.normalize_runtime_provider("google-gemini") == "google"
    assert svc.normalize_runtime_provider("openai") == "openai"

    assert svc.previous_model_key_for_server("ollama") == "PREVIOUS_MODEL_OLLAMA"
    assert svc.previous_model_key_for_server("vllm") == "PREVIOUS_MODEL_VLLM"
    assert svc.previous_model_key_for_server("onnx") == "PREVIOUS_MODEL_ONNX"


def test_dedupe_servers_by_name():
    payload = [
        {"name": "onnx", "id": 1},
        {"name": "ONNX", "id": 2},
        {"name": "ollama", "id": 3},
        {"name": "", "id": 4},
    ]

    deduped = svc.dedupe_servers_by_name(payload)

    assert deduped == [{"name": "onnx", "id": 1}, {"name": "ollama", "id": 3}]


def test_installed_binaries_detection(monkeypatch):
    monkeypatch.setattr(
        svc.shutil, "which", lambda name: "/bin/ok" if name == "ollama" else None
    )
    assert svc.is_ollama_installed() is True

    monkeypatch.setattr(svc.shutil, "which", lambda _name: None)
    monkeypatch.setattr(
        svc.importlib.util,
        "find_spec",
        lambda name: object() if name == "vllm" else None,
    )
    assert svc.is_vllm_installed() is True

    monkeypatch.setattr(svc.importlib.util, "find_spec", lambda _name: None)
    assert svc.is_vllm_installed() is False

    monkeypatch.setattr(
        svc.importlib.util,
        "find_spec",
        lambda name: SimpleNamespace() if name == "onnxruntime_genai" else None,
    )
    assert svc.is_onnx_runtime_installed() is True
