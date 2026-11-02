"""Matched diagnostic evaluation contracts and paired timings, without model imports."""

from __future__ import annotations

import math
import re
import statistics
from collections.abc import Mapping, Sequence
from typing import Any

from venom_core.services.gemma4_operator.material import SHA256, digest
from venom_core.services.gemma4_operator.profile import MODEL

ARMS = frozenset({"base", "adapter"})
COMMON = (
    "benchmark_sha256",
    "model",
    "revision",
    "effective_precision",
    "runtime_backend",
    "runtime_version",
    "context",
    "max_new_tokens",
    "seed",
    "tools_sha256",
    "evaluator_sha256",
    "concurrency",
    "tokenizer_sha256",
    "template_sha256",
)
INTEGER_FIELDS = frozenset({"context", "max_new_tokens", "seed", "concurrency"})
HASH_FIELDS = frozenset(
    {
        "benchmark_sha256",
        "tools_sha256",
        "evaluator_sha256",
        "tokenizer_sha256",
        "template_sha256",
    }
)


def _identity(value: Mapping[str, Any], arm: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("gemma_evaluation_identity_required")
    for key in COMMON:
        item = value.get(key)
        if key in INTEGER_FIELDS:
            if type(item) is not int or item < (0 if key == "seed" else 1):
                raise ValueError("gemma_evaluation_identity_invalid:" + key)
        elif not isinstance(item, str) or not item.strip():
            raise ValueError("gemma_evaluation_identity_invalid:" + key)
        elif key in HASH_FIELDS and SHA256.fullmatch(item) is None:
            raise ValueError("gemma_evaluation_identity_invalid:" + key)
    if value["model"] != MODEL or not re.fullmatch(r"[a-f0-9]{40}", value["revision"]):
        raise ValueError("gemma_evaluation_model_or_revision_invalid")
    if value["effective_precision"] not in {"nf4", "bf16"}:
        raise ValueError("gemma_evaluation_precision_unsupported")
    if value.get("requested_precision") != value["effective_precision"]:
        raise ValueError("gemma_evaluation_precision_mismatch")
    adapter = value.get("adapter_sha256")
    if arm == "adapter" and (
        not isinstance(adapter, str) or SHA256.fullmatch(adapter) is None
    ):
        raise ValueError("gemma_evaluation_adapter_identity_required")
    if arm == "base" and adapter is not None:
        raise ValueError("gemma_evaluation_base_has_adapter")
    return {key: value[key] for key in COMMON} | {
        "requested_precision": value["requested_precision"],
        "adapter_sha256": adapter,
    }


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise ValueError("gemma_evaluation_timing_invalid:" + name)
    if not math.isfinite(value) or value < 0:
        raise ValueError("gemma_evaluation_timing_invalid:" + name)
    return float(value)


def _trial(row: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(row, dict) or row.get("arm") not in ARMS:
        raise ValueError("gemma_evaluation_trial_invalid")
    for key in ("case_id", "problem_group", "family", "language"):
        if not isinstance(row.get(key), str) or not row[key].strip():
            raise ValueError("gemma_evaluation_trial_invalid:" + key)
    oracle = row.get("oracle")
    if not isinstance(oracle, dict):
        raise ValueError("gemma_evaluation_oracle_required")
    flags = (
        oracle.get("success"),
        oracle.get("success_without_oracle_confirmation"),
        oracle.get("incorrect_success_status"),
        row.get("timed_out"),
    )
    if any(type(value) is not bool for value in flags):
        raise ValueError("gemma_evaluation_oracle_flags_required")
    violations = oracle.get("scope_violations")
    if not isinstance(violations, list) or any(
        not isinstance(item, str) for item in violations
    ):
        raise ValueError("gemma_evaluation_scope_required")
    failure_kind = row.get("failure_kind")
    if failure_kind not in {None, "model", "infrastructure"}:
        raise ValueError("gemma_evaluation_failure_kind_invalid")
    task = _number(row.get("task_seconds"), "task_seconds")
    active = _number(row.get("active_task_seconds"), "active_task_seconds")
    if active > task + 0.001:
        raise ValueError("gemma_evaluation_active_exceeds_total")
    success = (
        oracle["success"]
        and not violations
        and not oracle["success_without_oracle_confirmation"]
        and not oracle["incorrect_success_status"]
        and not row["timed_out"]
        and failure_kind is None
    )
    return {
        key: row[key]
        for key in ("case_id", "problem_group", "family", "language", "arm")
    } | {
        "success": success,
        "reported_success": oracle["success"],
        "scope_violations": list(violations),
        "unconfirmed_success": oracle["success_without_oracle_confirmation"],
        "incorrect_success_status": oracle["incorrect_success_status"],
        "timed_out": row["timed_out"],
        "failure_kind": failure_kind,
        "task_seconds": task,
        "active_task_seconds": active,
    }


def _median(rows: Sequence[dict[str, Any]], field: str) -> float | None:
    return statistics.median(row[field] for row in rows) if rows else None


def _arm_summary(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    return {
        "trials": len(rows),
        "successes": sum(row["success"] for row in rows),
        "success_rate": sum(row["success"] for row in rows) / len(rows),
        "timeouts": sum(row["timed_out"] for row in rows),
        "scope_violations": sum(bool(row["scope_violations"]) for row in rows),
        "unconfirmed_successes": sum(row["unconfirmed_success"] for row in rows),
        "incorrect_success_statuses": sum(
            row["incorrect_success_status"] for row in rows
        ),
        "infrastructure_errors": sum(
            row["failure_kind"] == "infrastructure" for row in rows
        ),
        "task_p50_seconds": _median(rows, "task_seconds"),
        "active_task_p50_seconds": _median(rows, "active_task_seconds"),
    }


def compare_trials(
    rows: Sequence[dict[str, Any]], *, identities: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    """Compare paired runs only when actual runtime/precision identities match.

    A CPU report is diagnostic evidence, never authorization to activate an adapter.
    Original rows remain unchanged; all failures count in the accuracy denominator.
    """
    if not isinstance(identities, Mapping) or set(identities) != ARMS:
        raise ValueError("gemma_evaluation_identities_required")
    identity = {arm: _identity(identities[arm], arm) for arm in sorted(ARMS)}
    if any(identity["base"][key] != identity["adapter"][key] for key in COMMON):
        raise ValueError("gemma_evaluation_unmatched_configuration")
    if not isinstance(rows, (list, tuple)) or not rows:
        raise ValueError("gemma_evaluation_trials_required")
    pairs: dict[str, dict[str, dict[str, Any]]] = {}
    for row in rows:
        checked = _trial(row)
        pair = pairs.setdefault(checked["case_id"], {})
        if checked["arm"] in pair:
            raise ValueError("gemma_evaluation_duplicate_trial")
        pair[checked["arm"]] = checked
    for pair in pairs.values():
        if set(pair) != ARMS:
            raise ValueError("gemma_evaluation_incomplete_pairs")
        if any(
            pair["base"][key] != pair["adapter"][key]
            for key in ("problem_group", "family", "language")
        ):
            raise ValueError("gemma_evaluation_case_identity_mismatch")
    arm_rows = {arm: [pairs[key][arm] for key in sorted(pairs)] for arm in sorted(ARMS)}
    common = sorted(
        key for key, pair in pairs.items() if all(pair[arm]["success"] for arm in ARMS)
    )
    timings = {}
    for arm in sorted(ARMS):
        correct = [pairs[key][arm] for key in common]
        timings[arm] = {
            "task_p50_seconds": _median(correct, "task_seconds"),
            "active_task_p50_seconds": _median(correct, "active_task_seconds"),
        }
    return {
        "schema_version": 1,
        "qualification": "diagnostic_only",
        "evidence_scope": "supplied_trials_and_identities",
        "promotion_authorized": False,
        "activation_authorized": False,
        "identity": identity,
        "identities_sha256": digest(identity),
        "trials_sha256": digest(rows),
        "pairs": len(pairs),
        "arms": {arm: _arm_summary(arm_rows[arm]) for arm in sorted(ARMS)},
        "common_correct": {
            "count": len(common),
            "case_ids": common,
            "timings": timings,
        },
        "comparison_complete": not any(
            row["failure_kind"] == "infrastructure"
            for group in arm_rows.values()
            for row in group
        ),
        "trials": arm_rows,
    }
