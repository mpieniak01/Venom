"""Tests for Academy self-learning service."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from venom_core.config import SETTINGS
from venom_core.services.academy.self_learning_service import SelfLearningService


class DummyEmbeddingService:
    def __init__(
        self,
        *,
        service_type: str = "local",
        fallback_active: bool = False,
        embedding_dimension: int = 384,
    ) -> None:
        self.service_type = service_type
        self._local_fallback_mode = fallback_active
        self.embedding_dimension = embedding_dimension


class DummyVectorStore:
    def __init__(self, *, fallback_active: bool = False) -> None:
        self.calls: list[dict[str, object]] = []
        self.embedding_service = DummyEmbeddingService(fallback_active=fallback_active)

    def upsert(self, text, metadata=None, collection_name=None, chunk_text=False):
        self.calls.append(
            {
                "text": text,
                "metadata": metadata,
                "collection_name": collection_name,
                "chunk_text": chunk_text,
            }
        )
        return {"message": "ok", "chunks_count": 1}


class DummyModelManager:
    def __init__(self, models):
        self._models = models

    async def list_local_models(self):
        return self._models


async def _wait_terminal(
    service: SelfLearningService,
    run_id: str,
    timeout_seconds: float = 5.0,
):
    terminal = {"completed", "completed_with_warnings", "failed"}
    deadline = asyncio.get_event_loop().time() + timeout_seconds
    while asyncio.get_event_loop().time() < deadline:
        status = service.get_status(run_id)
        if status is not None and status["status"] in terminal:
            return status
        await asyncio.sleep(0.05)
    raise AssertionError(f"Run {run_id} did not reach terminal state")


@pytest.mark.asyncio
async def test_rag_index_run_completes_and_indexes_vectors(tmp_path: Path):
    repo_root = tmp_path / "repo"
    docs_dir = repo_root / "docs"
    docs_dir.mkdir(parents=True)
    (docs_dir / "intro.md").write_text(
        "Hello knowledge graph from docs", encoding="utf-8"
    )

    vector_store = DummyVectorStore()
    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(repo_root),
        vector_store=vector_store,
    )

    run_id = service.start_run(
        mode="rag_index",
        sources=["docs"],
        rag_config={
            "embedding_profile_id": "local:default",
            "embedding_policy": "strict",
        },
        dry_run=False,
    )
    status = await _wait_terminal(service, run_id)

    assert status["status"] == "completed"
    assert status["progress"]["indexed_vectors"] > 0
    assert vector_store.calls


@pytest.mark.asyncio
async def test_llm_finetune_dry_run_creates_dataset_artifact(tmp_path: Path):
    repo_root = tmp_path / "repo"
    docs_dev_dir = repo_root / "docs_dev"
    docs_dev_dir.mkdir(parents=True)
    (docs_dev_dir / "howto.md").write_text(
        "Developer knowledge sample", encoding="utf-8"
    )

    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(repo_root),
    )
    assert service is not None
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        SelfLearningService,
        "_is_trainable_model_candidate",
        staticmethod(lambda _model_id: True),
    )

    try:
        run_id = service.start_run(
            mode="llm_finetune",
            sources=["docs_dev"],
            llm_config={"base_model": "qwen2.5-coder:3b"},
            dry_run=True,
        )
        status = await _wait_terminal(service, run_id)
    finally:
        monkeypatch.undo()

    assert status["status"] == "completed"
    dataset_path = status["artifacts"].get("dataset_path")
    assert isinstance(dataset_path, str)
    assert Path(dataset_path).exists()


@pytest.mark.asyncio
async def test_run_with_binary_only_input_ends_with_warnings(tmp_path: Path):
    repo_root = tmp_path / "repo"
    docs_dir = repo_root / "docs"
    docs_dir.mkdir(parents=True)
    (docs_dir / "binary.md").write_bytes(b"\x00\x01\x02")

    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(repo_root),
        vector_store=DummyVectorStore(),
    )

    run_id = service.start_run(
        mode="rag_index",
        sources=["docs"],
        rag_config={
            "embedding_profile_id": "local:default",
            "embedding_policy": "strict",
        },
        dry_run=False,
    )
    status = await _wait_terminal(service, run_id)

    assert status["status"] == "completed_with_warnings"
    assert "No files processed" in (status.get("error_message") or "")


def test_start_run_rejects_empty_sources(tmp_path: Path):
    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"), repo_root=str(tmp_path)
    )
    with pytest.raises(ValueError, match="At least one source"):
        service.start_run(mode="rag_index", sources=[])


def test_start_run_rejects_llm_without_base_model(tmp_path: Path):
    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"), repo_root=str(tmp_path)
    )
    with pytest.raises(ValueError, match="base_model"):
        service.start_run(mode="llm_finetune", sources=["docs"], dry_run=True)


def test_start_run_uses_shared_trainable_model_validator(tmp_path: Path):
    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(tmp_path),
        is_model_trainable_fn=lambda _model_id: False,
    )
    with pytest.raises(ValueError, match="not trainable"):
        service.start_run(
            mode="llm_finetune",
            sources=["docs"],
            llm_config={"base_model": "unsloth/Phi-3-mini-4k-instruct"},
            dry_run=True,
        )


def test_start_run_rejects_rag_without_embedding_profile(tmp_path: Path):
    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"), repo_root=str(tmp_path)
    )
    with pytest.raises(ValueError, match="embedding_profile_id"):
        service.start_run(mode="rag_index", sources=["docs"], dry_run=True)


@pytest.mark.asyncio
async def test_capabilities_exposes_trainable_models_and_embedding_profiles(
    tmp_path: Path,
):
    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(tmp_path),
        vector_store=DummyVectorStore(),
    )

    async def _mock_models() -> list[dict[str, object]]:
        return [
            {
                "model_id": "qwen2.5-coder:3b",
                "label": "qwen2.5-coder:3b",
                "provider": "ollama",
                "recommended": True,
                "runtime_compatibility": {"ollama": True},
                "recommended_runtime": "ollama",
            }
        ]

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(service, "_load_trainable_models", _mock_models)
    try:
        payload = await service.get_capabilities()
    finally:
        monkeypatch.undo()

    assert payload["default_base_model"] == "qwen2.5-coder:3b"
    assert payload["default_embedding_profile_id"] == "local:default"
    assert payload["embedding_profiles"][0]["healthy"] is True


@pytest.mark.asyncio
async def test_capabilities_uses_shared_trainable_models_loader(tmp_path: Path):
    async def _loader(_mgr):
        return [
            {
                "model_id": "custom/model",
                "label": "Custom Model",
                "provider": "huggingface",
                "trainable": True,
                "recommended": False,
                "runtime_compatibility": {"vllm": True},
                "recommended_runtime": "vllm",
            }
        ]

    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(tmp_path),
        vector_store=DummyVectorStore(),
        trainable_models_loader=_loader,
    )
    payload = await service.get_capabilities()
    assert payload["trainable_models"][0]["model_id"] == "custom/model"


@pytest.mark.asyncio
async def test_rag_strict_policy_fails_when_fallback_active(tmp_path: Path):
    repo_root = tmp_path / "repo"
    docs_dir = repo_root / "docs"
    docs_dir.mkdir(parents=True)
    (docs_dir / "intro.md").write_text(
        "Knowledge for strict mode test", encoding="utf-8"
    )

    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(repo_root),
        vector_store=DummyVectorStore(fallback_active=True),
    )
    run_id = service.start_run(
        mode="rag_index",
        sources=["docs"],
        rag_config={
            "embedding_profile_id": "local:default",
            "embedding_policy": "strict",
        },
        dry_run=False,
    )
    status = await _wait_terminal(service, run_id)

    assert status["status"] == "failed"
    assert "fallback mode" in (status.get("error_message") or "")


@pytest.mark.asyncio
async def test_load_trainable_models_falls_back_when_loader_raises(tmp_path: Path):
    async def _broken_loader(_mgr):
        raise RuntimeError("loader failed")

    manager = DummyModelManager(
        [
            {
                "name": "Qwen/Qwen2.5-Coder-3B-Instruct",
                "provider": "huggingface",
                "runtime": "vllm",
            }
        ]
    )
    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(tmp_path),
        model_manager=manager,
        trainable_models_loader=_broken_loader,
    )

    models = await service._load_trainable_models()
    assert models
    assert any(item["model_id"] == "Qwen/Qwen2.5-Coder-3B-Instruct" for item in models)


@pytest.mark.asyncio
async def test_load_trainable_models_uses_loader_payload_when_present(tmp_path: Path):
    async def _loader(_mgr):
        return [
            {
                "model_id": "custom/model",
                "label": "Custom",
                "provider": "huggingface",
                "trainable": True,
                "runtime_compatibility": {"vllm": True},
                "recommended_runtime": "vllm",
            }
        ]

    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(tmp_path),
        model_manager=DummyModelManager([]),
        trainable_models_loader=_loader,
    )

    models = await service._load_trainable_models()
    assert models == [
        {
            "model_id": "custom/model",
            "label": "Custom",
            "provider": "huggingface",
            "recommended": False,
            "runtime_compatibility": {"vllm": True},
            "recommended_runtime": "vllm",
        }
    ]


@pytest.mark.asyncio
async def test_load_trainable_models_adds_config_default_when_missing(tmp_path: Path):
    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(tmp_path),
        model_manager=DummyModelManager([]),
    )
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(SETTINGS, "ACADEMY_DEFAULT_BASE_MODEL", "custom/default-model")
    monkeypatch.setattr(
        SelfLearningService,
        "_is_trainable_model_candidate",
        staticmethod(lambda _model_id, _provider=None: True),
    )
    try:
        models = await service._load_trainable_models()
    finally:
        monkeypatch.undo()

    assert any(
        item["model_id"] == "custom/default-model" and item["provider"] == "config"
        for item in models
    )


def test_chunk_text_prefers_natural_split_when_possible():
    text = ("alpha beta gamma delta epsilon\n" * 200).strip()
    chunks = SelfLearningService._chunk_text(text, chunk_size=1000, overlap=120)
    assert len(chunks) > 1
    assert all(chunk.strip() for chunk in chunks)


def test_add_log_trims_to_limit(tmp_path: Path):
    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(tmp_path),
    )
    run = type("RunStub", (), {"logs": []})()

    for index in range(520):
        service._add_log(run, f"log-{index}")

    assert len(run.logs) == 500
    assert run.logs[0] == "log-20"


@pytest.mark.asyncio
async def test_rag_allow_fallback_policy_allows_indexing(tmp_path: Path):
    repo_root = tmp_path / "repo"
    docs_dir = repo_root / "docs"
    docs_dir.mkdir(parents=True)
    (docs_dir / "intro.md").write_text(
        "Knowledge for fallback mode test", encoding="utf-8"
    )

    vector_store = DummyVectorStore(fallback_active=True)
    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(repo_root),
        vector_store=vector_store,
    )
    run_id = service.start_run(
        mode="rag_index",
        sources=["docs"],
        rag_config={
            "embedding_profile_id": "local:default",
            "embedding_policy": "allow_fallback",
        },
        dry_run=False,
    )
    status = await _wait_terminal(service, run_id)

    assert status["status"] == "completed"
    assert vector_store.calls


def test_delete_run_rejects_invalid_identifier(tmp_path: Path):
    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"), repo_root=str(tmp_path)
    )
    assert service.delete_run("../../etc/passwd") is False
