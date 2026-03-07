"""Schemas for Academy self-learning endpoints."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

SelfLearningMode = Literal["llm_finetune", "rag_index"]
SelfLearningSource = Literal[
    "docs",
    "docs_en",
    "docs_pl",
    "docs_dev",
    "code",
    "repo_readmes",
]
SelfLearningDatasetStrategy = Literal[
    "reconstruct",
    "qa_from_docs",
    "repo_tasks_basic",
]
SelfLearningTaskMixPreset = Literal["balanced", "qa-heavy", "repair-heavy"]
SelfLearningStatus = Literal[
    "pending",
    "running",
    "completed",
    "completed_with_warnings",
    "failed",
]
SelfLearningEmbeddingPolicy = Literal["strict", "allow_fallback"]
SelfLearningRagChunkingMode = Literal["plain", "code_aware"]
SelfLearningRagRetrievalMode = Literal["vector", "hybrid"]


def _default_sources() -> list[SelfLearningSource]:
    return ["docs"]


class SelfLearningLimits(BaseModel):
    """Safety limits for source discovery and parsing."""

    max_file_size_kb: int = Field(default=128, ge=16, le=4096)
    max_files: int = Field(default=300, ge=1, le=10000)
    max_total_size_mb: int = Field(default=32, ge=1, le=4096)


class SelfLearningLlmConfig(BaseModel):
    """Optional overrides for LLM fine-tuning mode."""

    base_model: str | None = None
    runtime_id: str | None = Field(default=None, min_length=1, max_length=32)
    dataset_strategy: SelfLearningDatasetStrategy = "reconstruct"
    task_mix_preset: SelfLearningTaskMixPreset = "balanced"
    lora_rank: int = Field(default=8, ge=4, le=64)
    learning_rate: float = Field(default=2e-4, gt=0, le=1e-2)
    num_epochs: int = Field(default=2, ge=1, le=20)
    batch_size: int = Field(default=1, ge=1, le=32)
    max_seq_length: int = Field(default=1024, ge=256, le=8192)


class SelfLearningRagConfig(BaseModel):
    """Optional overrides for RAG indexing mode."""

    collection: str = Field(default="default", min_length=1, max_length=64)
    category: str = Field(default="academy_self_learning", min_length=1, max_length=64)
    chunk_text: bool = False
    chunking_mode: SelfLearningRagChunkingMode = "plain"
    retrieval_mode: SelfLearningRagRetrievalMode = "vector"
    embedding_profile_id: str | None = Field(default=None, min_length=1, max_length=128)
    embedding_policy: SelfLearningEmbeddingPolicy = "strict"


class SelfLearningStartRequest(BaseModel):
    """Request to start self-learning pipeline."""

    mode: SelfLearningMode
    sources: list[SelfLearningSource] = Field(default_factory=_default_sources)
    limits: SelfLearningLimits = Field(default_factory=SelfLearningLimits)
    llm_config: SelfLearningLlmConfig | None = None
    rag_config: SelfLearningRagConfig | None = None
    dry_run: bool = False


class SelfLearningStartResponse(BaseModel):
    """Response returned immediately after run start."""

    run_id: str
    message: str


class SelfLearningProgress(BaseModel):
    """Progress counters for pipeline visibility."""

    files_discovered: int = 0
    files_processed: int = 0
    chunks_created: int = 0
    records_created: int = 0
    indexed_vectors: int = 0


class SelfLearningRunStatusResponse(BaseModel):
    """Detailed status payload for a self-learning run."""

    run_id: str
    status: SelfLearningStatus
    mode: SelfLearningMode
    sources: list[SelfLearningSource] = Field(default_factory=list)
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    progress: SelfLearningProgress = Field(default_factory=SelfLearningProgress)
    artifacts: dict[str, Any] = Field(default_factory=dict)
    logs: list[str] = Field(default_factory=list)
    error_message: str | None = None


class SelfLearningListResponse(BaseModel):
    """List of self-learning runs."""

    runs: list[SelfLearningRunStatusResponse] = Field(default_factory=list)
    count: int = 0


class SelfLearningDeleteResponse(BaseModel):
    """Delete response for single or all runs."""

    message: str
    count: int | None = None


class SelfLearningTrainableModelInfo(BaseModel):
    """Trainable-model metadata used by self-learning configurator."""

    model_id: str
    label: str
    provider: str
    recommended: bool = False
    runtime_compatibility: dict[str, bool] = Field(default_factory=dict)
    recommended_runtime: str | None = None


class SelfLearningEmbeddingProfile(BaseModel):
    """Embedding runtime profile available for RAG indexing."""

    profile_id: str
    provider: str
    model: str
    dimension: int | None = None
    healthy: bool = False
    fallback_active: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class SelfLearningCapabilitiesResponse(BaseModel):
    """Capabilities payload for self-learning UI preflight/configuration."""

    trainable_models: list[SelfLearningTrainableModelInfo] = Field(default_factory=list)
    embedding_profiles: list[SelfLearningEmbeddingProfile] = Field(default_factory=list)
    default_base_model: str | None = None
    default_embedding_profile_id: str | None = None
