"""Private, persistent stack knowledge backed by the existing journal."""

from __future__ import annotations

import json

from venom_core.infrastructure.providers.vast.client import VastError
from venom_core.infrastructure.providers.vast.models import (
    EnvironmentPlan,
    WorkloadProfile,
    digest,
)
from venom_core.services.vast_environments.qualification import POLICY_VERSION
from venom_core.services.vast_environments.startup import startup
from venom_core.services.vast_environments.store import Journal

INDEX_NAME = "qualifications.json"
INDEX_LOCK = digest("vast-qualification-index")[:32]


def workload_key(profile: WorkloadProfile) -> str:
    return digest(
        {
            "policy": POLICY_VERSION,
            "mode": profile.mode,
            "image": profile.image,
            "cpu_arch": profile.cpu_arch,
            "model": profile.model,
            "model_digest": profile.model_digest,
            "context_tokens": profile.context_tokens,
            "output_tokens": profile.output_tokens,
            "gpu_memory_utilization": profile.gpu_memory_utilization,
            "max_parallel_requests": profile.max_parallel_requests,
            "worker_packages": profile.worker_packages,
            "worker_tasks": profile.worker_tasks,
            "runtime": profile.runtime.model_dump(mode="json"),
            "template_hash": profile.template_hash,
            "template_configuration": profile.template_configuration_sha256,
            "startup": digest(startup(profile)),
        }
    )


def entries(journal: Journal) -> list[dict]:
    path = journal.root / INDEX_NAME
    if not path.exists():
        return []
    try:
        if path.stat().st_size > 8_000_000:
            raise ValueError
        data = json.loads(path.read_text(encoding="utf-8"))
        if (
            not isinstance(data, dict)
            or data.get("schema_version") != 1
            or not isinstance(data.get("entries"), dict)
        ):
            raise ValueError
        values = list(data["entries"].values())
        if any(
            not isinstance(x, dict)
            or x.get("status") not in {"suitable", "unsuitable", "inconclusive"}
            for x in values
        ):
            raise ValueError
        return values
    except (OSError, ValueError):
        raise VastError("vast.qualification_history_invalid") from None


def remember(journal: Journal, plan: EnvironmentPlan, report: dict) -> dict:
    probe = (report.get("observed") or {}).get("probe") or {}
    offer = plan.assessment.offer
    context = {
        "gpu_name": offer.get("gpu_name") or probe.get("gpu_name"),
        "compute_cap": probe.get("compute_cap") or offer.get("compute_cap"),
        "driver_version": probe.get("driver_version") or offer.get("driver_version"),
        "host_id": offer.get("host_id"),
        "machine_id": offer.get("machine_id"),
        "gpu_ram": offer.get("gpu_ram"),
        "cpu_ram": offer.get("cpu_ram"),
    }
    evidence_id = digest({"plan_id": plan.plan_id, "report": report})[:32]
    row = {
        "schema_version": 1,
        "workload_key": workload_key(plan.profile),
        "context": context,
        "plan_id": plan.plan_id,
        "evidence_id": evidence_id,
        "image": plan.profile.image,
        "template_hash": plan.profile.template_hash,
        "engine_version": (report.get("observed") or {}).get("engine_version"),
        "status": report["status"],
        "cause_scope": report["cause_scope"],
        "reasons": report["reasons"],
        "observed_at": report["observed_at"],
    }
    with journal.lock(INDEX_LOCK):
        current = entries(journal)
        key = digest(
            {
                "workload": row["workload_key"],
                "context": context,
                "scope": row["cause_scope"],
            }
        )
        index = {
            digest(
                {
                    "workload": x["workload_key"],
                    "context": x["context"],
                    "scope": x["cause_scope"],
                }
            ): x
            for x in current
        }
        index[key] = row
        payload = {"schema_version": 1, "entries": index}
        if len(json.dumps(payload)) > 8_000_000:
            raise VastError("vast.qualification_history_limit")
        journal.write(
            journal.path(evidence_id, ".qualification.json"),
            {"summary": row, "report": report},
        )
        journal.write(journal.root / INDEX_NAME, payload)
    return row


def _context_match(entry: dict, offer: dict) -> bool:
    context, scope = entry["context"], entry["cause_scope"]
    if scope == "image":
        return True
    keys = ["gpu_name", "compute_cap", "driver_version"]
    if scope in {"host", "workload"}:
        keys += ["host_id", "machine_id", "gpu_ram", "cpu_ram"]
    if scope not in {"stack_gpu", "host", "workload"}:
        return False
    return all(
        context.get(key) is not None and context.get(key) == offer.get(key)
        for key in keys
    )


def lookup(journal: Journal, profile: WorkloadProfile, offer: dict) -> dict:
    rows = [x for x in entries(journal) if x["workload_key"] == workload_key(profile)]
    exact = [x for x in rows if _context_match(x, offer)]
    candidates = exact or rows
    if not candidates:
        return {"status": "not_tested", "excluded": False, "match": "none"}
    latest = max(candidates, key=lambda x: x["observed_at"])
    return {
        **latest,
        "match": "exact" if exact else "partial",
        "excluded": bool(exact and latest["status"] == "unsuitable"),
        "qualification": "previous_observation; current_instance_not_tested",
    }


def report(journal: Journal, plan_id: str) -> dict:
    plan = journal.plan(plan_id)
    record = journal.record(plan_id)
    return {
        "schema_version": 1,
        "plan_id": plan_id,
        "state": record.state,
        "ssh_state": record.ssh_state,
        "runtime_state": record.runtime_state,
        "requirements": plan.profile.model_dump(mode="json"),
        "declared": plan.assessment.runtime,
        "reports": record.reports,
        "costs": record.reports.get(
            "costs",
            {
                "status": "not_requested",
                "quote": plan.assessment.quote.model_dump(mode="json"),
            },
        ),
        "budget": {
            "max_hourly_usd": str(plan.max_hourly_usd),
            "max_total_usd": str(plan.max_total_usd),
        },
        "history": [row for row in entries(journal) if row["plan_id"] == plan_id],
        "evidence_retained_after_destroy": True,
    }
