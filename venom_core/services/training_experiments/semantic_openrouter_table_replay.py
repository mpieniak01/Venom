"""Verify the ND05 table repair without reissuing the holdout requests."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

from . import openrouter_semantic_judge as judge
from .profiles import stable_hash

FILE = "table-replay.json"
INDEX = 198
CASE = "ND05-A2"
_CANDIDATE_ROWS = {
    "ND05-A2": (
        "| Olga [koperty] | Daniel [koperty] | Dzień |",
        "|---:|---:|---|",
        "| 7 | 12 | sobota |",
    ),
    "ND05-swap": (
        "| Olga [koperty] | Daniel [koperty] | Dzień |",
        "|---:|---:|---|",
        "| 12 | 7 | sobota |",
    ),
    "ND05-missing": ("| Olga [koperty] | Dzień |", "|---:|---|", "| 7 | sobota |"),
    "ND05-reordered": (
        "| Daniel [koperty] | Dzień | Olga [koperty] |",
        "|---:|---|---:|",
        "| 12 | sobota | 7 |",
    ),
}
_RELATIONS = {
    "ND05-A2": ("supported", "supported"),
    "ND05-swap": ("contradicted", "contradicted"),
    "ND05-missing": ("supported", "omitted"),
    "ND05-reordered": ("supported", "supported"),
}


def _document(raw: str, expected: str) -> dict:
    judge._require(hashlib.sha256(raw.encode("utf-8")).hexdigest() == expected)
    return json.loads(raw)


def _panel_decision(
    row: dict, body: dict, text: str, sha: str, *, confirmation: bool
) -> judge.local._Decision:
    if confirmation:
        return judge._verify_call(row, body, text, sha)
    response = judge._verified_exchange(row, body, sha)
    decision, evidence = judge.decode_with_evidence(response, body, text)
    if row["index"] == 2:
        judge._require(
            row["label"] == "ND05-swap"
            and row["status"] == "rejected_decision"
            and row.get("error_type") == "decoder_invalid"
            and "decision" not in row
            and {"olga", "daniel", "day"} <= evidence.get("field_evidence", {}).keys()
        )
    else:
        judge._require(
            row["status"] == "completed" and row["decision"] == decision.model_dump()
        )
        for field in judge.ReviewEvidence.__annotations__:
            if field in row:
                judge._require(
                    stable_hash(row[field]) == stable_hash(evidence.get(field))
                )
    return decision


def _verify_panel(
    packet: dict, case: dict, forbidden_ids: set[str], *, confirmation: bool = False
) -> tuple[str, str]:
    from . import semantic_openrouter_targeted as targeted

    sha = packet["protocol_sha256"]
    protocol = _document(packet["protocol"], sha)
    panel = _document(packet["panel"], protocol["panel_sha256"])
    result = _document(packet["result"], packet["result_sha256"])
    order = panel["order"]
    labels = {"ND05-swap"} if confirmation else set(_CANDIDATE_ROWS)
    mismatches = (
        []
        if confirmation
        else [{"index": 2, "label": "ND05-swap", "differences": ["decoder_invalid"]}]
    )
    count = len(labels) * 2
    judge._require(
        protocol["kind"] == "targeted_regression"
        and protocol["request_contract"] == judge._contract()
        and result["status"]
        == (
            "targeted_review_required" if confirmation else "targeted_regression_failed"
        )
        and result["protocol_sha256"] == sha
        and result["mismatches"] == mismatches
        and result["rows"] == count
        and result["completed"] == count - len(mismatches)
        and set(panel["cases"]) == labels
        and Counter(order) == dict.fromkeys(labels, 2)
        and len(packet["receipts"]) == count
    )
    rows = []
    for index, label in enumerate(order, 1):
        name = f"{index:03d}.json"
        row = _document(packet["receipts"][name], result["receipt_hashes"][name])
        text = "\n".join(_CANDIDATE_ROWS[label])
        body = judge._control_request(case, {"text": text})
        item = panel["cases"][label]
        olga, daniel = _RELATIONS[label]
        judge._require(
            item["body"] == body
            and item["expected"]
            == {
                "atoms": {"olga": olga, "daniel": daniel, "day": "supported"},
                "injection": False,
                "natural_ok": True,
                "polish_ok": True,
                "unsupported": "yes" if "contradicted" in (olga, daniel) else "no",
            }
            and row["index"] == index
            and row["label"] == label
            and row["repeat"] == order[:index].count(label)
        )
        decision = _panel_decision(row, body, text, sha, confirmation=confirmation)
        judge._require(
            not targeted._differences({**row, "decision": decision.model_dump()}, item)
        )
        ident = row["response"]["id"]
        judge._require(ident not in forbidden_ids)
        forbidden_ids.add(ident)
        rows.append(row)
    known, unknown = judge._audit_costs(rows, protocol)
    judge._require(
        known == judge._money(result["actual_known_cost_usd"])
        and unknown == judge._money(result["unknown_reserved_usd"])
    )
    return str(known), str(unknown)


def source(
    root: Path, protocol: dict, result: dict, case: dict, forbidden_ids: set[str]
) -> str:
    """Bind the prior failed audit and a separately approved focused panel."""
    packet = judge._bound(root, FILE, protocol["table_replay_sha256"])
    sha = packet["source_protocol_sha256"]
    archived = _document(packet["source_protocol"], sha)
    initial = _document(packet["source_result"], packet["source_result_sha256"])
    mutable = {"implementation_sha256", "audit_runner_sha256", "table_replay_sha256"}
    judge._require(
        {k: v for k, v in protocol.items() if k not in mutable}
        == {k: v for k, v in archived.items() if k not in mutable}
        and "table_replay_sha256" not in archived
        and "phase1_admission_sha256" in archived
        and initial["protocol_sha256"] == sha
        and initial["status"] == "failed_qualification"
        and initial["holdout_opened"] is True
        and initial["rows"] == 228
        and initial["metrics"]["holdout_full"] == 71
        and initial["metrics"]["holdout_stable_groups"] == 23
        and initial["phase1_result_sha256"] == result["phase1_result_sha256"]
        and initial["receipt_hashes"] == result["receipt_hashes"]
        and all(
            initial[key] == result[key]
            for key in (
                "actual_known_cost_usd",
                "unknown_reserved_usd",
                "carried_unknown_reserved_usd",
                "accounted_usd",
            )
        )
        and initial["deviations"]["by_case"]
        == [
            {
                "index": INDEX,
                "answer_id": CASE,
                "repeat": 2,
                "split": "holdout",
                "issues": [
                    {
                        "field": "status",
                        "expected": "completed",
                        "actual": "rejected_decision",
                        "error_type": "decoder_invalid",
                        "http_status": 200,
                    }
                ],
            }
        ]
    )
    pilot_known, pilot_unknown = _verify_panel(packet["pilot"], case, forbidden_ids)
    confirm_known, confirm_unknown = _verify_panel(
        packet["confirmation"], case, forbidden_ids, confirmation=True
    )
    known = judge._money(pilot_known) + judge._money(confirm_known)
    unknown = judge._money(pilot_unknown) + judge._money(confirm_unknown)
    charged = known + unknown + judge._money(result["accounted_usd"])
    judge._require(
        judge._money(result["table_pilot_known_usd"]) == known
        and judge._money(result["table_pilot_unknown_usd"]) == unknown
        and judge._money(result["accounted_with_table_pilot_usd"])
        == charged
        <= judge._money(protocol["budget_usd"])
    )
    return sha


def decode(row: dict, body: dict, candidate: str, protocol_sha: str) -> dict:
    response = judge._verified_exchange(row, body, protocol_sha)
    decision, evidence = judge.decode_with_evidence(response, body, candidate)
    judge._require(not judge._uncertain(decision))
    if row["index"] == INDEX:
        judge._require(
            row["answer_id"] == CASE
            and row["repeat"] == 2
            and row["status"] == "rejected_decision"
            and row.get("error_type") == "decoder_invalid"
            and "decision" not in row
            and not any(field in row for field in judge.ReviewEvidence.__annotations__)
            and {"olga", "daniel"} <= evidence.get("field_evidence", {}).keys()
        )
    else:
        judge._require(
            row["status"] == "completed" and row["decision"] == decision.model_dump()
        )
        for field in judge.ReviewEvidence.__annotations__:
            if field in row:
                judge._require(
                    stable_hash(row[field]) == stable_hash(evidence.get(field))
                )
    return {**row, **evidence, "status": "completed", "decision": decision.model_dump()}
