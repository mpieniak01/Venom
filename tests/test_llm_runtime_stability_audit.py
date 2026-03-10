from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_module():
    repo_root = Path(__file__).resolve().parents[1]
    script_path = repo_root / "scripts" / "dev" / "llm_runtime_stability_audit.py"
    spec = importlib.util.spec_from_file_location(
        "llm_runtime_stability_audit", script_path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_pick_model_prefers_gemma3_pattern():
    module = _load_module()
    model = module._pick_model(
        available_models=["llama3.2:3b", "gemma3:4b", "gemma2:2b"],
        preferred_patterns=["gemma3", "gemma2"],
    )
    assert model == "gemma3:4b"


def test_pick_model_falls_back_to_first_when_no_match():
    module = _load_module()
    model = module._pick_model(
        available_models=["qwen2.5:7b", "llama3.2:3b"],
        preferred_patterns=["gemma3"],
    )
    assert model == "qwen2.5:7b"


def test_runtime_models_from_options_deduplicates():
    module = _load_module()
    payload = {
        "runtimes": [
            {
                "runtime_id": "ollama",
                "models": [
                    {"name": "gemma3:4b"},
                    {"name": "Gemma3:4b"},
                    {"name": "gemma2:2b"},
                ],
            }
        ]
    }
    assert module._runtime_models_from_options(payload, "ollama") == [
        "gemma3:4b",
        "gemma2:2b",
    ]


def test_runtime_models_from_options_missing_runtime_returns_empty():
    module = _load_module()
    payload = {"runtimes": [{"runtime_id": "vllm", "models": [{"name": "foo"}]}]}
    assert module._runtime_models_from_options(payload, "onnx") == []


def test_verify_active_server_allows_model_mismatch_when_not_strict(monkeypatch):
    module = _load_module()
    monkeypatch.setattr(
        module,
        "_http_json",
        lambda *_args, **_kwargs: (
            200,
            {
                "active_server": "onnx",
                "active_model": "models/gemma-3-1b-it-onnx-q4-genai",
            },
        ),
    )
    ok, _msg = module._verify_active_server(
        "http://127.0.0.1:8000",
        runtime="onnx",
        model="gemma-3-4b-it-onnx-build-test",
        strict_model=False,
    )
    assert ok is True
