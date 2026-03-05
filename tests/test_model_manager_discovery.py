from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from venom_core.core import model_manager_discovery as discovery


class _Discovery(discovery.ModelManagerDiscoveryMixin):
    def __init__(self, base: Path) -> None:
        self.models_dir = base / "models-main"
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.ollama_cache_path = base / "ollama-cache.json"
        self._last_ollama_warning = 0.0


class _Response:
    def __init__(self, status_code: int, payload: dict[str, Any]) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload


class _Client:
    def __init__(self, response: _Response) -> None:
        self._response = response

    async def __aenter__(self) -> "_Client":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def aget(self, _url: str, raise_for_status: bool = False) -> _Response:
        return self._response


class _RaisingClient:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def __aenter__(self):
        raise self._exc

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


def test_detect_model_type_and_provider_variants(tmp_path: Path) -> None:
    gguf = tmp_path / "m.gguf"
    gguf.write_text("x", encoding="utf-8")
    onnx = tmp_path / "m.onnx"
    onnx.write_text("x", encoding="utf-8")
    onnx_dir = tmp_path / "onnx-dir"
    onnx_dir.mkdir()

    assert discovery.ModelManagerDiscoveryMixin._detect_model_type_and_provider(
        model_path=gguf, provider="vllm"
    ) == ("gguf", "vllm")
    assert discovery.ModelManagerDiscoveryMixin._detect_model_type_and_provider(
        model_path=onnx, provider="vllm"
    ) == ("onnx", "onnx")
    assert discovery.ModelManagerDiscoveryMixin._detect_model_type_and_provider(
        model_path=onnx_dir, provider="vllm"
    ) == ("folder", "onnx")


def test_onnx_metadata_helpers(tmp_path: Path) -> None:
    model_dir = tmp_path / "phi3-cuda-int4"
    model_dir.mkdir()
    metadata_path = model_dir / discovery.ONNX_METADATA_FILENAME
    metadata_path.write_text(json.dumps({"provider": "onnx", "x": 1}), encoding="utf-8")

    loaded = discovery.ModelManagerDiscoveryMixin._load_onnx_metadata(model_dir)
    assert loaded["provider"] == "onnx"
    inferred = discovery.ModelManagerDiscoveryMixin._default_onnx_metadata_for_path(
        model_dir
    )
    assert inferred["precision"] == "int4"
    assert inferred["execution_provider"] == "cuda"


def test_manifest_and_cache_helpers(tmp_path: Path) -> None:
    mgr = _Discovery(tmp_path)
    manifests = (
        mgr.models_dir / "manifests" / "registry.ollama.ai" / "library" / "mistral"
    )
    manifests.mkdir(parents=True)
    manifest_file = manifests / "latest"
    manifest_file.write_text(
        json.dumps({"layers": [{"size": 2}, {"size": 3}], "config": {"size": 5}}),
        encoding="utf-8",
    )

    entries = mgr._load_ollama_manifest_entries(mgr.models_dir / "manifests")
    assert entries
    assert entries[0]["name"] == "mistral:latest"
    assert entries[0]["size_gb"] is not None

    models: dict[str, dict[str, Any]] = {}
    mgr._register_manifest_fallbacks([mgr.models_dir], models)
    assert "ollama::mistral:latest" in models

    cache_entries = [{"name": "qwen:latest", "provider": "ollama"}]
    mgr._save_ollama_cache(cache_entries)
    loaded_models: dict[str, dict[str, Any]] = {}
    mgr._load_ollama_cache(loaded_models)
    assert "ollama::qwen:latest" in loaded_models


def test_collect_ollama_entries_prefers_latest(tmp_path: Path) -> None:
    mgr = _Discovery(tmp_path)
    entries = mgr._collect_ollama_entries(
        [
            {"name": "foo:old", "digest": "d1", "size": 1, "details": {}},
            {"name": "foo:latest", "digest": "d1", "size": 1, "details": {}},
            {"name": "bar:no-digest", "size": 1, "details": {}},
        ]
    )
    names = sorted(e["name"] for e in entries)
    assert names == ["bar:no-digest", "foo:latest"]


def test_resolve_ollama_tags_url_and_metadata_fallbacks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mgr = _Discovery(tmp_path)
    monkeypatch.setenv(
        "LLM_LOCAL_ENDPOINT", "http://127.0.0.1:11434/v1/chat/completions"
    )
    assert mgr._resolve_ollama_tags_url() == "http://127.0.0.1:11434/api/tags"

    monkeypatch.setenv("LLM_LOCAL_ENDPOINT", "")
    fallback_url = mgr._resolve_ollama_tags_url()
    assert fallback_url.endswith("/api/tags")

    broken_dir = tmp_path / "broken"
    broken_dir.mkdir()
    (broken_dir / discovery.ONNX_METADATA_FILENAME).write_text("{bad", encoding="utf-8")
    assert discovery.ModelManagerDiscoveryMixin._load_onnx_metadata(broken_dir) == {}

    json_file = tmp_path / "model.onnx.json"
    json_file.write_text(json.dumps(["not-a-dict"]), encoding="utf-8")
    assert (
        discovery.ModelManagerDiscoveryMixin._load_onnx_metadata(
            tmp_path / "model.onnx"
        )
        == {}
    )


def test_manifest_helpers_and_cache_failures(tmp_path: Path) -> None:
    mgr = _Discovery(tmp_path)

    outside = tmp_path / "outside.manifest"
    outside.write_text("{}", encoding="utf-8")
    assert (
        discovery.ModelManagerDiscoveryMixin._resolve_manifest_relative_parts(
            mgr.models_dir / "manifests",
            outside,
        )
        is None
    )
    assert (
        discovery.ModelManagerDiscoveryMixin._build_ollama_manifest_entry_name(
            ("registry", "namespace", "model", "latest")
        )
        == "namespace/model:latest"
    )

    unreadable = tmp_path / "bad-manifest"
    unreadable.write_text("{bad", encoding="utf-8")
    assert (
        discovery.ModelManagerDiscoveryMixin._read_manifest_size_bytes(unreadable) == 0
    )

    mgr.ollama_cache_path.write_text("{bad", encoding="utf-8")
    models: dict[str, dict[str, Any]] = {}
    mgr._load_ollama_cache(models)
    assert models == {}


def test_local_model_candidate_filters_academy_artifacts(tmp_path: Path) -> None:
    academy_dir = tmp_path / "self_learning_abc"
    academy_dir.mkdir()
    (academy_dir / "adapter").mkdir()
    (academy_dir / "train_script.py").write_text("print(1)", encoding="utf-8")

    assert (
        discovery.ModelManagerDiscoveryMixin._is_local_model_candidate(
            academy_dir,
            set(),
        )
        is False
    )


def test_local_model_candidate_workspace_fallback(tmp_path: Path) -> None:
    plain_dir = tmp_path / "gemma-3"
    plain_dir.mkdir()

    assert (
        discovery.ModelManagerDiscoveryMixin._is_local_model_candidate(
            plain_dir,
            set(),
            allow_workspace_fallback=False,
        )
        is False
    )
    assert (
        discovery.ModelManagerDiscoveryMixin._is_local_model_candidate(
            plain_dir,
            set(),
            allow_workspace_fallback=True,
        )
        is True
    )


def test_looks_like_runtime_dir_helpers(tmp_path: Path) -> None:
    onnx_by_metadata = tmp_path / "onnx-meta"
    onnx_by_metadata.mkdir()
    (onnx_by_metadata / discovery.ONNX_METADATA_FILENAME).write_text(
        "{}",
        encoding="utf-8",
    )
    assert discovery.ModelManagerDiscoveryMixin._looks_like_onnx_runtime_dir(
        onnx_by_metadata
    )

    onnx_by_genai = tmp_path / "onnx-genai"
    onnx_by_genai.mkdir()
    (onnx_by_genai / "genai_config.json").write_text("{}", encoding="utf-8")
    assert discovery.ModelManagerDiscoveryMixin._looks_like_onnx_runtime_dir(
        onnx_by_genai
    )

    onnx_by_file = tmp_path / "onnx-file"
    onnx_by_file.mkdir()
    (onnx_by_file / "model.onnx").write_text("x", encoding="utf-8")
    assert discovery.ModelManagerDiscoveryMixin._looks_like_onnx_runtime_dir(
        onnx_by_file
    )

    hf_by_safetensors = tmp_path / "hf-safe"
    hf_by_safetensors.mkdir()
    (hf_by_safetensors / "config.json").write_text("{}", encoding="utf-8")
    (hf_by_safetensors / "model.safetensors").write_text("x", encoding="utf-8")
    assert discovery.ModelManagerDiscoveryMixin._looks_like_hf_runtime_dir(
        hf_by_safetensors
    )

    hf_by_bin = tmp_path / "hf-bin"
    hf_by_bin.mkdir()
    (hf_by_bin / "config.json").write_text("{}", encoding="utf-8")
    (hf_by_bin / "pytorch_model-00001.bin").write_text("x", encoding="utf-8")
    assert discovery.ModelManagerDiscoveryMixin._looks_like_hf_runtime_dir(hf_by_bin)


def test_is_academy_artifact_dir_recognizes_training_outputs(tmp_path: Path) -> None:
    run_dir = tmp_path / "self_learning_123"
    run_dir.mkdir()
    assert discovery.ModelManagerDiscoveryMixin._is_academy_artifact_dir(run_dir)

    checkpoint_dir = tmp_path / "checkpoint-200"
    checkpoint_dir.mkdir()
    assert discovery.ModelManagerDiscoveryMixin._is_academy_artifact_dir(checkpoint_dir)

    training_log_only = tmp_path / "train-output"
    training_log_only.mkdir()
    (training_log_only / "training.log").write_text("step", encoding="utf-8")
    assert discovery.ModelManagerDiscoveryMixin._is_academy_artifact_dir(
        training_log_only
    )


@pytest.mark.asyncio
async def test_list_local_models_registers_local_and_ollama(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mgr = _Discovery(tmp_path)
    (mgr.models_dir / "tiny.gguf").write_text("x", encoding="utf-8")

    monkeypatch.setattr(
        discovery,
        "TrafficControlledHttpClient",
        lambda **_: _Client(
            _Response(
                200,
                {
                    "models": [
                        {
                            "name": "llama3:latest",
                            "digest": "sha",
                            "size": 42,
                            "details": {"quantization_level": "q4"},
                        }
                    ]
                },
            )
        ),
    )

    models = await mgr.list_local_models()
    names = {m["name"] for m in models}
    assert "tiny.gguf" in names
    assert "llama3:latest" in names


@pytest.mark.asyncio
async def test_list_local_models_registers_vllm_runtime_from_academy_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mgr = _Discovery(tmp_path)
    runtime_dir = mgr.models_dir / "self_learning_run-123" / "runtime_vllm"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    (runtime_dir / "config.json").write_text("{}", encoding="utf-8")
    (runtime_dir / "model.safetensors").write_text("x", encoding="utf-8")

    monkeypatch.setattr(
        discovery,
        "TrafficControlledHttpClient",
        lambda **_: _Client(_Response(500, {"models": []})),
    )

    models = await mgr.list_local_models()
    model_names = {model["name"] for model in models}
    assert "venom-adapter-self_learning_run-123" in model_names
    runtime_model = next(
        model
        for model in models
        if model["name"] == "venom-adapter-self_learning_run-123"
    )
    assert runtime_model["provider"] == "vllm"
    assert runtime_model["path"] == str(runtime_dir)


@pytest.mark.asyncio
async def test_list_local_models_network_error_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mgr = _Discovery(tmp_path)
    (mgr.models_dir / "tiny.gguf").write_text("x", encoding="utf-8")
    req = discovery.httpx.Request("GET", "http://localhost/api/tags")
    monkeypatch.setattr(
        discovery,
        "TrafficControlledHttpClient",
        lambda **_: _RaisingClient(discovery.httpx.ConnectError("down", request=req)),
    )
    models = await mgr.list_local_models()
    assert any(model["name"] == "tiny.gguf" for model in models)
    assert mgr._last_ollama_warning > 0.0

    monkeypatch.setattr(
        discovery,
        "TrafficControlledHttpClient",
        lambda **_: _Client(_Response(500, {"models": []})),
    )
    models = await mgr.list_local_models()
    assert any(model["name"] == "tiny.gguf" for model in models)
