"""Modele API dla endpointów związanych z modelami AI.

DEPRECATED: This module is being phased out. Use venom_core.api.schemas instead.
Re-exports provided for backward compatibility.
"""

from venom_core.api.model_schemas.model_requests import (
    ModelActivateRequest,
    ModelConfigUpdateRequest,
    ModelInstallRequest,
    ModelRegistryInstallRequest,
    ModelSwitchRequest,
    TranslationRequest,
)
from venom_core.api.model_schemas.model_validators import (
    validate_huggingface_model_name,
    validate_model_name_basic,
    validate_model_name_extended,
    validate_ollama_model_name,
    validate_provider,
    validate_runtime,
)

# Re-exports from new centralized schemas for backward compatibility
from venom_core.api.schemas import (
    ActivateAdapterRequest,
    AdapterInfo,
    DatasetPreviewResponse,
    DatasetRequest,
    DatasetResponse,
    DatasetScopeRequest,
    GovernanceStatusResponse,
    HistoryRequestDetail,
    HistoryRequestSummary,
    JobStatusResponse,
    LearningToggleRequest,
    LimitsConfigResponse,
    MemoryIngestRequest,
    MemoryIngestResponse,
    MemorySearchRequest,
    ProviderActivateRequest,
    ProviderCapability,
    ProviderCredentialStatusResponse,
    ProviderInfo,
    ProviderStatus,
    TaskExtraContext,
    TaskRequest,
    TaskResponse,
    TrainableModelInfo,
    TrainingRequest,
    TrainingResponse,
    UpdateLimitRequest,
    UploadFileInfo,
)

__all__ = [
    # Model-specific Requests
    "ModelInstallRequest",
    "ModelSwitchRequest",
    "ModelRegistryInstallRequest",
    "ModelActivateRequest",
    "TranslationRequest",
    "ModelConfigUpdateRequest",
    # Validators
    "validate_model_name_basic",
    "validate_model_name_extended",
    "validate_huggingface_model_name",
    "validate_ollama_model_name",
    "validate_provider",
    "validate_runtime",
    # Re-exported schemas (backward compatibility)
    "HistoryRequestSummary",
    "HistoryRequestDetail",
    "ProviderCapability",
    "ProviderStatus",
    "ProviderInfo",
    "ProviderActivateRequest",
    "TaskExtraContext",
    "TaskRequest",
    "TaskResponse",
    "MemoryIngestRequest",
    "MemoryIngestResponse",
    "MemorySearchRequest",
    "LearningToggleRequest",
    "GovernanceStatusResponse",
    "LimitsConfigResponse",
    "ProviderCredentialStatusResponse",
    "UpdateLimitRequest",
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
]
