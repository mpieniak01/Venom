"""Schemas for multi_runtime execution profile.

Deliberately separate from VENOM_RUNTIME_PROFILE (full|light|llm_off), which
controls the overall Venom local-stack. This module owns the contract for the
execution profile of the multi_runtime daemon itself: precision, token budgets,
cache strategy, and behavioral flags.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

ApplyMode = Literal["live", "soft_reload", "hard_restart", "unsupported"]

RejectionReason = Literal[
    "unsupported_field",
    "unsupported_combination",
    "requires_restart",
    "model_not_available",
    "assistant_model_not_available",
    "quantization_backend_unavailable",
    "precision_not_supported_for_runtime",
    "value_out_of_range",
]


class MultiRuntimeProfile(BaseModel):
    """Execution profile for the multi_runtime daemon.

    Fields are grouped into two tiers:
    - Active MVP: applied immediately or on soft-reload.
    - Prepared limited: present in the contract, but apply_mode is 'unsupported'
      until the underlying loader supports them. Backend never lies about these.
    """

    profile_id: str = Field("default", description="Profile identifier")
    display_name: str = Field("Default", description="Human-readable profile name")
    runtime_id: str = Field(
        "multi_runtime", description="Runtime this profile belongs to"
    )
    compatibility: str = Field(
        "multi_runtime_native", description="Compatibility profile string"
    )

    # --- Active MVP fields ---
    model_id: str = Field(..., description="Primary model HuggingFace ID")
    assistant_model_id: Optional[str] = Field(
        None, description="Drafter/assistant model ID (None = disabled)"
    )
    cache_implementation: Optional[str] = Field(
        None, description="KV-cache strategy (None = framework default)"
    )
    max_new_tokens: int = Field(
        128, ge=1, le=32768, description="Generation token budget"
    )
    image_token_budget: int = Field(
        280, ge=70, le=1120, description="Vision token budget for image inputs"
    )
    enable_thinking: bool = Field(
        False, description="Enable chain-of-thought reasoning"
    )
    reasoning_summary_enabled: bool = Field(
        False, description="Surface compressed reasoning summary in response"
    )
    emotion_detection_enabled: bool = Field(
        False, description="Run emotion inference on voice input"
    )
    emotion_response_style_enabled: bool = Field(
        False, description="Adapt response style based on detected emotion"
    )

    # --- Prepared limited fields (apply_mode=unsupported until loader supports them) ---
    precision: str = Field(
        "auto",
        description=(
            "Model precision. Currently only 'auto' is loaded; "
            "other values are accepted in the contract but marked unsupported."
        ),
    )
    quantization_backend: Optional[str] = Field(
        None,
        description=(
            "Quantization backend (e.g. 'bitsandbytes'). "
            "Accepted in the contract but unsupported until bitsandbytes is installed."
        ),
    )
    device_target: str = Field(
        "auto",
        description="Compute device target ('auto', 'cpu', 'cuda'). Currently unsupported.",
    )


class MultiRuntimeApplyMatrix(BaseModel):
    """Documents the required apply_mode for every profile field."""

    model_id: ApplyMode = "hard_restart"
    assistant_model_id: ApplyMode = "hard_restart"
    cache_implementation: ApplyMode = "soft_reload"
    max_new_tokens: ApplyMode = "live"
    image_token_budget: ApplyMode = "live"
    enable_thinking: ApplyMode = "live"
    reasoning_summary_enabled: ApplyMode = "live"
    emotion_detection_enabled: ApplyMode = "live"
    emotion_response_style_enabled: ApplyMode = "live"
    precision: ApplyMode = "unsupported"
    quantization_backend: ApplyMode = "unsupported"
    device_target: ApplyMode = "unsupported"


class MultiRuntimeSupportedOptions(BaseModel):
    """Enumerated valid values for constrained fields."""

    cache_implementation: list[Optional[str]] = Field(
        default_factory=lambda: [None, "static", "dynamic", "offloaded"]
    )
    precision: list[str] = Field(default_factory=lambda: ["auto"])
    device_target: list[str] = Field(default_factory=lambda: ["auto", "cpu", "cuda"])
    quantization_backend: list[Optional[str]] = Field(default_factory=lambda: [None])


class MultiRuntimeProfileResponse(BaseModel):
    """Full read response for the multi_runtime profile endpoint."""

    runtime_id: str = "multi_runtime"
    profile: MultiRuntimeProfile
    apply_matrix: MultiRuntimeApplyMatrix
    supported_options: MultiRuntimeSupportedOptions
    daemon_reachable: bool = Field(
        False, description="True when values were read from a live daemon"
    )


class MultiRuntimeProfileUpdateRequest(BaseModel):
    """Partial update request — only fields that should change are included."""

    model_id: Optional[str] = None
    assistant_model_id: Optional[str] = None
    cache_implementation: Optional[str] = None
    max_new_tokens: Optional[int] = Field(None, ge=1, le=32768)
    image_token_budget: Optional[int] = Field(None, ge=70, le=1120)
    enable_thinking: Optional[bool] = None
    reasoning_summary_enabled: Optional[bool] = None
    emotion_detection_enabled: Optional[bool] = None
    emotion_response_style_enabled: Optional[bool] = None
    precision: Optional[str] = None
    quantization_backend: Optional[str] = None
    device_target: Optional[str] = None


class MultiRuntimeFieldRejection(BaseModel):
    """Describes why a single field was rejected during a profile update."""

    field: str
    value: Any
    reason: RejectionReason
    detail: str = ""


class MultiRuntimeProfileUpdateResponse(BaseModel):
    """Result of a profile update attempt."""

    accepted: dict[str, Any] = Field(
        default_factory=dict,
        description="Fields accepted for application, keyed by field name",
    )
    rejected: list[MultiRuntimeFieldRejection] = Field(
        default_factory=list,
        description="Fields that could not be applied and why",
    )
    required_apply_mode: ApplyMode = Field(
        "live",
        description="Most restrictive apply_mode among all accepted fields",
    )
    applied: bool = Field(
        False,
        description="True when the update was immediately applied to a live daemon",
    )
    message: str = ""
