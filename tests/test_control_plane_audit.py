from __future__ import annotations

from venom_core.api.model_schemas.workflow_control import ReasonCode, ResourceType
from venom_core.services.control_plane_audit import ControlPlaneAuditTrail


def test_log_operation_and_lookup_filters():
    trail = ControlPlaneAuditTrail(max_entries=10)

    op1 = trail.log_operation(
        triggered_by="alice",
        operation_type="plan",
        resource_type=ResourceType.CONFIG,
        resource_id="system",
        params={"changes": 1},
        result="success",
        reason_code=ReasonCode.SUCCESS_HOT_SWAP,
        duration_ms=12.5,
    )
    op2 = trail.log_operation(
        triggered_by="bob",
        operation_type="apply",
        resource_type=ResourceType.RUNTIME,
        resource_id="backend",
        params={"ticket": "t1"},
        result="failure",
        reason_code=ReasonCode.OPERATION_FAILED,
        error_message="boom",
    )

    assert op1 != op2
    assert trail.get_operation(op1) is not None
    assert trail.get_operation("missing") is None

    by_type = trail.get_entries(operation_type="apply")
    assert len(by_type) == 1
    assert by_type[0].operation_id == op2

    by_user = trail.get_entries(triggered_by="alice")
    assert len(by_user) == 1
    assert by_user[0].operation_id == op1

    failures = trail.get_recent_failures(limit=5)
    assert len(failures) == 1
    assert failures[0].result == "failure"
    assert failures[0].operation_id == op2


def test_max_entries_and_clear_old_entries_keeps_recent():
    trail = ControlPlaneAuditTrail(max_entries=2)

    trail.log_operation(
        triggered_by="u1",
        operation_type="plan",
        resource_type=ResourceType.CONFIG,
        resource_id="s1",
        params={},
        result="success",
        reason_code=ReasonCode.SUCCESS_HOT_SWAP,
    )
    trail.log_operation(
        triggered_by="u2",
        operation_type="apply",
        resource_type=ResourceType.KERNEL,
        resource_id="s2",
        params={},
        result="failure",
        reason_code=ReasonCode.OPERATION_FAILED,
    )
    trail.log_operation(
        triggered_by="u3",
        operation_type="apply",
        resource_type=ResourceType.PROVIDER,
        resource_id="s3",
        params={},
        result="success",
        reason_code=ReasonCode.SUCCESS_HOT_SWAP,
    )

    # max_entries=2: first entry should be dropped
    entries = trail.get_entries(limit=10)
    assert len(entries) == 2
    ids = {entry.resource_id for entry in entries}
    assert ids == {"s2", "s3"}

    # Fresh entries are within retention window, nothing should be removed.
    trail.clear_old_entries(days=30)
    assert len(trail.get_entries(limit=10)) == 2
