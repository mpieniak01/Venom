"""API schemas for tasks and history endpoints."""

from uuid import UUID

from pydantic import BaseModel, Field


class TaskExtraContext(BaseModel):
    """Additional contextual payload for task execution."""

    files: list[str] | None = None
    links: list[str] | None = None
    paths: list[str] | None = None
    notes: list[str] | None = None


class TaskRequest(BaseModel):
    """Request DTO for creating a task."""

    content: str
    preferred_language: str | None = Field(
        default=None, description="Preferred response language (pl/en/de)"
    )
    session_id: str | None = Field(
        default=None, description="Chat session identifier for context continuity"
    )
    preference_scope: str | None = Field(
        default=None, description="Preference scope: session/global"
    )
    tone: str | None = Field(
        default=None, description="Preferred response tone (concise/detailed/neutral)"
    )
    style_notes: str | None = Field(
        default=None, description="Additional style instructions"
    )
    forced_tool: str | None = Field(
        default=None, description="Forced tool/skill (e.g. 'git', 'docs')"
    )
    forced_provider: str | None = Field(
        default=None, description="Forced LLM provider (e.g. 'gpt', 'gem')"
    )
    forced_intent: str | None = Field(
        default=None, description="Forced intent (e.g. GENERAL_CHAT)"
    )
    images: list[str] | None = None
    store_knowledge: bool = Field(
        default=True, description="Persist lessons and insights from this task"
    )
    generation_params: dict[str, object] | None = Field(
        default=None, description="Generation params (temperature, max_tokens, etc.)"
    )
    expected_config_hash: str | None = Field(
        default=None, description="Expected LLM config hash from UI"
    )
    expected_runtime_id: str | None = Field(
        default=None, description="Expected LLM runtime_id from UI"
    )
    extra_context: TaskExtraContext | None = Field(
        default=None, description="Additional context passed to task execution"
    )


class TaskResponse(BaseModel):
    """Response DTO after task creation."""

    task_id: UUID
    status: str
    llm_provider: str | None = None
    llm_model: str | None = None
    llm_endpoint: str | None = None
    policy_blocked: bool = False
    reason_code: str | None = None
    user_message: str | None = None


class HistoryRequestSummary(BaseModel):
    """Skrócony widok requestu dla listy historii."""

    request_id: UUID
    prompt: str
    status: str
    session_id: str | None = None
    created_at: str
    finished_at: str | None = None
    duration_seconds: float | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    llm_endpoint: str | None = None
    llm_config_hash: str | None = None
    llm_runtime_id: str | None = None
    forced_tool: str | None = None
    forced_provider: str | None = None
    forced_intent: str | None = None
    error_code: str | None = None
    error_class: str | None = None
    error_message: str | None = None
    error_details: dict | None = None
    error_stage: str | None = None
    error_retryable: bool | None = None
    feedback: dict | None = None
    result: str | None = None


class HistoryRequestDetail(BaseModel):
    """Szczegółowy widok requestu z krokami."""

    request_id: UUID
    prompt: str
    status: str
    session_id: str | None = None
    created_at: str
    finished_at: str | None = None
    duration_seconds: float | None = None
    steps: list
    llm_provider: str | None = None
    llm_model: str | None = None
    llm_endpoint: str | None = None
    llm_config_hash: str | None = None
    llm_runtime_id: str | None = None
    forced_tool: str | None = None
    forced_provider: str | None = None
    forced_intent: str | None = None
    first_token: dict | None = None
    streaming: dict | None = None
    context_preview: dict | None = None
    generation_params: dict | None = None
    llm_runtime: dict | None = None
    context_used: dict | None = None
    error_code: str | None = None
    error_class: str | None = None
    error_message: str | None = None
    error_details: dict | None = None
    error_stage: str | None = None
    error_retryable: bool | None = None
    result: str | None = None
    feedback: dict | None = None
