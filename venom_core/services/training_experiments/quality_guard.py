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
    for record_id in settings["reference_record_ids"]:
        record = _reference(fetch, record_id)
        observed = _identity(record["identity"])
        _compare_identity(identity, observed)
        identity = observed
        cases = _cases(record, categories)
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


def blocked(reason: str) -> dict:
    return {
        "status": "blocked",
        "reasons": [{"code": reason}],
        "protected_count": None,
        "lost_case_ids": [],
        "new_critical_case_ids": [],
        "category_deltas": {},
    }


def _decisions(policy: dict, cases: dict) -> tuple[set[str], list[str], dict]:
    protected = set(policy["protected_case_ids"])
    critical = []
    summaries: dict[str, dict] = {}
    for key, case in cases.items():
        base = _flag(case, "base", "usable")
        candidate = _flag(case, "candidate", "usable")
        if base and policy["protect_base_hits"]:
            protected.add(key)
        if policy["no_new_critical"]:
            base_critical = _flag(case, "base", "critical")
            candidate_critical = _flag(case, "candidate", "critical")
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
    }, protocol
