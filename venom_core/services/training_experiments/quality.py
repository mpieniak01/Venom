"""Immutable evaluation history and deterministic, paired quality analysis."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path

from scripts.academy.omni_pl_chat_recipe import (
    LANGUAGE_TARGET_MODULES,
    P13_LANGUAGE_SELECTOR,
    validate_target_modules,
)
from venom_core.core.environment_policy import ensure_data_mutation_allowed
from venom_core.services.remote_training.lifecycle import (
    atomic_json,
    file_lock,
    validate_run_id,
)
from venom_core.services.remote_training.paths import operator_path

from .profiles import MAX_JSON_BYTES, read_json, stable_hash
from .quality_schema import QualityRecord

_IDENTITY_FIELDS = ("base_sha256", "dataset_sha256", "protocol_sha256")
_PRIORITY_FACTORS = ("target_modules", "loss", "loss_mode", "rank", "learning_rate")


def quality_record_view(record: QualityRecord | dict) -> dict:
    supplied_digest = None
    if isinstance(record, dict):
        payload = dict(record)
        supplied_digest = payload.pop("result_sha256", None)
        record = QualityRecord.model_validate(payload)
    view = record.model_dump(mode="json")
    view["protected_case_ids"] = sorted(view["protected_case_ids"])
    view["evidence_gaps"] = sorted(set(view["evidence_gaps"]))
    # Preserve previously sealed v1 records when the new optional fields are absent.
    for key in ("reviewed_run", "cohorts"):
        if view[key] is None:
            del view[key]
    if "cohorts" in view:
        view["cohorts"] = {name: sorted(ids) for name, ids in view["cohorts"].items()}
    digest = stable_hash(view)
    if supplied_digest is not None and supplied_digest != digest:
        raise ValueError("quality_record_hash_changed")
    return {**view, "result_sha256": digest}


class QualityStore:
    """Store sealed normalized records under the local experiment root."""

    def __init__(self, root: Path):
        self.directory = operator_path(root / "quality")

    def _path(self, record_id: str) -> Path:
        validate_run_id(record_id)
        return operator_path(self.directory / f"{record_id}.json")

    def get(self, record_id: str) -> dict:
        payload = read_json(self._path(record_id))
        if (
            not isinstance(payload, dict)
            or not isinstance(payload.get("result_sha256"), str)
            or payload.get("record_id") != record_id
        ):
            raise ValueError("quality_record_invalid")
        return quality_record_view(payload)

    def list(self) -> tuple[list[dict], list[str]]:
        """Return verified records and the IDs of unreadable entries."""
        records = []
        unavailable = []
        for path in sorted(self.directory.glob("*.json")):
            try:
                records.append(self.get(path.stem))
            except (OSError, ValueError, RecursionError):
                unavailable.append(path.stem)
        return records, unavailable

    def import_record(self, record: QualityRecord | dict) -> dict:
        ensure_data_mutation_allowed("academy_quality_import")
        view = quality_record_view(record)
        raw = json.dumps(view, indent=2, sort_keys=True, allow_nan=False) + "\n"
        if len(raw.encode()) > MAX_JSON_BYTES:
            raise ValueError("quality_record_too_large")
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        path = self._path(view["record_id"])
        with file_lock(self.directory / ".import.lock"):
            if path.exists():
                previous = self.get(view["record_id"])
                if previous != view:
                    raise ValueError("quality_record_identity_conflict")
                return previous
            atomic_json(path, view)
        return view


def _protected_case_ids(record: dict, reference: dict | None) -> list[str]:
    if record["split"] != "dev":
        return []
    return sorted(
        set(record["protected_case_ids"])
        | set((reference or {}).get("protected_case_ids", ()))
    )


def comparison_issues(record: dict, reference: dict) -> list[str]:
    left, right = record["identity"], reference["identity"]
    issues = []
    if any(left[field] is None or right[field] is None for field in _IDENTITY_FIELDS):
        issues.append("quality_identity_unverified")
    for field, code in (
        ("model", "quality_model_mismatch"),
        ("base_sha256", "quality_base_mismatch"),
        ("dataset_sha256", "quality_dataset_mismatch"),
        ("protocol_sha256", "quality_protocol_mismatch"),
    ):
        if (
            left[field] is not None
            and right[field] is not None
            and left[field] != right[field]
        ):
            issues.append(code)
    if record["split"] != reference["split"]:
        issues.append("quality_split_mismatch")
    cases, peers = record["cases"], reference["cases"]
    if cases.keys() != peers.keys():
        issues.append("quality_case_set_mismatch")
    elif any(
        case["category"] != peers[case_id]["category"]
        for case_id, case in cases.items()
    ):
        issues.append("quality_category_mismatch")
    if record.get("cohorts") != reference.get("cohorts"):
        issues.append("quality_cohort_mismatch")
    return issues


def _paired_rows(
    record: dict, reference: dict | None
) -> list[tuple[str, str, dict, dict]]:
    return [
        (
            case_id,
            case["category"],
            reference["cases"][case_id]["candidate"] if reference else case["base"],
            case["candidate"],
        )
        for case_id, case in sorted(record["cases"].items())
    ]


def _critical_count(values: list[dict]) -> int | None:
    if any(value["critical"] is None for value in values):
        return None
    return sum(value["critical"] is True for value in values)


def _counts(pairs: list[tuple[dict, dict]], category: str, label: str) -> dict:
    left, right = map(list, zip(*pairs, strict=True))
    left_usable = sum(value["usable"] for value in left)
    right_usable = sum(value["usable"] for value in right)
    left_critical, right_critical = _critical_count(left), _critical_count(right)
    return {
        "category": category,
        "n": len(pairs),
        f"{label}_usable": left_usable,
        "candidate_usable": right_usable,
        f"{label}_critical": left_critical,
        "candidate_critical": right_critical,
        "usable_delta": (right_usable - left_usable) / len(pairs),
        "critical_delta": (
            (right_critical - left_critical) / len(pairs)
            if left_critical is not None and right_critical is not None
            else None
        ),
        "lost_usable": sum(a["usable"] and not b["usable"] for a, b in pairs),
        "gained_usable": sum(not a["usable"] and b["usable"] for a, b in pairs),
    }


def _summaries(paired: list[tuple[str, str, dict, dict]], label: str) -> list[dict]:
    groups: dict[str, list[tuple[dict, dict]]] = defaultdict(list)
    for _, category, left, right in paired:
        groups[category].append((left, right))
        groups["total"].append((left, right))
    return [
        _counts(groups[category], category, label)
        for category in ("total", *sorted(groups.keys() - {"total"}))
    ]


def _cohort_summaries(
    paired: list[tuple[str, str, dict, dict]],
    cohorts: dict[str, list[str]],
    label: str,
) -> list[dict]:
    by_id = {case_id: (left, right) for case_id, _, left, right in paired}
    return [
        _counts([by_id[case_id] for case_id in ids], cohort, label)
        for cohort, ids in sorted(cohorts.items())
    ]


def _finding(
    code: str, *, fields: Iterable[str] = (), cases: Iterable[str] = ()
) -> dict:
    return {"code": code, "fields": sorted(fields), "case_ids": sorted(cases)}


def _outcome_findings(
    paired: list[tuple[str, str, dict, dict]], cases: dict
) -> list[dict]:
    events: dict[str, list[str]] = defaultdict(list)
    for case_id, _, left, right in paired:
        if left["usable"] != right["usable"]:
            result = (
                "quality_gained_usable" if right["usable"] else "quality_lost_usable"
            )
            events[result].append(case_id)
        base_critical = cases[case_id]["base"]["critical"]
        if None in (base_critical, left["critical"], right["critical"]):
            events["quality_critical_unknown"].append(case_id)
        if base_critical is False and right["critical"] is True:
            events["quality_new_critical"].append(case_id)
    return [_finding(code, cases=cases) for code, cases in sorted(events.items())]


def _paired_protection(
    record: dict, reference: dict | None, protected_ids: list[str]
) -> dict:
    ids = set(protected_ids)
    cases = record["cases"]
    missing = ids - cases.keys()
    ref_cases = reference["cases"] if reference else {}
    return {
        "total": len(ids),
        "evaluated": len(ids - missing),
        "passed": sum(
            cases[case_id]["candidate"]["usable"] for case_id in ids - missing
        ),
        "base_passed": sum(
            cases[case_id]["base"]["usable"] for case_id in ids - missing
        ),
        "reference_passed": (
            sum(
                ref_cases[case_id]["candidate"]["usable"]
                for case_id in ids & ref_cases.keys()
            )
            if reference is not None
            else None
        ),
        "missing_case_ids": sorted(missing),
        "reference_missing_case_ids": sorted(ids - ref_cases.keys())
        if reference
        else [],
    }


def _normalized_recipe(record: dict) -> dict:
    recipe = record["recipe"] or {}
    modules = recipe.get("target_modules")
    if modules == P13_LANGUAGE_SELECTOR:
        modules = list(LANGUAGE_TARGET_MODULES)
    try:
        canonical = validate_target_modules(modules)
    except ValueError:
        return recipe
    return {**recipe, "target_modules": canonical}


def _recipe_changes(record: dict, reference: dict) -> list[str]:
    recipe, previous = _normalized_recipe(record), _normalized_recipe(reference)
    return [
        field
        for field in sorted(recipe.keys() & previous.keys())
        if recipe[field] is not None
        and previous[field] is not None
        and recipe[field] != previous[field]
    ]


def _known_outcomes_differ(left: dict, right: dict) -> bool:
    return left["usable"] != right["usable"] or (
        left["critical"] is not None
        and right["critical"] is not None
        and left["critical"] != right["critical"]
    )


def _context_findings(record: dict, reference: dict, changes: list[str]) -> list[dict]:
    fields = list(changes)
    findings = []
    for key, code in (
        ("train_sha256", "quality_training_changed"),
        ("runtime", "quality_runtime_changed"),
    ):
        if (
            record[key] is not None
            and reference[key] is not None
            and record[key] != reference[key]
        ):
            fields.append(key)
            findings.append(_finding(code, fields=(key,)))
    if len(fields) > 1:
        findings.append(_finding("quality_recipe_confounded", fields=fields))
    changed_baseline = [
        case_id
        for case_id, case in record["cases"].items()
        if _known_outcomes_differ(case["base"], reference["cases"][case_id]["base"])
    ]
    if changed_baseline:
        findings.append(
            _finding("quality_baseline_outcomes_changed", cases=changed_baseline)
        )
    return findings


def _proposal_reasons(
    record: dict,
    reference: dict | None,
    factor: str | None,
    reasons: list[str],
) -> list[str]:
    missing = list(reasons)
    if record["split"] != "dev":
        missing.append("quality_holdout_excluded")
    if reference is None:
        if not reasons:
            missing.append("quality_reference_required")
        return missing
    if factor is None:
        missing.append("quality_recipe_difference_unverified")
    if record["train_sha256"] is None:
        missing.append("quality_training_identity_missing")
    if not record["runtime"]:
        missing.append("quality_runtime_identity_missing")
    return missing


def _proposal(
    record: dict,
    reference: dict | None,
    changes: list[str],
    reasons: list[str],
) -> dict:
    factor = next((field for field in _PRIORITY_FACTORS if field in changes), None)
    if factor is None and changes:
        factor = changes[0]
    missing = _proposal_reasons(record, reference, factor, reasons)
    variants = []
    if not missing and factor is not None and reference is not None:
        control = _normalized_recipe(record)
        alternate = _normalized_recipe(reference)[factor]
        variants = [
            {"name": "control", "recipe": dict(control)},
            {
                "name": "isolated",
                "recipe": {**control, factor: alternate},
            },
        ]
    return {
        "status": "ready" if variants else "insufficient_evidence",
        "kind": "isolate_recipe_factor" if factor else None,
        "factor": factor,
        "reference_id": reference["record_id"] if reference else None,
        "variants": variants,
        "fixed": {"train_sha256": record["train_sha256"], "runtime": record["runtime"]},
        "reasons": missing,
        "measurement": ["usable_by_category", "protected_cases", "critical_errors"],
        "stop_condition": "stop_on_protected_regression_or_new_critical",
    }


def _decision(
    record: dict, issues: list[str], findings: list[dict], score: dict, protected: dict
) -> str:
    if record["outcome"] is not None:
        return record["outcome"]
    codes = {finding["code"] for finding in findings}
    if "quality_new_critical" in codes:
        return "STOP"
    if (
        issues
        or "quality_critical_unknown" in codes
        or "quality_baseline_outcomes_changed" in codes
        or protected["missing_case_ids"]
        or any(record["identity"][field] is None for field in _IDENTITY_FIELDS)
    ):
        return "INCOMPLETE"
    if (
        score["lost_usable"]
        or not score["gained_usable"]
        or protected["passed"] < protected["total"]
    ):
        return "REVISE"
    return "GO"


def analyze_quality(
    record: QualityRecord | dict,
    reference: QualityRecord | dict | None = None,
) -> dict:
    """Compare explicit matching cases and suggest a one-factor dev experiment."""
    current = quality_record_view(record)
    peer = quality_record_view(reference) if reference is not None else None
    issues = comparison_issues(current, peer) if peer is not None else []
    matched = peer if not issues else None
    base_pairs = _paired_rows(current, None)
    summary = _summaries(base_pairs, "base")
    pairs = _paired_rows(current, matched) if matched is not None else base_pairs
    comparison = _summaries(pairs, "reference") if matched is not None else []
    cohorts = current.get("cohorts", {})
    findings = _outcome_findings(pairs, current["cases"])
    changes = _recipe_changes(current, matched) if matched is not None else []
    if matched is not None:
        findings.extend(_context_findings(current, matched, changes))
    protected_ids = _protected_case_ids(current, matched)
    protected = _paired_protection(current, matched, protected_ids)
    proposal_issues = list(issues)
    if protected["missing_case_ids"]:
        proposal_issues.append("quality_protected_evidence_missing")
    if any(
        finding["code"] == "quality_baseline_outcomes_changed" for finding in findings
    ):
        proposal_issues.append("quality_baseline_outcomes_changed")
    return {
        "record": current,
        "reference_id": peer["record_id"] if peer else None,
        "comparable": matched is not None,
        "comparison_issues": issues,
        "summary": summary,
        "comparison": comparison,
        "cohorts": _cohort_summaries(base_pairs, cohorts, "base"),
        "cohort_comparison": (
            _cohort_summaries(pairs, cohorts, "reference")
            if matched is not None
            else []
        ),
        "findings": findings,
        "decision": _decision(
            current, issues, findings, (comparison or summary)[0], protected
        ),
        "proposal": _proposal(current, matched, changes, proposal_issues),
        "protected": protected,
        "protected_case_ids": protected_ids,
    }
