"""Tests for Academy self-learning service."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock

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
    assert "repo_commit_sha" in status["artifacts"]
    freshness = status["artifacts"].get("knowledge_freshness")
    assert isinstance(freshness, dict)
    assert freshness.get("mode") == "indexed"


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
    report_path = status["artifacts"].get("dataset_report_path")
    assert isinstance(report_path, str)
    report_payload = json.loads(Path(report_path).read_text(encoding="utf-8"))
    assert report_payload["strategy"] == "reconstruct"
    assert report_payload["quality_ok"] is True
    evaluation = status["artifacts"].get("evaluation")
    assert isinstance(evaluation, dict)
    assert evaluation.get("kind") == "proxy_eval"
    assert evaluation.get("decision") in {"promote", "reject"}
    eval_report_path = status["artifacts"].get("evaluation_report_path")
    assert isinstance(eval_report_path, str)
    assert Path(eval_report_path).exists()


@pytest.mark.asyncio
async def test_llm_finetune_repo_tasks_strategy_uses_task_mix_and_report(
    tmp_path: Path,
):
    repo_root = tmp_path / "repo"
    docs_dir = repo_root / "docs"
    docs_dir.mkdir(parents=True)
    (docs_dir / "architecture.md").write_text(
        "Venom architecture module A.\n" * 120,
        encoding="utf-8",
    )

    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(repo_root),
    )
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        SelfLearningService,
        "_is_trainable_model_candidate",
        staticmethod(lambda _model_id: True),
    )

    try:
        run_id = service.start_run(
            mode="llm_finetune",
            sources=["docs"],
            llm_config={
                "base_model": "qwen2.5-coder:3b",
                "dataset_strategy": "repo_tasks_basic",
                "task_mix_preset": "repair-heavy",
            },
            dry_run=True,
        )
        status = await _wait_terminal(service, run_id)
    finally:
        monkeypatch.undo()

    assert status["status"] == "completed"
    report_path = status["artifacts"].get("dataset_report_path")
    assert isinstance(report_path, str)
    report_payload = json.loads(Path(report_path).read_text(encoding="utf-8"))
    assert report_payload["strategy"] == "repo_tasks_basic"
    assert report_payload["task_mix_preset"] == "repair-heavy"
    assert report_payload["accepted_records"] > 0
    assert report_payload["task_distribution"].get("bugfix_hint", 0) > 0
    evaluation = status["artifacts"].get("evaluation")
    assert isinstance(evaluation, dict)
    assert evaluation.get("mode") == "llm_finetune"


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
    models = {item["model"] for item in payload["embedding_profiles"]}
    assert "sentence-transformers/all-MiniLM-L6-v2" in models
    assert "intfloat/multilingual-e5-base" in models
    assert any(
        item["model"] == "intfloat/multilingual-e5-base" and item["healthy"] is False
        for item in payload["embedding_profiles"]
    )


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


def test_set_runtime_dependencies_updates_runtime_fields(tmp_path: Path):
    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(tmp_path),
    )
    vector_store = object()
    gpu_habitat = object()
    model_manager = object()
    loader = lambda *_: []  # noqa: E731
    trainable = lambda _model_id: True  # noqa: E731

    service.set_runtime_dependencies(
        vector_store=vector_store,
        gpu_habitat=gpu_habitat,
        model_manager=model_manager,
        trainable_models_loader=loader,
        is_model_trainable_fn=trainable,
    )

    assert service.vector_store is vector_store
    assert service.gpu_habitat is gpu_habitat
    assert service.model_manager is model_manager
    assert service.trainable_models_loader is loader
    assert service.is_model_trainable_fn is trainable


def test_delete_and_clear_runs_cancel_active_pipeline_tasks(tmp_path: Path):
    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(tmp_path),
    )
    run_id_1 = "11111111-1111-1111-1111-111111111111"
    run_id_2 = "22222222-2222-2222-2222-222222222222"

    service._runs[run_id_1] = service._run_from_payload(
        {
            "run_id": run_id_1,
            "mode": "rag_index",
            "sources": ["docs"],
            "status": "running",
            "created_at": "2026-03-04T10:00:00+00:00",
        }
    )
    service._runs[run_id_2] = service._run_from_payload(
        {
            "run_id": run_id_2,
            "mode": "rag_index",
            "sources": ["docs"],
            "status": "running",
            "created_at": "2026-03-04T10:00:00+00:00",
        }
    )

    task_1 = MagicMock()
    task_1.done.return_value = False
    task_2 = MagicMock()
    task_2.done.return_value = False
    service._pipeline_tasks[run_id_1] = task_1
    service._pipeline_tasks[run_id_2] = task_2

    assert service.delete_run(run_id_1) is True
    task_1.cancel.assert_called_once()

    cleared = service.clear_all_runs()
    assert cleared == 1
    task_2.cancel.assert_called_once()


def test_parse_rag_config_normalizes_policy_and_profile(tmp_path: Path):
    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(tmp_path),
    )
    cfg = service._parse_rag_config(
        {
            "collection": "  custom  ",
            "category": "  cat  ",
            "chunk_text": 1,
            "chunking_mode": "invalid-mode",
            "retrieval_mode": "unknown-mode",
            "embedding_profile_id": "  local:default  ",
            "embedding_policy": "unsupported",
        }
    )
    assert cfg.collection == "custom"
    assert cfg.category == "cat"
    assert cfg.chunk_text is True
    assert cfg.chunking_mode == "plain"
    assert cfg.retrieval_mode == "vector"
    assert cfg.embedding_profile_id == "local:default"
    assert cfg.embedding_policy == "strict"


def test_parse_llm_config_normalizes_dataset_strategy_and_task_mix(tmp_path: Path):
    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(tmp_path),
    )
    cfg = service._parse_llm_config(
        {
            "base_model": "qwen2.5-coder:3b",
            "dataset_strategy": "unsupported",
            "task_mix_preset": "invalid",
        }
    )
    assert cfg.base_model == "qwen2.5-coder:3b"
    assert cfg.dataset_strategy == "reconstruct"
    assert cfg.task_mix_preset == "balanced"


def test_extract_file_text_handles_read_error_and_empty_content(tmp_path: Path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True)
    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(repo_root),
    )
    run = service._run_from_payload(
        {
            "run_id": "33333333-3333-3333-3333-333333333333",
            "mode": "rag_index",
            "sources": ["docs"],
            "status": "running",
            "created_at": "2026-03-04T10:00:00+00:00",
        }
    )

    assert service._extract_file_text(run, repo_root / "missing.md") is None
    empty_file = repo_root / "empty.md"
    empty_file.write_text("   ", encoding="utf-8")
    assert service._extract_file_text(run, empty_file) is None


def test_chunk_extracted_files_code_aware_adds_symbol_and_language_metadata(
    tmp_path: Path,
):
    repo_root = tmp_path / "repo"
    source_file = repo_root / "venom_core" / "sample.py"
    source_file.parent.mkdir(parents=True)
    source_file.write_text(
        "class Demo:\n    pass\n\n"
        "def first_function():\n    return 1\n\n"
        "def second_function():\n    return 2\n",
        encoding="utf-8",
    )

    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(repo_root),
    )
    extracted_files = [
        (
            source_file,
            source_file.read_text(encoding="utf-8"),
            "sha",
            "venom_core/sample.py",
            "code",
        )
    ]
    chunks = service._chunk_extracted_files(
        extracted_files,
        rag_mode=True,
        rag_config=service._parse_rag_config(
            {
                "chunking_mode": "code_aware",
                "retrieval_mode": "hybrid",
                "embedding_profile_id": "local:default",
            }
        ),
    )

    assert chunks
    assert any(chunk.get("symbol") for chunk in chunks)
    assert all(chunk.get("language") == "python" for chunk in chunks)
    assert all("last_modified" in chunk for chunk in chunks)


@pytest.mark.asyncio
async def test_run_rag_index_dry_run_and_missing_store_paths(tmp_path: Path):
    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(tmp_path / "repo"),
    )
    run = service._run_from_payload(
        {
            "run_id": "44444444-4444-4444-4444-444444444444",
            "mode": "rag_index",
            "sources": ["docs"],
            "status": "running",
            "created_at": "2026-03-04T10:00:00+00:00",
            "dry_run": True,
            "rag_config": {
                "embedding_profile_id": "local:default",
                "embedding_policy": "strict",
            },
        }
    )
    service._run_rag_index(run, chunks=[{"text": "x"}], extracted_files=[])
    assert run.progress.indexed_vectors == 1
    assert isinstance(run.artifacts.get("knowledge_freshness"), dict)
    assert run.artifacts.get("knowledge_freshness", {}).get("mode") == "dry_run"

    run.dry_run = False
    with pytest.raises(Exception, match="VectorStore is not available"):
        service._run_rag_index(run, chunks=[{"text": "x"}], extracted_files=[])


def test_run_dir_rejects_invalid_identifier(tmp_path: Path):
    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(tmp_path),
    )
    with pytest.raises(ValueError, match="Invalid run_id"):
        service._run_dir("not-a-uuid")


def test_resolve_repo_commit_sha_returns_none_outside_git(tmp_path: Path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True)
    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(repo_root),
    )
    assert service._resolve_repo_commit_sha() is None


@pytest.mark.asyncio
async def test_rag_index_run_writes_proxy_evaluation_artifact(tmp_path: Path):
    repo_root = tmp_path / "repo"
    docs_dir = repo_root / "docs"
    docs_dir.mkdir(parents=True)
    (docs_dir / "guide.md").write_text("Venom knowledge.\n" * 80, encoding="utf-8")

    class EmbeddingServiceStub:
        service_type = "local"
        local_model_name = "sentence-transformers/all-MiniLM-L6-v2"
        embedding_dimension = 384
        _local_fallback_mode = False

    class VectorStoreStub:
        embedding_service = EmbeddingServiceStub()

        def upsert(self, **_kwargs):
            return {"chunks_count": 1}

    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(repo_root),
        vector_store=VectorStoreStub(),
    )
    run_id = service.start_run(
        mode="rag_index",
        sources=["docs"],
        rag_config={
            "embedding_profile_id": "local:default",
            "chunking_mode": "code_aware",
            "retrieval_mode": "hybrid",
        },
        dry_run=False,
    )
    status = await _wait_terminal(service, run_id)
    assert status["status"] in {"completed", "completed_with_warnings"}
    evaluation = status["artifacts"].get("evaluation")
    assert isinstance(evaluation, dict)
    assert evaluation.get("mode") == "rag_index"
    assert evaluation.get("kind") == "proxy_eval"
