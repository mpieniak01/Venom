"""Edge-case tests for ControlPlaneService helpers and branchy paths."""

from __future__ import annotations

from datetime import datetime, timezone

from venom_core.api.model_schemas.workflow_control import (
    AppliedChange,
    ApplyMode,
    CompatibilityReport,
    ControlApplyRequest,
    ControlPlanRequest,
    ControlPlanResponse,
    ReasonCode,
    ResourceChange,
    ResourceType,
)
from venom_core.services.control_plane import ControlPlaneService


def _make_applied_change(resource_id: str = "r1") -> AppliedChange:
    return AppliedChange(
        resource_type=ResourceType.CONFIG,
        resource_id=resource_id,
        action="update",
        apply_mode=ApplyMode.HOT_SWAP,
        reason_code=ReasonCode.SUCCESS_HOT_SWAP,
        message="ok",
        timestamp=datetime.now(timezone.utc),
    )


def _make_plan(
    *,
    valid: bool = True,
    restart_required_services: list[str] | None = None,
    planned_count: int = 1,
) -> ControlPlanResponse:
    return ControlPlanResponse(
        execution_ticket="ticket-1",
        valid=valid,
        reason_code=ReasonCode.SUCCESS_HOT_SWAP,
        compatibility_report=CompatibilityReport(
            compatible=valid, issues=[], warnings=[]
        ),
        planned_changes=[_make_applied_change(f"id-{i}") for i in range(planned_count)],
        hot_swap_changes=[],
        restart_required_services=restart_required_services or [],
        rejected_changes=[],
        estimated_duration_seconds=1.0,
    )


def test_plan_changes_returns_in_progress_when_operation_locked(monkeypatch):
    service = ControlPlaneService()
    request = ControlPlanRequest(
        changes=[
            ResourceChange(
                resource_type=ResourceType.CONFIG,
                resource_id="x",
                action="update",
            )
        ]
    )

    monkeypatch.setattr(service, "_begin_operation", lambda *_args, **_kwargs: False)

    response = service.plan_changes(request=request, triggered_by="tester")

    assert response.reason_code == ReasonCode.OPERATION_IN_PROGRESS
    assert response.valid is False
    assert "Operation already in progress" in response.rejected_changes[0]


def test_apply_changes_returns_restart_required_when_not_confirmed():
    service = ControlPlaneService()
    plan = _make_plan(restart_required_services=["runtime"], planned_count=1)
    plan_request = ControlPlanRequest(
        changes=[
            ResourceChange(
                resource_type=ResourceType.RUNTIME,
                resource_id="runtime",
                action="restart",
            )
        ]
    )
    service._pending_plans["ticket-1"] = {
        "response": plan,
        "request": plan_request,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    response = service.apply_changes(
        request=ControlApplyRequest(execution_ticket="ticket-1", confirm_restart=False),
        triggered_by="tester",
    )

    assert response.apply_mode == ApplyMode.RESTART_REQUIRED
    assert response.reason_code == ReasonCode.SUCCESS_RESTART_PENDING
    assert response.pending_restart == ["runtime"]


def test_apply_plan_changes_rolls_back_on_partial_failure(monkeypatch):
    service = ControlPlaneService()
    change_ok = ResourceChange(
        resource_type=ResourceType.CONFIG, resource_id="ok", action="update"
    )
    change_fail = ResourceChange(
        resource_type=ResourceType.CONFIG, resource_id="fail", action="update"
    )
    plan_request = ControlPlanRequest(changes=[change_ok, change_fail])

    def fake_apply_single_change(*, requested_change, rollback_snapshot):
        if requested_change.resource_id == "fail":
            raise RuntimeError("boom")
        rollback_snapshot["AI_MODE"] = "standard"
        return _make_applied_change(requested_change.resource_id)

    monkeypatch.setattr(service, "_apply_single_change", fake_apply_single_change)
    monkeypatch.setattr(service, "_rollback_config_changes", lambda **_kwargs: True)

    result = service._apply_plan_changes(
        plan_request=plan_request,
        triggered_by="tester",
        execution_ticket="ticket-1",
    )

    assert len(result["applied_changes"]) == 1
    assert result["rollback_attempted"] is True
    assert result["rollback_success"] is True
    assert any("Rollback completed" in item for item in result["failed_changes"])


def test_build_apply_response_covers_all_modes():
    service = ControlPlaneService()
    plan_restart = _make_plan(restart_required_services=["runtime"], planned_count=1)
    plan_hot = _make_plan(restart_required_services=[], planned_count=1)

    failed_response = service._build_apply_response(
        execution_ticket="t1",
        plan=plan_hot,
        applied_changes=[],
        failed_changes=["x"],
        rollback_attempted=False,
        rollback_snapshot={},
    )
    restart_response = service._build_apply_response(
        execution_ticket="t2",
        plan=plan_restart,
        applied_changes=plan_restart.planned_changes,
        failed_changes=[],
        rollback_attempted=False,
        rollback_snapshot={},
    )
    hot_response = service._build_apply_response(
        execution_ticket="t3",
        plan=plan_hot,
        applied_changes=plan_hot.planned_changes,
        failed_changes=[],
        rollback_attempted=False,
        rollback_snapshot={},
    )

    assert failed_response.apply_mode == ApplyMode.REJECTED
    assert restart_response.apply_mode == ApplyMode.RESTART_REQUIRED
    assert hot_response.apply_mode == ApplyMode.HOT_SWAP


def test_get_pending_plan_for_apply_handles_missing_and_invalid_plan():
    service = ControlPlaneService()

    missing = service._get_pending_plan_for_apply(
        ControlApplyRequest(execution_ticket="missing", confirm_restart=False)
    )
    assert missing[2] is not None
    assert missing[2].message == "Invalid or expired execution ticket"

    service._pending_plans["invalid"] = {
        "response": _make_plan(valid=False, planned_count=0),
        "request": ControlPlanRequest(changes=[]),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    invalid = service._get_pending_plan_for_apply(
        ControlApplyRequest(execution_ticket="invalid", confirm_restart=False)
    )
    assert invalid[2] is not None
    assert invalid[2].message == "Cannot apply invalid plan"


def test_check_restart_confirmation_none_when_confirmed():
    service = ControlPlaneService()
    plan = _make_plan(restart_required_services=["runtime"])

    assert (
        service._check_restart_confirmation(
            plan=plan,
            request=ControlApplyRequest(execution_ticket="t", confirm_restart=True),
        )
        is None
    )
