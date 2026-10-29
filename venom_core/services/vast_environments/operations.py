"""Workload operations shared by CLI and future API endpoints."""

from __future__ import annotations

import re
import subprocess
import time

import httpx

from venom_core.infrastructure.providers.vast.client import VastError
from venom_core.infrastructure.providers.vast.models import now
from venom_core.infrastructure.providers.vast.runtime_contracts import version_parts
from venom_core.services.vast_environments.evaluation import OllamaProbe
from venom_core.services.vast_environments.gpu_probe import probe_gpu
from venom_core.services.vast_environments.history import remember
from venom_core.services.vast_environments.lifecycle import Environments
from venom_core.services.vast_environments.openai_probe import OpenAIProbe
from venom_core.services.vast_environments.openai_probe import ready as openai_ready
from venom_core.services.vast_environments.qualification import qualify
from venom_core.services.vast_environments.recipes import validate_recipe
from venom_core.services.vast_environments.runtime_scripts import vllm_wait_seconds
from venom_core.services.vast_environments.ssh import inspect, ssh_args, tunnel
from venom_core.services.vast_environments.startup import startup


def _engine_version_from_banner(value: str) -> str | None:
    """Read the first adjacent major/minor/optional-patch digit runs in linear time."""
    runs = iter(re.finditer(r"\d+", value))
    previous = next(runs, None)
    if previous is None:
        return None
    for current in runs:
        if value[previous.end() : current.start()] != ".":
            previous = current
            continue
        end = current.end()
        patch = next(runs, None)
        if patch is not None and value[end : patch.start()] == ".":
            end = patch.end()
        return value[previous.start() : end]
    return None


def _check_ollama_capacity(plan, capacity: dict) -> None:
    blocking = [reason for reason in capacity["reasons"] if reason != "startup"]
    if blocking or capacity["unknown"]:
        raise VastError("vast.capacity_mismatch")
    facts = capacity["facts"]
    gpu = str(facts.get("gpu", "")).split(",")
    engine = _engine_version_from_banner(str(facts.get("ollama_version", "")))
    for actual, minimum in (
        (gpu[1].strip() if len(gpu) >= 2 else None, plan.profile.runtime.min_driver),
        (engine, plan.profile.runtime.min_engine_version),
    ):
        if minimum:
            observed, required = version_parts(actual), version_parts(minimum)
            if observed is None or required is None or observed < required:
                raise VastError("vast.runtime_version_mismatch")


def _provision(plan, instance: dict, accept_new: bool) -> dict:
    if plan.profile.mode == "ollama":
        capacity = inspect(plan, instance, accept_new)
        _check_ollama_capacity(plan, capacity)
    process = subprocess.run(
        ssh_args(plan, instance, accept_new) + ["bash", "-s"],
        input=startup(plan.profile, download_model=True),
        text=True,
        capture_output=True,
        timeout=(
            vllm_wait_seconds(plan.profile) + 60 if plan.profile.mode == "vllm" else 600
        ),
        check=False,
    )
    if process.returncode:
        raise VastError("vast.provision_failed")
    return {"startup": "completed", "readiness": "unknown"}


def _gpu_facts(plan, instance: dict, accept_new: bool = False) -> dict:
    try:
        return probe_gpu(plan, instance, accept_new)
    except VastError as error:
        return {"status": "error", "reason": error.code}


def _engine_ready(client, profile) -> dict:
    if profile.mode == "vllm":
        return openai_ready(client, profile)
    probe = OllamaProbe(client, profile)
    if not profile.model:
        return probe.engine_ready()
    engine = probe.ready()
    engine["loaded_model"] = _loaded_model(client, profile)
    return engine


def _model_operation(plan, instance: dict, operation: str) -> dict:
    if plan.profile.mode not in {"ollama", "vllm"}:
        raise VastError("vast.ollama_profile_required")
    if operation == "benchmark" and not plan.profile.model:
        raise VastError("vast.model_digest_required")
    inspection = inspect(plan, instance)
    if inspection["reasons"]:
        raise VastError("vast.capacity_mismatch")
    with (
        tunnel(plan, instance) as endpoint,
        httpx.Client(
            base_url=endpoint,
            timeout=httpx.Timeout(180, connect=10),
            trust_env=False,
            follow_redirects=False,
        ) as client,
    ):
        engine = _engine_ready(client, plan.profile)
        if not plan.profile.model:
            return {**engine, "inspection": inspection}
        facts = _gpu_facts(plan, instance)
        preliminary = qualify(
            plan, inspection, facts, engine, evaluate_performance=False
        )
        if operation == "ready":
            result = dict(engine)
        elif preliminary["status"] != "suitable":
            result = {
                "status": preliminary["status"],
                "samples": [],
                "errors": preliminary["reasons"],
                "not_run": "runtime_not_qualified",
            }
        else:
            probe_type = OpenAIProbe if plan.profile.mode == "vllm" else OllamaProbe
            result = probe_type(client, plan.profile).benchmark()
        qualification = qualify(
            plan,
            inspection,
            facts,
            engine,
            dict(result)
            if operation == "benchmark" and "not_run" not in result
            else None,
            evaluate_performance=operation == "benchmark",
        )
        result["qualification_report"] = qualification
        if operation == "benchmark":
            result["status"] = qualification["status"]
    result["inspection"] = inspection
    return result


def _loaded_model(client: httpx.Client, profile) -> dict:
    response = client.get("/api/ps")
    response.raise_for_status()
    rows = response.json().get("models", [])
    matches = [
        row
        for row in rows
        if isinstance(row, dict) and row.get("name") == profile.model
    ]
    if len(matches) != 1:
        return {}
    return {key: matches[0].get(key) for key in ["name", "digest", "size", "size_vram"]}


def _qualify_operation(plan, instance: dict, accept_new: bool) -> dict:
    inspection = inspect(plan, instance, accept_new)
    engine = {}
    if plan.profile.mode in {"ollama", "vllm"} and not inspection["reasons"]:
        try:
            with (
                tunnel(plan, instance) as endpoint,
                httpx.Client(
                    base_url=endpoint,
                    timeout=30,
                    trust_env=False,
                    follow_redirects=False,
                ) as client,
            ):
                engine = _engine_ready(client, plan.profile)
        except (VastError, httpx.HTTPError, ValueError, TypeError):
            engine["readiness"] = "inconclusive"
    return qualify(plan, inspection, _gpu_facts(plan, instance, accept_new), engine)


def _perform(plan, instance: dict, operation: str, accept_new: bool) -> dict:
    if operation == "inspect":
        return inspect(plan, instance, accept_new)
    if operation == "provision":
        return _provision(plan, instance, accept_new)
    if operation == "qualify":
        return _qualify_operation(plan, instance, accept_new)
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
        qualification = (
            result if operation == "qualify" else result.get("qualification_report")
        )
        fresh.reports[operation] = result
        fresh.ssh_state = "ready"
        if operation == "ready":
            fresh.runtime_state = "ready"
        fresh.observed_at = now()
        # Keep the paid operation's report even if the shared index is locked,
        # corrupt or unwritable. Index failure is a separate observation.
        service.journal.save_record(fresh)
        if not isinstance(qualification, dict):
            return
        if qualification.get("performance_evaluated", True) is False:
            return
        try:
            result["qualification_history"] = remember(
                service.journal, service.journal.plan(plan_id), qualification
            )
        except (VastError, OSError) as error:
            if isinstance(error, VastError):
                code = error.code
            else:
                code = "vast.qualification_history_write_failed"
            result["qualification_history"] = {"status": "error", "error": code}
        fresh.reports[operation] = result
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
        transient = error.code in {"vast.transport_error", "vast.retry_exhausted"}
        if not transient and error.status is not None:
            transient = error.status in {408, 429} or error.status >= 500
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
