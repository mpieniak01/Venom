import pytest
from pydantic import ValidationError

from venom_core.api.model_schemas.model_requests import (
    ModelRegistryInstallRequest,
    OnnxBuildRequest,
)
from venom_core.api.model_schemas.model_validators import validate_runtime


def test_onnx_build_request_normalizes_provider_and_precision():
    req = OnnxBuildRequest(
        model_name="google/gemma-3-4b-it",
        execution_provider="CUDA",
        precision="FP16",
    )
    assert req.execution_provider == "cuda"
    assert req.precision == "fp16"


def test_onnx_build_request_rejects_invalid_execution_provider():
    try:
        OnnxBuildRequest(
            model_name="google/gemma-3-4b-it",
            execution_provider="bad-provider",
            precision="int4",
        )
        assert False, "expected ValidationError"
    except ValidationError as exc:
        assert "execution_provider musi być: cuda|cpu|directml" in str(exc)


def test_onnx_build_request_rejects_invalid_precision():
    try:
        OnnxBuildRequest(
            model_name="google/gemma-3-4b-it",
            execution_provider="cuda",
            precision="int8",
        )
        assert False, "expected ValidationError"
    except ValidationError as exc:
        assert "precision musi być: int4|fp16" in str(exc)


def test_validate_runtime_accepts_onnx():
    assert validate_runtime("onnx") == "onnx"


def test_validate_runtime_rejects_unknown_runtime():
    try:
        validate_runtime("unknown")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "Runtime musi być 'vllm', 'ollama' lub 'onnx'" in str(exc)


def test_model_registry_install_request_runs_post_init_for_huggingface():
    req = ModelRegistryInstallRequest(
        name="google/gemma-3-4b-it",
        provider="huggingface",
        runtime="vllm",
    )
    assert req.provider == "huggingface"
    assert req.runtime == "vllm"


def test_model_registry_install_request_rejects_huggingface_with_non_vllm_runtime():
    with pytest.raises(
        ValidationError, match="Runtime dla HuggingFace musi być 'vllm'"
    ):
        ModelRegistryInstallRequest(
            name="google/gemma-3-4b-it",
            provider="huggingface",
            runtime="ollama",
        )


def test_model_registry_install_request_validates_ollama_runtime_contract():
    req = ModelRegistryInstallRequest(
        name="gemma2:2b",
        provider="ollama",
        runtime="ollama",
    )
    assert req.provider == "ollama"
    assert req.runtime == "ollama"

    with pytest.raises(ValidationError, match="Runtime dla Ollama musi być 'ollama'"):
        ModelRegistryInstallRequest(
            name="gemma2:2b",
            provider="ollama",
            runtime="vllm",
        )
