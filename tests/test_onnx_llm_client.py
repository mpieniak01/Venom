import pytest

from venom_core.execution.onnx_llm_client import OnnxLlmClient, is_onnx_genai_available


class DummySettings:
    ONNX_LLM_ENABLED = True
    ONNX_LLM_MODEL_PATH = "models/test-onnx"
    ONNX_LLM_EXECUTION_PROVIDER = "cuda"
    ONNX_LLM_PRECISION = "int4"
    ONNX_LLM_MAX_NEW_TOKENS = 321
    ONNX_LLM_TEMPERATURE = 0.15


def test_is_onnx_genai_available_returns_bool():
    assert isinstance(is_onnx_genai_available(), bool)


def test_status_payload_contains_expected_fields():
    client = OnnxLlmClient(settings=DummySettings())
    payload = client.status_payload()
    assert payload["enabled"] is True
    assert payload["execution_provider"] == "cuda"
    assert payload["precision"] == "int4"
    assert payload["max_new_tokens"] == 321
    assert payload["temperature"] == pytest.approx(0.15)
    assert "ready" in payload
    assert "genai_installed" in payload
    assert "model_path_exists" in payload


def test_has_model_path_false_when_missing(tmp_path):
    settings = DummySettings()
    settings.ONNX_LLM_MODEL_PATH = str(tmp_path / "missing-model")
    client = OnnxLlmClient(settings=settings)
    assert client.has_model_path() is False


def test_has_model_path_true_for_existing_path(tmp_path):
    model_dir = tmp_path / "phi-onnx"
    model_dir.mkdir(parents=True)
    settings = DummySettings()
    settings.ONNX_LLM_MODEL_PATH = str(model_dir)
    client = OnnxLlmClient(settings=settings)
    assert client.has_model_path() is True


def test_ensure_ready_fails_when_disabled():
    settings = DummySettings()
    settings.ONNX_LLM_ENABLED = False
    client = OnnxLlmClient(settings=settings)
    with pytest.raises(RuntimeError, match="disabled"):
        client.ensure_ready()


def test_ensure_ready_fails_when_path_missing(tmp_path, monkeypatch):
    settings = DummySettings()
    settings.ONNX_LLM_MODEL_PATH = str(tmp_path / "missing-model")
    client = OnnxLlmClient(settings=settings)
    monkeypatch.setattr(
        "venom_core.execution.onnx_llm_client.is_onnx_genai_available", lambda: True
    )
    with pytest.raises(RuntimeError, match="does not exist"):
        client.ensure_ready()


def test_can_serve_true_when_enabled_installed_and_path_exists(tmp_path, monkeypatch):
    model_dir = tmp_path / "phi-onnx"
    model_dir.mkdir(parents=True)
    settings = DummySettings()
    settings.ONNX_LLM_MODEL_PATH = str(model_dir)
    client = OnnxLlmClient(settings=settings)
    monkeypatch.setattr(
        "venom_core.execution.onnx_llm_client.is_onnx_genai_available", lambda: True
    )
    assert client.can_serve() is True


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("cuda", "cuda"),
        ("CUDAExecutionProvider", "cuda"),
        ("cpu", "cpu"),
        ("CpuExecutionProvider", "cpu"),
        ("directml", "directml"),
        ("dml", "directml"),
        ("DirectMLExecutionProvider", "directml"),
        ("invalid-provider", "cuda"),
    ],
)
def test_normalize_execution_provider(raw, expected):
    assert OnnxLlmClient._normalize_execution_provider(raw) == expected


def test_provider_fallback_order_prefers_cpu_only_for_cpu():
    assert OnnxLlmClient._provider_fallback_order("cpu") == ["cpu"]
    assert OnnxLlmClient._provider_fallback_order("cuda") == ["cuda", "cpu"]
    assert OnnxLlmClient._provider_fallback_order("directml") == [
        "directml",
        "cpu",
    ]
