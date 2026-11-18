"""Exercise exact Markdown evidence and latest-source table attribution."""

from __future__ import annotations

import pytest

from venom_core.services.training_experiments import table_evidence
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
def test_table_recovers_recorded_discontinuous_quote(
    criterion: str, row: str, header: str, cell: str, column: int
) -> None:
    observed = f"{SHORT_HEADER}\n{ALIGNMENT}\n{row}"
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


def test_table_uses_names_and_units_rather_than_fixed_columns() -> None:
    candidate = (
        "| Dzień | Igor [sztuki] | Ela [sztuki] |\n|---|---:|---:|\n| piątek | 4 | 2 |"
    )
    observed = "| Dzień | Ela [sztuki] |\n|---|---:|\n| piątek | 2"
    material = _material(candidate, "W piątek Ela odbiera 2 sztuki i Igor 4 sztuki.")
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
