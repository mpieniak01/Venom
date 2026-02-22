from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from venom_core.execution.onnx_llm_client import OnnxLlmClient, is_onnx_genai_available


def _settings(**overrides):
    base = {
        "ONNX_LLM_ENABLED": True,
        "ONNX_LLM_MODEL_PATH": "models/test-onnx",
        "ONNX_LLM_EXECUTION_PROVIDER": "cuda",
        "ONNX_LLM_PRECISION": "int4",
        "ONNX_LLM_MAX_NEW_TOKENS": 321,
        "ONNX_LLM_TEMPERATURE": 0.15,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


class _FakeTokenArray:
    def __init__(self, values):
        self._values = list(values)

    def tolist(self):
        return list(self._values)


def _fake_og_module(
    *, fail_aliases: set[str] | None = None, template_raises: bool = False
):
    fail_aliases = fail_aliases or set()

    class Config:
        def __init__(self, model_path):
            self.model_path = model_path
            self.providers = []

        def clear_providers(self):
            self.providers = []

        def append_provider(self, provider):
            self.providers.append(provider)

    class Model:
        def __init__(self, arg):
            if isinstance(arg, Config):
                alias = arg.providers[-1] if arg.providers else "auto"
                if alias in fail_aliases:
                    raise RuntimeError(f"provider failed: {alias}")
                self.device_type = alias
            else:
                self.device_type = "auto"

    class TokenizerStream:
        def decode(self, token_id: int):
            return {101: "A", 102: "B"}.get(token_id, "")

    class Tokenizer:
        def __init__(self, _model):
            pass

        def create_stream(self):
            return TokenizerStream()

        def apply_chat_template(self, _messages_json: str, add_generation_prompt: bool):
            if template_raises:
                raise RuntimeError("template error")
            return "templated-prompt" if add_generation_prompt else "templated"

        def encode(self, _prompt: str):
            return [11, 12]

    class GeneratorParams:
        def __init__(self, _model):
            self.options = {}

        def set_search_options(self, **kwargs):
            self.options = kwargs

    class Generator:
        def __init__(self, _model, _params):
            self._tokens = [101, 102]
            self._index = 0

        def append_tokens(self, _input_ids):
            return None

        def is_done(self):
            return self._index >= len(self._tokens)

        def generate_next_token(self):
            return None

        def get_next_tokens(self):
            if self.is_done():
                return None
            token = self._tokens[self._index]
            self._index += 1
            return _FakeTokenArray([token])

    return SimpleNamespace(
        Config=Config,
        Model=Model,
        Tokenizer=Tokenizer,
        GeneratorParams=GeneratorParams,
        Generator=Generator,
    )


def _prepare_model_dir(tmp_path):
    model_dir = tmp_path / "phi-onnx"
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "genai_config.json").write_text("{}", encoding="utf-8")
    return model_dir


def test_is_onnx_genai_available_returns_bool():
    assert isinstance(is_onnx_genai_available(), bool)


def test_has_model_path_true_for_existing_path(tmp_path):
    model_dir = _prepare_model_dir(tmp_path)
    client = OnnxLlmClient(settings=_settings(ONNX_LLM_MODEL_PATH=str(model_dir)))
    assert client.has_model_path() is True


def test_has_model_path_false_when_missing(tmp_path):
    client = OnnxLlmClient(
        settings=_settings(ONNX_LLM_MODEL_PATH=str(tmp_path / "missing-model"))
    )
    assert client.has_model_path() is False


def test_resolve_runtime_model_path_from_nested_genai_config(tmp_path):
    root = tmp_path / "root"
    nested = root / "nested"
    nested.mkdir(parents=True)
    (nested / "genai_config.json").write_text("{}", encoding="utf-8")
    client = OnnxLlmClient(settings=_settings(ONNX_LLM_MODEL_PATH=str(root)))
    assert client._resolve_runtime_model_path() == nested


def test_ensure_ready_fails_when_disabled():
    client = OnnxLlmClient(settings=_settings(ONNX_LLM_ENABLED=False))
    with pytest.raises(RuntimeError, match="disabled"):
        client.ensure_ready()


def test_ensure_ready_fails_when_genai_missing(tmp_path, monkeypatch):
    model_dir = _prepare_model_dir(tmp_path)
    client = OnnxLlmClient(settings=_settings(ONNX_LLM_MODEL_PATH=str(model_dir)))
    monkeypatch.setattr(
        "venom_core.execution.onnx_llm_client.is_onnx_genai_available", lambda: False
    )
    with pytest.raises(RuntimeError, match="not installed"):
        client.ensure_ready()


def test_ensure_ready_fails_when_path_missing(tmp_path, monkeypatch):
    client = OnnxLlmClient(
        settings=_settings(ONNX_LLM_MODEL_PATH=str(tmp_path / "missing-model"))
    )
    monkeypatch.setattr(
        "venom_core.execution.onnx_llm_client.is_onnx_genai_available", lambda: True
    )
    with pytest.raises(RuntimeError, match="does not exist"):
        client.ensure_ready()


def test_can_serve_true_when_enabled_installed_and_path_exists(tmp_path, monkeypatch):
    model_dir = _prepare_model_dir(tmp_path)
    client = OnnxLlmClient(settings=_settings(ONNX_LLM_MODEL_PATH=str(model_dir)))
    monkeypatch.setattr(
        "venom_core.execution.onnx_llm_client.is_onnx_genai_available", lambda: True
    )
    assert client.can_serve() is True


def test_status_payload_contains_resolved_path_and_runtime_fields(
    tmp_path, monkeypatch
):
    model_dir = _prepare_model_dir(tmp_path)
    client = OnnxLlmClient(settings=_settings(ONNX_LLM_MODEL_PATH=str(model_dir)))
    monkeypatch.setattr(
        "venom_core.execution.onnx_llm_client.is_onnx_genai_available", lambda: True
    )
    payload = client.status_payload()
    assert payload["enabled"] is True
    assert payload["execution_provider"] == "cuda"
    assert payload["precision"] == "int4"
    assert payload["resolved_model_path"] == str(model_dir)
    assert payload["ready"] is True
    assert "active_execution_provider" in payload
    assert "runtime_device_type" in payload


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
    assert OnnxLlmClient._provider_fallback_order("directml") == ["directml", "cpu"]


def test_provider_aliases_contains_expected_values():
    assert OnnxLlmClient._provider_aliases("cuda")[0] == "cuda"
    assert "CPUExecutionProvider" in OnnxLlmClient._provider_aliases("cpu")
    assert "dml" in OnnxLlmClient._provider_aliases("directml")


def test_create_model_with_provider_uses_first_working_alias(tmp_path):
    model_dir = _prepare_model_dir(tmp_path)
    client = OnnxLlmClient(settings=_settings(ONNX_LLM_MODEL_PATH=str(model_dir)))
    fake_og = _fake_og_module()
    model = client._create_model_with_provider(fake_og, str(model_dir))
    assert model is not None
    assert client.status_payload()["active_execution_provider"] in {
        "cuda",
        "CUDAExecutionProvider",
    }


def test_create_model_with_provider_falls_back_to_cpu_alias(tmp_path):
    model_dir = _prepare_model_dir(tmp_path)
    client = OnnxLlmClient(settings=_settings(ONNX_LLM_MODEL_PATH=str(model_dir)))
    fake_og = _fake_og_module(
        fail_aliases={"cuda", "CUDAExecutionProvider"},
    )
    model = client._create_model_with_provider(fake_og, str(model_dir))
    assert model is not None
    assert client.status_payload()["active_execution_provider"] in {
        "cpu",
        "CPUExecutionProvider",
    }


def test_create_model_with_provider_uses_auto_when_all_aliases_fail(tmp_path):
    model_dir = _prepare_model_dir(tmp_path)
    client = OnnxLlmClient(settings=_settings(ONNX_LLM_MODEL_PATH=str(model_dir)))
    fake_og = _fake_og_module(
        fail_aliases={
            "cuda",
            "CUDAExecutionProvider",
            "cpu",
            "CPUExecutionProvider",
        },
    )
    model = client._create_model_with_provider(fake_og, str(model_dir))
    assert model is not None
    assert client.status_payload()["active_execution_provider"] == "auto"


def test_messages_to_text_and_build_prompt_fallback(tmp_path):
    model_dir = _prepare_model_dir(tmp_path)
    client = OnnxLlmClient(settings=_settings(ONNX_LLM_MODEL_PATH=str(model_dir)))
    client._tokenizer = _fake_og_module(template_raises=True).Tokenizer(None)
    prompt = client._build_prompt(
        [
            {"role": "system", "content": "be concise"},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": ""},
        ]
    )
    assert "system: be concise" in prompt
    assert "user: hello" in prompt


def test_ensure_runtime_builds_model_once_and_caches(tmp_path, monkeypatch):
    model_dir = _prepare_model_dir(tmp_path)
    client = OnnxLlmClient(settings=_settings(ONNX_LLM_MODEL_PATH=str(model_dir)))
    fake_og = _fake_og_module()
    monkeypatch.setattr(
        "venom_core.execution.onnx_llm_client.is_onnx_genai_available", lambda: True
    )
    monkeypatch.setitem(sys.modules, "onnxruntime_genai", fake_og)
    client._ensure_runtime()
    first_model = client._model
    client._ensure_runtime()
    assert client._model is first_model
    assert client._tokenizer is not None
    assert client._tokenizer_stream is not None


def test_stream_generate_and_generate_return_text(tmp_path, monkeypatch):
    model_dir = _prepare_model_dir(tmp_path)
    client = OnnxLlmClient(
        settings=_settings(
            ONNX_LLM_MODEL_PATH=str(model_dir), ONNX_LLM_MAX_NEW_TOKENS=2
        )
    )
    fake_og = _fake_og_module()
    monkeypatch.setattr(
        "venom_core.execution.onnx_llm_client.is_onnx_genai_available", lambda: True
    )
    monkeypatch.setitem(sys.modules, "onnxruntime_genai", fake_og)
    parts = list(
        client.stream_generate(
            messages=[{"role": "user", "content": "hello"}],
            max_new_tokens=2,
            temperature=0.3,
        )
    )
    assert parts == ["A", "B"]
    assert client.generate(messages=[{"role": "user", "content": "hello"}]) == "AB"
