"""Centralized API schemas for all Venom endpoints.

This module serves as the single source of truth for API request/response models,
replacing inline models in route files.
"""

from venom_core.api.schemas.academy import (
    ActivateAdapterRequest,
    AdapterInfo,
    DatasetPreviewResponse,
    DatasetRequest,
    DatasetResponse,
    DatasetScopeRequest,
    JobStatusResponse,
    TrainableModelInfo,
    TrainingRequest,
    TrainingResponse,
    UploadFileInfo,
)
from venom_core.api.schemas.governance import (
    GovernanceStatusResponse,
    LimitsConfigResponse,
    ProviderCredentialStatusResponse,
    UpdateLimitRequest,
)
from venom_core.api.schemas.memory import (
    LearningToggleRequest,
    MemoryIngestRequest,
    MemoryIngestResponse,
    MemorySearchRequest,
)
from venom_core.api.schemas.providers import (
    ProviderActivateRequest,
    ProviderCapability,
    ProviderInfo,
    ProviderStatus,
)
from venom_core.api.schemas.tasks import (
    HistoryRequestDetail,
    HistoryRequestSummary,
    TaskExtraContext,
    TaskRequest,
    TaskResponse,
)
from venom_core.api.schemas.workflow_control import (
    AuditEntry,
    ControlApplyRequest,
    ControlApplyResponse,
    ControlAuditResponse,
    ControlOptionsResponse,
    ControlPlanRequest,
    ControlPlanResponse,
    ControlStateResponse,
    ResourceType,
)

__all__ = [
    # Academy
    "DatasetRequest",
    "DatasetResponse",
    "TrainingRequest",
    "TrainingResponse",
    "JobStatusResponse",
    "AdapterInfo",
    "ActivateAdapterRequest",
    "UploadFileInfo",
    "DatasetScopeRequest",
    "DatasetPreviewResponse",
    "TrainableModelInfo",
    # Governance
    "GovernanceStatusResponse",
    "LimitsConfigResponse",
    "ProviderCredentialStatusResponse",
    "UpdateLimitRequest",
    # Memory
    "MemoryIngestRequest",
    "MemoryIngestResponse",
    "MemorySearchRequest",
    "LearningToggleRequest",
    # Providers
    "ProviderCapability",
    "ProviderStatus",
    "ProviderInfo",
    "ProviderActivateRequest",
    # Tasks
    "TaskExtraContext",
    "TaskRequest",
    "TaskResponse",
    "HistoryRequestSummary",
    "HistoryRequestDetail",
    # Workflow control
    "ControlPlanRequest",
    "ControlPlanResponse",
    "ControlApplyRequest",
    "ControlApplyResponse",
    "ControlStateResponse",
    "ControlOptionsResponse",
    "AuditEntry",
    "ControlAuditResponse",
    "ResourceType",
]
