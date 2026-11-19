"""Verified transfer of the accepted Luna phase-one archive to the price rubric."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path

from . import openrouter_semantic_judge as judge
from .profiles import stable_hash

FILE = "phase1-admission.json"
_PREVIOUS = {
    "2e3f0eb6ba9863348a119d9410c6557e13ff3a419ae96a44126f59e9da428b65",
    "2d0e270cb7e74c0c1db52c535552807824674411aeadf7f1983925046c62b2b6",
}
_CURRENT = "0b66969dbe6c827943ad5ad72be157261fbd5000c2983d148532386a38273b5f"
_PILOT = "c8148066ff3acefd724351a214cad54b8c8f6e32af25c69d7300502ae31f5606"
_PRICE_IMPACT = {"X0701", "X0702", "X0703", "X0704"}


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _checked_json(document: str, sha: str) -> dict:
    judge._require(_hash(document) == sha)
    return json.loads(document)


def _reserve(row: dict) -> Decimal:
    return judge._money(row["reserved_usd"])


def _verify_pilot(packet: dict, used_generations: set[str]) -> tuple[Decimal, Decimal]:
    protocol = _checked_json(packet["protocol"], packet["protocol_sha256"])
    panel = _checked_json(packet["panel"], _PILOT)
    result = json.loads(packet["result"])
    judge._require(
        protocol["panel_sha256"] == _PILOT
        and protocol["request_contract"] == judge._contract()
        and result["protocol_sha256"] == packet["protocol_sha256"]
        and result["status"] == "targeted_review_required"
        and result["rows"] == result["completed"] == 12
        and not result["mismatches"]
        and len(panel["cases"]) == 6
        and len(packet["receipts"]) == 12
    )
    rows = []
    for index, label in enumerate(panel["order"], 1):
        name = f"{index:03d}.json"
        row = _checked_json(packet["receipts"][name], result["receipt_hashes"][name])
        case = panel["cases"][label]
        body = case["body"]
        material = json.loads(body["messages"][1]["content"])
        judge._require(
            row["index"] == index
            and row["label"] == label
            and row["repeat"] == panel["order"][:index].count(label)
            and body
            == judge._control_request(
                {**material, "id": label}, {"text": material["candidate"]}
            )
        )
        decision = judge._verify_call(
            row, body, material["candidate"], packet["protocol_sha256"]
        )
        judge._require(
            {k: getattr(decision, k) for k in judge.DECISION_FIELDS} == case["expected"]
        )
        generation = row["response"]["id"]
        judge._require(generation not in used_generations)
        used_generations.add(generation)
        rows.append(row)
    known, unknown = judge._audit_costs(rows, protocol)
    judge._require(
        known == judge._money(result["actual_known_cost_usd"])
        and unknown == judge._money(result["unknown_reserved_usd"])
    )
    return known, unknown


def verify(root: Path, manifest: dict, protocol: dict) -> tuple[list[dict], dict]:
    """Recompute every accepted decision and account for its source exchange."""
    evidence = judge._bound(root, FILE, protocol["phase1_admission_sha256"])
    judge._require(
        judge._contract()["prompt_sha256"] == _CURRENT
        and evidence["policy"] == "luna-price-20261119"
        and evidence["reviewed_affected_ids"] == sorted(_PRICE_IMPACT)
        and evidence["phase1_files_sha256"] == stable_hash(manifest["files"])
        and len(evidence["receipts"]) == 156
    )
    source_contracts = {
        sha: _checked_json(data, sha)["request_contract"]
        for sha, data in evidence["source_protocols"].items()
    }
    order = judge._audit_order(root, manifest, phase1=True)
    rows: list[dict] = []
    generations: set[str] = set()
    affected = set()
    for index, entry in enumerate(order, 1):
        ident, split = entry["answer_id"], entry["split"]
        archived = evidence["receipts"][index - 1]
        row = _checked_json(archived["receipt"], archived["sha256"])
        case, answer = judge._jobs(root, manifest, split)[0][ident]
        current = judge._control_request(case, answer)
        messages = row["request"]["messages"]
        prompt = _hash(messages[0]["content"])
        source_sha = row["protocol_sha256"]
        contract = source_contracts[source_sha]
        judge._require(
            prompt in _PREVIOUS
            and contract["prompt_sha256"] == prompt
            and all(
                contract[k] == judge._contract()[k]
                for k in (
                    "judge",
                    "model",
                    "provider",
                    "endpoint",
                    "route",
                    "zdr_required",
                )
            )
            and row["index"] == archived["source_index"]
            and (row["index"] == index or ident == "X0503")
            and (ident == "X0503" or all(row.get(k) == v for k, v in entry.items()))
            and (
                ident != "X0503"
                or row.get("label") == "X0503"
                and row.get("repeat") == 1
            )
            and row["http_status"] == 200
            and not judge._rate_limit_attempts(row)
        )
        # The rubric may change; packet, schema, route and generation parameters must match.
        request = {**current, "messages": [messages[0], current["messages"][1]]}
        response = judge._verified_exchange(row, request, source_sha)
        decision, _ = judge.decode_with_evidence(response, request, answer["text"])
        judge._require(
            not judge._uncertain(decision) and response["id"] not in generations
        )
        generations.add(response["id"])
        if any(
            c["id"] in {"price", "fee"}
            and any(
                token in c["description"].lower()
                for token in ("nie podaj", "brak", "nieznan")
            )
            for c in case["criteria"]
        ):
            affected.add(ident)
        rows.append(
            {
                **row,
                **entry,
                "index": index,
                "status": "completed",
                "decision": decision.model_dump(),
            }
        )
    judge._require(affected == _PRICE_IMPACT)
    metrics = judge._audit_metrics(root, manifest, rows, phase1=True)
    judge._require(
        metrics
        == {
            k: v
            for k, v in manifest["thresholds"].items()
            if not k.startswith("holdout")
        }
    )
    known, unknown = _verify_pilot(evidence["pilot"], generations)
    historical_known = sum((judge._money(r["cost_usd"]) for r in rows), Decimal(0))
    carried = judge._money(protocol["initial_accounted_usd"])
    carried_unknown = judge._money(protocol["initial_unknown_reserved_usd"])
    judge._require(
        unknown <= carried_unknown
        and historical_known + known + carried_unknown <= carried
    )
    return rows, metrics
