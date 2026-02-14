"""Control Plane Service for managing workflow and system configuration.

This service aggregates and coordinates changes across:
- Decision strategy and intent mode
- Kernel and runtime configuration
- Provider and model selection
- Embedding and workflow control
"""

import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from venom_core.api.model_schemas.workflow_control import (
    AppliedChange,
    ApplyMode,
    CompatibilityReport,
    ControlApplyRequest,
    ControlApplyResponse,
    ControlPlanRequest,
    ControlPlanResponse,
    ReasonCode,
    ResourceChange,
    ResourceType,
    SystemState,
)
from venom_core.services.config_manager import config_manager
from venom_core.services.control_plane_audit import get_control_plane_audit_trail
from venom_core.services.control_plane_compatibility import get_compatibility_validator
from venom_core.services.runtime_controller import runtime_controller
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
                logger.error(f"Failed to apply change {change.resource_id}: {e}")
                failed_changes.append(f"{change.resource_id}: {str(e)}")
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
        workflow_status = workflow_service.get_latest_workflow_status()

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
                "available": ["ollama", "huggingface", "openai"],
            },
            embedding_model=embedding_model,
            workflow_status=workflow_status,
            active_operations=self._get_active_operations_snapshot(),
            health={
                "overall": health_overall,
                "checks": health_checks,
                "compatibility_issues": compatibility_issues,
            },
        )

        return state

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
            if not change.resource_id:
                raise ValueError("CONFIG changes require resource_id as config key")
            return {change.resource_id: effective_new_value}

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
        hybrid_provider = str(config.get("HYBRID_CLOUD_PROVIDER", "")).strip().lower()
        if hybrid_provider:
            return hybrid_provider
        return "ollama"

    def _resolve_model_from_config(self, config: dict[str, Any], provider: str) -> str:
        model = str(config.get("LLM_MODEL_NAME", "")).strip()
        if model:
            return model
        for key in ("HYBRID_LOCAL_MODEL", "HYBRID_CLOUD_MODEL", "LAST_MODEL_OLLAMA"):
            val = str(config.get(key, "")).strip()
            if val:
                return val
        fallback_models = self._compatibility_validator.matrix.provider_models.get(
            provider, []
        )
        return fallback_models[0] if fallback_models else "llama2"

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
