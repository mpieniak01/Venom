"""Workload operations shared by CLI and future API endpoints."""

from __future__ import annotations

import subprocess
import time

import httpx

from venom_core.infrastructure.providers.vast.client import VastError
from venom_core.infrastructure.providers.vast.models import now
from venom_core.services.vast_environments.evaluation import OllamaProbe
from venom_core.services.vast_environments.lifecycle import Environments
from venom_core.services.vast_environments.openai_probe import ready as openai_ready
from venom_core.services.vast_environments.recipes import validate_recipe
from venom_core.services.vast_environments.ssh import inspect, ssh_args, tunnel
from venom_core.services.vast_environments.startup import startup


def _provision(plan, instance: dict, accept_new: bool) -> dict:
    process = subprocess.run(
        ssh_args(plan, instance, accept_new) + ["bash", "-s"],
        input=startup(plan.profile),
        text=True,
        capture_output=True,
        timeout=600,
        check=False,
    )
    if process.returncode:
        raise VastError("vast.provision_failed")
    return {"startup": "completed", "readiness": "unknown"}


def _model_operation(plan, instance: dict, operation: str) -> dict:
    if plan.profile.mode == "vllm" and operation == "benchmark":
        raise VastError("vast.vllm_benchmark_not_supported")
    if plan.profile.mode not in {"ollama", "vllm"}:
        raise VastError("vast.ollama_profile_required")
    inspection = inspect(plan, instance)
    if inspection["reasons"]:
        raise VastError("vast.capacity_mismatch")
    with (
        tunnel(plan, instance) as endpoint,
        httpx.Client(
            base_url=endpoint, timeout=30, trust_env=False, follow_redirects=False
        ) as client,
    ):
        if plan.profile.mode == "vllm":
            result = openai_ready(client, plan.profile)
        else:
            probe = OllamaProbe(client, plan.profile)
            result = probe.ready() if operation == "ready" else probe.benchmark()
    result["inspection"] = inspection
    if (
        operation == "benchmark"
        and inspection["unknown"]
        and result["status"] == "suitable"
    ):
        result["status"] = "inconclusive"
    return result


def _perform(plan, instance: dict, operation: str, accept_new: bool) -> dict:
    if operation == "inspect":
        return inspect(plan, instance, accept_new)
    if operation == "provision":
        return _provision(plan, instance, accept_new)
    if operation in {"ready", "benchmark"}:
        return _model_operation(plan, instance, operation)
    raise VastError("vast.invalid_action")


def _save_failure(
    service: Environments, plan_id: str, operation: str, code: str
) -> None:
    with service.journal.lock(plan_id):
        failed = service.journal.record(plan_id)
        failed.reports[operation] = {
            "status": "error",
            "error": code,
            "observed_at": now().isoformat(),
        }
        if operation in {"ready", "benchmark"}:
            failed.runtime_state = "error"
        if code.startswith(("vast.ssh", "vast.tunnel")):
            failed.ssh_state = "unknown"
        service.journal.save_record(failed)


def _save_result(
    service: Environments, plan_id: str, operation: str, result: dict
) -> None:
    with service.journal.lock(plan_id):
        fresh = service.journal.record(plan_id)
        fresh.reports[operation] = result
        fresh.ssh_state = "ready"
        if operation == "ready":
            fresh.runtime_state = "ready"
        fresh.observed_at = now()
        service.journal.save_record(fresh)


def workload(
    service: Environments, plan_id: str, operation: str, accept_new: bool = False
) -> dict:
    plan = service.journal.plan(plan_id)
    validate_recipe(plan.profile)
    record = service.reconcile(plan_id)
    if record.instance_id is None:
        raise VastError("vast.instance_required")
    try:
        result = _perform(plan, record.instance, operation, accept_new)
    except (
        VastError,
        OSError,
        subprocess.TimeoutExpired,
        httpx.HTTPError,
        ValueError,
    ) as exc:
        code = exc.code if isinstance(exc, VastError) else "vast.workload_failed"
        _save_failure(service, plan_id, operation, code)
        raise VastError(code) from None
    _save_result(service, plan_id, operation, result)
    return result


def _observe(service: Environments, plan_id: str):
    try:
        return service.reconcile(plan_id)
    except VastError as error:
        transient = error.code in {"vast.transport_error", "vast.retry_exhausted"} or (
            error.status is not None
            and (error.status in {408, 429} or error.status >= 500)
        )
        if not transient:
            raise
        return service.journal.record(plan_id)


def _expired(record, duration_minutes: int) -> bool:
    if record.submitted_at is None:
        return False
    return (now() - record.submitted_at).total_seconds() >= duration_minutes * 60


def monitor(
    service: Environments, plan_id: str, max_seconds: int = 600, sleep=time.sleep
) -> dict:
    if not 1 <= max_seconds <= 86400:
        raise VastError("vast.invalid_timeout")
    plan = service.journal.plan(plan_id)
    if plan.finish_policy == "manual":
        raise VastError("vast.manual_cleanup_required")
    deadline = time.monotonic() + max_seconds
    while True:
        record = _observe(service, plan_id)
        if record.state == "destroyed":
            return {"state": "destroyed"}
        if _expired(record, plan.profile.duration_minutes):
            result = service.cleanup(plan_id)
            return {"state": result.state, "confirmation_required": True}
        if time.monotonic() >= deadline:
            return {
                "state": record.state,
                "monitor": "ended_resources_may_still_be_billed",
            }
        sleep(min(15, max(0, deadline - time.monotonic())))
