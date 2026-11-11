"""Rubric scoring preserves semantics and rejects incomplete evaluation evidence."""

import copy

import pytest

from scripts.academy.omni_pl_chat_scoring import aggregate


def fixture():
    case = {
        "record_id": "new",
        "task": "source",
        "criteria": [
            {"id": "time", "kind": "content"},
            {"id": "citation", "kind": "format"},
        ],
    }
    answers = [
        {
            "case": case,
            "answers": {
                "A": {"text": "Start o szesnastej.", "finish": "stop", "error": None}
            },
        }
    ]
    grades = [
        {
            "record_id": "new",
            "label": "A",
            "criteria": {"time": True, "citation": False},
            "polish_ok": True,
            "natural_ok": True,
            "critical_error": False,
            "reason": "Poprawna parafraza godziny 16:00; brakuje wymaganego źródła.",
        }
    ]
    return [case], answers, grades


def test_paraphrase_and_missing_citation_are_reported_separately():
    cases, answers, grades = fixture()
    total = aggregate(cases, answers, grades)["summaries"]["A"]["total"]
    assert total["semantic"] == total["usable"] == 1
    assert total["passed"] == total["format"] == 0


def test_wrong_fact_and_critical_error_cannot_be_hidden_by_correct_format():
    cases, answers, grades = fixture()
    grades[0]["criteria"] = {"time": False, "citation": True}
    grades[0]["critical_error"] = True
    total = aggregate(cases, answers, grades)["summaries"]["A"]["total"]
    assert total["format"] == 1
    assert total["semantic"] == total["passed"] == 0
    assert total["critical"] == 1


@pytest.mark.parametrize("change", ["missing", "duplicate", "criterion", "truthy"])
def test_missing_or_ambiguous_judgments_fail(change):
    cases, answers, grades = fixture()
    if change == "missing":
        grades = []
    elif change == "duplicate":
        grades.append(copy.deepcopy(grades[0]))
    elif change == "criterion":
        del grades[0]["criteria"]["time"]
    else:
        grades[0]["criteria"]["time"] = "false"
    with pytest.raises(ValueError):
        aggregate(cases, answers, grades)


@pytest.mark.parametrize("field,value", [("finish", "length"), ("error", "timeout")])
def test_runtime_failures_stay_in_the_denominator(field, value):
    cases, answers, grades = fixture()
    answers[0]["answers"]["A"][field] = value
    grades[0]["criteria"]["citation"] = True
    total = aggregate(cases, answers, grades)["summaries"]["A"]["total"]
    assert total["n"] == total["runtime_or_length_failure"] == 1
    assert total["semantic"] == total["passed"] == 0


def test_each_variant_must_have_every_case():
    cases, answers, grades = fixture()
    answers[0]["answers"]["B"] = copy.deepcopy(answers[0]["answers"]["A"])
    with pytest.raises(ValueError, match="judgments"):
        aggregate(cases, answers, grades)
