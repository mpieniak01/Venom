"""API schemas for Academy (model training) endpoints."""

from typing import Any

from pydantic import BaseModel, Field, field_validator


class DatasetRequest(BaseModel):
    """Request do wygenerowania datasetu."""

    lessons_limit: int = Field(default=200, ge=10, le=1000)
    git_commits_limit: int = Field(default=100, ge=0, le=500)
    include_task_history: bool = Field(default=False)
    format: str = Field(default="alpaca", pattern="^(alpaca|sharegpt)$")


class DatasetResponse(BaseModel):
    """Response z wygenerowanego datasetu."""

    success: bool
    dataset_path: str | None = None
    statistics: dict[str, Any] = Field(default_factory=dict)
    message: str = ""


class TrainingRequest(BaseModel):
    """Request do rozpoczęcia treningu."""

    dataset_path: str | None = None
    base_model: str | None = None
    lora_rank: int = Field(default=16, ge=4, le=64)
    learning_rate: float = Field(default=2e-4, gt=0, le=1e-2)
    num_epochs: int = Field(default=3, ge=1, le=20)
    batch_size: int = Field(default=4, ge=1, le=32)
    max_seq_length: int = Field(default=2048, ge=256, le=8192)

    @field_validator("learning_rate")
    @classmethod
    def validate_lr(cls, v):
        if v <= 0 or v > 1e-2:
            raise ValueError("learning_rate must be in range (0, 0.01]")
        return v


class TrainingResponse(BaseModel):
    """Response po rozpoczęciu treningu."""

    success: bool
    job_id: str | None = None
    message: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)


class JobStatusResponse(BaseModel):
    """Response ze statusem joba."""

    job_id: str
    status: str  # queued, preparing, running, finished, failed, cancelled
    logs: str = ""
    started_at: str | None = None
    finished_at: str | None = None
    adapter_path: str | None = None
    error: str | None = None


class AdapterInfo(BaseModel):
    """Informacje o adapterze."""

    adapter_id: str
    adapter_path: str
    base_model: str
    created_at: str
    training_params: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = False


class ActivateAdapterRequest(BaseModel):
    """Request do aktywacji adaptera."""

    adapter_id: str
    adapter_path: str


class UploadFileInfo(BaseModel):
    """Informacje o uploadowanym pliku."""

    id: str
    name: str
    size_bytes: int
    mime: str
    created_at: str
    status: str  # "validating", "ready", "failed"
    records_estimate: int = 0
    sha256: str
    error: str | None = None


class DatasetScopeRequest(BaseModel):
    """Request do kuracji datasetu z wybranym scope."""

    lessons_limit: int = Field(default=200, ge=10, le=1000)
    git_commits_limit: int = Field(default=100, ge=0, le=500)
    include_task_history: bool = Field(default=False)
    format: str = Field(default="alpaca", pattern="^(alpaca|sharegpt)$")
    # New fields for scope selection
    include_lessons: bool = Field(default=True)
    include_git: bool = Field(default=True)
    upload_ids: list[str] = Field(default_factory=list)
    quality_profile: str = Field(
        default="balanced", pattern="^(strict|balanced|lenient)$"
    )


class DatasetPreviewResponse(BaseModel):
    """Response z preview datasetu przed curate."""

    total_examples: int
    by_source: dict[str, int]
    removed_low_quality: int
    warnings: list[str] = Field(default_factory=list)
    samples: list[dict[str, Any]] = Field(default_factory=list)


class TrainableModelInfo(BaseModel):
    """Informacje o modelu trenowalnym."""

    model_id: str
    label: str
    provider: str
    trainable: bool
    reason_if_not_trainable: str | None = None
    recommended: bool = False
    installed_local: bool = False
