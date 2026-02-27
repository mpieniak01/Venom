from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from venom_core.core import model_registry_catalog as catalog
from venom_core.core import model_registry_manifest as manifest
from venom_core.core import model_registry_operations as operations
from venom_core.core import model_registry_runtime as runtime
from venom_core.core.model_registry_types import (
    ModelCapabilities,
    ModelMetadata,
    ModelOperation,
    ModelProvider,
    OperationStatus,
)


class _DummyTask:
    def add_done_callback(self, _cb):
        return None

    def cancelled(self) -> bool:
        return False

    def exception(self):
        return None


def _create_task_stub(coro):
    coro.close()
    return _DummyTask()


@pytest.mark.asyncio
async def test_catalog_and_news_paths():
    registry = SimpleNamespace(
        _external_cache={},
        _external_cache_ttl_seconds=3600,
        hf_client=SimpleNamespace(
            list_models=AsyncMock(
                return_value=[
                    {"modelId": "org/model-a", "downloads": 1, "likes": 2, "tags": []}
                ]
            ),
            fetch_blog_feed=AsyncMock(return_value=[{"title": "n"}]),
            fetch_papers_month=AsyncMock(return_value=[{"title": "p"}]),
            search_models=AsyncMock(
                return_value=[
                    {"modelId": "org/model-x", "downloads": 3, "likes": 1, "tags": []}
                ]
            ),
        ),
        ollama_catalog_client=SimpleNamespace(
            list_tags=AsyncMock(
                return_value={
                    "models": [
                        {
                            "name": "llama3:8b",
                            "size": 2 * 1024**3,
                            "details": {
                                "family": "llama",
                                "parameter_size": "8B",
                                "quantization_level": "Q4",
                                "format": "gguf",
                            },
                        }
                    ]
                }
            ),
            search_models=AsyncMock(
                return_value=[{"name": "phi3:mini", "description": "mini"}]
            ),
        ),
    )

    trend = await catalog.list_trending_models(registry, ModelProvider.HUGGINGFACE, 5)
    assert trend["stale"] is False
    assert trend["models"][0]["provider"] == "huggingface"

    cat = await catalog.list_catalog_models(registry, ModelProvider.OLLAMA, 5)
    assert cat["models"][0]["runtime"] == "ollama"
    assert cat["models"][0]["size_gb"] == 2.0

    # cache hit path
    cached = await catalog.list_catalog_models(registry, ModelProvider.OLLAMA, 5)
    assert cached["stale"] is False
    assert len(cached["models"]) == 1

    news_blog = await catalog.list_news(
        registry, ModelProvider.HUGGINGFACE, kind="blog"
    )
    news_papers = await catalog.list_news(
        registry, ModelProvider.HUGGINGFACE, kind="papers", month="2026-02"
    )
    news_other = await catalog.list_news(registry, ModelProvider.OLLAMA)
    assert news_blog["items"] and news_papers["items"]
    assert news_other["items"] == []

    search_hf = await catalog.search_external_models(
        registry, ModelProvider.HUGGINGFACE, "phi"
    )
    search_ollama = await catalog.search_external_models(
        registry, ModelProvider.OLLAMA, "phi"
    )
    search_short = await catalog.search_external_models(
        registry, ModelProvider.HUGGINGFACE, "x"
    )
    assert search_hf["count"] == 1
    assert search_ollama["models"][0]["description"] == "mini"
    assert search_short["count"] == 0


@pytest.mark.asyncio
async def test_catalog_error_paths_and_formatters():
    registry = SimpleNamespace(
        _external_cache={},
        _external_cache_ttl_seconds=3600,
        hf_client=SimpleNamespace(
            list_models=AsyncMock(side_effect=RuntimeError("hf-down")),
            fetch_blog_feed=AsyncMock(side_effect=RuntimeError("news-down")),
            fetch_papers_month=AsyncMock(side_effect=RuntimeError("papers-down")),
            search_models=AsyncMock(side_effect=RuntimeError("search-down")),
        ),
        ollama_catalog_client=SimpleNamespace(
            list_tags=AsyncMock(return_value={"models": [{"name": ""}]}),
            search_models=AsyncMock(side_effect=RuntimeError("ollama-down")),
        ),
    )
    failed_catalog = await catalog.list_catalog_models(
        registry, ModelProvider.HUGGINGFACE, 5
    )
    assert failed_catalog["stale"] is True
    assert failed_catalog["models"] == []

    failed_news = await catalog.list_news(registry, ModelProvider.HUGGINGFACE)
    assert failed_news["stale"] is True
    assert "news-down" in failed_news["error"]

    # default branch with unsupported provider
    unknown = await catalog.search_external_models(registry, ModelProvider.VLLM, "abc")
    assert unknown["count"] == 0

    search_err = await catalog.search_external_models(
        registry, ModelProvider.HUGGINGFACE, "abc"
    )
    assert search_err["count"] == 0
    assert "error" in search_err

    # non-list payload branch
    registry.hf_client.list_models = AsyncMock(return_value={"items": []})
    payload = await catalog._fetch_huggingface_models(
        registry, sort="downloads", limit=2
    )
    assert payload == []

    entry = catalog._format_catalog_entry(
        provider=ModelProvider.OLLAMA,
        model_name="m",
        display_name="M",
        runtime="ollama",
    )
    assert entry["tags"] == []


def test_manifest_load_and_save_paths(tmp_path: Path):
    registry = SimpleNamespace(manifest_path=tmp_path / "manifest.json", manifest={})

    manifest.load_manifest(registry)
    assert registry.manifest == {}

    registry.manifest_path.write_text(
        json.dumps(
            {
                "models": [
                    {
                        "name": "m1",
                        "provider": "ollama",
                        "display_name": "M1",
                        "status": "installed",
                        "runtime": "ollama",
                        "capabilities": {
                            "generation_schema": {
                                "temperature": {
                                    "type": "float",
                                    "default": 0.2,
                                    "min": 0.0,
                                    "max": 1.0,
                                }
                            }
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    manifest.load_manifest(registry)
    assert "m1" in registry.manifest
    assert registry.manifest["m1"].capabilities.generation_schema is not None

    manifest.save_manifest(registry)
    saved = json.loads(registry.manifest_path.read_text(encoding="utf-8"))
    assert "updated_at" in saved
    assert saved["models"][0]["name"] == "m1"

    with patch("builtins.open", side_effect=OSError("boom")):
        manifest.save_manifest(registry)


@pytest.mark.asyncio
async def test_runtime_paths(monkeypatch, tmp_path: Path):
    settings = SimpleNamespace(
        REPO_ROOT=str(tmp_path),
        LLM_MODEL_NAME="",
        ACTIVE_LLM_SERVER="",
    )
    config_manager = SimpleNamespace(update_config=Mock())

    template_dir = tmp_path / "model_dir"
    template_dir.mkdir(parents=True, exist_ok=True)
    (template_dir / "chat_template.jinja").write_text("{{ x }}", encoding="utf-8")

    with (
        patch("venom_core.config.SETTINGS", settings),
        patch("venom_core.services.config_manager.config_manager", config_manager),
    ):
        meta = ModelMetadata(
            name="m1",
            provider=ModelProvider.HUGGINGFACE,
            display_name="M1",
            runtime="vllm",
            local_path=str(template_dir),
        )
        updates = {}
        runtime.apply_vllm_activation_updates(
            SimpleNamespace(),
            "m1",
            meta,
            updates,
            settings,
        )
        assert updates["VLLM_SERVED_MODEL_NAME"] == "m1"
        assert updates["VLLM_CHAT_TEMPLATE"].endswith("chat_template.jinja")

        runtime.apply_model_activation_config(SimpleNamespace(), "m1", "vllm", meta)
        assert settings.ACTIVE_LLM_SERVER == "vllm"

    bad = SimpleNamespace()

    class _Reject:
        def __setattr__(self, _k, _v):
            raise RuntimeError("nope")

    runtime.safe_setattr(_Reject(), "X", 1)
    runtime.safe_setattr(bad, "Y", 2)
    assert bad.Y == 2

    registry = SimpleNamespace(
        manifest={},
        providers={},
        _save_manifest=Mock(),
    )
    assert (
        await runtime.ensure_model_metadata_for_activation(registry, "x", "vllm")
        is False
    )

    provider = SimpleNamespace(
        get_model_info=AsyncMock(
            return_value=ModelMetadata(
                name="x",
                provider=ModelProvider.OLLAMA,
                display_name="x",
                runtime="ollama",
            )
        )
    )
    registry.providers = {ModelProvider.OLLAMA: provider}
    assert (
        await runtime.ensure_model_metadata_for_activation(registry, "x", "ollama")
        is True
    )
    assert "x" in registry.manifest

    monkeypatch.setattr(
        runtime,
        "ensure_model_metadata_for_activation",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        runtime,
        "restart_runtime_after_activation",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        runtime,
        "apply_model_activation_config",
        Mock(return_value=settings),
    )
    ok = await runtime.activate_model(
        SimpleNamespace(
            manifest={
                "x": ModelMetadata(
                    name="x",
                    provider=ModelProvider.OLLAMA,
                    display_name="x",
                    runtime="ollama",
                )
            }
        ),
        "x",
        "ollama",
    )
    assert ok is True


@pytest.mark.asyncio
async def test_operations_paths(monkeypatch):
    asyncio_lock = AsyncMock()
    asyncio_lock.__aenter__.return_value = None
    asyncio_lock.__aexit__.return_value = None

    provider_obj = SimpleNamespace(
        install_model=AsyncMock(return_value=True),
        remove_model=AsyncMock(return_value=True),
    )
    registry = SimpleNamespace(
        providers={
            ModelProvider.OLLAMA: provider_obj,
            ModelProvider.HUGGINGFACE: provider_obj,
        },
        operations={},
        manifest={},
        _runtime_locks={"ollama": asyncio_lock, "vllm": asyncio_lock},
        _background_tasks=set(),
        _save_manifest=Mock(),
    )

    with patch(
        "venom_core.core.model_registry_operations.asyncio.create_task",
        side_effect=_create_task_stub,
    ):
        op_id = await operations.install_model(
            registry, "m", ModelProvider.OLLAMA, runtime="ollama"
        )
    assert op_id in registry.operations

    with pytest.raises(ValueError):
        await operations.install_model(
            registry, "m", ModelProvider.OLLAMA, runtime="vllm"
        )
    with pytest.raises(ValueError):
        await operations.install_model(
            registry, "m", ModelProvider.VLLM, runtime="vllm"
        )

    op = ModelOperation(
        operation_id="1",
        model_name="m",
        operation_type="install",
        status=OperationStatus.PENDING,
    )
    await operations._install_model_task(registry, op, ModelProvider.OLLAMA, "ollama")
    assert op.status == OperationStatus.COMPLETED
    assert "m" in registry.manifest

    provider_obj.install_model = AsyncMock(return_value=False)
    op_fail = ModelOperation(
        operation_id="2",
        model_name="m2",
        operation_type="install",
        status=OperationStatus.PENDING,
    )
    await operations._install_model_task(
        registry, op_fail, ModelProvider.OLLAMA, "ollama"
    )
    assert op_fail.status == OperationStatus.FAILED

    registry.manifest["m"] = ModelMetadata(
        name="m",
        provider=ModelProvider.OLLAMA,
        display_name="m",
        runtime="ollama",
        capabilities=ModelCapabilities(),
    )
    with patch(
        "venom_core.core.model_registry_operations.asyncio.create_task",
        side_effect=_create_task_stub,
    ):
        remove_id = await operations.remove_model(registry, "m")
    assert remove_id in registry.operations

    op_remove = ModelOperation(
        operation_id="3",
        model_name="m",
        operation_type="remove",
        status=OperationStatus.PENDING,
    )
    await operations._remove_model_task(registry, op_remove, ModelProvider.OLLAMA)
    assert op_remove.status == OperationStatus.COMPLETED

    with pytest.raises(ValueError):
        await operations.remove_model(registry, "missing")

    # helper accessors
    registry.operations["x"] = op_remove
    assert operations.get_operation_status(registry, "x") is op_remove
    assert operations.list_operations(registry, limit=1)[0] is op_remove
    assert operations.get_model_capabilities(registry, "missing") is None
