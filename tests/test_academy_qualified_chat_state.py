import pytest

from venom_core.api.schemas.llm_simple import HistoryMessage
from venom_core.services.academy.qualified_chat_evidence import evidence_reply
from venom_core.services.academy.qualified_chat_explanations import explanation_hint
from venom_core.services.academy.qualified_chat_fit import fit_hint
from venom_core.services.academy.qualified_chat_mechanisms import (
    ice_melting_reply,
    thermal_followup_reply,
)
from venom_core.services.academy.qualified_chat_schedule import (
    draft_time_revision,
    route_shift,
)


def _user(content: str) -> HistoryMessage:
    return HistoryMessage(role="user", content=content)


def test_explicit_single_sentence_overrides_the_compact_explanation_format():
    assert (
        explanation_hint("Wyjaśnij kondensację w jednym zdaniu.", [], token_budget=96)
        == ""
    )
    assert "Dwa krótkie zdania" in explanation_hint(
        "Wyjaśnij kondensację.", [], token_budget=96
    )


@pytest.mark.parametrize(
    ("latest", "expected"),
    [
        ("Ten kroplownik działa już prawidłowo.", "Czy słaby przepływ"),
        ("Na linii B ten kroplownik działa już prawidłowo.", "drożność wskazanego"),
        ("Czy ten kroplownik działa już prawidłowo?", "drożność wskazanego"),
    ],
)
def test_single_emitter_recovery_is_an_assertion_about_the_same_zone(latest, expected):
    answer = evidence_reply(
        "Co sprawdzić w nawadnianiu linii A?",
        [
            _user(
                "Na linii A jeden kroplownik działa słabo, a pozostałe działają normalnie."
            ),
            _user(latest),
        ],
    )
    assert answer is not None
    assert expected in answer


@pytest.mark.parametrize(
    ("assertion", "expected"),
    [
        ("Filtr jest czysty, bez osadu.", "Zmierz ciśnienie"),
        ("Filtr zawiera osad.", "Oczyść zabrudzony filtr"),
    ],
)
def test_irrigation_filter_distinguishes_presence_and_absence_of_deposit(
    assertion, expected
):
    answer = evidence_reply(
        "Co sprawdzić w nawadnianiu linii A?",
        [
            _user("Na linii A kilka kroplowników ma słaby przepływ."),
            _user(assertion),
        ],
    )
    assert answer is not None
    assert answer.startswith(expected)


@pytest.mark.parametrize(
    ("observation", "expected"),
    [
        ("Na linii A kilka kroplowników ma słaby przepływ.", "Sprawdź filtr wspólny"),
        ("Czy na linii A kilka kroplowników ma słaby przepływ?", "Czy słaby przepływ"),
        ("Jeśli kilka kroplowników ma słaby przepływ.", "Czy słaby przepływ"),
    ],
)
def test_irrigation_uses_current_assertions_and_skips_questions(observation, expected):
    answer = evidence_reply(f"{observation} Co sprawdzić przy nawadnianiu linii A?", [])
    assert answer is not None
    assert answer.startswith(expected)


def test_ventilation_advice_requires_the_latest_observed_mirror_fog():
    baseline = [_user("Lustro w łazience paruje."), _user("Wyciąg jest sprawny.")]
    prompt = "Jak ograniczyć to przed prysznicem?"
    reply = evidence_reply(prompt, baseline)
    assert reply is not None
    assert reply.startswith("Włącz wyciąg")
    correction = _user("Poprawka: lustro jednak nie paruje.")
    assert evidence_reply(prompt, [*baseline, correction]) is None
    reply = evidence_reply(
        prompt, [*baseline, correction, _user("Lustro znów paruje.")]
    )
    assert reply is not None
    assert reply.startswith("Włącz wyciąg")


@pytest.mark.parametrize(
    ("initial", "first_shift", "second_shift", "answer"),
    [
        (
            "23:50",
            "Przesuń spotkanie o 20 minut później.",
            "Przesuń spotkanie o 5 minut później.",
            "Spotkanie: następnego dnia o 00:15.",
        ),
        (
            "00:10",
            "Cofnij spotkanie o 20 minut.",
            "Cofnij spotkanie o 5 minut.",
            "Spotkanie: poprzedniego dnia o 23:45.",
        ),
        (
            "23:50",
            "Przesuń spotkanie o 20 minut później.",
            "Cofnij spotkanie o 15 minut.",
            "Spotkanie: o 23:55.",
        ),
        (
            "08:05",
            "Przesuń spotkanie o 20 minut później.",
            "Przesuń spotkanie o 5 minut później.",
            "Spotkanie: o 08:30.",
        ),
    ],
)
def test_schedule_keeps_the_day_offset_from_the_original_declaration(
    initial, first_shift, second_shift, answer
):
    assert (
        route_shift(
            second_shift,
            [
                {"role": "user", "content": f"Zapisz spotkanie: o {initial}."},
                {"role": "user", "content": first_shift},
            ],
        )
        == answer
    )


@pytest.mark.parametrize(
    ("previous_time", "expected"),
    [
        ("8:05", "Proszę, przypomnij mi o sadzonkach o 09:35."),
        ("08:05", "Proszę, przypomnij mi o sadzonkach o 09:35."),
        ("08:15", None),
        ("08:05 lub 9:05", None),
    ],
)
def test_reminder_comparison_normalizes_leading_zero_without_accepting_ambiguity(
    previous_time, expected
):
    assert (
        draft_time_revision(
            "Zmień godzinę w szkicu na 9:35.",
            [
                _user(f"Zmień godzinę w szkicu na {previous_time}."),
                HistoryMessage(
                    role="assistant",
                    content="Proszę, przypomnij mi o sadzonkach o 08:05.",
                ),
            ],
        )
        == expected
    )


def test_fit_uses_inner_dimensions_for_fit_without_reusing_them_for_area():
    request = "Czy kartka się zmieści? Nie mogę jej zginać."
    external = [_user(f"Pudełko ma na zewnątrz 20 × 30 cm. {request}")]
    internal = [_user(f"Pudełko ma wewnątrz 20 × 30 cm. {request}")]
    assert fit_hint("Kartka ma 20 × 30 cm.", external) == ""
    assert "mieści się bez składania" in fit_hint("20 × 30 cm", internal)
    assert fit_hint("Prostokąt ma 10 × 15 cm. Oblicz jego pole.", internal) == ""


def test_explicit_temperature_disables_the_ice_melting_template():
    question = "Wyjaśnij w dwóch zdaniach, czy w identycznych warunkach lód topi się szybciej na aluminium niż na korku."
    assert ice_melting_reply(f"Oba podłoża mają -10°C. {question}", []) is None
    reply = ice_melting_reply(question, [])
    assert reply is not None
    assert reply.startswith("Jeśli oba podłoża są cieplejsze od lodu")


def test_thermal_followup_requires_compatible_object_modifiers():
    history = [
        _user(
            "Miedziana płyta ma 20°C, a drewniany klocek 18°C. Wskaż kierunek przepływu ciepła."
        )
    ]
    revision = "Nie znam temperatury {} klocka. Skróć wyjaśnienie do jednego zdania."
    assert thermal_followup_reply(revision.format("plastikowego"), history) is None
    reply = thermal_followup_reply(revision.format("drewnianego"), history)
    assert reply is not None
    assert reply.startswith("Brakuje temperatury drewnianego klocka")
