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


def workload(
    service: Environments, plan_id: str, operation: str, accept_new: bool = False
) -> dict:
    plan = service.journal.plan(plan_id)
    validate_recipe(plan.profile)
    record = service.reconcile(plan_id)
    if record.instance_id is None:
        raise VastError("vast.instance_required")
    try:
        if operation == "inspect":
            result = inspect(plan, record.instance, accept_new)
        elif operation == "provision":
            process = subprocess.run(
                ssh_args(plan, record.instance, accept_new) + ["bash", "-s"],
                input=startup(plan.profile),
                text=True,
                capture_output=True,
                timeout=600,
                check=False,
            )
            if process.returncode:
                raise VastError("vast.provision_failed")
            result = {"startup": "completed", "readiness": "unknown"}
        elif operation in {"ready", "benchmark"}:
            if plan.profile.mode == "vllm" and operation == "benchmark":
                raise VastError("vast.vllm_benchmark_not_supported")
            if plan.profile.mode not in {"ollama", "vllm"}:
                raise VastError("vast.ollama_profile_required")
            inspection = inspect(plan, record.instance)
            if inspection["reasons"]:
                raise VastError("vast.capacity_mismatch")
            with tunnel(plan, record.instance) as endpoint:
                with httpx.Client(
                    base_url=endpoint,
                    timeout=30,
                    trust_env=False,
                    follow_redirects=False,
                ) as client:
                    if plan.profile.mode == "vllm":
                        result = openai_ready(client, plan.profile)
                    else:
                        probe = OllamaProbe(client, plan.profile)
                        result = (
                            probe.ready() if operation == "ready" else probe.benchmark()
                        )
                    result["inspection"] = inspection
                    if (
                        operation == "benchmark"
                        and inspection["unknown"]
                        and result["status"] == "suitable"
                    ):
                        result["status"] = "inconclusive"
        else:
            raise VastError("vast.invalid_action")
    except (
        VastError,
        OSError,
        subprocess.TimeoutExpired,
        httpx.HTTPError,
        ValueError,
    ) as exc:
        code = exc.code if isinstance(exc, VastError) else "vast.workload_failed"
        with service.journal.lock(plan_id):
            failed = service.journal.record(plan_id)
            failed.reports[operation] = {
                "status": "error",
                "error": code,
                "observed_at": now().isoformat(),
            }
            if operation in {"ready", "benchmark"}:
                failed.runtime_state = "error"
            if code.startswith("vast.ssh") or code.startswith("vast.tunnel"):
                failed.ssh_state = "unknown"
            service.journal.save_record(failed)
        raise VastError(code) from None
    with service.journal.lock(plan_id):
        fresh = service.journal.record(plan_id)
        fresh.reports[operation] = result
        fresh.ssh_state = "ready"
        if operation == "ready":
            fresh.runtime_state = "ready"
        fresh.observed_at = now()
        service.journal.save_record(fresh)
    return result


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
        record = service.reconcile(plan_id)
        if record.state == "destroyed":
            return {"state": "destroyed"}
        if record.submitted_at:
            elapsed = (now() - record.submitted_at).total_seconds()
            if elapsed >= plan.profile.duration_minutes * 60:
                result = service.cleanup(plan_id)
                return {"state": result.state, "confirmation_required": True}
        if time.monotonic() >= deadline:
            return {
                "state": record.state,
                "monitor": "ended_resources_may_still_be_billed",
            }
        sleep(min(15, max(0, deadline - time.monotonic())))
