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

    def _build_search_dirs(self):
        return [self.models_dir]

    def _discover_other_models(self, *_):
        pass


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
    ) == ("folder", "vllm")


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
    blob_dir = mgr.models_dir / "blobs"
    blob_dir.mkdir()
    digest = "sha256:" + "a" * 64
    (blob_dir / digest.replace(":", "-")).write_bytes(b"weights")
    manifest_file.write_text(
        json.dumps(
            {
                "layers": [
                    {
                        "mediaType": "application/vnd.ollama.image.model",
                        "digest": digest,
                        "size": 7,
                    }
                ],
                "config": {"digest": digest, "size": 7},
            }
        )
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
    assert "ollama::qwen:latest" not in loaded_models
    mgr._save_ollama_cache(
        [
            {
                "name": "qwen:latest",
                "digest": "current",
                "quantization": "q4",
                "active": True,
            }
        ]
    )
    loaded_models["ollama::qwen:latest"] = {
        "name": "qwen:latest",
        "digest": "current",
        "active": False,
    }
    mgr._load_ollama_cache(loaded_models)
    assert loaded_models["ollama::qwen:latest"]["quantization"] == "q4"
    assert loaded_models["ollama::qwen:latest"]["active"] is False


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
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.delenv("OLLAMA_ENDPOINT", raising=False)
    monkeypatch.setenv(
        "LLM_LOCAL_ENDPOINT", "http://127.0.0.1:11434/v1/chat/completions"
    )
    assert mgr._resolve_ollama_tags_url() == "http://127.0.0.1:11434/api/tags"

    monkeypatch.setenv("LLM_LOCAL_ENDPOINT", "http://localhost:8014/v1")
    assert mgr._resolve_ollama_tags_url() == "http://localhost:11434/api/tags"

    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
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
        )
        is False
    )
    assert (
        discovery.ModelManagerDiscoveryMixin._is_local_model_candidate(
            plain_dir,
            set(),
        )
        is False
    )


def test_looks_like_runtime_dir_helpers(tmp_path: Path) -> None:
    onnx_by_metadata = tmp_path / "onnx-meta"
    onnx_by_metadata.mkdir()
    (onnx_by_metadata / discovery.ONNX_METADATA_FILENAME).write_text(
        "{}",
        encoding="utf-8",
    )
    assert not discovery.ModelManagerDiscoveryMixin._looks_like_onnx_runtime_dir(
        onnx_by_metadata
    )

    onnx_by_genai = tmp_path / "onnx-genai"
    onnx_by_genai.mkdir()
    (onnx_by_genai / "genai_config.json").write_text("{}", encoding="utf-8")
    assert not discovery.ModelManagerDiscoveryMixin._looks_like_onnx_runtime_dir(
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


def test_payload_evidence_rejects_incomplete_shards_and_accepts_cache_links(tmp_path):
    from venom_core.core.model_inventory import is_hf_model_dir

    (tmp_path / "config.json").write_text("{}")
    index = tmp_path / "model.safetensors.index.json"
    index.write_text(
        json.dumps(
            {"weight_map": {"a": "part.safetensors", "b": "missing.safetensors"}}
        )
    )
    blob = tmp_path.parent / (tmp_path.name + "-blob")
    blob.write_bytes(b"weights")
    (tmp_path / "part.safetensors").symlink_to(blob)
    assert not is_hf_model_dir(tmp_path)
    index.write_text(json.dumps({"weight_map": {"a": "part.safetensors"}}))
    assert is_hf_model_dir(tmp_path)
    index.write_text(json.dumps({"weight_map": {"a": "../outside"}}))
    assert not is_hf_model_dir(tmp_path)


def test_workspaces_metadata_and_empty_weights_are_not_installed_models(tmp_path):
    mgr = _Discovery(tmp_path)
    for name in [
        "cache",
        "metadata",
        "preprod",
        "research",
        "manifests-v2",
        "empty-onnx",
    ]:
        path = mgr.models_dir / name
        path.mkdir()
        (path / "genai_config.json").write_text("{}")
        (path / "venom_onnx_metadata.json").write_text("{}")
    (mgr.models_dir / "empty-onnx/model.onnx").touch()
    models = mgr._discover_local_models()
    assert not any(
        m["provider"] == "vllm" or m["provider"] == "onnx" for m in models.values()
    )


def test_stale_ollama_cache_does_not_resurrect_removed_models(tmp_path, monkeypatch):
    mgr = _Discovery(tmp_path)
    mgr.ollama_cache_path.write_text(
        json.dumps([{"name": "deleted:latest", "provider": "ollama"}])
    )
    monkeypatch.setattr(mgr, "_discover_other_models", lambda *_: None)
    assert mgr._discover_local_models() == {}


def test_model_cache_enumerates_only_complete_snapshots_once(tmp_path):
    from venom_core.core.model_inventory import cached_model_paths

    path = tmp_path / "models--org--kept/snapshots/sha"
    path.mkdir(parents=True)
    (path / "config.json").write_text("{}")
    (path / "model.safetensors").write_bytes(b"weights")
    partial = tmp_path / "models--org--partial/snapshots/sha"
    partial.mkdir(parents=True)
    (partial / "config.json").write_text("{}")
    assert list(cached_model_paths([tmp_path, tmp_path])) == [("org/kept", path)]


@pytest.mark.parametrize("provider", ["ollama", "vllm", "onnx"])
@pytest.mark.asyncio
async def test_runtime_metadata_reports_loaded_models_without_generation(provider):
    import httpx

    from venom_core.services.model_runtime_inventory import observe_runtime_models

    requests = []

    def transport(request):
        requests.append((request.method, request.url.path))
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok", "engine": "onnx-gpu"})
        return httpx.Response(
            200, json={"models": [{"name": "served"}], "data": [{"id": "served"}]}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        result = await observe_runtime_models(
            provider, "http://127.0.0.1:11434/v1", client
        )
    assert result == {"status": "online", "models": ["served"]}
    assert all(method == "GET" for method, _ in requests)


@pytest.mark.asyncio
async def test_offline_and_malformed_metadata_are_distinct():
    import httpx

    from venom_core.services.model_runtime_inventory import observe_runtime_models

    def offline(request):
        raise httpx.ConnectError("refused", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(offline)) as client:
        assert await observe_runtime_models(
            "ollama", "http://localhost:11434", client
        ) == {"status": "offline", "models": None}
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={}))
    ) as client:
        assert await observe_runtime_models(
            "vllm", "http://localhost:8001", client
        ) == {"status": "unverified", "models": None}
        assert await observe_runtime_models(
            "vllm", "https://remote.example", client
        ) == {"status": "unverified", "models": None}


def test_selected_configuration_does_not_imply_loaded_or_cross_engine_activity():
    from venom_core.services.model_runtime_inventory import annotate_runtime_models

    models = [
        {"name": "same", "provider": "ollama"},
        {"name": "same", "provider": "vllm"},
        {"name": "other", "provider": "transformers"},
    ]
    annotate_runtime_models(
        models,
        {
            "ollama": {"status": "offline", "models": None},
            "vllm": {"status": "online", "models": ["same"]},
        },
        "ollama",
        "same",
    )
    assert (
        models[0]["selected"]
        and models[0]["loaded"] is None
        and not models[0]["active"]
    )
    assert models[1]["loaded"] and not models[1]["selected"]
    assert models[2]["loaded"] is None and not models[2]["active"]


def test_sharded_checkpoints_without_index_require_every_shard(tmp_path):
    from venom_core.core.model_inventory import is_hf_model_dir

    (tmp_path / "config.json").write_text("{}")
    (tmp_path / "model-00001-of-00002.safetensors").write_bytes(b"weight")
    assert not is_hf_model_dir(tmp_path)
    (tmp_path / "model-00002-of-00002.safetensors").write_bytes(b"weight")
    assert is_hf_model_dir(tmp_path)


def test_other_runtimes_are_discovered_without_loading_them(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    mgr = _Discovery(tmp_path)
    hf = (
        tmp_path
        / ".local/share/venom/maintenance-comparison/hub/models--org--kept/snapshots/revision"
    )
    hf.mkdir(parents=True)
    (hf / "config.json").write_text("{}")
    (hf / "model.safetensors").write_bytes(b"weights")
    research = mgr.models_dir / "research/rwkv/revision"
    research.mkdir(parents=True)
    (research / "small.pth").write_bytes(b"weights")
    models = {}
    discovery.ModelManagerDiscoveryMixin._discover_other_models(
        mgr, [mgr.models_dir], models
    )
    assert {m["provider"] for m in models.values()} == {"transformers", "rwkv"}


@pytest.mark.asyncio
async def test_inventory_metadata_aggregation_has_no_inference_requests(monkeypatch):
    import httpx

    from venom_core.services.model_runtime_inventory import runtime_inventory

    requests = []

    def transport(request):
        requests.append(request)
        return httpx.Response(200, json={"models": []})

    client = httpx.AsyncClient(transport=httpx.MockTransport(transport))
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_: client)
    snapshot = await runtime_inventory({"ollama": "http://localhost:11434"})
    assert snapshot["ollama"]["status"] == "online"
    assert snapshot["ollama"]["checked_at"]
    assert (
        len(requests) == 1
        and requests[0].method == "GET"
        and requests[0].url.path == "/api/ps"
    )


@pytest.mark.asyncio
async def test_models_endpoint_does_not_mark_remembered_hybrid_model_active(
    monkeypatch,
):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from venom_core.api.routes import models_install as routes

    models = [
        {"name": "old-hybrid", "provider": "ollama"},
        {"name": "Qwen/Qwen3.5-9B", "provider": "transformers"},
    ]
    monkeypatch.setattr(
        routes,
        "get_model_manager",
        lambda: SimpleNamespace(
            list_local_models=AsyncMock(return_value=models),
            _resolve_ollama_tags_url=lambda: "http://localhost:11435/api/tags",
        ),
    )
    runtime = SimpleNamespace(
        provider="openrouter",
        model_name="remote",
        to_payload=lambda: {"provider": "openrouter", "model": "remote"},
    )
    monkeypatch.setattr(routes, "get_active_llm_runtime", lambda: runtime)
    monkeypatch.setattr(
        routes.config_manager,
        "get_runtime_snapshot",
        lambda **_: {
            "config": {"HYBRID_LOCAL_MODEL": "old-hybrid"},
            "active_model_id": "remote",
        },
    )
    monkeypatch.setattr(
        routes, "probe_runtime_status", AsyncMock(return_value=("ready", None))
    )
    monkeypatch.setattr(
        routes,
        "runtime_inventory",
        AsyncMock(return_value={"ollama": {"status": "offline", "models": None}}),
    )
    result = await routes.list_models()
    assert not any(m["active"] or m["selected"] for m in result["models"])
    assert result["models"][1]["activation_supported"] is False
    assert result["models"][1]["chat_compatible"] is False
    assert "transformers" in result["providers"]
    assert (
        routes.runtime_inventory.call_args.args[0]["ollama"]
        == "http://localhost:11435/api/tags"
    )


@pytest.mark.parametrize("weight_map", [None, [], "invalid", 42])
def test_invalid_checkpoint_weight_map_is_not_an_installation(tmp_path, weight_map):
    from venom_core.core.model_inventory import is_hf_model_dir

    (tmp_path / "config.json").write_text("{}")
    (tmp_path / "model.safetensors").write_bytes(b"weights")
    (tmp_path / "model.safetensors.index.json").write_text(
        json.dumps({"weight_map": weight_map})
    )
    assert not is_hf_model_dir(tmp_path)


@pytest.mark.asyncio
async def test_invalid_runtime_url_cannot_break_other_engine_observations():
    import httpx

    from venom_core.services.model_runtime_inventory import observe_runtime_models

    requests = []

    def transport(request):
        requests.append(request)
        return httpx.Response(200, json={"models": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        invalid = await observe_runtime_models("vllm", "http://[::1", client)
        valid = await observe_runtime_models("ollama", "http://localhost:11434", client)
    assert invalid == {"status": "unverified", "models": None}
    assert valid == {"status": "online", "models": []}
    assert len(requests) == 1
