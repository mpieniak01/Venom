from pydantic import ValidationError

from venom_core.api.model_schemas.model_requests import OnnxBuildRequest
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
