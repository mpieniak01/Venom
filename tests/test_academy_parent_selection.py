"""A narrow S/K win must not discard sealed wider regression evidence."""

import copy

import pytest

from venom_core.services.training_experiments.parent_selection import (
    select_campaign_parent,
)
from venom_core.services.training_experiments.profiles import stable_hash

REF = "1" * 64
CANDIDATE = "2" * 64
SHORT = {
    "usable_delta": 0.1,
    "passed_delta": 0.1,
    "full_retention": True,
    "new_critical_case_ids": [],
}


def report():
    cases = {
        f"inc17-dialogue-{group}-{conversation}-t{turn}": {"usable": 1, "passed": 1}
        for group in "WKSR"
        for conversation in range(1, 7)
        for turn in range(1, 7)
    }
    payload = {
        "factual_final_used": False,
        "model_identities": {
            "checkpoint-145": {"adapter_model.safetensors": REF},
            "checkpoint-25": {"adapter_model.safetensors": CANDIDATE},
        },
        "verdicts": {"P13": cases, "P25": copy.deepcopy(cases)},
        "critical_by_case": {
            key: dict.fromkeys(cases, False) for key in ("P13", "P25")
        },
    }
    return seal(payload)


def seal(payload):
    return {"payload": payload, "sha256": stable_hash(payload)}


def choose(evidence=None, short=None, checksum=None):
    return select_campaign_parent(
        short or SHORT,
        broad_report=evidence,
        expected_report_sha256=checksum or (evidence and evidence["sha256"]),
        reference_weight_sha256=REF,
        candidate_weight_sha256=CANDIDATE,
    )


def test_narrow_win_with_missing_broad_audit_retains_reference():
    result = choose()
    assert result["sk_recommendation"] == "P25"
    assert result["selected_parent"] == "P13"
    assert result["broad_gate"]["blockers"] == ["broad_audit_missing"]


def test_fully_retained_broad_evidence_allows_parent_but_not_promotion():
    result = choose(report())
    assert result["selected_parent"] == "P25"
    assert result["broad_gate"]["expected_pairs"] == 144
    assert result["qualified_candidate"] is None


def test_four_known_new_critical_errors_override_narrow_win():
    evidence = report()
    ids = [
        "inc17-dialogue-W-6-t6",
        "inc17-dialogue-S-1-t6",
        "inc17-dialogue-R-6-t3",
        "inc17-dialogue-R-6-t5",
    ]
    for ident in ids:
        evidence["payload"]["critical_by_case"]["P25"][ident] = True
    result = choose(seal(evidence["payload"]))
    assert result["selected_parent"] == "P13"
    assert result["broad_gate"]["new_critical_case_ids"] == sorted(ids)
    assert result["broad_gate"]["blockers"] == ["broad_new_critical"]


@pytest.mark.parametrize("metric", ["usable", "passed"])
def test_retention_loss_blocks_parent(metric):
    evidence = report()["payload"]
    evidence["verdicts"]["P25"]["inc17-dialogue-S-1-t6"][metric] = 0
    gate = choose(seal(evidence))["broad_gate"]
    assert gate["blockers"] == ["broad_retention_lost"]
    assert gate["lost_reference_case_ids"][metric] == ["inc17-dialogue-S-1-t6"]


@pytest.mark.parametrize("scope", ["usable", "critical"])
def test_null_remains_unresolved_and_blocks_parent(scope):
    evidence = report()["payload"]
    ident = "inc17-dialogue-K-5-t2"
    if scope == "usable":
        evidence["verdicts"]["P13"][ident]["usable"] = None
    else:
        evidence["critical_by_case"]["P25"][ident] = None
    gate = choose(seal(evidence))["broad_gate"]
    assert gate["unresolved_pair_case_ids"] == [ident]
    assert gate["blockers"] == ["broad_unresolved"]


@pytest.mark.parametrize(
    "change",
    [
        {"usable_delta": 0.0},
        {"passed_delta": -0.1},
        {"full_retention": False},
        {"new_critical_case_ids": ["SK-loss"]},
    ],
)
def test_short_tie_tradeoff_or_critical_retains_reference(change):
    result = choose(report(), {**SHORT, **change})
    assert result["sk_recommendation"] == result["selected_parent"] == "P13"


@pytest.mark.parametrize(
    "change",
    [
        {"usable_delta": float("nan")},
        {"passed_delta": float("inf")},
        {"full_retention": "true"},
        {"new_critical_case_ids": [3]},
    ],
)
def test_invalid_short_comparison_rejected(change):
    with pytest.raises(ValueError):
        choose(report(), {**SHORT, **change})


@pytest.mark.parametrize(
    "mutation", ["hash", "weights", "coverage", "ids", "metric", "critical", "final"]
)
def test_tamper_or_incomplete_evidence_fails_closed(mutation):
    evidence = report()
    payload = evidence["payload"]
    if mutation == "hash":
        evidence["sha256"] = "3" * 64
    elif mutation == "weights":
        payload["model_identities"]["checkpoint-25"]["adapter_model.safetensors"] = REF
    elif mutation == "coverage":
        payload["verdicts"]["P25"].pop("inc17-dialogue-K-1-t1")
    elif mutation == "ids":
        payload["verdicts"]["P13"]["other"] = payload["verdicts"]["P13"].pop(
            "inc17-dialogue-K-1-t1"
        )
    elif mutation == "metric":
        payload["verdicts"]["P25"]["inc17-dialogue-K-1-t1"]["usable"] = True
    elif mutation == "critical":
        payload["critical_by_case"]["P25"]["inc17-dialogue-K-1-t1"] = 0
    else:
        payload["factual_final_used"] = True
    if mutation != "hash":
        evidence = seal(payload)
    with pytest.raises(ValueError, match="broad_audit_invalid"):
        choose(evidence)


def test_external_expected_pin_cannot_be_resealed_with_the_report():
    with pytest.raises(ValueError):
        choose(report(), checksum="a" * 64)


def test_invalid_weight_pin_rejected():
    with pytest.raises(ValueError):
        select_campaign_parent(
            SHORT,
            broad_report=None,
            expected_report_sha256=None,
            reference_weight_sha256=REF,
            candidate_weight_sha256=REF,
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_metric",
        "string_metric",
        "missing_payload",
        "malformed_map",
        "malformed_id",
    ],
)
def test_strict_wider_schema_rejects_resealed_malformed_rows(mutation):
    evidence = report()
    payload = evidence["payload"]
    if mutation == "missing_metric":
        payload["verdicts"]["P25"]["inc17-dialogue-K-1-t1"].pop("usable")
    elif mutation == "string_metric":
        payload["verdicts"]["P25"]["inc17-dialogue-K-1-t1"]["usable"] = "1"
    elif mutation == "missing_payload":
        evidence = {"sha256": evidence["sha256"]}
    elif mutation == "malformed_map":
        payload["critical_by_case"] = []
    else:
        for section in ("verdicts", "critical_by_case"):
            for role in ("P13", "P25"):
                rows = payload[section][role]
                rows["other"] = rows.pop("inc17-dialogue-K-1-t1")
    if mutation != "missing_payload":
        evidence = seal(payload)
    with pytest.raises(ValueError):
        choose(evidence)
