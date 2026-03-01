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
