"""Edge-case tests for ControlPlaneService helpers and branchy paths."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from types import SimpleNamespace

import pytest

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


def test_plan_and_apply_exception_paths_are_audited(monkeypatch):
    service = ControlPlaneService()
    request = ControlPlanRequest(
        changes=[
            ResourceChange(
                resource_type=ResourceType.CONFIG,
                resource_id="AI_MODE",
                action="update",
            )
        ]
    )
    audit_calls: list[dict[str, object]] = []
    service._audit_trail = SimpleNamespace(
        log_operation=lambda **kwargs: audit_calls.append(kwargs)
    )

    def _raise_plan(_request):
        raise RuntimeError("plan-fail")

    monkeypatch.setattr(service, "_prepare_plan", _raise_plan)
    with pytest.raises(RuntimeError, match="plan-fail"):
        service.plan_changes(request=request, triggered_by="tester")

    assert audit_calls[-1]["operation_type"] == "plan"
    assert audit_calls[-1]["result"] == "failure"

    apply_request = ControlApplyRequest(
        execution_ticket="ticket-1", confirm_restart=True
    )

    def _raise_apply(_request):
        raise RuntimeError("apply-fail")

    monkeypatch.setattr(service, "_get_pending_plan_for_apply", _raise_apply)
    with pytest.raises(RuntimeError, match="apply-fail"):
        service.apply_changes(request=apply_request, triggered_by="tester")

    assert audit_calls[-1]["operation_type"] == "apply"
    assert audit_calls[-1]["result"] == "failure"


def test_prepare_plan_collects_rejections_without_compatibility_call(monkeypatch):
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

    monkeypatch.setattr(
        service,
        "_validate_change",
        lambda _change: {
            "valid": False,
            "apply_mode": ApplyMode.REJECTED,
            "reason_code": ReasonCode.INVALID_CONFIGURATION,
            "message": "invalid-change",
            "restart_services": [],
            "affected_services": [],
            "timestamp": datetime.now(timezone.utc),
        },
    )

    called = {"compat": False}

    def _never_called(*_args, **_kwargs):
        called["compat"] = True
        return True, []

    monkeypatch.setattr(service, "_validate_full_stack_compatibility", _never_called)

    prepared = service._prepare_plan(request)
    assert prepared["overall_compatible"] is False
    assert prepared["rejected_changes"] == ["x: invalid-change"]
    assert prepared["compatibility_issues"] == ["invalid-change"]
    assert called["compat"] is False


def test_validate_full_stack_and_mapping_helpers_cover_branches(monkeypatch):
    import venom_core.services.control_plane as control_plane_module

    service = ControlPlaneService()
    service._compatibility_validator = SimpleNamespace(
        matrix=SimpleNamespace(
            provider_models={"openai": ["gpt-4o"]},
            embedding_compatibility={
                "text-embedding-3-small": ["openai"],
                "sentence-transformers": ["ollama"],
            },
        ),
        validate_full_stack=lambda **kwargs: (
            True,
            [kwargs["runtime"], kwargs["provider"]],
        ),
    )
    monkeypatch.setattr(
        control_plane_module,
        "config_manager",
        SimpleNamespace(
            get_config=lambda mask_secrets=False: {
                "KERNEL": "standard",
                "WORKFLOW_RUNTIME": "python",
                "ACTIVE_PROVIDER": "ollama",
                "LLM_MODEL_NAME": "",
                "EMBEDDING_MODEL": "sentence-transformers",
                "INTENT_MODE": "simple",
                "HYBRID_LOCAL_MODEL": "",
                "HYBRID_CLOUD_MODEL": "",
                "LAST_MODEL_OLLAMA": "",
            }
        ),
    )

    current_state = SimpleNamespace(
        kernel="standard",
        embedding_model="sentence-transformers",
        intent_mode="simple",
    )
    compatible, issues = service._validate_full_stack_compatibility(
        current_state=current_state,
        changes=[
            ResourceChange(
                resource_type=ResourceType.RUNTIME,
                resource_id="runtime",
                action="update",
                new_value="hybrid",
            ),
            ResourceChange(
                resource_type=ResourceType.PROVIDER,
                resource_id="provider",
                action="update",
                new_value="openai",
            ),
            ResourceChange(
                resource_type=ResourceType.EMBEDDING_MODEL,
                resource_id="embedding",
                action="update",
                new_value="text-embedding-3-small",
            ),
            ResourceChange(
                resource_type=ResourceType.INTENT_MODE,
                resource_id="intent",
                action="update",
                new_value="semantic",
            ),
        ],
    )
    assert compatible is True
    assert issues == ["hybrid", "openai"]

    assert (
        service._resolve_runtime_from_config({"WORKFLOW_RUNTIME": "docker"}) == "docker"
    )
    assert (
        service._resolve_runtime_from_config({"LLM_SERVICE_TYPE": "hybrid"}) == "hybrid"
    )
    assert (
        service._resolve_runtime_from_config({"LLM_SERVICE_TYPE": "vllm"}) == "docker"
    )
    assert service._resolve_runtime_from_config({}) == "python"

    assert (
        service._resolve_provider_from_config({"ACTIVE_PROVIDER": "openai"}) == "openai"
    )
    assert (
        service._resolve_provider_from_config({"HYBRID_CLOUD_PROVIDER": "google"})
        == "google"
    )
    assert service._resolve_provider_from_config({}) == "ollama"

    assert (
        service._resolve_model_from_config({"LLM_MODEL_NAME": "model-x"}, "openai")
        == "model-x"
    )
    assert (
        service._resolve_model_from_config({"HYBRID_LOCAL_MODEL": "llama3"}, "openai")
        == "llama3"
    )
    assert service._resolve_model_from_config({}, "openai") == "gpt-4o"
    service._compatibility_validator.matrix.provider_models = {}
    assert service._resolve_model_from_config({}, "unknown") == "llama2"

    assert service._classify_embedding_source("") == "local"
    assert service._classify_embedding_source("missing") == "local"
    assert service._classify_embedding_source("text-embedding-3-small") == "cloud"
    assert service._classify_embedding_source("sentence-transformers") == "local"


def test_apply_single_change_rollback_and_health_branches(monkeypatch):
    import venom_core.services.control_plane as control_plane_module

    service = ControlPlaneService()

    requested = ResourceChange(
        resource_type=ResourceType.CONFIG,
        resource_id="AI_MODE",
        action="update",
        new_value="expert",
    )

    original_mapper = service._resource_change_to_config_updates
    monkeypatch.setattr(service, "_resource_change_to_config_updates", lambda _c: {})
    with pytest.raises(ValueError, match="No supported config updates"):
        service._apply_single_change(requested_change=requested, rollback_snapshot={})
    monkeypatch.setattr(service, "_resource_change_to_config_updates", original_mapper)

    monkeypatch.setattr(
        control_plane_module,
        "config_manager",
        SimpleNamespace(
            get_config=lambda mask_secrets=False: {"AI_MODE": "standard"},
            update_config=lambda updates: {
                "success": True,
                "message": "ok",
                "restart_required": ["backend"],
            },
        ),
    )
    applied = service._apply_single_change(
        requested_change=requested,
        rollback_snapshot={},
    )
    assert applied.apply_mode == ApplyMode.RESTART_REQUIRED

    assert service._rollback_config_changes({}, "tester", "ticket") is True

    monkeypatch.setattr(
        control_plane_module,
        "config_manager",
        SimpleNamespace(
            update_config=lambda updates: {"success": False, "message": "nope"}
        ),
    )
    assert (
        service._rollback_config_changes({"AI_MODE": "standard"}, "tester", "ticket")
        is False
    )

    def _raise_update(_updates):
        raise RuntimeError("rollback-error")

    monkeypatch.setattr(
        control_plane_module,
        "config_manager",
        SimpleNamespace(update_config=_raise_update),
    )
    assert (
        service._rollback_config_changes({"AI_MODE": "standard"}, "tester", "ticket")
        is False
    )

    assert (
        service._calculate_health_status(
            [SimpleNamespace(status=SimpleNamespace(value="error"))], compatible=True
        )
        == "critical"
    )
    assert (
        service._calculate_health_status(
            [SimpleNamespace(status=SimpleNamespace(value="ok"))], compatible=False
        )
        == "degraded"
    )
    assert (
        service._calculate_health_status(
            [SimpleNamespace(status=SimpleNamespace(value="ok"))], compatible=True
        )
        == "healthy"
    )

    assert service._begin_operation("op-1") is True
    assert service._begin_operation("op-1") is False
    assert service._get_active_operations_snapshot() == ["op-1"]
    service._end_operation("op-1")


def test_resource_change_to_config_updates_validation_errors():
    service = ControlPlaneService()

    with pytest.raises(ValueError, match="Unsupported action"):
        service._resource_change_to_config_updates(
            ResourceChange(
                resource_type=ResourceType.CONFIG,
                resource_id="AI_MODE",
                action="delete",
            )
        )

    with pytest.raises(ValueError, match="require resource_id"):
        service._resource_change_to_config_updates(
            ResourceChange(
                resource_type=ResourceType.CONFIG,
                resource_id="",
                action="update",
            )
        )

    with pytest.raises(ValueError, match="workflow operations API"):
        service._resource_change_to_config_updates(
            ResourceChange(
                resource_type=ResourceType.WORKFLOW,
                resource_id="wf",
                action="update",
            )
        )

    class _UnsupportedResourceType(Enum):
        UNSUPPORTED = "unsupported"

    unsupported_change = SimpleNamespace(
        action="update",
        new_value="x",
        resource_id="r",
        resource_type=_UnsupportedResourceType.UNSUPPORTED,
    )
    with pytest.raises(ValueError, match="Unsupported resource type"):
        service._resource_change_to_config_updates(unsupported_change)
