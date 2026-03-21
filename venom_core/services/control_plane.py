"""Control Plane Service for managing workflow and system configuration.

This service aggregates and coordinates changes across:
- Decision strategy and intent mode
- Kernel and runtime configuration
- Provider and model selection
- Embedding and workflow control
"""

import json
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from venom_core.api.schemas.workflow_control import (
    AppliedChange,
    ApplyMode,
    CompatibilityReport,
    ControlApplyRequest,
    ControlApplyResponse,
    ControlPlanRequest,
    ControlPlanResponse,
    ControlStateResponse,
    OperatorConfigField,
    OperatorExecutionStep,
    OperatorGraph,
    OperatorGraphEdge,
    OperatorGraphNode,
    OperatorMeta,
    OperatorRuntimeService,
    ReasonCode,
    ResourceChange,
    ResourceType,
    SystemState,
    WorkflowStatus,
    WorkflowTargetState,
)
from venom_core.services.config_manager import RESTART_REQUIREMENTS, config_manager
from venom_core.services.control_plane_audit import get_control_plane_audit_trail
from venom_core.services.control_plane_compatibility import get_compatibility_validator
from venom_core.services.runtime_controller import runtime_controller
from venom_core.services.runtime_dependencies import get_request_tracer
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class ControlPlaneService:
    """Service for planning and applying system-wide configuration changes."""

    def __init__(self):
        """Initialize control plane service."""
        self._pending_plans: dict[str, dict[str, Any]] = {}
        self._compatibility_validator = get_compatibility_validator()
        self._audit_trail = get_control_plane_audit_trail()
        self._lock = threading.Lock()
        self._active_operations: set[str] = set()

    RESOURCE_CONFIG_KEY_MAP: dict[ResourceType, str] = {
        ResourceType.DECISION_STRATEGY: "AI_MODE",
        ResourceType.INTENT_MODE: "INTENT_MODE",
        ResourceType.KERNEL: "KERNEL",
        ResourceType.RUNTIME: "WORKFLOW_RUNTIME",
        ResourceType.PROVIDER: "ACTIVE_PROVIDER",
        ResourceType.EMBEDDING_MODEL: "EMBEDDING_MODEL",
    }
    CLOUD_PROVIDERS = {
        "openai",
        "google",
        "anthropic",
        "azure-openai",
        "azure",
        "cohere",
        "mistral",
        "together",
        "groq",
        "bedrock",
        "gemini",
    }
    SERVICE_DEPENDENCIES: dict[str, list[str]] = {
        "backend": [],
        "ui": ["backend"],
        "llm_ollama": ["backend"],
        "llm_vllm": ["backend"],
        "hive": ["backend"],
        "nexus": ["backend"],
        "background_tasks": ["backend"],
        "academy": ["backend"],
        "intent_embedding_router": ["backend"],
    }
    STEP_STAGE_MAP: dict[str, str] = {
        "decision": "decision",
        "intent": "intent",
        "kernel": "execution",
        "embedding": "embedding",
        "provider": "runtime",
        "runtime": "runtime",
        "system": "system",
        "user": "ingress",
        "orchestrator": "orchestration",
    }
    STEP_CONFIG_KEY_MAP: dict[str, list[str]] = {
        "decision": ["AI_MODE"],
        "intent": ["INTENT_MODE"],
        "kernel": ["KERNEL"],
        "provider": ["ACTIVE_PROVIDER"],
        "embedding": ["EMBEDDING_MODEL"],
        "llm": ["ACTIVE_PROVIDER"],
        "model": ["ACTIVE_PROVIDER"],
    }

    def plan_changes(
        self, request: ControlPlanRequest, triggered_by: str
    ) -> ControlPlanResponse:
        """Plan configuration changes and validate compatibility.

        Args:
            request: Plan request with desired changes
            triggered_by: User or system requesting the plan

        Returns:
            Plan response with validation results
        """
        start_time = time.time()
        execution_ticket = str(uuid.uuid4())
        operation_id = f"plan:{execution_ticket}"

        if not self._begin_operation(operation_id):
            return self._build_plan_in_progress_response(execution_ticket)

        try:
            prepared_plan = self._prepare_plan(request)
            reason_code = self._resolve_plan_reason_code(
                overall_compatible=prepared_plan["overall_compatible"],
                restart_required_services=prepared_plan["restart_required_services"],
            )
            response = ControlPlanResponse(
                execution_ticket=execution_ticket,
                valid=prepared_plan["overall_compatible"],
                reason_code=reason_code,
                compatibility_report=CompatibilityReport(
                    compatible=prepared_plan["overall_compatible"],
                    issues=prepared_plan["compatibility_issues"],
                    warnings=prepared_plan["compatibility_warnings"],
                    affected_services=prepared_plan["affected_services"],
                ),
                planned_changes=prepared_plan["planned_changes"],
                hot_swap_changes=prepared_plan["hot_swap_changes"],
                restart_required_services=prepared_plan["restart_required_services"],
                rejected_changes=prepared_plan["rejected_changes"],
                estimated_duration_seconds=self._estimate_duration(
                    prepared_plan["planned_changes"]
                ),
            )

            # Store plan for later apply
            if not request.dry_run:
                self._store_pending_plan(execution_ticket, response, request)

            # Log to audit trail
            duration_ms = (time.time() - start_time) * 1000
            self._audit_trail.log_operation(
                triggered_by=triggered_by,
                operation_type="plan",
                resource_type=ResourceType.CONFIG,
                resource_id="system",
                params={
                    "changes_count": len(request.changes),
                    "dry_run": request.dry_run,
                },
                result="success" if prepared_plan["overall_compatible"] else "rejected",
                reason_code=reason_code,
                duration_ms=duration_ms,
            )

            return response

        except Exception as e:
            logger.exception("Failed to plan changes")
            duration_ms = (time.time() - start_time) * 1000
            self._audit_trail.log_operation(
                triggered_by=triggered_by,
                operation_type="plan",
                resource_type=ResourceType.CONFIG,
                resource_id="system",
                params={"changes_count": len(request.changes)},
                result="failure",
                reason_code=ReasonCode.OPERATION_FAILED,
                duration_ms=duration_ms,
                error_message=str(e),
            )
            raise
        finally:
            self._end_operation(operation_id)

    def apply_changes(
        self, request: ControlApplyRequest, triggered_by: str
    ) -> ControlApplyResponse:
        """Apply previously planned changes.

        Args:
            request: Apply request with execution ticket
            triggered_by: User or system applying the changes

        Returns:
            Apply response with results
        """
        start_time = time.time()
        operation_id = f"apply:{request.execution_ticket}"

        if not self._begin_operation(operation_id):
            return self._build_apply_in_progress_response(request.execution_ticket)

        try:
            plan, plan_request, early_response = self._get_pending_plan_for_apply(
                request
            )
            if early_response:
                return early_response
            assert plan is not None
            assert plan_request is not None

            early_restart_response = self._check_restart_confirmation(
                plan=plan, request=request
            )
            if early_restart_response:
                return early_restart_response

            apply_result = self._apply_plan_changes(
                plan_request=plan_request,
                triggered_by=triggered_by,
                execution_ticket=request.execution_ticket,
            )
            response = self._build_apply_response(
                execution_ticket=request.execution_ticket,
                plan=plan,
                applied_changes=apply_result["applied_changes"],
                failed_changes=apply_result["failed_changes"],
                rollback_attempted=apply_result["rollback_attempted"],
                rollback_snapshot=apply_result["rollback_snapshot"],
            )

            # Clean up pending plan
            with self._lock:
                self._pending_plans.pop(request.execution_ticket, None)

            # Log to audit trail
            duration_ms = (time.time() - start_time) * 1000
            self._audit_trail.log_operation(
                triggered_by=triggered_by,
                operation_type="apply",
                resource_type=ResourceType.CONFIG,
                resource_id="system",
                params={
                    "execution_ticket": request.execution_ticket,
                    "confirm_restart": request.confirm_restart,
                },
                result="success" if len(response.failed_changes) == 0 else "partial",
                reason_code=response.reason_code,
                duration_ms=duration_ms,
            )
            if apply_result["rollback_attempted"]:
                self._audit_trail.log_operation(
                    triggered_by=triggered_by,
                    operation_type="rollback",
                    resource_type=ResourceType.CONFIG,
                    resource_id="system",
                    params={"execution_ticket": request.execution_ticket},
                    result="success" if apply_result["rollback_success"] else "failure",
                    reason_code=(
                        ReasonCode.OPERATION_COMPLETED
                        if apply_result["rollback_success"]
                        else ReasonCode.OPERATION_FAILED
                    ),
                    duration_ms=duration_ms,
                    error_message=(
                        None
                        if apply_result["rollback_success"]
                        else "Rollback could not restore all configuration keys"
                    ),
                )

            return response

        except Exception as e:
            logger.exception("Failed to apply changes")
            duration_ms = (time.time() - start_time) * 1000
            self._audit_trail.log_operation(
                triggered_by=triggered_by,
                operation_type="apply",
                resource_type=ResourceType.CONFIG,
                resource_id="system",
                params={"execution_ticket": request.execution_ticket},
                result="failure",
                reason_code=ReasonCode.OPERATION_FAILED,
                duration_ms=duration_ms,
                error_message=str(e),
            )
            raise
        finally:
            self._end_operation(operation_id)

    def _build_plan_in_progress_response(
        self, execution_ticket: str
    ) -> ControlPlanResponse:
        return ControlPlanResponse(
            execution_ticket=execution_ticket,
            valid=False,
            reason_code=ReasonCode.OPERATION_IN_PROGRESS,
            compatibility_report=CompatibilityReport(
                compatible=False,
                issues=[
                    "Another plan operation is already in progress for this ticket"
                ],
                warnings=[],
                affected_services=[],
            ),
            planned_changes=[],
            hot_swap_changes=[],
            restart_required_services=[],
            rejected_changes=["Operation already in progress"],
            estimated_duration_seconds=0.0,
        )

    def _prepare_plan(self, request: ControlPlanRequest) -> dict[str, Any]:
        planned_changes: list[AppliedChange] = []
        hot_swap_changes: list[str] = []
        restart_required_services: list[str] = []
        rejected_changes: list[str] = []
        compatibility_issues: list[str] = []
        compatibility_warnings: list[str] = []
        affected_services: set[str] = set()

        for change in request.changes:
            result = self._validate_change(change)
            if result["valid"]:
                planned_changes.append(
                    AppliedChange(
                        resource_type=change.resource_type,
                        resource_id=change.resource_id,
                        action=change.action,
                        apply_mode=result["apply_mode"],
                        reason_code=result["reason_code"],
                        message=result["message"],
                        timestamp=result["timestamp"],
                    )
                )
                if result["apply_mode"] == ApplyMode.HOT_SWAP:
                    hot_swap_changes.append(change.resource_id)
                elif result["apply_mode"] == ApplyMode.RESTART_REQUIRED:
                    restart_required_services.extend(result["restart_services"])
                affected_services.update(result.get("affected_services", []))
                continue

            rejected_changes.append(f"{change.resource_id}: {result['message']}")
            compatibility_issues.append(result["message"])

        overall_compatible = len(rejected_changes) == 0
        if overall_compatible:
            current_state = self._get_current_state()
            compatible, issues = self._validate_full_stack_compatibility(
                current_state, request.changes
            )
            if not compatible:
                overall_compatible = False
                compatibility_issues.extend(issues)

        return {
            "planned_changes": planned_changes,
            "hot_swap_changes": hot_swap_changes,
            "restart_required_services": list(set(restart_required_services)),
            "rejected_changes": rejected_changes,
            "compatibility_issues": compatibility_issues,
            "compatibility_warnings": compatibility_warnings,
            "affected_services": list(affected_services),
            "overall_compatible": overall_compatible,
        }

    def _resolve_plan_reason_code(
        self, overall_compatible: bool, restart_required_services: list[str]
    ) -> ReasonCode:
        if not overall_compatible:
            return ReasonCode.INVALID_CONFIGURATION
        if restart_required_services:
            return ReasonCode.SUCCESS_RESTART_PENDING
        return ReasonCode.SUCCESS_HOT_SWAP

    def _store_pending_plan(
        self,
        execution_ticket: str,
        response: ControlPlanResponse,
        request: ControlPlanRequest,
    ) -> None:
        with self._lock:
            self._pending_plans[execution_ticket] = {
                "response": response,
                "request": request,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

    def _build_apply_in_progress_response(
        self, execution_ticket: str
    ) -> ControlApplyResponse:
        return ControlApplyResponse(
            execution_ticket=execution_ticket,
            apply_mode=ApplyMode.REJECTED,
            reason_code=ReasonCode.OPERATION_IN_PROGRESS,
            message="Apply operation already in progress for this ticket",
            applied_changes=[],
            pending_restart=[],
            failed_changes=["Operation already in progress"],
            rollback_available=True,
        )

    def _get_pending_plan_for_apply(
        self, request: ControlApplyRequest
    ) -> tuple[
        ControlPlanResponse | None,
        ControlPlanRequest | None,
        ControlApplyResponse | None,
    ]:
        with self._lock:
            pending = self._pending_plans.get(request.execution_ticket)
        if not pending:
            return (
                None,
                None,
                ControlApplyResponse(
                    execution_ticket=request.execution_ticket,
                    apply_mode=ApplyMode.REJECTED,
                    reason_code=ReasonCode.INVALID_CONFIGURATION,
                    message="Invalid or expired execution ticket",
                    applied_changes=[],
                    pending_restart=[],
                    failed_changes=["Invalid execution ticket"],
                ),
            )
        plan: ControlPlanResponse = pending["response"]
        plan_request: ControlPlanRequest = pending["request"]
        if not plan.valid:
            return (
                None,
                None,
                ControlApplyResponse(
                    execution_ticket=request.execution_ticket,
                    apply_mode=ApplyMode.REJECTED,
                    reason_code=ReasonCode.INVALID_CONFIGURATION,
                    message="Cannot apply invalid plan",
                    applied_changes=[],
                    pending_restart=[],
                    failed_changes=["Plan validation failed"],
                ),
            )
        return plan, plan_request, None

    def _check_restart_confirmation(
        self, plan: ControlPlanResponse, request: ControlApplyRequest
    ) -> ControlApplyResponse | None:
        if not plan.restart_required_services or request.confirm_restart:
            return None
        return ControlApplyResponse(
            execution_ticket=request.execution_ticket,
            apply_mode=ApplyMode.RESTART_REQUIRED,
            reason_code=ReasonCode.SUCCESS_RESTART_PENDING,
            message="Restart required but not confirmed",
            applied_changes=[],
            pending_restart=plan.restart_required_services,
            failed_changes=[],
        )

    def _apply_plan_changes(
        self,
        plan_request: ControlPlanRequest,
        triggered_by: str,
        execution_ticket: str,
    ) -> dict[str, Any]:
        applied_changes: list[AppliedChange] = []
        failed_changes: list[str] = []
        rollback_snapshot: dict[str, Any] = {}
        rollback_attempted = False
        rollback_success = False

        for change in plan_request.changes:
            try:
                applied_change = self._apply_single_change(
                    requested_change=change,
                    rollback_snapshot=rollback_snapshot,
                )
                applied_changes.append(applied_change)
            except Exception as e:
                error_type = type(e).__name__
                logger.error(
                    "Failed to apply requested change (error_type=%s)",
                    error_type,
                )
                failed_changes.append(
                    f"{change.resource_id}: apply_failed ({error_type})"
                )
                rollback_attempted = True
                rollback_success = self._rollback_config_changes(
                    rollback_snapshot=rollback_snapshot,
                    triggered_by=triggered_by,
                    execution_ticket=execution_ticket,
                )
                failed_changes.append(
                    "Rollback completed for applied config changes"
                    if rollback_success
                    else "Rollback failed for one or more keys"
                )
                break

        return {
            "applied_changes": applied_changes,
            "failed_changes": failed_changes,
            "rollback_snapshot": rollback_snapshot,
            "rollback_attempted": rollback_attempted,
            "rollback_success": rollback_success,
        }

    def _build_apply_response(
        self,
        execution_ticket: str,
        plan: ControlPlanResponse,
        applied_changes: list[AppliedChange],
        failed_changes: list[str],
        rollback_attempted: bool,
        rollback_snapshot: dict[str, Any],
    ) -> ControlApplyResponse:
        if failed_changes:
            apply_mode = ApplyMode.REJECTED
            reason_code = ReasonCode.OPERATION_FAILED
            message = (
                f"Applied {len(applied_changes)}/{len(plan.planned_changes)} changes"
            )
        elif plan.restart_required_services:
            apply_mode = ApplyMode.RESTART_REQUIRED
            reason_code = ReasonCode.SUCCESS_RESTART_PENDING
            message = "Changes applied, restart required"
        else:
            apply_mode = ApplyMode.HOT_SWAP
            reason_code = ReasonCode.SUCCESS_HOT_SWAP
            message = "All changes applied successfully"
        return ControlApplyResponse(
            execution_ticket=execution_ticket,
            apply_mode=apply_mode,
            reason_code=reason_code,
            message=message,
            applied_changes=applied_changes,
            pending_restart=plan.restart_required_services,
            failed_changes=failed_changes,
            rollback_available=rollback_attempted or bool(rollback_snapshot),
        )

    def get_system_state(self) -> SystemState:
        """Get current state of the entire system.

        Returns:
            Current system state
        """
        # Get runtime status
        runtime_status = runtime_controller.get_all_services_status()
        runtime_dict = {
            "services": [
                {
                    "name": s.name,
                    "status": s.status.value,
                    "uptime_seconds": s.uptime_seconds,
                }
                for s in runtime_status
            ]
        }

        # Get config
        config = config_manager.get_config(mask_secrets=False)

        # Get latest workflow status from WorkflowOperationService
        # Import here to avoid circular dependency.
        from venom_core.services.workflow_operations import get_workflow_service

        workflow_service = get_workflow_service()

        # --- Real-state parity (PR 204) ---
        # Pull the most recent request trace to expose actual runtime/provider/model context.
        active_request_id: str | None = None
        active_task_status: str | None = None
        llm_runtime_id: str | None = None
        llm_provider_name: str | None = None
        llm_model: str | None = None

        try:
            tracer = get_request_tracer()
            if tracer is not None:
                recent_traces = tracer.get_all_traces(limit=1)
                if recent_traces:
                    trace = recent_traces[0]
                    active_request_id = str(trace.request_id)
                    active_task_status = trace.status.value
                    llm_runtime_id = trace.llm_runtime_id
                    llm_provider_name = trace.llm_provider
                    llm_model = trace.llm_model

                    # Sync trace lifecycle with workflow service so that WF operations
                    # (pause/resume/cancel) target the real active request.
                    if active_task_status == "PROCESSING":
                        # Only register if new — preserves PAUSED state set by user ops.
                        workflow_service.register_workflow(
                            active_request_id, WorkflowStatus.RUNNING
                        )
                    elif active_task_status == "COMPLETED":
                        # Force-sync terminal state so WF service doesn't stay RUNNING.
                        workflow_service.sync_workflow_status(
                            active_request_id, WorkflowStatus.COMPLETED
                        )
                    elif active_task_status == "FAILED":
                        # Force-sync terminal state so WF service doesn't stay RUNNING.
                        workflow_service.sync_workflow_status(
                            active_request_id, WorkflowStatus.FAILED
                        )
        except (AttributeError, TypeError, ValueError, RuntimeError) as exc:
            # Tracer unavailable or malformed — proceed with no real-state data.
            logger.warning(
                "Request tracer unavailable while building control-plane state: %s",
                exc,
            )

        # Derive workflow_status: real trace status takes precedence over
        # the synthetic workflow service status.
        workflow_status = self._derive_workflow_status(
            active_task_status, active_request_id, workflow_service
        )

        # Compute allowed operations based on resolved workflow status.
        allowed_operations = self._compute_allowed_operations(
            workflow_status, active_request_id
        )

        # Build state
        derived_runtime = self._resolve_runtime_from_config(config)
        derived_provider = self._resolve_provider_from_config(config)
        derived_model = self._resolve_model_from_config(config, derived_provider)
        embedding_model = config.get(
            "EMBEDDING_MODEL",
            config.get("INTENT_EMBED_MODEL_NAME", "sentence-transformers"),
        )

        compatible, compatibility_issues = (
            self._compatibility_validator.validate_full_stack(
                kernel=str(config.get("KERNEL", "standard")),
                runtime=derived_runtime,
                provider=derived_provider,
                model=derived_model,
                embedding_model=str(embedding_model),
                intent_mode=str(config.get("INTENT_MODE", "simple")),
            )
        )
        health_overall = self._calculate_health_status(
            runtime_status, compatible=compatible
        )
        health_checks = [
            {"name": s.name, "status": s.status.value} for s in runtime_status
        ]
        if compatibility_issues:
            health_checks.append(
                {
                    "name": "compatibility",
                    "status": "degraded",
                    "issues": compatibility_issues,
                }
            )

        state = SystemState(
            timestamp=datetime.now(timezone.utc),
            decision_strategy=config.get("AI_MODE", "standard"),
            intent_mode=config.get("INTENT_MODE", "simple"),
            kernel=config.get("KERNEL", "standard"),
            runtime=runtime_dict,
            provider={
                "active": derived_provider,
                "available": ["ollama", "onnx", "huggingface", "openai"],
                "sourceType": self._classify_provider_source(derived_provider),
            },
            embedding_model=embedding_model,
            provider_source=self._classify_provider_source(derived_provider),
            embedding_source=self._classify_embedding_source(str(embedding_model)),
            workflow_status=workflow_status,
            active_operations=self._get_active_operations_snapshot(),
            health={
                "overall": health_overall,
                "checks": health_checks,
                "compatibility_issues": compatibility_issues,
            },
            active_request_id=active_request_id,
            active_task_status=active_task_status,
            llm_runtime_id=llm_runtime_id,
            llm_provider_name=llm_provider_name,
            llm_model=llm_model,
            allowed_operations=allowed_operations,
        )

        return state

    def get_control_state(self, request_id: str | None = None) -> ControlStateResponse:
        """Build canonical operator payload for workflow-control."""
        base_state = self.get_system_state()
        selected_trace, request_selector = self._select_trace(request_id)

        if selected_trace is not None:
            # Import here to avoid circular dependency.
            from venom_core.services.workflow_operations import get_workflow_service

            workflow_service = get_workflow_service()
            selected_request_id = str(selected_trace.request_id)
            selected_task_status = selected_trace.status.value
            selected_workflow_status = self._derive_workflow_status(
                selected_task_status,
                selected_request_id,
                workflow_service,
            )
            selected_allowed_operations = self._compute_allowed_operations(
                selected_workflow_status,
                selected_request_id,
            )
            base_state = base_state.model_copy(
                update={
                    "active_request_id": selected_request_id,
                    "active_task_status": selected_task_status,
                    "llm_runtime_id": selected_trace.llm_runtime_id,
                    "llm_provider_name": selected_trace.llm_provider,
                    "llm_model": selected_trace.llm_model,
                    "workflow_status": selected_workflow_status,
                    "allowed_operations": selected_allowed_operations,
                }
            )

        config_fields = self._build_operator_config_fields()
        runtime_services = self._build_operator_runtime_services()
        execution_steps = self._build_execution_steps(
            trace=selected_trace,
            system_state=base_state,
            runtime_services=runtime_services,
            allowed_operations=base_state.allowed_operations,
        )
        workflow_target = WorkflowTargetState(
            request_id=base_state.active_request_id,
            task_status=base_state.active_task_status,
            workflow_status=base_state.workflow_status.value,
            runtime_id=base_state.llm_runtime_id,
            provider=base_state.llm_provider_name,
            model=base_state.llm_model,
            allowed_operations=base_state.allowed_operations,
        )
        graph = self._build_operator_graph(
            system_state=base_state,
            config_fields=config_fields,
            runtime_services=runtime_services,
            execution_steps=execution_steps,
        )
        runtime_actions: list[str] = []
        for service in runtime_services:
            for action in service.allowed_actions:
                runtime_actions.append(f"runtime:{service.id}:{action}")
        step_actions: list[str] = []
        for step in execution_steps:
            for action in step.allowed_actions:
                step_actions.append(f"execution_step:{step.id}:{action}")

        return ControlStateResponse(
            system_state=base_state,
            meta=OperatorMeta(
                timestamp=base_state.timestamp,
                request_selector=request_selector,
            ),
            workflow_target=workflow_target,
            config_fields=config_fields,
            runtime_services=runtime_services,
            execution_steps=execution_steps,
            graph=graph,
            allowed_actions=sorted(
                set(base_state.allowed_operations + runtime_actions + step_actions)
            ),
            last_operation=None,
            pending_changes=[],
        )

    def _select_trace(self, request_id: str | None = None) -> tuple[Any | None, str]:
        """Select request trace from explicit request_id or canonical auto strategy."""
        tracer = get_request_tracer()
        if tracer is None:
            return None, "none"

        if request_id:
            try:
                trace = tracer.get_trace(UUID(request_id))
                if trace is not None:
                    return trace, "request_id"
            except (ValueError, TypeError, AttributeError):
                logger.warning(
                    "Invalid request_id for workflow-control state selector: %s",
                    request_id,
                )

        try:
            traces = tracer.get_all_traces(limit=200)
        except Exception:
            return None, "none"

        for trace in traces:
            trace_status = getattr(getattr(trace, "status", None), "value", "")
            if trace_status == "PROCESSING":
                return trace, "latest_active"

        if traces:
            return traces[0], "latest"
        return None, "none"

    def _build_operator_config_fields(self) -> list[OperatorConfigField]:
        config, sources = config_manager.get_effective_config_with_sources(
            mask_secrets=True
        )
        options = self.get_control_options()
        result: list[OperatorConfigField] = []
        for key in sorted(config.keys()):
            restart_services = RESTART_REQUIREMENTS.get(key, [])
            result.append(
                OperatorConfigField(
                    entity_id=f"config:{key}",
                    field="value",
                    key=key,
                    value=config.get(key),
                    effective_value=config.get(key),
                    source=sources.get(key, "default"),
                    editable=True,
                    restart_required=bool(restart_services),
                    affected_services=list(restart_services),
                    options=self._get_config_options_for_key(key, options),
                )
            )
        return result

    def _get_config_options_for_key(
        self, key: str, options: dict[str, Any]
    ) -> list[str]:
        mapping: dict[str, list[str]] = {
            "AI_MODE": options.get("decision_strategies", []),
            "INTENT_MODE": options.get("intent_modes", []),
            "KERNEL": options.get("kernels", []),
            "ACTIVE_PROVIDER": [
                *options.get("providers", {}).get("local", []),
                *options.get("providers", {}).get("cloud", []),
            ],
            "EMBEDDING_MODEL": [
                *options.get("embeddings", {}).get("local", []),
                *options.get("embeddings", {}).get("cloud", []),
            ],
        }
        return mapping.get(key, [])

    def _build_operator_runtime_services(self) -> list[OperatorRuntimeService]:
        statuses = runtime_controller.get_all_services_status()
        result: list[OperatorRuntimeService] = []
        for status in statuses:
            status_value = str(
                getattr(getattr(status, "status", None), "value", "unknown")
            )
            service_name = str(getattr(status, "name", ""))
            service_type_value = str(
                getattr(getattr(status, "service_type", None), "value", "runtime")
            )
            actionable = bool(getattr(status, "actionable", False))
            allowed_actions: list[str] = []
            if actionable:
                if status_value == "running":
                    allowed_actions = ["stop", "restart"]
                else:
                    allowed_actions = ["start"]
            result.append(
                OperatorRuntimeService(
                    id=service_type_value,
                    name=service_name,
                    kind=service_type_value,
                    status=status_value,
                    pid=getattr(status, "pid", None),
                    port=getattr(status, "port", None),
                    cpu_percent=float(getattr(status, "cpu_percent", 0.0) or 0.0),
                    memory_mb=float(getattr(status, "memory_mb", 0.0) or 0.0),
                    uptime_seconds=getattr(status, "uptime_seconds", None),
                    runtime_version=getattr(status, "runtime_version", None),
                    actionable=actionable,
                    allowed_actions=allowed_actions,
                    dependencies=self.SERVICE_DEPENDENCIES.get(service_type_value, []),
                )
            )
        return result

    def _build_execution_steps(
        self,
        trace: Any | None,
        system_state: SystemState,
        runtime_services: list[OperatorRuntimeService],
        allowed_operations: list[str],
    ) -> list[OperatorExecutionStep]:
        if trace is None:
            return []

        steps = getattr(trace, "steps", []) or []
        trace_id = str(getattr(trace, "request_id", "unknown"))
        result: list[OperatorExecutionStep] = []
        previous_step_id: str | None = None
        for index, step in enumerate(steps):
            component = str(getattr(step, "component", "unknown"))
            action = str(getattr(step, "action", "step"))
            status = str(getattr(step, "status", "unknown"))
            details = getattr(step, "details", None)
            step_id = f"{trace_id}:{index}"
            result.append(
                OperatorExecutionStep(
                    id=step_id,
                    component=component,
                    action=action,
                    status=status,
                    timestamp=getattr(step, "timestamp", None),
                    details=details,
                    stage=self._infer_step_stage(component=component, action=action),
                    related_service_id=self._infer_related_service_id(
                        component=component,
                        action=action,
                        system_state=system_state,
                        runtime_services=runtime_services,
                    ),
                    related_config_keys=self._infer_related_config_keys(
                        component=component,
                        action=action,
                        details=details,
                    ),
                    depends_on_step_id=previous_step_id,
                    severity=self._infer_step_severity(status=status, details=details),
                    allowed_actions=self._infer_step_allowed_actions(
                        status=status,
                        allowed_operations=allowed_operations,
                    ),
                )
            )
            previous_step_id = step_id
        return result

    def _infer_step_allowed_actions(
        self,
        status: str,
        allowed_operations: list[str],
    ) -> list[str]:
        normalized_status = status.strip().lower()
        if normalized_status in {"running", "processing", "pending"}:
            return []

        actions: list[str] = []
        if "retry_from_step" in allowed_operations or "retry" in allowed_operations:
            actions.append("retry_from_step")
        if "replay_step" in allowed_operations:
            actions.append("replay_step")
        if "skip_step" in allowed_operations:
            actions.append("skip_step")
        return actions

    def _infer_step_stage(self, component: str, action: str) -> str:
        normalized_component = component.strip().lower()
        normalized_action = action.strip().lower()

        for marker, stage in self.STEP_STAGE_MAP.items():
            if marker in normalized_component:
                return stage

        if "classify" in normalized_action or "intent" in normalized_action:
            return "intent"
        if "embed" in normalized_action:
            return "embedding"
        if "plan" in normalized_action or "route" in normalized_action:
            return "orchestration"
        return "execution"

    def _infer_related_service_id(
        self,
        component: str,
        action: str,
        system_state: SystemState,
        runtime_services: list[OperatorRuntimeService],
    ) -> str | None:
        service_lookup = {
            service.id.strip().lower(): service.id for service in runtime_services
        }
        kind_lookup = {
            (service.kind or "").strip().lower(): service.id
            for service in runtime_services
        }
        normalized_component = component.strip().lower()
        normalized_action = action.strip().lower()

        if normalized_component in service_lookup:
            return service_lookup[normalized_component]
        if normalized_component in kind_lookup:
            return kind_lookup[normalized_component]
        if normalized_component in {
            "decision",
            "intent",
            "kernel",
            "system",
            "orchestrator",
            "user",
        }:
            return service_lookup.get("backend")
        if "ui" in normalized_component:
            return service_lookup.get("ui")
        if "embed" in normalized_component or "embed" in normalized_action:
            return service_lookup.get("intent_embedding_router") or service_lookup.get(
                "backend"
            )

        provider_candidate = (system_state.llm_provider_name or "").strip()
        if not provider_candidate and system_state.provider:
            provider_candidate = str(system_state.provider.get("active", "")).strip()
        provider_name = provider_candidate.lower()
        provider_service_map = {
            "ollama": "llm_ollama",
            "vllm": "llm_vllm",
        }
        if provider_name:
            provider_service_id = provider_service_map.get(provider_name)
            if provider_service_id and provider_service_id in service_lookup:
                if (
                    provider_name in normalized_component
                    or provider_name in normalized_action
                ):
                    return provider_service_id
            if "llm" in normalized_component or "model" in normalized_component:
                if provider_service_id and provider_service_id in service_lookup:
                    return provider_service_id

        if "runtime" in normalized_component:
            return service_lookup.get("backend")
        return None

    def _infer_related_config_keys(
        self,
        component: str,
        action: str,
        details: Any,
    ) -> list[str]:
        normalized_component = component.strip().lower()
        normalized_action = action.strip().lower()
        keys: list[str] = []

        for marker, mapped_keys in self.STEP_CONFIG_KEY_MAP.items():
            if marker in normalized_component or marker in normalized_action:
                keys.extend(mapped_keys)

        parsed_details: Any = None
        detail_text = ""
        if isinstance(details, str):
            normalized_details = details.strip()
            if normalized_details.startswith(("{", "[")):
                try:
                    parsed_details = json.loads(normalized_details)
                except json.JSONDecodeError:
                    logger.warning(
                        f"Could not parse step details as JSON: {normalized_details[:200]}"
                    )
                    parsed_details = None
            if isinstance(parsed_details, (dict, list)):
                detail_text = json.dumps(parsed_details, ensure_ascii=False).lower()
            else:
                detail_text = details.lower()
        elif isinstance(details, (dict, list)):
            parsed_details = details
            detail_text = json.dumps(details, ensure_ascii=False).lower()

        if "intent" in detail_text:
            keys.append("INTENT_MODE")
        if "progress" in detail_text or "kernel" in detail_text:
            keys.append("KERNEL")
        if "embed" in detail_text:
            keys.append("EMBEDDING_MODEL")
        if "provider" in detail_text or "model" in detail_text:
            keys.append("ACTIVE_PROVIDER")

        return sorted(set(keys))

    def _infer_step_severity(self, status: str, details: Any) -> str:
        normalized_status = status.strip().lower()
        detail_text = str(details or "").lower()
        if normalized_status in {"error", "failed", "failure", "cancelled"}:
            return "error"
        if normalized_status in {"warning", "blocked", "paused"}:
            return "warning"
        if normalized_status in {"running", "in_progress", "processing"}:
            return "info"
        if (
            "error" in detail_text
            or "exception" in detail_text
            or "timeout" in detail_text
        ):
            return "error"
        return "normal"

    def _build_operator_graph(
        self,
        system_state: SystemState,
        config_fields: list[OperatorConfigField],
        runtime_services: list[OperatorRuntimeService],
        execution_steps: list[OperatorExecutionStep],
    ) -> OperatorGraph:
        nodes: list[OperatorGraphNode] = [
            OperatorGraphNode(
                id="decision",
                type="decision",
                label="Decision",
                data={"strategy": system_state.decision_strategy},
                position={"x": 0.0, "y": 0.0},
            ),
            OperatorGraphNode(
                id="intent",
                type="intent",
                label="Intent",
                data={"intentMode": system_state.intent_mode},
                position={"x": 220.0, "y": 120.0},
            ),
            OperatorGraphNode(
                id="kernel",
                type="kernel",
                label="Kernel",
                data={"kernel": system_state.kernel},
                position={"x": 440.0, "y": 240.0},
            ),
            OperatorGraphNode(
                id="runtime",
                type="runtime",
                label="Runtime",
                data={"runtime": system_state.runtime},
                position={"x": 660.0, "y": 360.0},
            ),
            OperatorGraphNode(
                id="embedding",
                type="embedding",
                label="Embedding",
                data={
                    "model": system_state.embedding_model,
                    "sourceType": system_state.embedding_source,
                    "sourceTag": system_state.embedding_source,
                },
                position={"x": 880.0, "y": 480.0},
            ),
            OperatorGraphNode(
                id="provider",
                type="provider",
                label="Provider",
                data={
                    "provider": system_state.provider,
                    "sourceType": system_state.provider_source,
                    "sourceTag": system_state.provider_source,
                },
                position={"x": 1100.0, "y": 600.0},
            ),
            OperatorGraphNode(
                id="config",
                type="config",
                label="Config",
                data={
                    "configFields": [
                        field.model_dump(mode="json") for field in config_fields
                    ],
                    "fieldCount": len(config_fields),
                },
                position={"x": 990.0, "y": 540.0},
            ),
        ]
        edges: list[OperatorGraphEdge] = [
            OperatorGraphEdge(
                id="e1", source="decision", target="intent", animated=True
            ),
            OperatorGraphEdge(id="e2", source="intent", target="kernel", animated=True),
            OperatorGraphEdge(
                id="e3", source="kernel", target="runtime", animated=True
            ),
            OperatorGraphEdge(
                id="e4", source="runtime", target="embedding", animated=True
            ),
            OperatorGraphEdge(
                id="e5", source="embedding", target="config", animated=True
            ),
            OperatorGraphEdge(
                id="e6", source="config", target="provider", animated=True
            ),
        ]

        for index, service in enumerate(runtime_services):
            node_id = f"runtime-service:{service.id}"
            nodes.append(
                OperatorGraphNode(
                    id=node_id,
                    type="runtime_service",
                    label=service.name,
                    data=service.model_dump(mode="json"),
                    position={
                        "x": 660.0 + (index % 3) * 240.0,
                        "y": 520.0 + (index // 3) * 120.0,
                    },
                )
            )
            edges.append(
                OperatorGraphEdge(
                    id=f"runtime-link:{service.id}",
                    source="runtime",
                    target=node_id,
                    animated=False,
                )
            )

        previous_step_id: str | None = None
        for index, step in enumerate(execution_steps):
            step_node_id = f"step:{step.id}"
            nodes.append(
                OperatorGraphNode(
                    id=step_node_id,
                    type="execution_step",
                    label=f"{step.component}:{step.action}",
                    data=step.model_dump(mode="json"),
                    position={"x": 200.0 + index * 220.0, "y": 760.0},
                )
            )
            if previous_step_id is None:
                edges.append(
                    OperatorGraphEdge(
                        id=f"step-link:start:{index}",
                        source="runtime",
                        target=step_node_id,
                    )
                )
            else:
                edges.append(
                    OperatorGraphEdge(
                        id=f"step-link:{index}",
                        source=previous_step_id,
                        target=step_node_id,
                    )
                )
            previous_step_id = step_node_id

        return OperatorGraph(nodes=nodes, edges=edges)

    def _derive_workflow_status(
        self,
        active_task_status: str | None,
        active_request_id: str | None,
        workflow_service: Any,
    ) -> WorkflowStatus:
        """Derive workflow_status from real trace status, falling back to WF service.

        Args:
            active_task_status: Trace status string (PROCESSING/COMPLETED/FAILED/…)
            active_request_id: Active request UUID string
            workflow_service: WorkflowOperationService instance

        Returns:
            WorkflowStatus reflecting real execution state
        """
        if active_task_status == "PROCESSING" and active_request_id:
            # Use WF service state which may be RUNNING or PAUSED after ops
            return workflow_service.get_workflow_status(active_request_id)
        if active_task_status == "COMPLETED":
            return WorkflowStatus.COMPLETED
        if active_task_status == "FAILED":
            return WorkflowStatus.FAILED
        # Fallback to synthetic WF service status
        return workflow_service.get_latest_workflow_status()

    def _compute_allowed_operations(
        self,
        workflow_status: WorkflowStatus,
        active_request_id: str | None,
    ) -> list[str]:
        """Compute which WF operations are currently permitted.

        Args:
            workflow_status: Resolved workflow status for active request
            active_request_id: Active request UUID string

        Returns:
            List of allowed operation names
        """
        if not active_request_id:
            return []
        if workflow_status == WorkflowStatus.RUNNING:
            return ["pause", "cancel"]
        if workflow_status == WorkflowStatus.PAUSED:
            return ["resume", "cancel"]
        if workflow_status in {WorkflowStatus.FAILED, WorkflowStatus.CANCELLED}:
            return ["retry", "retry_from_step", "replay_step", "skip_step", "dry_run"]
        if workflow_status == WorkflowStatus.COMPLETED:
            return ["retry_from_step", "replay_step", "skip_step", "dry_run"]
        return []

    def _validate_change(self, change: ResourceChange) -> dict[str, Any]:
        """Validate a single resource change.

        Args:
            change: Resource change to validate

        Returns:
            Validation result dict
        """
        # Simple validation - in production this would be more sophisticated
        valid = True
        apply_mode = ApplyMode.HOT_SWAP
        reason_code = ReasonCode.SUCCESS_HOT_SWAP
        message = "Change is valid"
        restart_services: list[str] = []
        affected_services: list[str] = []

        # Check if change requires restart
        if change.resource_type in [ResourceType.KERNEL, ResourceType.RUNTIME]:
            apply_mode = ApplyMode.RESTART_REQUIRED
            reason_code = ReasonCode.SUCCESS_RESTART_PENDING
            restart_services = ["backend"]
            affected_services = ["backend", "ui"]

        return {
            "valid": valid,
            "apply_mode": apply_mode,
            "reason_code": reason_code,
            "message": message,
            "restart_services": restart_services,
            "affected_services": affected_services,
            "timestamp": datetime.now(timezone.utc),
        }

    def _validate_full_stack_compatibility(
        self, current_state: SystemState, changes: list[ResourceChange]
    ) -> tuple[bool, list[str]]:
        """Validate full stack compatibility after applying changes.

        Args:
            current_state: Current system state
            changes: Planned changes

        Returns:
            Tuple of (compatible, list of issues)
        """
        config = config_manager.get_config(mask_secrets=False)

        # Extract values after changes would be applied
        kernel = str(config.get("KERNEL", current_state.kernel))
        runtime = self._resolve_runtime_from_config(config)
        provider = self._resolve_provider_from_config(config)
        model = self._resolve_model_from_config(config, provider)
        embedding_model = str(
            config.get("EMBEDDING_MODEL", current_state.embedding_model)
        )
        intent_mode = str(config.get("INTENT_MODE", current_state.intent_mode))

        # Apply changes to get projected state
        for change in changes:
            if change.resource_type == ResourceType.KERNEL:
                kernel = str(change.new_value)
            elif change.resource_type == ResourceType.RUNTIME:
                runtime = str(change.new_value)
            elif change.resource_type == ResourceType.PROVIDER:
                provider = str(change.new_value)
            elif change.resource_type == ResourceType.EMBEDDING_MODEL:
                embedding_model = str(change.new_value)
            elif change.resource_type == ResourceType.INTENT_MODE:
                intent_mode = str(change.new_value)

        # Validate projected state
        return self._compatibility_validator.validate_full_stack(
            kernel=kernel,
            runtime=runtime,
            provider=provider,
            model=model,
            embedding_model=embedding_model,
            intent_mode=intent_mode,
        )

    def _apply_single_change(
        self,
        requested_change: ResourceChange,
        rollback_snapshot: dict[str, Any],
    ) -> AppliedChange:
        """Apply a single config change and update rollback snapshot."""
        updates = self._resource_change_to_config_updates(requested_change)
        if not updates:
            raise ValueError(
                f"No supported config updates for resource_type={requested_change.resource_type.value}"
            )

        current_config = config_manager.get_config(mask_secrets=False)
        previous_values: dict[str, Any] = {}
        for key in updates:
            previous_values[key] = current_config.get(key, "")

        update_result = config_manager.update_config(updates)
        if not update_result.get("success"):
            raise RuntimeError(
                update_result.get("message", "Unknown config update error")
            )

        for key, value in previous_values.items():
            if key not in rollback_snapshot:
                rollback_snapshot[key] = value

        restart_required = bool(update_result.get("restart_required"))
        apply_mode = (
            ApplyMode.RESTART_REQUIRED if restart_required else ApplyMode.HOT_SWAP
        )
        reason_code = (
            ReasonCode.SUCCESS_RESTART_PENDING
            if restart_required
            else ReasonCode.SUCCESS_HOT_SWAP
        )

        return AppliedChange(
            resource_type=requested_change.resource_type,
            resource_id=requested_change.resource_id,
            action=requested_change.action,
            apply_mode=apply_mode,
            reason_code=reason_code,
            message=update_result.get("message", "Change applied"),
            timestamp=datetime.now(timezone.utc),
        )

    def _rollback_config_changes(
        self,
        rollback_snapshot: dict[str, Any],
        triggered_by: str,
        execution_ticket: str,
    ) -> bool:
        """Best-effort rollback for config changes."""
        if not rollback_snapshot:
            return True
        try:
            rollback_result = config_manager.update_config(rollback_snapshot)
            if rollback_result.get("success"):
                logger.warning(
                    "Rollback succeeded for execution_ticket=%s keys=%s",
                    execution_ticket,
                    list(rollback_snapshot.keys()),
                )
                return True
            logger.error(
                "Rollback failed for execution_ticket=%s: %s",
                execution_ticket,
                rollback_result.get("message"),
            )
            return False
        except Exception as exc:
            logger.exception(
                "Rollback exception for execution_ticket=%s by=%s: %s",
                execution_ticket,
                triggered_by,
                exc,
            )
            return False

    def _resource_change_to_config_updates(
        self, change: ResourceChange
    ) -> dict[str, Any]:
        """Map a workflow resource change to config_manager updates."""
        if change.action != "update":
            raise ValueError(
                f"Unsupported action '{change.action}' for control-plane apply"
            )

        effective_new_value = (
            change.new_value if change.new_value is not None else change.resource_id
        )

        if change.resource_type == ResourceType.CONFIG:
            config_key = change.resource_id
            if (
                not config_key
                and change.entity_id
                and change.entity_id.startswith("config:")
            ):
                config_key = change.entity_id.split(":", 1)[1]
            if not config_key and change.field:
                config_key = change.field
            if not config_key:
                raise ValueError(
                    "CONFIG changes require resource_id or entity_id/field as config key"
                )
            return {config_key: effective_new_value}

        if change.resource_type == ResourceType.WORKFLOW:
            raise ValueError(
                "Workflow resource changes are handled via workflow operations API"
            )

        config_key = self.RESOURCE_CONFIG_KEY_MAP.get(change.resource_type)
        if not config_key:
            raise ValueError(f"Unsupported resource type: {change.resource_type.value}")

        return {config_key: effective_new_value}

    def _resolve_runtime_from_config(self, config: dict[str, Any]) -> str:
        runtime = str(config.get("WORKFLOW_RUNTIME", "")).strip().lower()
        if runtime:
            return runtime

        llm_service_type = str(config.get("LLM_SERVICE_TYPE", "")).strip().lower()
        if llm_service_type in {"hybrid"}:
            return "hybrid"
        if llm_service_type in {"vllm", "docker"}:
            return "docker"
        return "python"

    def _resolve_provider_from_config(self, config: dict[str, Any]) -> str:
        provider = str(config.get("ACTIVE_PROVIDER", "")).strip().lower()
        if provider:
            return provider
        llm_service_type = str(config.get("LLM_SERVICE_TYPE", "")).strip().lower()
        if llm_service_type in {"onnx", "ollama", "vllm"}:
            return llm_service_type
        hybrid_provider = str(config.get("HYBRID_CLOUD_PROVIDER", "")).strip().lower()
        if hybrid_provider:
            return hybrid_provider
        return "ollama"

    def _resolve_model_from_config(self, config: dict[str, Any], provider: str) -> str:
        model = str(config.get("LLM_MODEL_NAME", "")).strip()
        if model:
            return model
        for key in (
            "HYBRID_LOCAL_MODEL",
            "HYBRID_CLOUD_MODEL",
            "LAST_MODEL_OLLAMA",
            "LAST_MODEL_ONNX",
            "ONNX_LLM_MODEL_PATH",
        ):
            val = str(config.get(key, "")).strip()
            if val:
                return val
        fallback_models = self._compatibility_validator.matrix.provider_models.get(
            provider, []
        )
        return fallback_models[0] if fallback_models else "llama2"

    def _classify_provider_source(self, provider: str) -> str:
        normalized = (provider or "").strip().lower()
        return "cloud" if normalized in self.CLOUD_PROVIDERS else "local"

    def _classify_embedding_source(self, embedding_model: str) -> str:
        model_key = (embedding_model or "").strip()
        if not model_key:
            return "local"
        compatibility = (
            self._compatibility_validator.matrix.embedding_compatibility.get(model_key)
        )
        if not compatibility:
            return "local"
        if any(
            self._classify_provider_source(provider) == "cloud"
            for provider in compatibility
        ):
            return "cloud"
        return "local"

    def get_control_options(self) -> dict[str, Any]:
        """Return option catalogs for provider/embedding split into local/cloud."""
        provider_models = self._compatibility_validator.matrix.provider_models
        embedding_compatibility = (
            self._compatibility_validator.matrix.embedding_compatibility
        )
        decision_strategies = ["standard", "advanced", "heuristic"]
        intent_modes = sorted(
            self._compatibility_validator.matrix.intent_mode_requirements.keys()
        )
        kernels = sorted(self._compatibility_validator.matrix.kernel_runtime.keys())

        providers_local: list[str] = []
        providers_cloud: list[str] = []
        for provider in sorted(provider_models.keys()):
            if self._classify_provider_source(provider) == "cloud":
                providers_cloud.append(provider)
            else:
                providers_local.append(provider)

        embeddings_local: list[str] = []
        embeddings_cloud: list[str] = []
        for embedding_model, compatible_providers in sorted(
            embedding_compatibility.items()
        ):
            if any(
                self._classify_provider_source(provider) == "cloud"
                for provider in compatible_providers
            ):
                embeddings_cloud.append(embedding_model)
            else:
                embeddings_local.append(embedding_model)

        state = self.get_system_state()
        active_provider = str((state.provider or {}).get("active", "ollama"))
        active_embedding = str(state.embedding_model or "")

        return {
            "decision_strategies": decision_strategies,
            "intent_modes": intent_modes,
            "kernels": kernels,
            "provider_sources": ["local", "cloud"],
            "embedding_sources": ["local", "cloud"],
            "providers": {
                "local": providers_local,
                "cloud": providers_cloud,
            },
            "embeddings": {
                "local": embeddings_local,
                "cloud": embeddings_cloud,
            },
            "kernel_runtimes": {
                kernel: sorted(compatible_runtimes)
                for kernel, compatible_runtimes in sorted(
                    self._compatibility_validator.matrix.kernel_runtime.items()
                )
            },
            "intent_requirements": {
                intent_mode: dict(requirements)
                for intent_mode, requirements in sorted(
                    self._compatibility_validator.matrix.intent_mode_requirements.items()
                )
            },
            "provider_embeddings": {
                provider: [
                    embedding_model
                    for embedding_model, compatible_providers in sorted(
                        embedding_compatibility.items()
                    )
                    if provider in compatible_providers
                ]
                for provider in sorted(provider_models.keys())
            },
            "embedding_providers": {
                embedding_model: sorted(compatible_providers)
                for embedding_model, compatible_providers in sorted(
                    embedding_compatibility.items()
                )
            },
            "active": {
                "provider_source": self._classify_provider_source(active_provider),
                "embedding_source": self._classify_embedding_source(active_embedding),
            },
        }

    def _calculate_health_status(
        self, runtime_statuses: list[Any], compatible: bool
    ) -> str:
        has_error = False
        for service in runtime_statuses:
            status_obj = getattr(service, "status", None)
            status_value = getattr(status_obj, "value", status_obj)
            if str(status_value).lower() == "error":
                has_error = True
                break
        if has_error:
            return "critical"
        if not compatible:
            return "degraded"
        return "healthy"

    def _begin_operation(self, operation_id: str) -> bool:
        with self._lock:
            if operation_id in self._active_operations:
                return False
            self._active_operations.add(operation_id)
            return True

    def _end_operation(self, operation_id: str) -> None:
        with self._lock:
            self._active_operations.discard(operation_id)

    def _get_active_operations_snapshot(self) -> list[str]:
        with self._lock:
            return sorted(self._active_operations)

    def _estimate_duration(self, changes: list[AppliedChange]) -> float:
        """Estimate duration for applying changes.

        Args:
            changes: List of changes to apply

        Returns:
            Estimated duration in seconds
        """
        # Simple estimation: 1 second per change
        return float(len(changes))

    def _get_current_state(self) -> SystemState:
        """Get current system state.

        Returns:
            Current system state
        """
        return self.get_system_state()


# Singleton instance
_control_plane_service: ControlPlaneService | None = None


def get_control_plane_service() -> ControlPlaneService:
    """Get singleton control plane service instance.

    Returns:
        ControlPlaneService instance
    """
    global _control_plane_service
    if _control_plane_service is None:
        _control_plane_service = ControlPlaneService()
    return _control_plane_service
