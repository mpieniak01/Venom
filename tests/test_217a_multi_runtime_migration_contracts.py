"""Testy kontraktu migracji 217A: gemma4_audio → multi_runtime.

Pilnują, że:
1. Publiczne identyfikatory runtime to wyłącznie multi_runtime.
2. Stara nazwa gemma4_audio jest normalizowana, a nie odrzucana.
3. Backend, API i warstwy serwisowe są spójne z nową nazwą.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from venom_core.utils.runtime_names import (
    MULTI_RUNTIME_ID,
    is_multi_runtime,
    normalize_runtime_id,
)

# ---------------------------------------------------------------------------
# Testy helpera normalizacji
# ---------------------------------------------------------------------------


def test_multi_runtime_id_constant():
    assert MULTI_RUNTIME_ID == "multi_runtime"


def test_is_multi_runtime_canonical():
    assert is_multi_runtime("multi_runtime") is True


def test_is_multi_runtime_legacy_input():
    assert is_multi_runtime("gemma4_audio") is True


def test_is_multi_runtime_with_suffix_canonical():
    assert is_multi_runtime("multi_runtime@localhost:8014") is True


def test_is_multi_runtime_with_suffix_legacy():
    assert is_multi_runtime("gemma4_audio@localhost:8014") is True


def test_is_multi_runtime_rejects_other_runtimes():
    assert is_multi_runtime("ollama") is False
    assert is_multi_runtime("vllm") is False
    assert is_multi_runtime("onnx") is False
    assert is_multi_runtime("openai") is False
    assert is_multi_runtime(None) is False
    assert is_multi_runtime("") is False


def test_normalize_runtime_id_canonical_passthrough():
    assert normalize_runtime_id("multi_runtime") == "multi_runtime"


def test_normalize_runtime_id_legacy_to_canonical():
    assert normalize_runtime_id("gemma4_audio") == "multi_runtime"


def test_normalize_runtime_id_suffix_canonical():
    assert (
        normalize_runtime_id("multi_runtime@localhost:8014")
        == "multi_runtime@localhost:8014"
    )


def test_normalize_runtime_id_suffix_legacy():
    assert (
        normalize_runtime_id("gemma4_audio@localhost:8014")
        == "multi_runtime@localhost:8014"
    )


def test_normalize_runtime_id_other_runtimes_unchanged():
    assert normalize_runtime_id("ollama") == "ollama"
    assert normalize_runtime_id("vllm") == "vllm"
    assert normalize_runtime_id("onnx") == "onnx"


def test_normalize_runtime_id_none():
    assert normalize_runtime_id(None) == ""


# ---------------------------------------------------------------------------
# Kontrakt: get_active_llm_runtime z config gemma4_audio zwraca multi_runtime
# ---------------------------------------------------------------------------


def test_llm_runtime_resolution_legacy_config_returns_multi_runtime():
    from venom_core.utils import llm_runtime

    class _Settings:
        LLM_SERVICE_TYPE = "local"
        AI_MODE = "LOCAL"
        LLM_MODEL_NAME = "google/gemma-4-E2B-it"
        LLM_LOCAL_ENDPOINT = "http://localhost:8014/v1"
        ACTIVE_LLM_SERVER = "gemma4_audio"
        GEMMA4_AUDIO_ENDPOINT = "http://localhost:8014/v1"
        VLLM_ENDPOINT = ""

    runtime = llm_runtime.get_active_llm_runtime(_Settings())
    assert runtime.provider == "multi_runtime", (
        f"Oczekiwano provider='multi_runtime', dostałem '{runtime.provider}'"
    )


def test_llm_runtime_resolution_canonical_config_returns_multi_runtime():
    from venom_core.utils import llm_runtime

    class _Settings:
        LLM_SERVICE_TYPE = "local"
        AI_MODE = "LOCAL"
        LLM_MODEL_NAME = "google/gemma-4-E2B-it"
        LLM_LOCAL_ENDPOINT = "http://localhost:8014/v1"
        ACTIVE_LLM_SERVER = "multi_runtime"
        GEMMA4_AUDIO_ENDPOINT = "http://localhost:8014/v1"
        VLLM_ENDPOINT = ""

    runtime = llm_runtime.get_active_llm_runtime(_Settings())
    assert runtime.provider == "multi_runtime"


def test_infer_local_provider_from_port_8014_returns_multi_runtime():
    from venom_core.utils.llm_runtime import infer_local_provider

    assert infer_local_provider("http://localhost:8014/v1") == "multi_runtime"
    assert infer_local_provider("http://gemma4.internal:8014") == "multi_runtime"


# ---------------------------------------------------------------------------
# Kontrakt: llm_server_controller wystawia multi_runtime jako klucz serwera
# ---------------------------------------------------------------------------


def test_server_controller_exposes_multi_runtime_key():
    from venom_core.core.llm_server_controller import LlmServerController

    cfg = SimpleNamespace(
        VLLM_START_COMMAND="",
        VLLM_STOP_COMMAND="",
        VLLM_RESTART_COMMAND="",
        VLLM_ENDPOINT="http://localhost:8001/v1",
        OLLAMA_START_COMMAND="",
        OLLAMA_STOP_COMMAND="",
        OLLAMA_RESTART_COMMAND="",
        GEMMA4_AUDIO_START_COMMAND="",
        GEMMA4_AUDIO_STOP_COMMAND="",
        GEMMA4_AUDIO_RESTART_COMMAND="",
        GEMMA4_AUDIO_ENDPOINT="http://localhost:8014/v1",
        GEMMA4_AUDIO_HOST="localhost",
        GEMMA4_AUDIO_PORT=8014,
    )
    controller = LlmServerController(cfg)
    names = {srv["name"] for srv in controller.list_servers()}
    assert "multi_runtime" in names, f"Brak 'multi_runtime' w {names}"
    assert "gemma4_audio" not in names, (
        "'gemma4_audio' nie powinno być już publicznym kluczem"
    )


def test_server_controller_multi_runtime_provider():
    from venom_core.core.llm_server_controller import LlmServerController

    cfg = SimpleNamespace(
        VLLM_START_COMMAND="",
        VLLM_STOP_COMMAND="",
        VLLM_RESTART_COMMAND="",
        VLLM_ENDPOINT="http://localhost:8001/v1",
        OLLAMA_START_COMMAND="",
        OLLAMA_STOP_COMMAND="",
        OLLAMA_RESTART_COMMAND="",
        GEMMA4_AUDIO_START_COMMAND="",
        GEMMA4_AUDIO_STOP_COMMAND="",
        GEMMA4_AUDIO_RESTART_COMMAND="",
        GEMMA4_AUDIO_ENDPOINT="http://localhost:8014/v1",
        GEMMA4_AUDIO_HOST="localhost",
        GEMMA4_AUDIO_PORT=8014,
    )
    controller = LlmServerController(cfg)
    servers = {srv["name"]: srv for srv in controller.list_servers()}
    assert servers["multi_runtime"]["provider"] == "multi_runtime"


# ---------------------------------------------------------------------------
# Kontrakt: system_llm_service zwraca multi_runtime w zbiorach
# ---------------------------------------------------------------------------


def test_allowed_servers_full_profile_uses_multi_runtime():
    from venom_core.services.system_llm_service import allowed_local_servers

    full_set = allowed_local_servers(profile="full", onnx_enabled=False)
    assert "multi_runtime" in full_set
    assert "gemma4_audio" not in full_set


def test_installed_servers_includes_multi_runtime():
    from venom_core.services.system_llm_service import installed_local_servers

    installed = installed_local_servers(
        ollama_installed=False, vllm_installed=False, onnx_installed=False
    )
    assert "multi_runtime" in installed
    assert "gemma4_audio" not in installed


# ---------------------------------------------------------------------------
# Kontrakt: apply_model_activation_config normalizuje ACTIVE_LLM_SERVER
# ---------------------------------------------------------------------------


def test_apply_model_activation_config_normalizes_runtime_to_canonical(monkeypatch):
    from venom_core.config import SETTINGS
    from venom_core.core import model_registry_runtime
    from venom_core.services.config_manager import config_manager

    monkeypatch.setattr(
        SETTINGS, "LLM_LOCAL_ENDPOINT", "http://localhost:11434", raising=False
    )
    monkeypatch.setattr(SETTINGS, "LLM_MODEL_NAME", "old-model", raising=False)
    monkeypatch.setattr(SETTINGS, "ACTIVE_LLM_SERVER", "ollama", raising=False)
    monkeypatch.setattr(SETTINGS, "LLM_SERVICE_TYPE", "local", raising=False)
    monkeypatch.setattr(config_manager, "update_config", MagicMock(), raising=False)

    configured = model_registry_runtime.apply_model_activation_config(
        "google/gemma-4-E2B-it", "gemma4_audio", SimpleNamespace(local_path="")
    )
    assert configured.ACTIVE_LLM_SERVER == "multi_runtime", (
        f"ACTIVE_LLM_SERVER powinno być 'multi_runtime', dostałem '{configured.ACTIVE_LLM_SERVER}'"
    )


def test_apply_model_activation_config_with_canonical_name(monkeypatch):
    from venom_core.config import SETTINGS
    from venom_core.core import model_registry_runtime
    from venom_core.services.config_manager import config_manager

    monkeypatch.setattr(
        SETTINGS, "LLM_LOCAL_ENDPOINT", "http://localhost:11434", raising=False
    )
    monkeypatch.setattr(SETTINGS, "LLM_MODEL_NAME", "old-model", raising=False)
    monkeypatch.setattr(SETTINGS, "ACTIVE_LLM_SERVER", "ollama", raising=False)
    monkeypatch.setattr(SETTINGS, "LLM_SERVICE_TYPE", "local", raising=False)
    monkeypatch.setattr(config_manager, "update_config", MagicMock(), raising=False)

    configured = model_registry_runtime.apply_model_activation_config(
        "google/gemma-4-E2B-it", "multi_runtime", SimpleNamespace(local_path="")
    )
    assert configured.ACTIVE_LLM_SERVER == "multi_runtime"


# ---------------------------------------------------------------------------
# Kontrakt regresji: stara nazwa NIE POJAWIA SIĘ w publicznych polach API
# ---------------------------------------------------------------------------


def test_static_models_runtime_id_is_multi_runtime():
    from unittest.mock import patch

    from venom_core.api.routes import system_llm

    with patch.object(
        system_llm,
        "gemma4_audio_available_models",
        side_effect=lambda role="target", settings_obj=None: ["google/gemma-4-E2B-it"],
    ):
        models = system_llm._gemma4_audio_static_models(  # noqa: SLF001
            active_provider="multi_runtime",
            active_model="google/gemma-4-E2B-it",
        )
    for model in models:
        assert model["runtime_id"] == "multi_runtime", (
            f"runtime_id powinno być 'multi_runtime', dostałem '{model['runtime_id']}'"
        )
        assert model["provider"] == "multi_runtime", (
            f"provider powinno być 'multi_runtime', dostałem '{model['provider']}'"
        )


@pytest.mark.asyncio
async def test_local_models_grouped_by_multi_runtime_key():
    from unittest.mock import patch

    from venom_core.api.routes import system_llm

    active_runtime = SimpleNamespace(
        provider="multi_runtime", model_name="google/gemma-4-E2B-it"
    )
    with (
        patch.object(system_llm, "get_active_llm_runtime", return_value=active_runtime),
        patch.object(
            system_llm,
            "gemma4_audio_available_models",
            side_effect=lambda role="target", settings_obj=None: [
                "google/gemma-4-E2B-it"
            ],
        ),
    ):
        grouped, _ = await system_llm._local_models_by_runtime(  # noqa: SLF001
            model_manager=object(),
            local_models=[],
        )
    assert "multi_runtime" in grouped, "Klucz 'multi_runtime' powinien być w grouped"
    assert "gemma4_audio" not in grouped, (
        "'gemma4_audio' nie powinno być kluczem w grouped"
    )
