"""Verify a pinned offline audit before Academy approves any training."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from importlib.metadata import distributions
from pathlib import Path

from scripts.academy.omni_pl_chat_audit import reject_duplicate_keys
from scripts.academy.omni_pl_chat_masks import SNAPSHOT_PIN
from venom_core.services.remote_training.paths import operator_path

from .data_audit_schema import AuditBucket, AuditReport, AuditTaxonomy
from .profiles import MAX_JSON_BYTES, Profile, digest, read_json, resolve_input, rows

AUDIT_ERROR_PREFIX = "experiment_data_audit_"
_GROUPS = ("replay", "fresh")
_PINNED_FILES = {
    "template_sha256": "chat_template.jinja",
    "tokenizer_sha256": "tokenizer.json",
    "tokenizer_config_sha256": "tokenizer_config.json",
    "model_config_sha256": "config.json",
}


class AuditError(ValueError):
    def __init__(self, reason: str, *, summary: dict | None = None) -> None:
        super().__init__(AUDIT_ERROR_PREFIX + reason)
        self.summary = summary or {}


def _read_sealed(path: Path, expected: str) -> object:
    try:
        with operator_path(path).open("rb") as stream:
            payload = stream.read(MAX_JSON_BYTES + 1)
    except FileNotFoundError as exc:
        raise AuditError("missing") from exc
    except (OSError, ValueError) as exc:
        raise AuditError("invalid") from exc
    if len(payload) > MAX_JSON_BYTES:
        raise AuditError("invalid")
    if hashlib.sha256(payload).hexdigest() != expected:
        raise AuditError("changed")
    try:
        return json.loads(payload, object_pairs_hook=reject_duplicate_keys)
    except (ValueError, RecursionError) as exc:
        raise AuditError("invalid") from exc


def _versions(venv: Path) -> dict[str, str]:
    sites = [str(path) for path in venv.glob("lib/python*/site-packages")]
    result = {}
    for name in ("transformers", "tokenizers"):
        entries = list(distributions(name=name, path=sites))
        if len(entries) != 1 or not entries[0].version:
            raise AuditError("incompatible")
        result[name] = entries[0].version
    return result


def _verify_protocol(
    root: Path, profile: Profile, recipe: dict, report: AuditReport
) -> None:
    pin = read_json(SNAPSHOT_PIN)
    identity = (profile.model, pin["revision"], digest(SNAPSHOT_PIN))
    if (report.model, report.revision, report.snapshot_sha256) != identity:
        raise AuditError("incompatible")
    if (report.train_sha256, report.dev_sha256) != (
        profile.train_sha256,
        profile.dev_sha256,
    ):
        raise AuditError("incompatible")
    tokenization = report.tokenization
    if tokenization.max_tokens != recipe["max_tokens"]:
        raise AuditError("incompatible")
    expected = {
        field: pin["files"][filename]["sha256"]
        for field, filename in _PINNED_FILES.items()
    }
    expected.update(_versions(resolve_input(root, profile.training_venv)))
    if any(getattr(tokenization, field) != value for field, value in expected.items()):
        raise AuditError("incompatible")
    snapshot = resolve_input(root, profile.snapshot)
    if any(
        digest(snapshot / filename) != expected[field]
        for field, filename in _PINNED_FILES.items()
    ):
        raise AuditError("incompatible")


def _combined(buckets: list[AuditBucket]) -> dict[str, int]:
    return {
        "records": sum(bucket.records for bucket in buckets),
        "supervised_tokens": sum(bucket.supervised_tokens for bucket in buckets),
        "input_tokens": sum(bucket.input_tokens for bucket in buckets),
        "max_input_tokens": max(
            (bucket.max_input_tokens for bucket in buckets), default=0
        ),
        "max_supervised_tokens": max(
            (bucket.max_supervised_tokens for bucket in buckets), default=0
        ),
    }


def _verify_coverage(
    report: AuditReport, taxonomy: AuditTaxonomy, train_ids: set[str]
) -> None:
    if train_ids != taxonomy.records.keys() or report.totals.records != len(train_ids):
        raise AuditError("invalid")
    counts = Counter((tag.skill, tag.group) for tag in taxonomy.records.values())
    if report.skills.keys() != {skill for skill, _ in counts}:
        raise AuditError("invalid")
    for group in _GROUPS:
        buckets = []
        for skill, pair in report.skills.items():
            bucket = getattr(pair, group)
            if bucket.records != counts[skill, group]:
                raise AuditError("invalid")
            buckets.append(bucket)
        if _combined(buckets) != getattr(report.groups, group).model_dump():
            raise AuditError("invalid")
    if (
        _combined([report.groups.replay, report.groups.fresh])
        != report.totals.model_dump()
    ):
        raise AuditError("invalid")
    if report.totals.max_input_tokens > report.tokenization.max_tokens:
        raise AuditError("invalid")


def _violations(policy: dict, report: AuditReport) -> list[dict]:
    violations = []
    subsets = [(None, policy["groups"], report.groups)]
    subsets.extend(
        (skill, floors, report.skills.get(skill))
        for skill, floors in sorted(policy["skills"].items())
    )
    for skill, floors, pair in subsets:
        for group, limits in sorted(floors.items()):
            bucket = getattr(pair, group) if pair is not None else None
            for metric in ("records", "supervised_tokens"):
                actual = getattr(bucket, metric) if bucket is not None else 0
                minimum = limits["min_" + metric]
                if actual < minimum:
                    violation = {
                        "group": group,
                        "metric": metric,
                        "actual": actual,
                        "minimum": minimum,
                    }
                    if skill is not None:
                        violation["skill"] = skill
                    violations.append(violation)
    return violations


def verify_data_audit(
    root: Path, profile_id: str, profile: Profile, recipe: dict
) -> dict | None:
    audit = profile.data_audit
    if audit is None:
        return None
    report_source = root / "profiles" / f"{profile_id}.data-audit.json"
    taxonomy_source = root / "profiles" / f"{profile_id}.taxonomy.json"
    try:
        report = AuditReport.model_validate(
            _read_sealed(report_source, audit.report_sha256)
        )
        taxonomy = AuditTaxonomy.model_validate(
            _read_sealed(taxonomy_source, audit.taxonomy_sha256)
        )
        train = resolve_input(root, profile.train)
        dev = resolve_input(root, profile.dev)
        if digest(train) != profile.train_sha256 or digest(dev) != profile.dev_sha256:
            raise AuditError("changed")
        if report.taxonomy_sha256 != audit.taxonomy_sha256:
            raise AuditError("incompatible")
        _verify_protocol(root, profile, recipe, report)
        _verify_coverage(report, taxonomy, {row["record_id"] for row in rows(train)})
    except AuditError:
        raise
    except FileNotFoundError as exc:
        raise AuditError("missing") from exc
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise AuditError("invalid") from exc
    policy = audit.policy.model_dump()
    summary = {
        "report_sha256": audit.report_sha256,
        "report": report.model_dump(),
        "policy": policy,
    }
    leakage = report.leakage.model_dump(exclude={"normalization"})
    if any(leakage.values()):
        raise AuditError("leakage", summary=summary)
    violations = _violations(policy, report)
    if violations:
        raise AuditError("threshold", summary={**summary, "violations": violations})
    return {"status": "passed", **summary}


def verify_audit_preflight(audit: dict, receipt: dict) -> None:
    """Cross-check reported totals against the runner's independently encoded train."""
    report = audit["report"]
    expected = {**report["totals"], "train_sha256": report["train_sha256"]}
    if any(receipt.get(field) != value for field, value in expected.items()):
        raise AuditError("incompatible")
