from __future__ import annotations

import pytest

from venom_core.services.training_experiments.semantic_fact_evidence import compare
from venom_core.services.training_experiments.semantic_judge_v5 import Relation


def _compare(
    candidate: str,
    criterion: str,
    messages: str | list[tuple[str, str]],
    observed: str = "brak w odpowiedzi",
    relation: Relation = "omitted",
    *,
    evidence: list[dict] | None = None,
):
    if isinstance(messages, str):
        messages = [("user", messages)]
    material = {
        "candidate": candidate,
        "criteria": [{"id": "reviewed_slot", "description": criterion}],
        "messages": [{"role": role, "content": content} for role, content in messages],
        "evidence": evidence or [],
    }
    return compare(material, candidate, "reviewed_slot", observed, relation)


def test_current_role_preserves_source_assignment_across_explicit_update():
    candidate = "Za sztukę płacisz 12 zł. U Anki odbierzesz 7 pudeł."
    result = _compare(
        candidate,
        "Osoba obsługująca odbiór: Anka.",
        [
            ("user", "Jutro odbiór u Anki. Osobą obsługującą odbiór jest Anka."),
            ("assistant", "Obsługa to Ola."),
            ("user", "Zmieniam liczbę na siedem. Osoba przy odbiorze bez zmian."),
        ],
    )
    assert result is not None
    assert result["effective_relation"] == "supported"
    assert result["raw_relation"] == "omitted"
    assert result["effective_observed"] == "U Anki odbierzesz 7 pudeł."
    assert result["source"] == {
        "message_index": 0,
        "quote": "Osobą obsługującą odbiór jest Anka.",
        "continuity_index": 2,
        "continuity_quote": "Osoba przy odbiorze bez zmian.",
    }


@pytest.mark.parametrize(
    "candidate",
    [
        "Karton odbierzesz w punkcie «U Miry».",
        "W punkcie «U Miry». Karton odbierzesz u Miry.",
        "Karton odbierzesz u Haliny.",
        "Nie odbierzesz u Miry.",
        "Chyba odbierzesz u Miry.",
        "U Miry odbierzesz, ale Halina wydaje karton.",
        "Karton odbierzesz u Miry. Wydaje Halina.",
        "Karton odbierzesz u Miry. To przykład.",
        "Karton odbierzesz u Miry. To nieaktualne.",
        "Karton odbierzesz u Miry. Anuluję to.",
    ],
)
def test_same_name_without_unambiguous_candidate_pickup_binding_is_delegated(candidate):
    assert (
        _compare(candidate, "Osoba obsługująca odbiór: Mira.", "Odbiór obsługuje Mira.")
        is None
    )


@pytest.mark.parametrize(
    "latest",
    [
        "Osoba przy odbiorze bez zmian. Odbiór obsługuje Ewa.",
        "Podaj odbiór i liczbę.",
        "Osoba przy odbiorze bez zmian. Szyld to «U Miry».",
        "Odbiór obsługuje Mira. Obsługą odbioru zajmie się Ola.",
        "Osoba przy odbiorze bez zmian. Odbiór u Olgi.",
        "Osoba przy odbiorze bez zmian. Wycofuję to ustalenie.",
    ],
)
def test_role_reference_rejects_ambiguous_or_stale_user_history(latest):
    assert (
        _compare(
            "Pudło odbierzesz u Miry.",
            "Osoba obsługująca odbiór: Mira.",
            [("user", "Odbiór obsługuje Mira."), ("user", latest)],
        )
        is None
    )


def test_role_reference_ignores_assistant_assignments_and_checks_current_card_sign():
    candidate = "Pudło odbierzesz u Miry."
    criterion = "Osoba obsługująca odbiór: Mira."
    history = [
        ("assistant", "Odbiór obsługuje Mira."),
        ("user", "Osoba przy odbiorze bez zmian."),
    ]
    assert _compare(candidate, criterion, history) is None
    source = "Odbiór obsługuje Mira."
    card = {"current": True, "text": "Szyld to «U Miry»."}
    assert _compare(candidate, criterion, source, evidence=[card]) is None
    assert (
        _compare(candidate, criterion, source, evidence=[{**card, "current": False}])
        is not None
    )


@pytest.mark.parametrize(
    ("source_value", "answer_value", "effective"),
    [
        ("+4,7", "4.7", "supported"),
        ("−4,70", "-4.7", "supported"),
        ("-4,7", "4.7", "contradicted"),
        ("+4,7", "-4.7", "contradicted"),
    ],
)
def test_decimals_preserve_sign_unit_and_measurement(
    source_value, answer_value, effective
):
    candidate = f"**Pomiar B** — prąd **{answer_value} mA**, czas **30 sekund**."
    result = _compare(
        candidate,
        f"Prąd wynosi {source_value} mA.",
        f"Pomiar B: prąd {source_value} mA przez 30 sekund. Podaj pomiar i prąd.",
        f"**{answer_value} mA**",
    )
    assert result is not None
    assert result["effective_relation"] == effective
    assert result["effective_observed"] == candidate


@pytest.mark.parametrize(
    ("candidate", "source", "observed"),
    [
        ("Pomiar X: prąd 4.7 mA.", "Pomiar B: prąd +4,7 mA.", "4.7 mA"),
        ("Pomiar B: prąd 4.7 A.", "Pomiar B: prąd +4,7 mA.", "4.7 A"),
        (
            "Pomiar B: prąd 4.7 mA.",
            "Pomiar B: prąd +4,7 mA. Podaj z jawnym plusem.",
            "4.7 mA",
        ),
        ("Pomiar B: prąd 4.7 mA.", "Pomiar B: prąd -4,7 mA.", "4.7 mA"),
        ("Pomiar B: prąd 4.7 mA. Prąd = -4.7 mA.", "Pomiar B: prąd +4,7 mA.", "4.7 mA"),
        (
            "Pomiar B: prąd 4.7 mA.",
            "Pomiar B: prąd +4,7 mA. Prąd wynosi -4,7 mA.",
            "4.7 mA",
        ),
        ("Pomiar B: prąd 4.7 mA.", "Pomiar B: prąd +4,7 mA.", "4,7 mA"),
        ("Pomiar B: prąd 4.7 mA.", "Pomiar B: prąd +4,7 mA.", "Pomiar B"),
        (
            "Pomiar B: prąd 4.7 mA. To tylko przykład.",
            "Pomiar B: prąd +4,7 mA.",
            "4.7 mA",
        ),
    ],
)
def test_current_ambiguity_or_wrong_unit_is_delegated(candidate, source, observed):
    assert _compare(candidate, "Prąd wynosi +4,7 mA.", source, observed) is None


@pytest.mark.parametrize(
    ("candidate", "observed"),
    [
        (
            "Minusem dziewięciu stopni nie należy się kierować. Odbiór o 8:00.",
            "Minusem dziewięciu stopni nie należy się kierować.",
        ),
        ("Nie ustawiaj −9°C.", "−9°C"),
        ("Nie stosuj minus dziewięć °C.", "minus dziewięć °C"),
        ("Nie stosuj -9°C. Odbiór o 8:00.", "Nie stosuj -9°C."),
    ],
)
def test_active_rejection_of_current_setting_is_a_contradiction(candidate, observed):
    result = _compare(
        candidate,
        "Po korekcie nastawa próbna wynosi minus dziewięć stopni Celsjusza.",
        [
            ("user", "Nastawa wynosi minus jedenaście stopni Celsjusza."),
            ("assistant", "Potwierdzam −11°C."),
            ("user", "Zmieniłam nastawę na -9°C. Podaj aktualną nastawę."),
        ],
        observed,
    )
    assert result is not None
    assert result["effective_relation"] == "contradicted"
    assert result["effective_observed"] in candidate
    assert result["source"]["message_index"] == 2
    assert result["source"]["quote"] == "Zmieniłam nastawę na -9°C."


@pytest.mark.parametrize(
    ("candidate", "source"),
    [
        (
            "Nie ustawiaj −11°C.",
            "Zmieniłam nastawę na minus dziewięć stopni Celsjusza.",
        ),
        ("Nie ustawiaj +9°C.", "Zmieniłam nastawę na minus dziewięć stopni Celsjusza."),
        ("Nie ustawiaj −9°F.", "Zmieniłam nastawę na minus dziewięć stopni Celsjusza."),
        ("Nie ustawiaj −9°C. Nastawa wynosi −9°C.", "Zmieniłam nastawę na -9°C."),
        ("Nie ustawiaj −9°C.", "Zmieniłam nastawę na -9°C. Nastawa wynosi -10°C."),
        ("Nie ustawiaj −9°C.", "Zmieniłam nastawę na -9°C. Wycofuję zmianę."),
        ("Odbiór o 8:00.", "Zmieniłam nastawę na -9°C."),
        ("Nie stosuj −9°C. Cofam tę instrukcję.", "Zmieniłam nastawę na -9°C."),
        (
            "Nie stosuj minus dziewięćstopni Celsjusza.",
            "Zmieniłam nastawę na -9°C.",
        ),
        (
            "Nie stosuj minus -9°C.",
            "Zmieniłam nastawę na -9°C.",
        ),
    ],
)
def test_temperature_does_not_infer_rejection_when_current_value_is_unclear(
    candidate, source
):
    assert _compare(candidate, "Nastawa wynosi -9°C.", source) is None


def test_omission_token_cannot_substitute_for_a_literal_observation():
    assert (
        _compare(
            "Pudło odbierzesz u Miry.",
            "Osoba obsługująca odbiór: Mira.",
            "Odbiór obsługuje Mira.",
            "brak w odpowiedzi",
            "supported",
        )
        is None
    )
