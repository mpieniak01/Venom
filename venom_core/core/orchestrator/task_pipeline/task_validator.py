from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from venom_core.config import SETTINGS
from venom_core.core.models import TaskRequest
from venom_core.core.slash_commands import normalize_forced_provider
from venom_core.utils.llm_runtime import compute_llm_config_hash, get_active_llm_runtime

if TYPE_CHECKING:
    from venom_core.core.orchestrator.orchestrator_core import Orchestrator


class TaskValidator:
    """Validates task constraints, capabilities, and routing."""

    def __init__(self, orch: "Orchestrator"):
        self.orch = orch

    def validate_forced_tool(
        self, task_id: UUID, forced_tool: str | None, forced_intent: str | None
    ) -> None:
        if forced_tool and not forced_intent:
            envelope = self.orch._build_error_envelope(
                error_code="forced_tool_unknown",
                error_message=f"Nieznane narzędzie w dyrektywie /{forced_tool}",
                error_details={"forced_tool": forced_tool},
                stage="intent_detection",
                retryable=False,
            )
            self.orch._set_runtime_error(task_id, envelope)
            raise RuntimeError("forced_tool_unknown")

    def validate_capabilities(
        self, task_id: UUID, kernel_required: bool, tool_required: bool
    ) -> None:
        if self.orch.request_tracer:
            self.orch.request_tracer.add_step(
                task_id,
                "DecisionGate",
                "requirements_resolved",
                status="ok",
                details=f"tool_required={tool_required}, kernel_required={kernel_required}",
            )

        if kernel_required and not getattr(self.orch.task_dispatcher, "kernel", None):
            if self.orch.request_tracer:
                self.orch.request_tracer.add_step(
                    task_id,
                    "DecisionGate",
                    "capability_required",
                    status="ok",
                    details="kernel",
                )
                self.orch.request_tracer.add_step(
                    task_id,
                    "DecisionGate",
                    "requirements_missing",
                    status="error",
                    details="missing=kernel",
                )
                self.orch.request_tracer.add_step(
                    task_id,
                    "Execution",
                    "execution_contract_violation",
                    status="error",
                    details="kernel_required",
                )
            envelope = self.orch._build_error_envelope(
                error_code="execution_contract_violation",
                error_message="Missing required capability: kernel",
                error_details={"missing": ["kernel"]},
                stage="agent_precheck",
                retryable=False,
            )
            self.orch._set_runtime_error(task_id, envelope)
            raise RuntimeError("execution_contract_violation")

    def validate_routing(
        self, task_id: UUID, request: TaskRequest, forced_provider: str
    ) -> None:
        runtime_info = get_active_llm_runtime()
        normalized_forced_provider = normalize_forced_provider(forced_provider)

        # ONNX runtime is handled via dedicated in-process adapter paths.
        # Standard orchestrator task path currently depends on SK OpenAI-compatible
        # connectors and may not execute ONNX models correctly.
        if runtime_info.provider == "onnx":
            envelope = self.orch._build_error_envelope(
                error_code="runtime_not_supported",
                error_message=(
                    "Runtime ONNX nie jest jeszcze obsługiwany w trybie zadaniowym "
                    "(Normal/Complex). Przełącz na vLLM/Ollama lub użyj trybu Direct."
                ),
                error_details={
                    "active_provider": runtime_info.provider,
                    "active_model": runtime_info.model_name,
                    "service_type": runtime_info.service_type,
                },
                stage="routing_validation",
                retryable=False,
            )
            self.orch._set_runtime_error(task_id, envelope)
            raise RuntimeError("runtime_not_supported")

        # Check provider mismatch
        if (
            normalized_forced_provider
            and runtime_info.provider != normalized_forced_provider
        ):
            envelope = self.orch._build_error_envelope(
                error_code="forced_provider_mismatch",
                error_message=(
                    "Wymuszony provider nie jest aktywny. "
                    f"Aktywny={runtime_info.provider}, wymagany={normalized_forced_provider}."
                ),
                error_details={
                    "active_provider": runtime_info.provider,
                    "required_provider": normalized_forced_provider,
                },
                stage="routing_validation",
                retryable=False,
            )
            self.orch._set_runtime_error(task_id, envelope)
            raise RuntimeError("forced_provider_mismatch")

        # Check config hash / runtime ID mismatch
        expected_hash = request.expected_config_hash or SETTINGS.LLM_CONFIG_HASH
        expected_runtime_id = request.expected_runtime_id
        actual_hash = runtime_info.config_hash or compute_llm_config_hash(
            runtime_info.provider, runtime_info.endpoint, runtime_info.model_name
        )

        if self.orch.request_tracer:
            self.orch.request_tracer.add_step(
                task_id,
                "Orchestrator",
                "routing_resolved",
                status="ok",
                details=(
                    f"provider={runtime_info.provider}, model={runtime_info.model_name}, "
                    f"endpoint={runtime_info.endpoint}, hash={actual_hash}, runtime={runtime_info.runtime_id}"
                ),
            )

        mismatch = False
        mismatch_details = []
        if expected_hash and actual_hash != expected_hash:
            mismatch = True
            mismatch_details.append(
                f"expected_hash={expected_hash}, actual_hash={actual_hash}"
            )
        if expected_runtime_id and runtime_info.runtime_id != expected_runtime_id:
            mismatch = True
            mismatch_details.append(
                f"expected_runtime={expected_runtime_id}, actual_runtime={runtime_info.runtime_id}"
            )

        if mismatch:
            if self.orch.request_tracer:
                self.orch.request_tracer.add_step(
                    task_id,
                    "Orchestrator",
                    "routing_mismatch",
                    status="error",
                    details="; ".join(mismatch_details),
                )
            envelope = self.orch._build_error_envelope(
                error_code="routing_mismatch",
                error_message="Active runtime does not match expected configuration.",
                error_details={
                    "expected_hash": expected_hash,
                    "actual_hash": actual_hash,
                    "expected_runtime": expected_runtime_id,
                    "actual_runtime": runtime_info.runtime_id,
                },
                stage="routing",
                retryable=False,
            )
            self.orch._set_runtime_error(task_id, envelope)
            raise RuntimeError("routing_mismatch")
