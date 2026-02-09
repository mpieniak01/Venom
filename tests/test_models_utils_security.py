"""Security-focused tests for models_utils filesystem name normalization."""

import pytest
from fastapi import HTTPException

from venom_core.api.routes.models_utils import (
    read_ollama_manifest_params,
    read_vllm_generation_config,
    validate_generation_params,
)


@pytest.mark.parametrize(
    "model_name",
    [
        "",
        "../secret",
        "..\\secret",
        "/etc/passwd",
        "model;rm -rf /",
        "model$(whoami)",
    ],
)
def test_read_ollama_manifest_params_rejects_unsafe_model_name(model_name: str):
    assert read_ollama_manifest_params(model_name) == {}


@pytest.mark.parametrize(
    "model_name",
    [
        "../secret",
        "..\\secret",
        "/etc/passwd",
        "model;cat /etc/passwd",
        "model`uname`",
    ],
)
def test_read_vllm_generation_config_rejects_unsafe_model_name(model_name: str):
    assert read_vllm_generation_config(model_name) == {}


def test_validate_generation_params_accepts_supported_types():
    schema = {
        "temperature": {"type": "float", "min": 0.0, "max": 2.0},
        "max_tokens": {"type": "int", "min": 1, "max": 4096},
        "stream": {"type": "bool"},
        "mode": {"type": "enum", "options": ["fast", "balanced"]},
    }
    params = {
        "temperature": "0.8",
        "max_tokens": "512",
        "stream": True,
        "mode": "fast",
    }

    validated = validate_generation_params(params, schema)

    assert validated == {
        "temperature": 0.8,
        "max_tokens": 512,
        "stream": True,
        "mode": "fast",
    }


def test_validate_generation_params_raises_for_unknown_key_and_invalid_values():
    schema = {
        "temperature": {"type": "float", "min": 0.0, "max": 2.0},
        "mode": {"type": "enum", "options": ["fast", "balanced"]},
    }
    params = {
        "temperature": "9.9",
        "mode": "invalid",
        "unknown": "x",
    }

    with pytest.raises(HTTPException) as exc:
        validate_generation_params(params, schema)

    detail = str(exc.value.detail)
    assert "Nieznany parametr: unknown" in detail
    assert "Parametr temperature powyżej max 2.0" in detail
    assert "Parametr mode musi być jedną z opcji" in detail


def test_validate_generation_params_rejects_unsupported_spec_type():
    schema = {"foo": {"type": "mystery"}}
    with pytest.raises(HTTPException) as exc:
        validate_generation_params({"foo": "bar"}, schema)
    assert "Nieobsługiwany typ parametru foo" in str(exc.value.detail)
