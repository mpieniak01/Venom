"""Security-focused tests for models_utils filesystem name normalization."""

import pytest

from venom_core.api.routes.models_utils import (
    read_ollama_manifest_params,
    read_vllm_generation_config,
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
