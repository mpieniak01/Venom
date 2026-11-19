"""Exercise exact Markdown evidence and latest-source table attribution."""

from __future__ import annotations

import copy
import hashlib
import json
from decimal import Decimal

import pytest

from venom_core.services.training_experiments import openrouter_semantic_judge as judge
from venom_core.services.training_experiments import (
    semantic_openrouter_table_replay as replay,
)
from venom_core.services.training_experiments import table_evidence
from venom_core.services.training_experiments.profiles import stable_hash
from venom_core.services.training_experiments.semantic_judge_v5 import (
    observed_from_answer,
)

HEADER = "| Mila [paczki] | Bruno [paczki] | Dzień |"
ALIGNMENT = "|---:|---:|---|"
TABLE = f"{HEADER}\n{ALIGNMENT}\n| 8 | 11 | środa |"
SHORT_HEADER = "| Mila [paczki] | Bruno [paczki] |"
USER = (
    "W środę Mila ma odebrać 8 paczek, a Bruno 11 paczek. "
    "Podaj liczbę dla każdej osoby i dzień."
)


def _material(candidate: str = TABLE, user: str = USER) -> dict:
    return {
        "candidate": candidate,
        "criteria": [
            {"id": "mila", "description": "Mila odbiera 8 paczek."},
            {"id": "bruno", "description": "Bruno odbiera 11 paczek."},
            {"id": "day", "description": "Odbiór odbywa się w środę."},
        ],
        "messages": [{"role": "user", "content": user}],
    }


@pytest.mark.parametrize(
    ("criterion", "row", "header", "cell", "column"),
    [
        ("mila", "| 8", "Mila [paczki]", "8", 0),
        ("bruno", "| 8 | 11", "Bruno [paczki]", "11", 1),
    ],
)
@pytest.mark.parametrize(
    "clip", ["as_recorded", "header_left", "header_right", "all_edges"]
)
def test_table_recovers_recorded_discontinuous_quote(
    criterion: str, row: str, header: str, cell: str, column: int, clip: str
) -> None:
    header_quote, alignment = SHORT_HEADER, ALIGNMENT
    if clip in {"header_left", "all_edges"}:
        header_quote = header_quote.removeprefix("|").lstrip()
    if clip in {"header_right", "all_edges"}:
        header_quote = header_quote.removesuffix("|").rstrip()
    if clip == "all_edges":
        alignment = alignment.strip("|")
        row = row.strip("|").strip()
    observed = f"{header_quote}\n{alignment}\n{row}"
    assert not observed_from_answer(observed, "supported", TABLE)
    trace = table_evidence.compare(_material(), TABLE, criterion, observed, "supported")
    assert trace is not None
    assert trace["observed"] == observed
    assert trace["effective_observed"] == TABLE
    assert trace["raw_relation"] == trace["effective_relation"] == "supported"
    assert (trace["header"], trace["cell"], trace["column"]) == (header, cell, column)
    assert trace["source"]["value"] == cell
    assert trace["source"]["quote"] in USER


@pytest.mark.parametrize(
    ("criterion", "observed", "cell"),
    [
        ("mila", f"{SHORT_HEADER}\n{ALIGNMENT}\n| 11", "11"),
        ("bruno", f"{SHORT_HEADER}\n{ALIGNMENT}\n| 11 | 8", "8"),
    ],
)
def test_table_rejects_swapped_counts_even_when_review_supports(
    criterion: str, observed: str, cell: str
) -> None:
    candidate = TABLE.replace("| 8 | 11 |", "| 11 | 8 |")
    trace = table_evidence.compare(
        _material(candidate), candidate, criterion, observed, "supported"
    )
    assert trace is not None
    assert trace["raw_relation"] == "supported"
    assert trace["effective_relation"] == "contradicted"
    assert trace["cell"] == cell
    assert trace["effective_observed"] == candidate


@pytest.mark.parametrize(
    ("prefix", "day"), [("W piątek", "piątek"), ("We wtorek", "wtorek")]
)
def test_table_uses_names_and_units_rather_than_fixed_columns(
    prefix: str, day: str
) -> None:
    candidate = (
        f"| Dzień | Igor [sztuki] | Ela [sztuki] |\n|---|---:|---:|\n| {day} | 4 | 2 |"
    )
    observed = f"| Dzień | Ela [sztuki] |\n|---|---:|\n| {day} | 2"
    material = _material(candidate, f"{prefix} Ela odbiera 2 sztuki i Igor 4 sztuki.")
    material["criteria"] = [{"id": "first", "description": "Ela: 2 sztuki."}]
    trace = table_evidence.compare(material, candidate, "first", observed, "supported")
    assert trace is not None
    assert trace["column"] == 2
    assert trace["effective_relation"] == "supported"
    assert trace["effective_observed"] == candidate


@pytest.mark.parametrize(
    "observed",
    [
        "| Mila [paczki] |\n|---:|\n| 99",
        "| Mila [paczki] |\n|:---|\n| 8",
        "| Bruno [paczki] | Mila [paczki] |\n|---:|---:|\n| 11 | 8",
        "| Bruno [paczki] |\n|---:|\n| 11",
        "| Mila [paczki] | Mila [paczki] |\n|---:|---:|\n| 8 | 8",
        "Mila [paczki] | Bruno [paczki] |\n|---:|---:|---|\n| 99 | 11",
        "Bruno [paczki] | Mila [paczki]\n---:|---:\n11 | 8",
        "Mila [sztuki] | Bruno [paczki] |\n|---:|---:|---|\n| 8 | 11",
        "Mila odbiera 8 paczek.",
    ],
)
def test_table_never_recovers_fabricated_or_misattributed_proof(observed: str) -> None:
    assert not observed_from_answer(observed, "supported", TABLE)
    assert (
        table_evidence.compare(_material(), TABLE, "mila", observed, "supported")
        is None
    )


@pytest.mark.parametrize(
    "candidate",
    [
        TABLE.replace("Bruno [paczki]", "MILA [paczki]"),
        TABLE.removeprefix("|"),
        TABLE.removesuffix("|"),
        TABLE.replace("Bruno [paczki]", "Mila [sztuki]"),
        TABLE.replace("Bruno [paczki]", "Mila"),
        TABLE.replace("| 8 | 11 | środa |", "| 8 | środa |"),
        TABLE.replace("Mila [paczki]", "Mila [sztuki]"),
        TABLE.replace("| 8 |", "| +8 |"),
        TABLE.replace("|---:|---:|---|", "| 2 | 4 | 6 |"),
        f"{TABLE}\n| 1 | 2 | czwartek |",
        f"{TABLE}\nMila odbiera 9 paczek.",
        f"{TABLE}\n\n{TABLE}",
    ],
)
def test_table_declines_ambiguous_or_unrelated_structures(candidate: str) -> None:
    observed = f"{SHORT_HEADER}\n{ALIGNMENT}\n| 8"
    assert (
        table_evidence.compare(
            _material(candidate), candidate, "mila", observed, "supported"
        )
        is None
    )


@pytest.mark.parametrize(
    "user",
    [
        "Mila nie odbiera 8 paczek, a Bruno 11 paczek.",
        "Mila odbiera 8 paczek. Korekta: Mila odbiera 7 paczek.",
        "Mila odbiera 8 paczek. Ustalono dla Mili 7 paczek. Mila potwierdziła.",
        "Mila odbiera 7 paczek.",
        "Mila odbiera 8 sztuk.",
        "Podaj bieżącą liczbę paczek.",
    ],
)
def test_table_never_uses_old_or_conflicting_assignments(user: str) -> None:
    material = _material(user=user)
    material["messages"].insert(0, {"role": "user", "content": USER})
    material["messages"].append({"role": "assistant", "content": USER})
    assert table_evidence.compare(material, TABLE, "mila", TABLE, "supported") is None


def test_table_keeps_unrelated_criterion_for_ordinary_literal_validation() -> None:
    assert (
        table_evidence.compare(_material(), TABLE, "day", "środa", "supported") is None
    )


SORTING_SOURCE = (
    "Dla sortowania: Olga liczy 7 kopert, Daniel 12, odbiór partii w sobotę. "
    "Podaj liczbę każdej osoby i dzień."
)
SORTING_TABLE = "| Olga [koperty] | Daniel [koperty] | Dzień |\n|---:|---:|---|\n| 7 | 12 | sobota |"
SORTING_QUOTES = (
    "| Olga [koperty] | Daniel [koperty] |\n|---:|---:|---|\n| 7",
    "| Daniel [koperty] |\n|---:|---:|---|\n| 12",
)


def _sorting_material(user=SORTING_SOURCE):
    return {
        "messages": [{"role": "user", "content": user}],
        "criteria": [
            {"id": "olga", "description": "Olga liczy 7 kopert."},
            {"id": "daniel", "description": "Daniel liczy 12 kopert."},
            {"id": "day", "description": "Odbiór w sobotę."},
        ],
    }


@pytest.mark.parametrize(
    ("field", "quote", "column"),
    [("olga", SORTING_QUOTES[0], 0), ("daniel", SORTING_QUOTES[1], 1)],
)
def test_sorting_count_projection_binds_each_column(field, quote, column):
    trace = table_evidence.compare(
        _sorting_material(), SORTING_TABLE, field, quote, "supported"
    )
    assert trace is not None
    assert trace["effective_observed"] == SORTING_TABLE
    assert trace["effective_relation"] == "supported"
    assert trace["column"] == column
    assert trace["source"]["quote"] in SORTING_SOURCE


def test_sorting_table_rejects_wrong_source_or_column():
    daniel = SORTING_QUOTES[1]
    for damaged in (
        daniel.replace("| 12", "| 7"),
        daniel.replace("[koperty]", "[paczki]"),
        daniel.replace("Daniel", "Olga"),
    ):
        assert (
            table_evidence.compare(
                _sorting_material(), SORTING_TABLE, "daniel", damaged, "supported"
            )
            is None
        )
    conflicting = SORTING_SOURCE.replace("Daniel 12", "Daniel 12 lub 14")
    assert (
        table_evidence.compare(
            _sorting_material(conflicting), SORTING_TABLE, "daniel", daniel, "supported"
        )
        is None
    )
    swapped = SORTING_TABLE.replace("| 7 | 12 |", "| 12 | 7 |")
    trace = table_evidence.compare(
        _sorting_material(),
        swapped,
        "daniel",
        daniel.replace("| 12", "| 7"),
        "supported",
    )
    assert trace is not None
    assert trace["effective_relation"] == "contradicted"


@pytest.mark.parametrize("day", ["sobota", "wtorek"])
def test_sorting_projection_with_full_row_recovers_counts_and_day(day):
    candidate = SORTING_TABLE.replace("sobota", day).replace("| 7 | 12", "| 12 | 7")
    observed = candidate.replace(" | Dzień |", " |")
    for field in ("olga", "daniel", "day"):
        proof = table_evidence.compare(
            _sorting_material(), candidate, field, observed, "supported"
        )
        assert proof is not None
        assert proof["effective_observed"] == candidate
        assert proof["effective_relation"] == (
            "supported" if field == "day" and day == "sobota" else "contradicted"
        )
    modified_day = observed.replace(day, "piątek")
    assert (
        table_evidence.compare(
            _sorting_material(), candidate, "day", modified_day, "supported"
        )
        is None
    )


def test_sorting_projection_refuses_later_day_correction():
    source = SORTING_SOURCE + " Korekta: odbiór jest we wtorek."
    observed = SORTING_TABLE.replace(" | Dzień |", " |")
    assert (
        table_evidence.compare(
            _sorting_material(source), SORTING_TABLE, "day", observed, "supported"
        )
        is None
    )


@pytest.mark.parametrize("number", ["٨", "８"])
@pytest.mark.parametrize("location", ["candidate", "source", "criterion"])
def test_table_counts_remain_ascii_only(number, location):
    candidate = (
        TABLE.replace("| 8 |", f"| {number} |") if location == "candidate" else TABLE
    )
    material = _material(candidate)
    if location == "source":
        material["messages"][0]["content"] = USER.replace(
            "8 paczek", f"{number} paczek"
        )
    elif location == "criterion":
        material["criteria"][0]["description"] = f"Mila odbiera {number} paczek."
    assert (
        table_evidence.compare(material, candidate, "mila", candidate, "supported")
        is None
    )


def test_sorting_implicit_unit_does_not_cross_mixed_explicit_units():
    source = "Dla sortowania: Mila liczy 8 paczek, Bruno 11 sztuk, Olga 4."
    assert table_evidence._assignment_clauses(source) == []


@pytest.mark.parametrize(
    ("singular", "plural", "genitive"),
    [("przesyłka", "przesyłki", "przesyłek"), ("pudełko", "pudełka", "pudełek")],
)
def test_table_unit_aliases_keep_canonical_attribution(singular, plural, genitive):
    candidate = TABLE.replace("paczki", plural)
    material = _material(candidate, f"Mila odbiera 8 {genitive}.")
    material["criteria"][0]["description"] = f"Mila odbiera 8 {singular}."
    trace = table_evidence.compare(material, candidate, "mila", candidate, "supported")
    assert trace is not None
    assert trace["source"]["unit"] == plural
    assert trace["effective_relation"] == "supported"


@pytest.mark.parametrize(
    "withdrawal",
    ["Anuluję odbiór.", "Wycofuję cały przydział.", "Odwołuję wszystkie ustalenia."],
)
def test_table_invalidates_global_withdrawal_without_repeating_entity(withdrawal):
    material = _material(user=USER + " " + withdrawal)
    assert table_evidence.compare(material, TABLE, "mila", TABLE, "supported") is None


def _sealed_document(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return raw, hashlib.sha256(raw.encode()).hexdigest()


def _replay_panel(case, *, confirmation=False):
    candidates = {
        "ND05-A2": (SORTING_TABLE, ("supported", "supported")),
        "ND05-swap": (
            SORTING_TABLE.replace("| 7 | 12 |", "| 12 | 7 |"),
            ("contradicted", "contradicted"),
        ),
        "ND05-missing": (
            "| Olga [koperty] | Dzień |\n|---:|---|\n| 7 | sobota |",
            ("supported", "omitted"),
        ),
        "ND05-reordered": (
            "| Daniel [koperty] | Dzień | Olga [koperty] |\n|---:|---|---:|\n| 12 | sobota | 7 |",
            ("supported", "supported"),
        ),
    }
    labels = ["ND05-swap"] if confirmation else list(candidates)
    order = labels * 2
    cases = {}
    for label in labels:
        candidate, (olga, daniel) = candidates[label]
        cases[label] = {
            "body": judge._control_request(case, {"text": candidate}),
            "expected": {
                "atoms": {"olga": olga, "daniel": daniel, "day": "supported"},
                "injection": False,
                "natural_ok": True,
                "polish_ok": True,
                "unsupported": "yes" if label == "ND05-swap" else "no",
            },
        }
    panel, panel_sha = _sealed_document({"cases": cases, "order": order})
    protocol, protocol_sha = _sealed_document(
        {
            "kind": "targeted_regression",
            "request_contract": judge._contract(),
            "panel_sha256": panel_sha,
            "rate_limit": {"backoff_seconds": [1, 2], "max_retries_per_audit": 2},
        }
    )
    receipts, hashes = {}, {}
    for index, label in enumerate(order, 1):
        text = candidates[label][0]
        item = cases[label]
        body = item["body"]
        value = {
            "checks": {
                field: {
                    "observed": "brak w odpowiedzi" if relation == "omitted" else text,
                    "relation": "omitted" if relation == "omitted" else "supported",
                }
                for field, relation in item["expected"]["atoms"].items()
            },
            "additional_claims": [],
            "injection": False,
            "polish_ok": True,
            "natural_ok": True,
            "reason": "synthetic offline receipt",
        }
        response = {
            "id": f"{'confirmation' if confirmation else 'pilot'}-{index}",
            "model": judge.MODEL,
            "provider": judge.PROVIDER,
            "choices": [
                {"finish_reason": "stop", "message": {"content": json.dumps(value)}}
            ],
            "usage": {"cost": 0.00001},
        }
        decision, evidence = judge.decode_with_evidence(response, body, text)
        row = {
            "index": index,
            "label": label,
            "repeat": order[:index].count(label),
            "call_id": response["id"],
            "protocol_sha256": protocol_sha,
            "request": body,
            "request_sha256": stable_hash(body),
            "response": response,
            "response_sha256": stable_hash(response),
            "status": "completed",
            "decision": decision.model_dump(),
            **evidence,
            "cost_usd": "0.00001",
            "reserved_usd": str(judge.reserve(body)),
            "started_at": "2026-01-01T00:00:00+00:00",
            "finished_at": "2026-01-01T00:00:01+00:00",
        }
        if index == 2 and not confirmation:
            row.update(status="rejected_decision", error_type="decoder_invalid")
            row.pop("decision")
            for field in judge.ReviewEvidence.__annotations__:
                row.pop(field, None)
        name = f"{index:03d}.json"
        receipts[name], hashes[name] = _sealed_document(row)
    mismatches = (
        []
        if confirmation
        else [{"index": 2, "label": "ND05-swap", "differences": ["decoder_invalid"]}]
    )
    result, result_sha = _sealed_document(
        {
            "status": "targeted_review_required"
            if confirmation
            else "targeted_regression_failed",
            "protocol_sha256": protocol_sha,
            "mismatches": mismatches,
            "rows": len(order),
            "completed": len(order) - len(mismatches),
            "receipt_hashes": hashes,
            "actual_known_cost_usd": str(Decimal("0.00001") * len(order)),
            "unknown_reserved_usd": "0",
        }
    )
    return {
        "panel": panel,
        "protocol": protocol,
        "protocol_sha256": protocol_sha,
        "result": result,
        "result_sha256": result_sha,
        "receipts": receipts,
    }


@pytest.fixture
def table_replay_archive(tmp_path, monkeypatch):
    monkeypatch.setattr(
        judge.httpx,
        "Client",
        lambda **_: pytest.fail("offline table replay contacted provider"),
    )
    case = {"id": "ND05-A2", **_sorting_material()}
    source_protocol, source_sha = _sealed_document(
        {
            "phase1_admission_sha256": "a" * 64,
            "budget_usd": "1",
            "implementation_sha256": "old implementation",
            "audit_runner_sha256": "old runner",
        }
    )
    original = {
        "protocol_sha256": source_sha,
        "status": "failed_qualification",
        "holdout_opened": True,
        "rows": 228,
        "metrics": {"holdout_full": 71, "holdout_stable_groups": 23},
        "phase1_result_sha256": "b" * 64,
        "receipt_hashes": {"198.json": "c" * 64},
        "actual_known_cost_usd": "0.01",
        "unknown_reserved_usd": "0",
        "carried_unknown_reserved_usd": "0",
        "accounted_usd": "0.1",
        "deviations": {
            "by_case": [
                {
                    "index": 198,
                    "answer_id": "ND05-A2",
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
        },
    }
    source_result, source_result_sha = _sealed_document(original)
    packet = {
        "source_protocol": source_protocol,
        "source_protocol_sha256": source_sha,
        "source_result": source_result,
        "source_result_sha256": source_result_sha,
        "pilot": _replay_panel(case),
        "confirmation": _replay_panel(case, confirmation=True),
    }
    raw, sha = _sealed_document(packet)
    (tmp_path / replay.FILE).write_text(raw, encoding="utf-8")
    protocol = {
        **json.loads(source_protocol),
        "implementation_sha256": "new implementation",
        "audit_runner_sha256": "new runner",
        "table_replay_sha256": sha,
    }
    result = {
        **original,
        "table_pilot_known_usd": "0.00010",
        "table_pilot_unknown_usd": "0",
        "accounted_with_table_pilot_usd": "0.10010",
    }
    return tmp_path, case, packet, protocol, result


def _reseal_replay(tmp_path, packet, protocol):
    raw, sha = _sealed_document(packet)
    (tmp_path / replay.FILE).write_text(raw, encoding="utf-8")
    protocol["table_replay_sha256"] = sha


def _replace_panel_receipt(panel, name, row):
    result = json.loads(panel["result"])
    panel["receipts"][name], result["receipt_hashes"][name] = _sealed_document(row)
    panel["result"], panel["result_sha256"] = _sealed_document(result)


def test_table_replay_preserves_holdout_receipts_and_recomputes_fixed_decision(
    table_replay_archive,
):
    root, case, packet, protocol, result = table_replay_archive
    frozen = copy.deepcopy(result["receipt_hashes"])
    used = {"earlier-holdout-generation"}
    assert (
        replay.source(root, protocol, result, case, used)
        == packet["source_protocol_sha256"]
    )
    assert len(used) == 11
    assert result["receipt_hashes"] == frozen
    panel = packet["pilot"]
    ordinary = json.loads(panel["receipts"]["001.json"])
    body = ordinary["request"]
    assert (
        replay.decode(ordinary, body, SORTING_TABLE, panel["protocol_sha256"])
        == ordinary
    )
    rejected = {
        **ordinary,
        "index": 198,
        "answer_id": "ND05-A2",
        "repeat": 2,
        "status": "rejected_decision",
        "error_type": "decoder_invalid",
    }
    rejected.pop("decision")
    for field in judge.ReviewEvidence.__annotations__:
        rejected.pop(field, None)
    repaired = replay.decode(rejected, body, SORTING_TABLE, panel["protocol_sha256"])
    assert rejected["status"] == "rejected_decision"
    assert repaired["status"] == "completed"
    assert repaired["decision"]["atoms"] == {
        "olga": "supported",
        "daniel": "supported",
        "day": "supported",
    }
    assert repaired["field_evidence"]["olga"]["source"]["quote"] in SORTING_SOURCE
    assert repaired["response_sha256"] == rejected["response_sha256"]


@pytest.mark.parametrize(
    "damage",
    [
        "unsealed_bytes",
        "receipt_hashes",
        "phase1_result",
        "holdout_not_opened",
        "extra_failure",
        "overspend",
    ],
)
def test_table_replay_rejects_resealed_holdout_or_budget_substitution(
    table_replay_archive, damage
):
    root, case, packet, protocol, result = table_replay_archive
    if damage == "unsealed_bytes":
        (root / replay.FILE).write_text("{}", encoding="utf-8")
    elif damage == "receipt_hashes":
        result["receipt_hashes"] = {"198.json": "d" * 64}
    elif damage == "phase1_result":
        result["phase1_result_sha256"] = "d" * 64
    elif damage == "overspend":
        result["table_pilot_known_usd"] = "0.00009"
    else:
        original = json.loads(packet["source_result"])
        if damage == "holdout_not_opened":
            original["holdout_opened"] = False
        else:
            original["deviations"]["by_case"].append(
                copy.deepcopy(original["deviations"]["by_case"][0])
            )
        packet["source_result"], packet["source_result_sha256"] = _sealed_document(
            original
        )
        _reseal_replay(root, packet, protocol)
    with pytest.raises(ValueError, match=judge.ERROR):
        replay.source(root, protocol, result, case, set())


@pytest.mark.parametrize(
    "damage",
    [
        "request",
        "repeat",
        "generation",
        "rejected_status",
        "confirmation_proof",
        "panel_cost",
    ],
)
def test_table_replay_checks_all_panel_exchanges_and_independent_confirmation(
    table_replay_archive, damage
):
    root, case, packet, protocol, result = table_replay_archive
    panel = (
        packet["confirmation"] if damage == "confirmation_proof" else packet["pilot"]
    )
    name = "002.json" if damage == "rejected_status" else "001.json"
    row = json.loads(panel["receipts"][name])
    used = set()
    if damage == "request":
        row["request"]["model"] = "different-model"
        row["request_sha256"] = stable_hash(row["request"])
    elif damage == "repeat":
        row["repeat"] = 2
    elif damage == "generation":
        used.add(row["response"]["id"])
    elif damage == "rejected_status":
        row["error_type"] = "different_failure"
    elif damage == "confirmation_proof":
        row["field_evidence"] = {}
    else:
        panel_result = json.loads(panel["result"])
        panel_result["actual_known_cost_usd"] = "0"
        panel["result"], panel["result_sha256"] = _sealed_document(panel_result)
    if damage != "panel_cost":
        _replace_panel_receipt(panel, name, row)
    _reseal_replay(root, packet, protocol)
    with pytest.raises(ValueError, match=judge.ERROR):
        replay.source(root, protocol, result, case, used)


@pytest.mark.parametrize(
    "damage",
    ["wrong_case", "wrong_repeat", "invented_proof", "wrong_slot", "normal_proof"],
)
def test_table_repair_is_limited_to_the_single_archived_decoder_failure(
    table_replay_archive, damage
):
    _, _, packet, _, _ = table_replay_archive
    panel = packet["pilot"]
    ordinary = json.loads(panel["receipts"]["001.json"])
    row = {
        **ordinary,
        "index": 198,
        "answer_id": "ND05-A2",
        "repeat": 2,
        "status": "rejected_decision",
        "error_type": "decoder_invalid",
    }
    row.pop("decision")
    for field in judge.ReviewEvidence.__annotations__:
        row.pop(field, None)
    if damage == "wrong_case":
        row["answer_id"] = "other-case"
    elif damage == "wrong_repeat":
        row["repeat"] = 1
    elif damage == "invented_proof":
        row["field_evidence"] = ordinary["field_evidence"]
    elif damage == "wrong_slot":
        row["index"] = 197
    else:
        row = copy.deepcopy(ordinary)
        row["field_evidence"] = {}
    with pytest.raises(ValueError, match=judge.ERROR):
        replay.decode(row, ordinary["request"], SORTING_TABLE, panel["protocol_sha256"])
