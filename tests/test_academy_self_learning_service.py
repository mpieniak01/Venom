"""Tests for Academy self-learning service."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from venom_core.config import SETTINGS
from venom_core.services.academy.self_learning_service import (
    DEFAULT_EVALUATION_BASELINES,
    RagConfig,
    SelfLearningService,
    _normalize_evaluation_baseline_payload,
)


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


class DummyModelManagerWithUnload(DummyModelManager):
    def __init__(self, models):
        super().__init__(models)
        self.unload_calls = 0

    async def unload_all(self):
        self.unload_calls += 1
        return True


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
async def test_rag_index_docs_en_excludes_docs_pl_subtree(tmp_path: Path):
    repo_root = tmp_path / "repo"
    docs_dir = repo_root / "docs"
    docs_pl_dir = docs_dir / "PL"
    docs_pl_dir.mkdir(parents=True)
    (docs_dir / "intro.md").write_text("English docs content", encoding="utf-8")
    (docs_pl_dir / "wstep.md").write_text("Polska dokumentacja", encoding="utf-8")

    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(repo_root),
    )

    run_id = service.start_run(
        mode="rag_index",
        sources=["docs_en"],
        rag_config={
            "embedding_profile_id": "local:default",
            "embedding_policy": "strict",
        },
        dry_run=True,
    )
    status = await _wait_terminal(service, run_id)

    assert status["status"] == "completed"
    assert status["progress"]["files_discovered"] == 1


@pytest.mark.asyncio
async def test_rag_index_deduplicates_overlapping_docs_sources(tmp_path: Path):
    repo_root = tmp_path / "repo"
    docs_dir = repo_root / "docs"
    docs_pl_dir = docs_dir / "PL"
    docs_pl_dir.mkdir(parents=True)
    (docs_dir / "intro.md").write_text("English docs content", encoding="utf-8")
    (docs_pl_dir / "wstep.md").write_text("Polska dokumentacja", encoding="utf-8")

    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(repo_root),
    )

    run_id = service.start_run(
        mode="rag_index",
        sources=["docs", "docs_pl"],
        rag_config={
            "embedding_profile_id": "local:default",
            "embedding_policy": "strict",
        },
        dry_run=True,
    )
    status = await _wait_terminal(service, run_id)

    assert status["status"] == "completed"
    assert status["progress"]["files_discovered"] == 2


@pytest.mark.asyncio
async def test_rag_index_repo_readmes_source_collects_only_root_readmes(tmp_path: Path):
    repo_root = tmp_path / "repo"
    docs_dir = repo_root / "docs"
    nested_dir = repo_root / "venom_core"
    docs_dir.mkdir(parents=True)
    nested_dir.mkdir(parents=True)
    (repo_root / "README.md").write_text("Root README EN", encoding="utf-8")
    (repo_root / "README_PL.md").write_text("Root README PL", encoding="utf-8")
    (docs_dir / "README.md").write_text(
        "Docs README should be ignored", encoding="utf-8"
    )
    (nested_dir / "README.md").write_text(
        "Nested README should be ignored", encoding="utf-8"
    )

    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(repo_root),
    )

    run_id = service.start_run(
        mode="rag_index",
        sources=["repo_readmes"],
        rag_config={
            "embedding_profile_id": "local:default",
            "embedding_policy": "strict",
        },
        dry_run=True,
    )
    status = await _wait_terminal(service, run_id)

    assert status["status"] == "completed"
    assert status["progress"]["files_discovered"] == 2


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
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(SETTINGS, "ACADEMY_DEFAULT_BASE_MODEL", "")
    try:
        with pytest.raises(ValueError, match="base_model"):
            service.start_run(mode="llm_finetune", sources=["docs"], dry_run=True)
    finally:
        monkeypatch.undo()


def test_start_run_does_not_fallback_to_default_base_model_when_missing(
    tmp_path: Path,
):
    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(tmp_path),
        is_model_trainable_fn=lambda _model_id: True,
    )
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(SETTINGS, "ACADEMY_DEFAULT_BASE_MODEL", "custom/model")
    try:
        with pytest.raises(ValueError, match="llm_config.base_model is required"):
            service.start_run(mode="llm_finetune", sources=["docs"], dry_run=True)
    finally:
        monkeypatch.undo()


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


def test_start_run_rejects_llm_when_local_runtime_dependencies_missing(tmp_path: Path):
    class _FailingLocalHabitat:
        use_local_runtime = True

        def _check_local_dependencies(self) -> None:
            raise RuntimeError(
                "Brak wymaganych bibliotek do treningu: peft, trl, datasets"
            )

    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(tmp_path),
        gpu_habitat=_FailingLocalHabitat(),
        is_model_trainable_fn=lambda _model_id: True,
    )

    with pytest.raises(ValueError, match="Brak wymaganych bibliotek do treningu"):
        service.start_run(
            mode="llm_finetune",
            sources=["docs"],
            llm_config={"base_model": "unsloth/Phi-3-mini-4k-instruct"},
            dry_run=False,
        )


@pytest.mark.asyncio
async def test_start_run_allows_llm_dry_run_when_local_dependencies_missing(
    tmp_path: Path,
):
    class _FailingLocalHabitat:
        use_local_runtime = True

        def _check_local_dependencies(self) -> None:
            raise RuntimeError(
                "Brak wymaganych bibliotek do treningu: peft, trl, datasets"
            )

    repo_root = tmp_path / "repo"
    docs_dir = repo_root / "docs"
    docs_dir.mkdir(parents=True)
    (docs_dir / "intro.md").write_text(
        "Dry run sample with enough content for dataset quality checks.\n" * 80,
        encoding="utf-8",
    )

    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(repo_root),
        gpu_habitat=_FailingLocalHabitat(),
        is_model_trainable_fn=lambda _model_id: True,
    )

    run_id = service.start_run(
        mode="llm_finetune",
        sources=["docs"],
        llm_config={"base_model": "unsloth/Phi-3-mini-4k-instruct"},
        dry_run=True,
    )
    status = await _wait_terminal(service, run_id)
    assert status["status"] in {"completed", "completed_with_warnings"}
    service.clear_all_runs()


def test_is_trainable_model_handles_blank_and_validator_exception(tmp_path: Path):
    def _raiser(_model_id: str) -> bool:
        raise RuntimeError("validator failed")

    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(tmp_path),
        is_model_trainable_fn=_raiser,
    )

    assert service._is_trainable_model("   ") is False
    assert service._is_trainable_model("unsloth/Phi-3-mini-4k-instruct") is True


def test_resolve_default_embedding_profile_id_falls_back_to_first_profile(
    tmp_path: Path,
):
    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(tmp_path),
    )
    service._embedding_profiles = lambda: [  # type: ignore[method-assign]
        {"profile_id": "profile-a", "healthy": False},
        {"profile_id": "profile-b", "healthy": False},
    ]

    assert service._resolve_default_embedding_profile_id() == "profile-a"


def test_apply_mode_defaults_assigns_default_embedding_profile_for_rag(tmp_path: Path):
    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(tmp_path),
    )
    rag_config = RagConfig()
    service._resolve_default_embedding_profile_id = lambda: "local:default"  # type: ignore[method-assign]

    service._apply_mode_defaults(mode="rag_index", rag_config=rag_config)

    assert rag_config.embedding_profile_id == "local:default"


def test_fetch_local_models_sync_returns_list_from_sync_manager(tmp_path: Path):
    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(tmp_path),
        model_manager=MagicMock(
            list_local_models=MagicMock(return_value=[{"id": "m1"}])
        ),
    )

    assert service._fetch_local_models_sync() == [{"id": "m1"}]


def test_fetch_local_models_sync_returns_list_from_async_manager(tmp_path: Path):
    async def _list_local_models() -> list[dict[str, str]]:
        return [{"id": "m_async"}]

    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(tmp_path),
        model_manager=MagicMock(list_local_models=_list_local_models),
    )

    assert service._fetch_local_models_sync() == [{"id": "m_async"}]


def test_fetch_local_models_sync_returns_empty_on_manager_error(tmp_path: Path):
    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(tmp_path),
        model_manager=MagicMock(
            list_local_models=MagicMock(side_effect=RuntimeError("boom"))
        ),
    )

    assert service._fetch_local_models_sync() == []


def test_fetch_local_models_sync_returns_list_from_async_manager_inside_event_loop(
    tmp_path: Path,
):
    async def _list_local_models() -> list[dict[str, str]]:
        return [{"id": "m_loop"}]

    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(tmp_path),
        model_manager=MagicMock(list_local_models=_list_local_models),
    )

    async def _exercise() -> list[dict[str, str]]:
        return service._fetch_local_models_sync()

    assert asyncio.run(_exercise()) == [{"id": "m_loop"}]


def test_start_run_rejects_rag_without_embedding_profile(tmp_path: Path):
    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"), repo_root=str(tmp_path)
    )
    with pytest.raises(ValueError, match="embedding_profile_id"):
        service.start_run(mode="rag_index", sources=["docs"], dry_run=True)


def test_start_run_rejects_ollama_runtime_without_matching_runtime_family(
    tmp_path: Path,
):
    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"), repo_root=str(tmp_path)
    )
    with pytest.raises(
        ValueError, match="does not expose compatible local runtime targets"
    ):
        service.start_run(
            mode="llm_finetune",
            sources=["docs"],
            llm_config={
                "base_model": "unsloth/Phi-3-mini-4k-instruct",
                "runtime_id": "ollama",
            },
            dry_run=True,
        )


def test_start_run_preserves_requested_base_model_in_runtime_mismatch_error(
    tmp_path: Path,
):
    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(tmp_path),
        is_model_trainable_fn=lambda model_id: model_id == "gemma-3-4b-it",
    )
    with pytest.raises(
        ValueError,
        match="Model 'gemma-3-4b-it' does not expose compatible local runtime targets",
    ):
        service.start_run(
            mode="llm_finetune",
            sources=["repo_readmes"],
            llm_config={
                "base_model": "gemma-3-4b-it",
                "runtime_id": "ollama",
            },
            dry_run=True,
        )


def test_validate_runtime_compatibility_accepts_matching_local_runtime_family(
    tmp_path: Path,
):
    local_models = [
        {
            "name": "gemma-3-4b-it",
            "provider": "vllm",
            "runtime": "vllm",
            "source": "models",
        },
        {
            "name": "gemma3:latest",
            "provider": "ollama",
            "runtime": "ollama",
            "source": "ollama",
        },
    ]
    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(tmp_path),
        is_model_trainable_fn=lambda model_id: model_id == "gemma-3-4b-it",
    )
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(service, "_fetch_local_models_sync", lambda: local_models)

    try:
        service._validate_runtime_compatibility_for_base_model(
            base_model="gemma-3-4b-it",
            runtime_id="ollama",
        )
    finally:
        monkeypatch.undo()


@pytest.mark.asyncio
async def test_start_run_uses_default_embedding_profile_for_rag(tmp_path: Path):
    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(tmp_path),
        vector_store=DummyVectorStore(),
    )
    run_id = service.start_run(mode="rag_index", sources=["docs"], dry_run=True)
    status = service.get_status(run_id)
    assert status is not None
    assert status["rag_config"]["embedding_profile_id"] == "local:default"
    service.clear_all_runs()


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
async def test_capabilities_prefers_model_compatible_with_active_runtime(
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
                "model_id": "unsloth/Phi-3-mini-4k-instruct",
                "label": "phi",
                "provider": "unsloth",
                "recommended": True,
                "runtime_compatibility": {"vllm": True, "ollama": False},
                "recommended_runtime": "vllm",
            },
            {
                "model_id": "qwen2.5-coder:3b",
                "label": "qwen",
                "provider": "ollama",
                "recommended": False,
                "runtime_compatibility": {"vllm": False, "ollama": True},
                "recommended_runtime": "ollama",
            },
        ]

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(service, "_load_trainable_models", _mock_models)
    monkeypatch.setattr(SETTINGS, "ACTIVE_LLM_SERVER", "ollama")
    try:
        payload = await service.get_capabilities()
    finally:
        monkeypatch.undo()

    assert "default_base_model" not in payload


@pytest.mark.asyncio
async def test_capabilities_require_matching_ollama_runtime_family(
    tmp_path: Path,
):
    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(tmp_path),
        vector_store=DummyVectorStore(),
        model_manager=DummyModelManager(
            [
                {
                    "name": "unsloth/Phi-3-mini-4k-instruct",
                    "provider": "unsloth",
                    "runtime": "vllm",
                    "source": "models",
                },
                {
                    "name": "gemma-3-4b-it",
                    "provider": "vllm",
                    "runtime": "vllm",
                    "source": "models",
                },
                {
                    "name": "gemma3:latest",
                    "provider": "ollama",
                    "runtime": "ollama",
                    "source": "ollama",
                },
            ]
        ),
    )

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(SETTINGS, "ACTIVE_LLM_SERVER", "ollama")
    monkeypatch.setattr(
        SETTINGS,
        "ACADEMY_DEFAULT_BASE_MODEL",
        "unsloth/Phi-3-mini-4k-instruct",
    )
    try:
        payload = await service.get_capabilities()
    finally:
        monkeypatch.undo()

    by_id = {item["model_id"]: item for item in payload["trainable_models"]}
    assert by_id["unsloth/Phi-3-mini-4k-instruct"]["runtime_compatibility"] == {
        "vllm": True,
        "ollama": False,
    }
    assert by_id["google/gemma-3-4b-it"]["runtime_compatibility"]["ollama"] is True
    assert "default_base_model" not in payload


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
async def test_load_trainable_models_does_not_add_config_default_when_missing(
    tmp_path: Path,
):
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

    assert not any(item["provider"] == "config" for item in models)
    assert all(item["model_id"] != "custom/default-model" for item in models)


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


def test_add_log_debounces_snapshot_writes(tmp_path: Path):
    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(tmp_path),
    )
    run_id = "123e4567-e89b-42d3-a456-426614174000"
    run = service._run_from_payload(
        {
            "run_id": run_id,
            "mode": "rag_index",
            "sources": ["docs"],
            "status": "running",
            "created_at": "2026-03-05T00:00:00+00:00",
            "logs": [],
        }
    )
    snapshot_calls: list[str] = []
    monkeypatch = pytest.MonkeyPatch()
    monotonic_iter = iter([10.0, 10.2, 11.5])
    monkeypatch.setattr(
        "venom_core.services.academy.self_learning_service.time.monotonic",
        lambda: next(monotonic_iter),
    )
    monkeypatch.setattr(
        service,
        "_append_run_snapshot",
        lambda current_run: snapshot_calls.append(current_run.logs[-1]),
    )
    try:
        service._add_log(run, "step-1")
        service._add_log(run, "step-2")
        service._add_log(run, "step-3")
    finally:
        monkeypatch.undo()

    assert snapshot_calls == ["step-1", "step-3"]


def test_get_status_recovers_orphaned_running_llm_run_with_live_logs(tmp_path: Path):
    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(tmp_path),
    )
    run_id = "77777777-7777-7777-7777-777777777777"
    run = service._run_from_payload(
        {
            "run_id": run_id,
            "mode": "llm_finetune",
            "sources": ["docs"],
            "limits": {},
            "llm_config": {"base_model": "unsloth/Phi-3-mini-4k-instruct"},
            "rag_config": {},
            "status": "running",
            "created_at": "2026-03-05T00:00:00+00:00",
            "started_at": "2026-03-05T00:00:01+00:00",
            "logs": [],
            "artifacts": {},
            "progress": {},
            "error_message": None,
        }
    )
    service._runs[run_id] = run

    class HabitatStub:
        @staticmethod
        def get_training_status(_job_name: str):
            return {"status": "running", "logs": "epoch=1\nloss=0.4567"}

    service.gpu_habitat = HabitatStub()
    payload = service.get_status(run_id)

    assert payload is not None
    assert payload["status"] == "running"
    assert any("[train:running] loss=0.4567" in line for line in payload["logs"])


def test_get_status_recovers_orphaned_finished_llm_run_and_writes_metadata(
    tmp_path: Path,
):
    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(tmp_path),
    )
    models_dir = tmp_path / "models"
    run_id = "88888888-8888-8888-8888-888888888888"
    output_dir = models_dir / f"self_learning_{run_id}"
    adapter_dir = output_dir / "adapter"
    adapter_dir.mkdir(parents=True, exist_ok=True)
    (adapter_dir / "adapter_config.json").write_text("{}", encoding="utf-8")

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(SETTINGS, "ACADEMY_MODELS_DIR", str(models_dir))
    try:
        run = service._run_from_payload(
            {
                "run_id": run_id,
                "mode": "llm_finetune",
                "sources": ["repo_readmes"],
                "limits": {},
                "llm_config": {
                    "base_model": "gemma-3-4b-it",
                    "runtime_id": "ollama",
                },
                "rag_config": {},
                "status": "running",
                "created_at": "2026-03-05T00:00:00+00:00",
                "started_at": "2026-03-05T00:00:01+00:00",
                "logs": [],
                "artifacts": {
                    "requested_base_model": "gemma-3-4b-it",
                    "effective_base_model": "gemma-3-4b-it",
                    "requested_runtime_id": "ollama",
                    "effective_runtime_id": "ollama",
                    "training_base_model": "/home/ubuntu/venom/models/gemma-3-4b-it",
                },
                "progress": {},
                "error_message": None,
            }
        )
        service._runs[run_id] = run

        class HabitatStub:
            @staticmethod
            def get_training_status(_job_name: str):
                return {"status": "finished", "logs": "finished"}

        service.gpu_habitat = HabitatStub()
        payload = service.get_status(run_id)
    finally:
        monkeypatch.undo()

    assert payload is not None
    assert payload["status"] == "completed"
    assert payload["artifacts"]["adapter_path"] == str(adapter_dir)
    metadata_path = output_dir / "metadata.json"
    assert metadata_path.exists()
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["metadata_version"] == 2
    assert metadata["effective_base_model"] == "gemma-3-4b-it"
    assert metadata["requested_runtime_id"] == "ollama"
    assert metadata["effective_runtime_id"] == "ollama"
    assert metadata["source_flow"] == "self_learning"


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


def test_evaluate_llm_run_handles_non_dict_task_distribution(tmp_path: Path):
    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(tmp_path / "repo"),
    )
    run = service._run_from_payload(
        {
            "run_id": "11111111-1111-4111-8111-111111111111",
            "mode": "llm_finetune",
            "sources": ["docs"],
            "llm_config": {
                "dataset_strategy": "repo_tasks_basic",
                "task_mix_preset": "balanced",
            },
            "rag_config": {},
            "progress": {"chunks_created": 10},
            "artifacts": {},
            "status": "running",
            "created_at": "2026-03-04T00:00:00+00:00",
            "logs": [],
        }
    )
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        service,
        "_read_dataset_report",
        lambda _run: {
            "accepted_records": 5,
            "task_distribution": ["bad-shape"],
        },
    )
    try:
        payload = service._evaluate_llm_run(run)
    finally:
        monkeypatch.undo()

    assert payload["kind"] == "proxy_eval"
    assert payload["metrics"]["fix_success_rate"] >= 0.0


def test_update_evaluation_baselines_persists_payload(tmp_path: Path):
    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(tmp_path / "repo"),
    )
    updated = service.update_evaluation_baselines(
        {
            "llm_finetune": {
                "repo_qa_accuracy": 0.61,
                "code_localization_accuracy": 0.52,
                "fix_success_rate": 0.37,
                "hallucination_rate_max": 0.28,
            }
        }
    )
    assert updated["llm_finetune"]["repo_qa_accuracy"] == 0.61
    baseline_file = Path(service.storage_dir) / "evaluation_baselines.json"
    assert baseline_file.exists()
    on_disk = json.loads(baseline_file.read_text(encoding="utf-8"))
    assert on_disk["llm_finetune"]["fix_success_rate"] == 0.37


def test_update_evaluation_baselines_rejects_out_of_range(tmp_path: Path):
    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(tmp_path / "repo"),
    )
    with pytest.raises(ValueError, match="EVALUATION_BASELINE_INVALID"):
        service.update_evaluation_baselines(
            {
                "rag_index": {
                    "repo_qa_accuracy": 1.2,
                    "code_localization_accuracy": 0.55,
                    "fix_success_rate": 0.3,
                    "hallucination_rate_max": 0.3,
                }
            }
        )


def test_normalize_evaluation_baseline_payload_validation_errors() -> None:
    assert _normalize_evaluation_baseline_payload(None) is None
    with pytest.raises(ValueError, match="Missing baseline field"):
        _normalize_evaluation_baseline_payload({"repo_qa_accuracy": 0.1})
    with pytest.raises(ValueError, match="must be numeric"):
        _normalize_evaluation_baseline_payload(
            {
                "repo_qa_accuracy": "x",
                "code_localization_accuracy": 0.2,
                "fix_success_rate": 0.3,
                "hallucination_rate_max": 0.4,
            }
        )


def test_load_evaluation_baselines_fallback_for_invalid_file(tmp_path: Path):
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir(parents=True)
    (storage_dir / "evaluation_baselines.json").write_text("{invalid", encoding="utf-8")
    service = SelfLearningService(
        storage_dir=str(storage_dir),
        repo_root=str(tmp_path / "repo"),
    )
    payload = service.get_evaluation_baselines()
    assert payload == DEFAULT_EVALUATION_BASELINES


def test_load_evaluation_baselines_fallback_for_invalid_mode_payload(tmp_path: Path):
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir(parents=True)
    (storage_dir / "evaluation_baselines.json").write_text(
        json.dumps({"llm_finetune": {"repo_qa_accuracy": 0.8}}),
        encoding="utf-8",
    )
    service = SelfLearningService(
        storage_dir=str(storage_dir),
        repo_root=str(tmp_path / "repo"),
    )
    payload = service.get_evaluation_baselines()
    assert payload["llm_finetune"] == DEFAULT_EVALUATION_BASELINES["llm_finetune"]
    assert payload["rag_index"] == DEFAULT_EVALUATION_BASELINES["rag_index"]


def test_get_evaluation_baselines_returns_copy(tmp_path: Path):
    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(tmp_path / "repo"),
    )
    payload = service.get_evaluation_baselines()
    payload["llm_finetune"]["repo_qa_accuracy"] = 0.01
    payload2 = service.get_evaluation_baselines()
    assert payload2["llm_finetune"]["repo_qa_accuracy"] != 0.01


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


@pytest.mark.asyncio
async def test_llm_finetune_waits_for_finished_job_and_adapter(tmp_path: Path):
    repo_root = tmp_path / "repo"
    docs_dir = repo_root / "docs"
    docs_dir.mkdir(parents=True)
    (docs_dir / "train.md").write_text(
        "Venom self learning sample.\n" * 120, encoding="utf-8"
    )

    class HabitatStub:
        use_local_runtime = False

        def __init__(self) -> None:
            self.training_containers: dict[str, dict[str, str]] = {}
            self._poll_count = 0

        def run_training_job(self, *, output_dir: str, job_name: str, **_kwargs):
            adapter_dir = Path(output_dir) / "adapter"
            adapter_dir.mkdir(parents=True, exist_ok=True)
            (adapter_dir / "adapter_config.json").write_text("{}", encoding="utf-8")
            self.training_containers[job_name] = {"status": "running"}
            return {"job_name": job_name, "status": "running"}

        def get_training_status(self, job_name: str):
            self._poll_count += 1
            if self._poll_count < 2:
                return {"status": "running", "logs": "still running"}
            self.training_containers[job_name] = {"status": "finished"}
            return {"status": "finished", "logs": "ok"}

    habitat = HabitatStub()
    model_manager = DummyModelManagerWithUnload([])
    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(repo_root),
        gpu_habitat=habitat,
        model_manager=model_manager,
        is_model_trainable_fn=lambda _model_id: True,
    )

    run_id = service.start_run(
        mode="llm_finetune",
        sources=["docs"],
        llm_config={"base_model": "unsloth/Phi-3-mini-4k-instruct"},
        dry_run=False,
    )
    status = await _wait_terminal(service, run_id)

    assert status["status"] == "completed"
    assert model_manager.unload_calls == 1
    adapter_path = status["artifacts"].get("adapter_path")
    assert isinstance(adapter_path, str)
    assert Path(adapter_path, "adapter_config.json").exists()
    metadata_payload = json.loads(
        Path(adapter_path).parent.joinpath("metadata.json").read_text(encoding="utf-8")
    )
    assert metadata_payload["source_flow"] == "self_learning"
    assert metadata_payload["requested_base_model"] == "unsloth/Phi-3-mini-4k-instruct"
    assert metadata_payload["effective_base_model"] == "unsloth/Phi-3-mini-4k-instruct"
    assert (
        metadata_payload["parameters"]["training_base_model"]
        == "unsloth/Phi-3-mini-4k-instruct"
    )


@pytest.mark.asyncio
async def test_llm_finetune_resolves_local_training_base_model_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    repo_root = tmp_path / "repo"
    docs_dir = repo_root / "docs"
    docs_dir.mkdir(parents=True)
    (docs_dir / "train.md").write_text(
        "Gemma local training.\n" * 120, encoding="utf-8"
    )

    model_dir = tmp_path / "models" / "gemma-3-4b-it"
    model_dir.mkdir(parents=True)
    (model_dir / "config.json").write_text("{}", encoding="utf-8")
    (model_dir / "model.safetensors").write_text("weights", encoding="utf-8")

    class HabitatStub:
        use_local_runtime = False

        def __init__(self) -> None:
            self.training_containers: dict[str, dict[str, str]] = {}
            self.base_model_calls: list[str] = []
            self._poll_count = 0

        def run_training_job(
            self, *, base_model: str, output_dir: str, job_name: str, **_kwargs
        ):
            self.base_model_calls.append(base_model)
            adapter_dir = Path(output_dir) / "adapter"
            adapter_dir.mkdir(parents=True, exist_ok=True)
            (adapter_dir / "adapter_config.json").write_text("{}", encoding="utf-8")
            self.training_containers[job_name] = {"status": "running"}
            return {"job_name": job_name, "status": "running"}

        def get_training_status(self, job_name: str):
            self._poll_count += 1
            if self._poll_count < 2:
                return {"status": "running", "logs": "still running"}
            self.training_containers[job_name] = {"status": "finished"}
            return {"status": "finished", "logs": "ok"}

    habitat = HabitatStub()
    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(repo_root),
        gpu_habitat=habitat,
        model_manager=DummyModelManagerWithUnload(
            [
                {
                    "name": "gemma-3-4b-it",
                    "provider": "vllm",
                    "runtime": "vllm",
                    "path": str(model_dir),
                },
                {
                    "name": "gemma3:latest",
                    "provider": "ollama",
                    "runtime": "ollama",
                    "path": "ollama://gemma3:latest",
                },
            ]
        ),
        is_model_trainable_fn=lambda _model_id: True,
    )
    expected_gguf = (
        tmp_path / "models" / "prepared" / "adapter" / "Adapter-F16-LoRA.gguf"
    )
    expected_gguf.parent.mkdir(parents=True, exist_ok=True)
    expected_gguf.write_text("gguf", encoding="utf-8")
    monkeypatch.setattr(
        "venom_core.services.academy.self_learning_service._adapter_runtime._ensure_ollama_adapter_gguf",
        lambda **_kwargs: expected_gguf,
    )

    run_id = service.start_run(
        mode="llm_finetune",
        sources=["docs"],
        llm_config={"base_model": "gemma-3-4b-it", "runtime_id": "ollama"},
        dry_run=False,
    )
    status = await _wait_terminal(service, run_id)

    assert status["status"] == "completed"
    assert habitat.base_model_calls
    assert habitat.base_model_calls[-1] == str(model_dir.resolve())
    assert status["artifacts"]["requested_runtime_id"] == "ollama"
    assert status["artifacts"]["effective_runtime_id"] == "ollama"
    assert status["artifacts"]["requested_base_model"] == "gemma-3-4b-it"
    assert status["artifacts"]["effective_base_model"] == "gemma-3-4b-it"
    assert status["artifacts"]["training_base_model"] == str(model_dir.resolve())
    assert status["artifacts"]["ollama_adapter_gguf_path"] == str(expected_gguf)
    metadata_payload = json.loads(
        Path(status["artifacts"]["adapter_path"])
        .parent.joinpath("metadata.json")
        .read_text(encoding="utf-8")
    )
    assert metadata_payload["requested_runtime_id"] == "ollama"
    assert metadata_payload["effective_runtime_id"] == "ollama"
    assert metadata_payload["requested_base_model"] == "gemma-3-4b-it"
    assert metadata_payload["effective_base_model"] == "gemma-3-4b-it"
    assert metadata_payload["parameters"]["training_base_model"] == str(
        model_dir.resolve()
    )


def test_start_run_fails_when_training_base_model_resolution_is_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(tmp_path / "repo"),
        is_model_trainable_fn=lambda _model_id: True,
    )
    monkeypatch.setattr(
        "venom_core.services.academy.self_learning_service.resolve_effective_training_base_model",
        lambda *_args, **_kwargs: "",
    )
    with pytest.raises(Exception) as exc:
        service.start_run(
            mode="llm_finetune",
            sources=["docs"],
            llm_config={"base_model": "gemma-3-4b-it"},
            dry_run=True,
        )
    detail = getattr(exc.value, "detail", {})
    assert detail.get("reason_code") == "MODEL_TRAINING_BASE_UNRESOLVED"


@pytest.mark.asyncio
async def test_run_llm_finetune_does_not_fallback_to_config_default_base_model(
    tmp_path: Path,
):
    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(tmp_path / "repo"),
    )
    run = service._run_from_payload(
        {
            "run_id": "55555555-5555-5555-5555-555555555555",
            "mode": "llm_finetune",
            "sources": ["docs"],
            "limits": {},
            "llm_config": {
                "num_epochs": 1,
                "dataset_strategy": "reconstruct",
                "task_mix_preset": "balanced",
            },
            "rag_config": {},
            "status": "running",
            "created_at": "2026-03-05T00:00:00+00:00",
            "logs": [],
            "artifacts": {},
            "progress": {},
        }
    )
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(SETTINGS, "ACADEMY_DEFAULT_BASE_MODEL", "custom/default-model")
    try:
        with pytest.raises(
            Exception, match="llm_config.base_model is required for fine-tuning"
        ):
            await service._run_llm_finetune(
                run,
                [
                    {
                        "text": "Venom academy training sample " * 50,
                        "path": "docs/intro.md",
                        "source": "docs",
                    }
                ],
            )
    finally:
        monkeypatch.undo()

    assert run.artifacts.get("selected_base_model") is None


def test_ensure_no_active_training_jobs_blocks_running_jobs(tmp_path: Path):
    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(tmp_path),
    )

    class HabitatStub:
        training_containers = {"job-a": {}}

        @staticmethod
        def get_training_status(_job_name: str):
            return {"status": "running"}

    with pytest.raises(Exception, match="Aktywny trening już trwa"):
        service._ensure_no_active_training_jobs(habitat=HabitatStub())


@pytest.mark.asyncio
async def test_release_runtime_models_logs_for_false_and_exception(tmp_path: Path):
    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(tmp_path),
    )
    run = service._run_from_payload(
        {
            "run_id": "33333333-3333-3333-3333-333333333333",
            "mode": "llm_finetune",
            "sources": ["docs"],
            "limits": {},
            "llm_config": {"base_model": "unsloth/Phi-3-mini-4k-instruct"},
            "rag_config": {},
            "status": "running",
            "created_at": "2026-03-05T00:00:00+00:00",
            "logs": [],
            "artifacts": {},
            "progress": {},
        }
    )

    class ModelManagerFalse:
        async def unload_all(self):
            return False

    class ModelManagerError:
        async def unload_all(self):
            raise RuntimeError("boom")

    service.model_manager = ModelManagerFalse()
    await service._release_runtime_models(run)
    assert any("unload returned false" in line for line in run.logs)

    service.model_manager = ModelManagerError()
    await service._release_runtime_models(run)
    assert any("runtime unload failed" in line for line in run.logs)


@pytest.mark.asyncio
async def test_wait_for_training_completion_handles_failed_timeout_and_missing_adapter(
    tmp_path: Path,
):
    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(tmp_path),
    )
    run = service._run_from_payload(
        {
            "run_id": "44444444-4444-4444-4444-444444444444",
            "mode": "llm_finetune",
            "sources": ["docs"],
            "limits": {},
            "llm_config": {
                "base_model": "unsloth/Phi-3-mini-4k-instruct",
                "num_epochs": 1,
            },
            "rag_config": {},
            "status": "running",
            "created_at": "2026-03-05T00:00:00+00:00",
            "logs": [],
            "artifacts": {},
            "progress": {},
        }
    )
    output_dir = tmp_path / "models"
    output_dir.mkdir(parents=True, exist_ok=True)

    class FailedHabitat:
        @staticmethod
        def get_training_status(_job_name: str):
            return {"status": "failed", "logs": "training crashed"}

    with pytest.raises(Exception, match="Błąd podczas treningu modelu"):
        await service._wait_for_training_completion(
            run=run,
            habitat=FailedHabitat(),
            training_job_id="job-failed",
            output_dir=output_dir,
        )

    class RunningHabitat:
        @staticmethod
        def get_training_status(_job_name: str):
            return {"status": "running", "logs": "still running"}

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        "venom_core.services.academy.self_learning_service._TRAINING_TIMEOUT_MIN_SECONDS",
        0,
    )
    monkeypatch.setattr(
        "venom_core.services.academy.self_learning_service._TRAINING_TIMEOUT_MAX_SECONDS",
        0,
    )
    try:
        with pytest.raises(Exception, match="przekroczył limit czasu"):
            await service._wait_for_training_completion(
                run=run,
                habitat=RunningHabitat(),
                training_job_id="job-timeout",
                output_dir=output_dir,
            )
    finally:
        monkeypatch.undo()

    class FinishedNoAdapterHabitat:
        @staticmethod
        def get_training_status(_job_name: str):
            return {"status": "finished", "logs": "finished without adapter"}

    with pytest.raises(Exception, match="bez zapisu adaptera"):
        await service._wait_for_training_completion(
            run=run,
            habitat=FinishedNoAdapterHabitat(),
            training_job_id="job-no-adapter",
            output_dir=output_dir,
        )


@pytest.mark.asyncio
async def test_wait_for_training_completion_appends_live_progress_logs(tmp_path: Path):
    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(tmp_path),
    )
    run = service._run_from_payload(
        {
            "run_id": "66666666-6666-6666-6666-666666666666",
            "mode": "llm_finetune",
            "sources": ["docs"],
            "limits": {},
            "llm_config": {
                "base_model": "unsloth/Phi-3-mini-4k-instruct",
                "num_epochs": 1,
            },
            "rag_config": {},
            "status": "running",
            "created_at": "2026-03-05T00:00:00+00:00",
            "logs": [],
            "artifacts": {},
            "progress": {},
        }
    )
    output_dir = tmp_path / "models"
    adapter_dir = output_dir / "adapter"
    adapter_dir.mkdir(parents=True, exist_ok=True)
    (adapter_dir / "adapter_config.json").write_text("{}", encoding="utf-8")

    class RunningThenFinishedHabitat:
        def __init__(self) -> None:
            self.calls = 0

        def get_training_status(self, _job_name: str):
            self.calls += 1
            if self.calls == 1:
                return {"status": "running", "logs": "step 1"}
            if self.calls == 2:
                return {"status": "running", "logs": "step 1\nstep 2"}
            return {"status": "finished", "logs": "step 1\nstep 2\ndone"}

    payload = await service._wait_for_training_completion(
        run=run,
        habitat=RunningThenFinishedHabitat(),
        training_job_id="job-live-logs",
        output_dir=output_dir,
    )

    assert payload.get("status") == "finished"
    assert any("Training status: running" in line for line in run.logs)
    assert any("[train:running] step 2" in line for line in run.logs)


def test_apply_resource_optimizations_reduces_training_footprint(tmp_path: Path):
    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(tmp_path),
    )
    run = service._run_from_payload(
        {
            "run_id": "11111111-1111-1111-1111-111111111111",
            "mode": "llm_finetune",
            "sources": ["docs"],
            "limits": {},
            "llm_config": {
                "base_model": "unsloth/Phi-3-mini-4k-instruct",
                "lora_rank": 16,
                "num_epochs": 4,
                "batch_size": 4,
                "max_seq_length": 2048,
            },
            "rag_config": {},
            "status": "running",
            "created_at": "2026-03-05T00:00:00+00:00",
            "logs": [],
            "artifacts": {},
            "progress": {},
        }
    )
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        "venom_core.services.academy.self_learning_service.psutil.virtual_memory",
        lambda: MagicMock(total=16 * 1024**3, available=6 * 1024**3, percent=62.0),
    )
    try:
        service._apply_resource_optimizations(run)
    finally:
        monkeypatch.undo()

    assert run.llm_config.batch_size == 1
    assert run.llm_config.max_seq_length == 1024
    assert run.llm_config.lora_rank == 8
    assert run.llm_config.num_epochs == 2


def test_apply_resource_optimizations_switches_to_ultra_safe_mode_on_critical_ram(
    tmp_path: Path,
):
    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(tmp_path),
    )
    run = service._run_from_payload(
        {
            "run_id": "22222222-2222-2222-2222-222222222222",
            "mode": "llm_finetune",
            "sources": ["docs"],
            "limits": {},
            "llm_config": {"base_model": "unsloth/Phi-3-mini-4k-instruct"},
            "rag_config": {},
            "status": "running",
            "created_at": "2026-03-05T00:00:00+00:00",
            "logs": [],
            "artifacts": {},
            "progress": {},
        }
    )
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        "venom_core.services.academy.self_learning_service.psutil.virtual_memory",
        lambda: MagicMock(total=16 * 1024**3, available=1 * 1024**3, percent=95.0),
    )
    try:
        service._apply_resource_optimizations(run)
    finally:
        monkeypatch.undo()
    assert run.llm_config.batch_size == 1
    assert run.llm_config.max_seq_length == 512
    assert run.llm_config.lora_rank == 4
    assert run.llm_config.num_epochs == 1
    assert "resource_optimizations_critical" in run.artifacts
    assert any("Critical low-RAM mode enabled" in line for line in run.logs)


def test_list_runs_refreshes_live_state_and_sorts_desc(tmp_path: Path):
    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(tmp_path),
    )
    run_a = service._run_from_payload(
        {
            "run_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "mode": "rag_index",
            "sources": ["docs"],
            "status": "running",
            "created_at": "2026-03-05T00:00:00+00:00",
        }
    )
    run_b = service._run_from_payload(
        {
            "run_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
            "mode": "rag_index",
            "sources": ["docs"],
            "status": "pending",
            "created_at": "2026-03-05T00:00:10+00:00",
        }
    )
    service._runs[run_a.run_id] = run_a
    service._runs[run_b.run_id] = run_b

    refreshed: list[str] = []
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        service,
        "_refresh_live_run_state",
        lambda run: refreshed.append(run.run_id),
    )
    try:
        payload = service.list_runs(limit=5)
    finally:
        monkeypatch.undo()

    assert run_a.run_id in refreshed and run_b.run_id in refreshed
    assert payload[0]["run_id"] == run_b.run_id


def test_recover_orphaned_run_non_llm_marks_failed(tmp_path: Path):
    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(tmp_path),
    )
    run = service._run_from_payload(
        {
            "run_id": "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
            "mode": "rag_index",
            "sources": ["docs"],
            "status": "running",
            "created_at": "2026-03-05T00:00:00+00:00",
            "logs": [],
        }
    )

    service._recover_orphaned_run(run)
    assert run.status == "failed"
    assert run.finished_at is not None
    assert run.error_message is not None
    assert any("monitor task lost" in line for line in run.logs)


def test_build_orphan_status_payload_from_files_and_process_detection(tmp_path: Path):
    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(tmp_path),
    )
    output_dir = tmp_path / "models" / "self_learning_run"
    output_dir.mkdir(parents=True)
    log_file = output_dir / "training.log"
    log_file.write_text("line\n" * 3000, encoding="utf-8")
    run = service._run_from_payload(
        {
            "run_id": "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
            "mode": "llm_finetune",
            "sources": ["docs"],
            "status": "running",
            "created_at": "2026-03-05T00:00:00+00:00",
            "artifacts": {"training_output_dir": str(output_dir)},
        }
    )

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(service, "_is_local_training_process_alive", lambda _rid: True)
    try:
        payload = service._build_orphan_status_payload_from_files(run)
    finally:
        monkeypatch.undo()
    assert payload is not None
    assert payload["status"] == "running"
    assert isinstance(payload["logs"], str)

    (output_dir / "adapter" / "adapter_config.json").parent.mkdir(parents=True)
    (output_dir / "adapter" / "adapter_config.json").write_text("{}", encoding="utf-8")
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(service, "_is_local_training_process_alive", lambda _rid: False)
    try:
        payload_finished = service._build_orphan_status_payload_from_files(run)
    finally:
        monkeypatch.undo()
    assert payload_finished is not None
    assert payload_finished["status"] == "finished"

    (output_dir / "adapter" / "adapter_config.json").unlink()
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(service, "_is_local_training_process_alive", lambda _rid: False)
    try:
        payload_failed = service._build_orphan_status_payload_from_files(run)
    finally:
        monkeypatch.undo()
    assert payload_failed is not None
    assert payload_failed["status"] == "failed"


def test_is_local_training_process_alive_and_add_log_dedup(tmp_path: Path):
    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(tmp_path),
    )
    run_id = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"

    class _Proc:
        def __init__(self, cmdline):
            self.info = {"cmdline": cmdline}

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        "venom_core.services.academy.self_learning_service.psutil.process_iter",
        lambda attrs=None: iter(
            [
                _Proc(["python", "worker.py"]),
                _Proc(["python", "train_script.py", f"self_learning_{run_id}"]),
            ]
        ),
    )
    try:
        assert service._is_local_training_process_alive(run_id) is True
    finally:
        monkeypatch.undo()

    run = service._run_from_payload(
        {
            "run_id": run_id,
            "mode": "rag_index",
            "sources": ["docs"],
            "status": "running",
            "created_at": "2026-03-05T00:00:00+00:00",
            "logs": [],
        }
    )
    service._add_log(run, "same")
    service._add_log(run, "same")
    assert run.logs == ["same"]


def test_is_path_allowed_for_docs_pl_and_docs_en(tmp_path: Path):
    repo_root = tmp_path / "repo"
    docs_dir = repo_root / "docs"
    docs_pl = docs_dir / "PL"
    docs_pl.mkdir(parents=True)
    en_file = docs_dir / "intro.md"
    pl_file = docs_pl / "wstep.md"
    en_file.write_text("en", encoding="utf-8")
    pl_file.write_text("pl", encoding="utf-8")

    service = SelfLearningService(
        storage_dir=str(tmp_path / "storage"),
        repo_root=str(repo_root),
    )
    assert service._is_path_allowed_for_source(source="docs_en", path=en_file) is True
    assert service._is_path_allowed_for_source(source="docs_en", path=pl_file) is False
    assert service._is_path_allowed_for_source(source="docs_pl", path=pl_file) is True
