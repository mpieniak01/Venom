"""API schemas for tasks and history endpoints."""

from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field

from venom_core.contracts.routing import ReasonCode, RuntimeTarget


class RoutingTarget(str, Enum):
    """Routing target runtime exposed to API clients."""

    OLLAMA = RuntimeTarget.LOCAL_OLLAMA.value
    VLLM = RuntimeTarget.LOCAL_VLLM.value
    OPENAI = RuntimeTarget.CLOUD_OPENAI.value
    GOOGLE = RuntimeTarget.CLOUD_GOOGLE.value
    AZURE = RuntimeTarget.CLOUD_AZURE.value


class RoutingReason(str, Enum):
    """Routing decision reason codes exposed to API clients."""

    DEFAULT_ECO_MODE = ReasonCode.DEFAULT_ECO_MODE.value
    TASK_COMPLEXITY_LOW = ReasonCode.TASK_COMPLEXITY_LOW.value
    TASK_COMPLEXITY_HIGH = ReasonCode.TASK_COMPLEXITY_HIGH.value
    SENSITIVE_CONTENT_OVERRIDE = ReasonCode.SENSITIVE_CONTENT_OVERRIDE.value
    FALLBACK_TIMEOUT = ReasonCode.FALLBACK_TIMEOUT.value
    FALLBACK_AUTH_ERROR = ReasonCode.FALLBACK_AUTH_ERROR.value
    FALLBACK_BUDGET_EXCEEDED = ReasonCode.FALLBACK_BUDGET_EXCEEDED.value
    FALLBACK_PROVIDER_DEGRADED = ReasonCode.FALLBACK_PROVIDER_DEGRADED.value
    FALLBACK_PROVIDER_OFFLINE = ReasonCode.FALLBACK_PROVIDER_OFFLINE.value
    FALLBACK_RATE_LIMIT = ReasonCode.FALLBACK_RATE_LIMIT.value
    POLICY_BLOCKED_BUDGET = ReasonCode.POLICY_BLOCKED_BUDGET.value
    POLICY_BLOCKED_RATE_LIMIT = ReasonCode.POLICY_BLOCKED_RATE_LIMIT.value
    POLICY_BLOCKED_NO_PROVIDER = ReasonCode.POLICY_BLOCKED_NO_PROVIDER.value
    POLICY_BLOCKED_CONTENT = ReasonCode.POLICY_BLOCKED_CONTENT.value
    USER_PREFERENCE = ReasonCode.USER_PREFERENCE.value


class RoutingDecisionSummary(BaseModel):
    """Serialized routing decision attached to task context/history."""

    target_runtime: RoutingTarget | None = None
    provider: str | None = None
    model: str | None = None
    reason_code: RoutingReason
    complexity_score: float = 0.0
    is_sensitive: bool = False
    fallback_applied: bool = False
    fallback_chain: list[str] = Field(default_factory=list)
    policy_gate_passed: bool = True
    estimated_cost_usd: float = 0.0
    budget_remaining_usd: float | None = None
    decision_timestamp: str
    decision_latency_ms: float = 0.0
    error_message: str | None = None


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
    routing_decision: RoutingDecisionSummary | None = None
    context_used: dict | None = None
    error_code: str | None = None
    error_class: str | None = None
    error_message: str | None = None
    error_details: dict | None = None
    error_stage: str | None = None
    error_retryable: bool | None = None
    result: str | None = None
    feedback: dict | None = None
