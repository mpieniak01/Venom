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
