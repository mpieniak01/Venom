"""Pin comparable development evidence and evaluate campaign selection guards."""

from __future__ import annotations

import re
from collections.abc import Callable

from .retention import fingerprint

_DIGEST = re.compile(r"[a-f0-9]{64}\Z")
_KEYS = ("model", "base_sha256", "dataset_sha256", "protocol_sha256")
EvidenceReader = Callable[[str], dict]


def _digest(value: object) -> bool:
    return isinstance(value, str) and _DIGEST.fullmatch(value) is not None


def _identity(identity: dict, *, protocol_required: bool = True) -> dict:
    model = identity.get("model")
    if not isinstance(model, str) or not model.strip():
        raise ValueError("campaign_quality_identity_missing")
    required = _KEYS[1:] if protocol_required else _KEYS[1:3]
    if any(not _digest(identity.get(key)) for key in required) or (
        identity.get("protocol_sha256") is not None
        and not _digest(identity["protocol_sha256"])
    ):
        raise ValueError("campaign_quality_identity_missing")
    return {key: identity.get(key) for key in _KEYS}


def _compare_identity(expected: dict, observed: dict) -> None:
    if any(
        expected[key] is not None and expected[key] != observed[key] for key in _KEYS
    ):
        raise ValueError("campaign_quality_identity_changed")


def _cases(record: dict, expected: dict) -> dict:
    if record.get("split") != "dev":
        raise ValueError("campaign_quality_dev_required")
    cases = record.get("cases")
    if not isinstance(cases, dict) or not cases or cases.keys() != expected.keys():
        raise ValueError("campaign_quality_case_coverage")
    if any(
        not isinstance(case, dict) or case.get("category") != expected[key]
        for key, case in cases.items()
    ):
        raise ValueError("campaign_quality_category_changed")
    return cases


def _reference(fetch: EvidenceReader, record_id: str) -> dict:
    try:
        record = fetch(record_id)
    except (OSError, KeyError, ValueError, TypeError) as exc:
        raise ValueError("campaign_quality_reference_unavailable") from exc
    if not isinstance(record, dict):
        raise ValueError("campaign_quality_reference_unavailable")
    if record.get("split") != "dev":
        raise ValueError("campaign_quality_dev_required")
    if not _digest(record.get("result_sha256")):
        raise ValueError("campaign_quality_reference_unavailable")
    return record


def _flag(case: dict, role: str, metric: str) -> bool:
    judgment = case.get(role)
    value = judgment.get(metric) if isinstance(judgment, dict) else None
    if type(value) is not bool:
        raise ValueError("campaign_quality_case_evidence_missing")
    return value


def _reference_hits(record: dict, cases: dict, protect_hits: bool) -> set[str]:
    protected = set(record.get("protected_case_ids") or [])
    if protect_hits:
        protected.update(
            key for key, case in cases.items() if _flag(case, "candidate", "usable")
        )
    return protected


def _parent_cases(record: dict, cases: dict, context: dict, settings: dict) -> dict:
    adapter = context.get("initial_adapter_sha256")
    if not _digest(adapter) or adapter != record.get("candidate_sha256"):
        raise ValueError("campaign_quality_parent_adapter_changed")
    return {
        key: {
            "usable": _flag(case, "candidate", "usable"),
            "critical": (
                _flag(case, "candidate", "critical")
                if settings["no_new_critical"]
                else case["candidate"].get("critical")
            ),
            **(
                {"passed": _flag(case, "candidate", "passed")}
                if settings.get("protect_parent_full_pass", False)
                else {}
            ),
        }
        for key, case in cases.items()
    }


def freeze_policy(settings: dict, context: dict, fetch: EvidenceReader) -> dict:
    """Bind the policy to verified dev context and immutable reference digests."""
    identity = _identity(context["identity"], protocol_required=False)
    categories = context["case_categories"]
    if not isinstance(categories, dict) or not categories:
        raise ValueError("campaign_quality_case_coverage")
    minima = settings["min_category_usable_delta"]
    if minima.keys() - set(categories.values()):
        raise ValueError("campaign_quality_category_unknown")
    protected = set(settings["protected_case_ids"])
    references = []
    parent_id = settings.get("parent_reference_record_id")
    parent_cases = None
    if settings.get("protect_parent_full_pass", False) and parent_id is None:
        raise ValueError("campaign_quality_parent_reference_missing")
    if parent_id is not None and parent_id not in settings["reference_record_ids"]:
        raise ValueError("campaign_quality_parent_reference_missing")
    for record_id in settings["reference_record_ids"]:
        record = _reference(fetch, record_id)
        observed = _identity(record["identity"])
        _compare_identity(identity, observed)
        identity = observed
        cases = _cases(record, categories)
        if record_id == parent_id:
            parent_cases = _parent_cases(record, cases, context, settings)
            protected.update(
                key for key, case in parent_cases.items() if case["usable"]
            )
        protected.update(
            _reference_hits(record, cases, settings["protect_reference_hits"])
        )
        references.append(
            {"record_id": record_id, "result_sha256": record["result_sha256"]}
        )
    if protected - categories.keys():
        raise ValueError("campaign_quality_protected_case_unknown")
    payload = {
        **{key: value for key, value in settings.items() if key != "source_record_id"},
        "protected_case_ids": sorted(protected),
        "references": references,
        "identity": identity,
        "case_categories": categories,
        **(
            {
                "parent_cases": parent_cases,
                "initial_adapter_sha256": context["initial_adapter_sha256"],
            }
            if parent_cases is not None
            else {}
        ),
    }
    source_id = settings.get("source_record_id")
    if source_id is not None:
        source = _reference(fetch, source_id)
        observed = _identity(source["identity"])
        _compare_identity(identity, observed)
        _cases(source, categories)
        _verify_source_context(source, context)
        payload.update(
            source_record_id=source_id,
            source_record={
                "record_id": source_id,
                "result_sha256": source["result_sha256"],
                "train_sha256": source["train_sha256"],
                "runtime": source["runtime"],
            },
            identity=observed,
        )
    return {**payload, "policy_sha256": fingerprint(payload)}


def _verify_source_context(source: dict, context: dict) -> None:
    train = source.get("train_sha256")
    if not _digest(train) or train != context.get("train_sha256"):
        raise ValueError("campaign_quality_training_identity_changed")
    runtime = source.get("runtime")
    if (
        not isinstance(runtime, dict)
        or not runtime
        or runtime != context.get("runtime")
    ):
        raise ValueError("campaign_quality_runtime_identity_changed")


def verify_policy(policy: dict, fetch: EvidenceReader) -> None:
    if fingerprint(
        {k: v for k, v in policy.items() if k != "policy_sha256"}
    ) != policy.get("policy_sha256"):
        raise ValueError("campaign_quality_policy_changed")
    for ref in policy["references"]:
        record = _reference(fetch, ref["record_id"])
        if record["result_sha256"] != ref["result_sha256"]:
            raise ValueError("campaign_quality_reference_changed")
    source = policy.get("source_record")
    if source is not None:
        observed = _reference(fetch, source["record_id"])
        if observed["result_sha256"] != source["result_sha256"]:
            raise ValueError("campaign_quality_source_changed")


def verify_context(policy: dict, context: dict) -> None:
    observed = _identity(context["identity"], protocol_required=False)
    expected = policy["identity"]
    fields = _KEYS if observed["protocol_sha256"] is not None else _KEYS[:3]
    if any(expected[key] != observed[key] for key in fields):
        raise ValueError("campaign_quality_identity_changed")
    if policy["case_categories"] != context["case_categories"]:
        raise ValueError("campaign_quality_case_coverage")
    if policy.get("source_record") is not None:
        _verify_source_context(policy["source_record"], context)
    if (
        policy.get("parent_cases") is not None
        and context.get("initial_adapter_sha256") != policy["initial_adapter_sha256"]
    ):
        raise ValueError("campaign_quality_parent_adapter_changed")


def blocked(reason: str) -> dict:
    return {
        "status": "blocked",
        "reasons": [{"code": reason}],
        "protected_count": None,
        "lost_case_ids": [],
        "new_critical_case_ids": [],
        "category_deltas": {},
    }


def _reference_flag(case: dict, reference: dict | None, metric: str) -> bool:
    if reference is not None:
        return reference[metric]
    return _flag(case, "base", metric)


def _decisions(policy: dict, cases: dict) -> tuple[set[str], list[str], dict]:
    protected = set(policy["protected_case_ids"])
    critical = []
    summaries: dict[str, dict] = {}
    for key, case in cases.items():
        reference = policy.get("parent_cases", {}).get(key)
        base = _reference_flag(case, reference, "usable")
        candidate = _flag(case, "candidate", "usable")
        if base and (policy["protect_base_hits"] or reference is not None):
            protected.add(key)
        if policy["no_new_critical"]:
            candidate_critical = _flag(case, "candidate", "critical")
            base_critical = _reference_flag(case, reference, "critical")
            if type(base_critical) is not bool:
                raise ValueError("campaign_quality_case_evidence_missing")
            if candidate_critical and not base_critical:
                critical.append(key)
        totals = summaries.setdefault(
            case["category"], {"n": 0, "base": 0, "candidate": 0}
        )
        totals["n"] += 1
        totals["base"] += int(base)
        totals["candidate"] += int(candidate)
    return protected, critical, summaries


def evaluate(
    policy: dict, record: dict, frozen_protocol: str | None
) -> tuple[dict, str]:
    """Judge exact paired dev outcomes under a pre-approved rule."""
    identity = _identity(record["identity"])
    _compare_identity(policy["identity"], identity)
    if policy.get("source_record") is not None:
        _verify_source_context(policy["source_record"], record)
    protocol = identity["protocol_sha256"]
    if frozen_protocol is not None and protocol != frozen_protocol:
        raise ValueError("campaign_quality_identity_changed")
    cases = _cases(record, policy["case_categories"])
    protected, new_critical, summaries = _decisions(policy, cases)
    lost = sorted(
        key for key in protected if not _flag(cases[key], "candidate", "usable")
    )
    reasons = []
    if lost:
        reasons.append({"code": "protected_case_lost", "count": len(lost)})
    if new_critical:
        reasons.append({"code": "new_critical_error", "count": len(new_critical)})
    full_pass = _full_pass_decision(policy, cases, reasons)
    for category, total in summaries.items():
        delta = (total["candidate"] - total["base"]) / total["n"]
        minimum = policy["min_category_usable_delta"].get(category)
        total.update(usable_delta=delta, minimum=minimum)
        if minimum is not None and delta < minimum:
            reasons.append({"code": "category_below_minimum", "category": category})
    return {
        "status": "rejected" if reasons else "passed",
        "reasons": reasons,
        "protected_count": len(protected),
        "lost_case_ids": lost,
        "new_critical_case_ids": sorted(new_critical),
        "category_deltas": summaries,
        **full_pass,
        **(
            {"parent_delta": {**_parent_delta(policy, cases), **full_pass}}
            if policy.get("parent_cases") is not None
            else {}
        ),
    }, protocol


def _parent_delta(policy: dict, cases: dict) -> dict:
    parent = policy["parent_cases"]
    return {
        "reference_record_id": policy["parent_reference_record_id"],
        "n": len(cases),
        "usable_delta": (
            sum(_flag(case, "candidate", "usable") for case in cases.values())
            - sum(case["usable"] for case in parent.values())
        )
        / len(cases),
        "critical_delta": _critical_delta(parent, cases),
    }


def _critical_delta(parent: dict, cases: dict) -> float | None:
    values = [
        (parent[key]["critical"], case["candidate"].get("critical"))
        for key, case in cases.items()
    ]
    if any(type(value) is not bool for pair in values for value in pair):
        return None
    return sum(
        int(candidate) - int(reference) for reference, candidate in values
    ) / len(values)


def _full_pass_decision(policy: dict, cases: dict, reasons: list[dict]) -> dict:
    if not policy.get("protect_parent_full_pass", False):
        return {}
    parent = policy.get("parent_cases")
    if not isinstance(parent, dict) or parent.keys() != cases.keys():
        raise ValueError("campaign_quality_parent_reference_missing")
    if any(type(case.get("passed")) is not bool for case in parent.values()):
        raise ValueError("campaign_quality_case_evidence_missing")
    protected = {key for key, case in parent.items() if case["passed"]}
    full_passes = {
        key for key, case in cases.items() if _flag(case, "candidate", "passed")
    }
    lost = sorted(protected - full_passes)
    delta = (len(full_passes) - len(protected)) / len(cases)
    if lost:
        reasons.append({"code": "parent_full_pass_lost", "count": len(lost)})
    if delta <= 0:
        reasons.append({"code": "parent_full_pass_no_gain"})
    return {
        "full_pass_delta": delta,
        "parent_full_pass_count": len(protected),
        "candidate_full_pass_count": len(full_passes),
        "lost_parent_full_pass_case_ids": lost,
    }
