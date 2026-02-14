"""Control Plane Service for managing workflow and system configuration.

This service aggregates and coordinates changes across:
- Decision strategy and intent mode
- Kernel and runtime configuration
- Provider and model selection
- Embedding and workflow control
"""

import time
import uuid
from typing import Any, Optional

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
    WorkflowStatus,
)
from venom_core.services.config_manager import config_manager
from venom_core.services.control_plane_audit import get_control_plane_audit_trail
from venom_core.services.control_plane_compatibility import (
    get_compatibility_validator,
)
from venom_core.services.runtime_controller import runtime_controller
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class ControlPlaneService:
    """Service for planning and applying system-wide configuration changes."""

    def __init__(self):
        """Initialize control plane service."""
        self._pending_plans: dict[str, ControlPlanResponse] = {}
        self._compatibility_validator = get_compatibility_validator()
        self._audit_trail = get_control_plane_audit_trail()

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

        try:
            # Validate and categorize changes
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
                    applied_change = AppliedChange(
                        resource_type=change.resource_type,
                        resource_id=change.resource_id,
                        action=change.action,
                        apply_mode=result["apply_mode"],
                        reason_code=result["reason_code"],
                        message=result["message"],
                        timestamp=result["timestamp"],
                    )
                    planned_changes.append(applied_change)

                    if result["apply_mode"] == ApplyMode.HOT_SWAP:
                        hot_swap_changes.append(change.resource_id)
                    elif result["apply_mode"] == ApplyMode.RESTART_REQUIRED:
                        restart_required_services.extend(result["restart_services"])

                    affected_services.update(result.get("affected_services", []))
                else:
                    rejected_changes.append(
                        f"{change.resource_id}: {result['message']}"
                    )
                    compatibility_issues.append(result["message"])

            # Check overall compatibility
            overall_compatible = len(rejected_changes) == 0

            if overall_compatible and not request.dry_run:
                # Perform full stack validation
                current_state = self._get_current_state()
                compatible, issues = self._validate_full_stack_compatibility(
                    current_state, request.changes
                )

                if not compatible:
                    overall_compatible = False
                    compatibility_issues.extend(issues)

            compatibility_report = CompatibilityReport(
                compatible=overall_compatible,
                issues=compatibility_issues,
                warnings=compatibility_warnings,
                affected_services=list(affected_services),
            )

            reason_code = (
                ReasonCode.SUCCESS_HOT_SWAP
                if overall_compatible and len(restart_required_services) == 0
                else ReasonCode.SUCCESS_RESTART_PENDING
                if overall_compatible
                else ReasonCode.INVALID_CONFIGURATION
            )

            response = ControlPlanResponse(
                execution_ticket=execution_ticket,
                valid=overall_compatible,
                reason_code=reason_code,
                compatibility_report=compatibility_report,
                planned_changes=planned_changes,
                hot_swap_changes=hot_swap_changes,
                restart_required_services=list(set(restart_required_services)),
                rejected_changes=rejected_changes,
                estimated_duration_seconds=self._estimate_duration(planned_changes),
            )

            # Store plan for later apply
            if not request.dry_run:
                self._pending_plans[execution_ticket] = response

            # Log to audit trail
            duration_ms = (time.time() - start_time) * 1000
            self._audit_trail.log_operation(
                triggered_by=triggered_by,
                operation_type="plan",
                resource_type=ResourceType.CONFIG,
                resource_id="system",
                params={"changes_count": len(request.changes), "dry_run": request.dry_run},
                result="success" if overall_compatible else "rejected",
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

        try:
            # Retrieve the plan
            plan = self._pending_plans.get(request.execution_ticket)
            if not plan:
                return ControlApplyResponse(
                    execution_ticket=request.execution_ticket,
                    apply_mode=ApplyMode.REJECTED,
                    reason_code=ReasonCode.INVALID_CONFIGURATION,
                    message="Invalid or expired execution ticket",
                    applied_changes=[],
                    pending_restart=[],
                    failed_changes=["Invalid execution ticket"],
                )

            if not plan.valid:
                return ControlApplyResponse(
                    execution_ticket=request.execution_ticket,
                    apply_mode=ApplyMode.REJECTED,
                    reason_code=ReasonCode.INVALID_CONFIGURATION,
                    message="Cannot apply invalid plan",
                    applied_changes=[],
                    pending_restart=[],
                    failed_changes=["Plan validation failed"],
                )

            # Check restart confirmation
            if plan.restart_required_services and not request.confirm_restart:
                return ControlApplyResponse(
                    execution_ticket=request.execution_ticket,
                    apply_mode=ApplyMode.RESTART_REQUIRED,
                    reason_code=ReasonCode.SUCCESS_RESTART_PENDING,
                    message="Restart required but not confirmed",
                    applied_changes=[],
                    pending_restart=plan.restart_required_services,
                    failed_changes=[],
                )

            # Apply changes
            applied_changes: list[AppliedChange] = []
            failed_changes: list[str] = []

            for change in plan.planned_changes:
                try:
                    self._apply_single_change(change)
                    applied_changes.append(change)
                except Exception as e:
                    logger.error(
                        f"Failed to apply change {change.resource_id}: {e}"
                    )
                    failed_changes.append(f"{change.resource_id}: {str(e)}")

            # Determine overall apply mode
            if len(failed_changes) > 0:
                apply_mode = ApplyMode.REJECTED
                reason_code = ReasonCode.OPERATION_FAILED
                message = f"Applied {len(applied_changes)}/{len(plan.planned_changes)} changes"
            elif len(plan.restart_required_services) > 0:
                apply_mode = ApplyMode.RESTART_REQUIRED
                reason_code = ReasonCode.SUCCESS_RESTART_PENDING
                message = "Changes applied, restart required"
            else:
                apply_mode = ApplyMode.HOT_SWAP
                reason_code = ReasonCode.SUCCESS_HOT_SWAP
                message = "All changes applied successfully"

            response = ControlApplyResponse(
                execution_ticket=request.execution_ticket,
                apply_mode=apply_mode,
                reason_code=reason_code,
                message=message,
                applied_changes=applied_changes,
                pending_restart=plan.restart_required_services,
                failed_changes=failed_changes,
                rollback_available=len(applied_changes) > 0,
            )

            # Clean up pending plan
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
                result="success" if len(failed_changes) == 0 else "partial",
                reason_code=reason_code,
                duration_ms=duration_ms,
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

    def get_system_state(self) -> SystemState:
        """Get current state of the entire system.

        Returns:
            Current system state
        """
        from datetime import datetime, timezone

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

        # Build state
        state = SystemState(
            timestamp=datetime.now(timezone.utc),
            decision_strategy=config.get("AI_MODE", "standard"),
            intent_mode=config.get("INTENT_MODE", "simple"),
            kernel=config.get("KERNEL", "standard"),
            runtime=runtime_dict,
            provider={
                "active": config.get("ACTIVE_PROVIDER", "ollama"),
                "available": ["ollama", "huggingface", "openai"],
            },
            embedding_model=config.get("EMBEDDING_MODEL", "sentence-transformers"),
            workflow_status=WorkflowStatus.IDLE,
            active_operations=[],
            health={"overall": "healthy", "checks": []},
        )

        return state

    def _validate_change(self, change: ResourceChange) -> dict[str, Any]:
        """Validate a single resource change.

        Args:
            change: Resource change to validate

        Returns:
            Validation result dict
        """
        from datetime import datetime, timezone

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
        # Extract values after changes would be applied
        kernel = current_state.kernel
        runtime = "python"  # Default
        provider = current_state.provider.get("active", "ollama")
        model = "llama2"  # Default
        embedding_model = current_state.embedding_model
        intent_mode = current_state.intent_mode

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

    def _apply_single_change(self, change: AppliedChange) -> None:
        """Apply a single change to the system.

        Args:
            change: Change to apply
        """
        logger.info(
            f"Applying change: {change.resource_type.value} - {change.resource_id}"
        )
        # In production, this would actually apply the change
        # For now, just log it
        pass

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
