"""Manual lifecycle acceptance and confirmed account-empty cleanup; no auto rentals."""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from contextlib import contextmanager
from typing import Any, cast

from venom_core.infrastructure.providers.vast.client import VastError
from venom_core.infrastructure.providers.vast.models import EnvironmentRecord, now
from venom_core.services.vast_environments.lifecycle import Environments
from venom_core.services.vast_environments.operations import workload


class ZeroCheckError(VastError):
    def __init__(self, code: str, report: dict[str, Any]):
        super().__init__(code)
        self.report = report


def _timeout(seconds: int) -> None:
    if not 1 <= seconds <= 600:
        raise VastError("vast.invalid_timeout")


def _inventory(service: Environments) -> list[int]:
    # VastClient.instances consumes all pages or raises; never substitute [] on error.
    rows = service.client.instances()
    if not isinstance(rows, list):
        raise VastError("vast.invalid_inventory")
    identifiers = [row.get("id") if isinstance(row, dict) else None for row in rows]
    if any(type(value) is not int or value <= 0 for value in identifiers):
        raise VastError("vast.invalid_inventory")
    if len(set(identifiers)) != len(identifiers):
        raise VastError("vast.invalid_inventory")
    return cast(list[int], identifiers)


def _save(service: Environments, plan_id: str, report: dict[str, Any]) -> None:
    report["checked_at"] = now().isoformat()
    service.journal.write(service.journal.path(plan_id, ".zero.json"), report)


def verify_zero(service: Environments) -> dict[str, Any]:
    result: dict[str, Any] = {
        "operation": "verify_zero",
        "checked_at": now().isoformat(),
        "instance_count": None,
        "instance_ids": None,
        "zero_confirmed": False,
    }
    try:
        identifiers = _inventory(service)
        result.update(
            instance_count=len(identifiers),
            instance_ids=identifiers,
            zero_confirmed=not identifiers,
        )
    except VastError as error:
        result["error"] = error.code
        raise ZeroCheckError(error.code, result) from None
    if identifiers:
        raise ZeroCheckError("vast.account_not_empty", result)
    return result


def _poll_cleanup(
    service: Environments,
    plan_id: str,
    report: dict[str, Any],
    timeout: int,
    sleep: Callable[[float], None],
    clock: Callable[[], float],
) -> None:
    deadline = clock() + timeout
    while True:
        report.update(instance_count=None, instance_ids=None, zero_confirmed=False)
        try:
            record = service.journal.record(plan_id)
            if record.state != "destroyed":
                record = service.reconcile(plan_id)
            report["instance_deleted"] = record.state == "destroyed"
            identifiers = _inventory(service)
            report.update(instance_count=len(identifiers), instance_ids=identifiers)
            report.pop("observation_error", None)
            if report["instance_deleted"] and not identifiers:
                report["zero_confirmed"] = True
                return
            if report["instance_deleted"] and record.instance_id not in identifiers:
                # Other resources must not be destroyed to satisfy a zero assertion.
                report["error"] = "vast.account_not_empty"
                return
        except VastError as error:
            report["observation_error"] = error.code
            if error.status in {401, 403}:
                return
        if clock() >= deadline:
            report["error"] = "vast.cleanup_unconfirmed"
            return
        sleep(min(2.0, max(0.0, deadline - clock())))


def _assert_owned_instance(
    service: Environments, plan_id: str, record: EnvironmentRecord
) -> None:
    """Only the exact provider-observed resource created for this plan is deletable."""
    plan = service.journal.plan(plan_id)
    observed = record.instance
    if (
        type(record.instance_id) is not int
        or record.instance_id <= 0
        or not isinstance(observed, dict)
        or observed.get("id") != record.instance_id
        or type(observed.get("id")) is not int
        or observed.get("label") != "venom-" + plan_id
    ):
        raise VastError("vast.cleanup_instance_mismatch")
    for key in ("host_id", "machine_id"):
        expected, actual = plan.assessment.offer.get(key), observed.get(key)
        if (
            type(expected) is not int
            or expected <= 0
            or type(actual) is not int
            or actual <= 0
            or actual != expected
        ):
            raise VastError("vast.cleanup_instance_mismatch")


def _cleanup_zero(
    service: Environments,
    plan_id: str,
    timeout: int = 120,
    *,
    before_destroy: Callable[[str], None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    _timeout(timeout)
    service.journal.plan(plan_id)
    record = service.journal.record(plan_id)
    report: dict[str, Any] = {
        "operation": "cleanup_zero",
        "plan_id": plan_id,
        "instance_id": record.instance_id,
        "instance_deleted": False,
        "instance_count": None,
        "instance_ids": None,
        "zero_confirmed": False,
    }
    _save(service, plan_id, report)
    try:
        if before_destroy is not None:
            before_destroy(plan_id)
        if record.state != "destroyed":
            record = service.reconcile(plan_id)
        report["instance_id"] = record.instance_id
        if record.instance_id is None:
            raise VastError("vast.cleanup_instance_unknown")
        if record.state != "destroyed":
            _assert_owned_instance(service, plan_id, record)
        service.export(plan_id)
        # Never replay a destroy request whose outcome is not known.
        if record.state != "destroyed" and record.pending_action != "destroy":
            try:
                service.change(plan_id, "destroy")
            except VastError as error:
                if not error.ambiguous:
                    raise
                report["destroy_outcome"] = "unknown"
        _poll_cleanup(service, plan_id, report, timeout, sleep, clock)
    except (VastError, OSError) as error:
        report["error"] = (
            error.code if isinstance(error, VastError) else "vast.cleanup_io_error"
        )
    _save(service, plan_id, report)
    if not report["zero_confirmed"]:
        raise ZeroCheckError(report.get("error", "vast.cleanup_unconfirmed"), report)
    return report


def _trial_zero(
    service: Environments,
    plan_id: str,
    timeout: int = 120,
    *,
    accept_new_host_key: bool = False,
    before_destroy: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Explicit paid command: one create, SSH inspection, then confirmed deletion."""
    _timeout(timeout)
    plan = service.journal.plan(plan_id)
    if plan.profile.mode != "inspect":
        raise VastError("vast.trial_inspect_profile_required")
    if service.journal.record(plan_id).state != "planned":
        raise VastError("vast.reconcile_required")
    report: dict[str, Any] = {
        "operation": "trial_zero",
        "plan_id": plan_id,
        "baseline_instance_ids": None,
        "ssh": "not_tested",
        "success": False,
    }
    try:
        baseline = _inventory(service)
        report["baseline_instance_ids"] = baseline
        if baseline:
            raise VastError("vast.account_not_empty")
    except VastError as error:
        report["error"] = error.code
        _save(service, plan_id, report)
        raise ZeroCheckError(error.code, report) from None
    _save(service, plan_id, report)
    submitted = False
    try:
        submitted = True
        created = service.create(
            plan_id
        )  # Exactly once; ambiguous outcomes are not retried.
        report["instance_id"] = created.instance_id
        record = service.wait(plan_id, timeout)
        if record.state != "running":
            raise VastError("vast.trial_host_not_running")
        inspected = workload(service, plan_id, "inspect", accept_new_host_key)
        report.update(
            ssh=inspected.get("ssh", "unknown"),
            capacity_reasons=inspected.get("reasons", []),
        )
        if report["ssh"] != "ready" or inspected.get("reasons"):
            raise VastError("vast.trial_inspection_failed")
    except KeyboardInterrupt:
        report["error"] = "vast.trial_interrupted"
    except (VastError, OSError) as error:
        report["error"] = (
            error.code if isinstance(error, VastError) else "vast.trial_io_error"
        )
    finally:
        if submitted:
            try:
                report["cleanup"] = _cleanup_zero(
                    service, plan_id, timeout, before_destroy=before_destroy
                )
            except ZeroCheckError as error:
                report["cleanup"] = error.report
        report["success"] = (
            "error" not in report
            and report.get("cleanup", {}).get("zero_confirmed") is True
        )
        _save(service, plan_id, report)
    if not report["success"]:
        raise ZeroCheckError(report.get("error", "vast.cleanup_unconfirmed"), report)
    return report


@contextmanager
def _workflow(service: Environments, plan_id: str):
    import fcntl

    target = service.journal.path(plan_id, ".zero.lock")
    descriptor = os.open(target, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise VastError("vast.plan_busy") from None
        yield
    finally:
        os.close(descriptor)


def cleanup_zero(
    service: Environments,
    plan_id: str,
    timeout: int = 120,
    *,
    before_destroy: Callable[[str], None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    _timeout(timeout)
    with _workflow(service, plan_id):
        return _cleanup_zero(
            service,
            plan_id,
            timeout,
            before_destroy=before_destroy,
            sleep=sleep,
            clock=clock,
        )


def trial_zero(
    service: Environments,
    plan_id: str,
    timeout: int = 120,
    *,
    accept_new_host_key: bool = False,
    before_destroy: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    _timeout(timeout)
    with _workflow(service, plan_id):
        return _trial_zero(
            service,
            plan_id,
            timeout,
            accept_new_host_key=accept_new_host_key,
            before_destroy=before_destroy,
        )
