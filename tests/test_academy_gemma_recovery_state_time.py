from collections.abc import Sequence

import pytest

from venom_core.api.schemas.llm_simple import HistoryMessage
from venom_core.services.chat_policy.studio_followup import studio_followup

_REQUEST = (
    "Poprosiłam o odczyt próbnej planszy, lecz jeszcze nikt nie potwierdził "
    "wykonania. Podsumuj stan."
)
_STARTED = (
    "Prośba nadal obowiązuje. Wiem tylko, że rozpoczęto odczyt. Zaktualizuj stan."
)
_WITHDRAWN = (
    "Prośbę wycofuję. Nie potwierdzam, czy rozpoczęty odczyt dokończono. "
    "Zapisz krótki status."
)
_PICKUP = (
    "Paczka należy do Mili, Julek ma ją tylko odebrać w jej imieniu. Wymień obie role."
)
_RESIGNED = (
    "Julek zrezygnował z odbioru, a nikt jeszcze nie potwierdził zastępcy. "
    "Powiedz, kto jest właścicielką i jaki jest stan odbioru."
)
_REPLACED = (
    "Mila potwierdza, że paczkę odbierze Paweł. Własność się nie zmienia. "
    "Podaj oba nazwiska lub imiona w rolach."
)
_DURATION = (
    "Pierwsze dwa napisy poprawiano przez 16 minut. Trzecia korekta trwała "
    "7 minut. Jaka jest suma?"
)
_DURATION_UPDATE = (
    "Trzecia korekta trwała jednak 9 minut. Czas dwóch pierwszych nadal może "
    "oznaczać sumę albo czas na jedną. Czy już da się podać jedną sumę?"
)
_DURATION_CONFIRMED = (
    "Potwierdzam: 16 minut to łączny czas dwóch pierwszych. "
    "Zsumuj z poprawionym czasem trzeciej."
)


def _history(
    *users: str, assistant: str = "Zadanie wykonano. Wynik to 90 min."
) -> Sequence[HistoryMessage]:
    return [
        turn
        for user in users
        for turn in (
            HistoryMessage(role="user", content=user),
            HistoryMessage(role="assistant", content=assistant),
        )
    ]


def test_status_keeps_observed_start_and_withdrawn_request_separate():
    assert studio_followup(_REQUEST, []) == (
        "Zgłoszono prośbę o odczyt próbnej planszy, a wykonania nie potwierdzono."
    )
    assert studio_followup(_STARTED, _history(_REQUEST)) == (
        "Prośba o odczyt próbnej planszy nadal obowiązuje, a rozpoczęto odczyt."
    )
    assert studio_followup(_WITHDRAWN, _history(_REQUEST, _STARTED)) == (
        "Prośbę o odczyt próbnej planszy wycofano. "
        "Rozpoczęto odczyt, ale nie potwierdzono dokończenia."
    )


@pytest.mark.parametrize("phase", ["nadal trwa", "zakończono", "nie wykonano"])
def test_status_can_report_an_explicit_phase_on_the_matching_request(phase):
    request = "Poprosiłem o przegląd listy, ale nikt nie potwierdził wykonania. Podsumuj stan."
    update = (
        f"Prośba nadal obowiązuje. Potwierdzam, że {phase} przegląd. Podsumuj stan."
    )
    assert studio_followup(update, _history(request)) == (
        f"Prośba o przegląd listy nadal obowiązuje, a {phase} przegląd."
    )


def test_withdrawal_of_another_request_and_unrelated_status_fall_back():
    assert studio_followup(_WITHDRAWN, _history(_REQUEST)) is None
    assert (
        studio_followup(_STARTED.replace("odczyt", "druk"), _history(_REQUEST)) is None
    )
    assert (
        studio_followup(_WITHDRAWN, _history(_REQUEST, "Co oznacza słowo odczyt?"))
        is None
    )
    quote = f"Przeczytaj zdanie „{_REQUEST}”."
    assert studio_followup(quote, []) is None
    assert (
        studio_followup(
            _WITHDRAWN, _history(_REQUEST, _STARTED.replace("rozpoczęto", "zakończono"))
        )
        is None
    )


def test_owner_is_unchanged_when_delegate_withdraws_or_is_replaced():
    assert studio_followup(_PICKUP, []) == (
        "Paczka należy do Mili, a Julek ma ją odebrać w jej imieniu."
    )
    assert studio_followup(
        _RESIGNED, _history(_PICKUP, assistant="Paczka nie została odebrana.")
    ) == (
        "Paczka należy do Mili. Julek zrezygnował z odbioru, "
        "a zastępcy jeszcze nie potwierdzono."
    )
    assert studio_followup(_REPLACED, _history(_PICKUP, _RESIGNED)) == (
        "Paczka nadal należy do Mili, a Paweł ma ją odebrać."
    )


def test_delegate_fresh_roles_and_mismatched_handover():
    source = (
        "Kasetka należy do Oli, Iza ma ją tylko odebrać w jej imieniu. Podaj obie role."
    )
    withdraw = (
        "Iza zrezygnowała z odbioru, a nie ma potwierdzonego zastępcy. "
        "Powiedz, kto jest właścicielką i jaki jest stan odbioru."
    )
    assert studio_followup(withdraw, _history(source)) == (
        "Kasetka należy do Oli. Iza zrezygnowała z odbioru, "
        "a zastępcy jeszcze nie potwierdzono."
    )
    assert studio_followup(withdraw, _history(_PICKUP)) is None
    assert studio_followup(_REPLACED, _history(source, withdraw)) is None
    assert studio_followup(_REPLACED, _history(_PICKUP, withdraw)) is None
    assert (
        studio_followup(
            "Paweł potwierdził odbiór paczki.", _history(_PICKUP, _RESIGNED)
        )
        is None
    )


def test_duration_unknown_scope_can_survive_a_change_in_the_third_amount():
    question = "Czy 16 min dotyczy obu korekt łącznie, czy każdej z osobna?"
    assert studio_followup(_DURATION, []) == question
    assert studio_followup(_DURATION_UPDATE, _history(_DURATION)) == question
    assert studio_followup(
        _DURATION_CONFIRMED, _history(_DURATION, _DURATION_UPDATE)
    ) == ("25 min")


@pytest.mark.parametrize(
    ("scope", "total"),
    [
        ("łączny czas dwóch pierwszych", "17 min"),
        ("czas każdej z dwóch pierwszych", "28 min"),
    ],
)
def test_duration_alternate_unit_and_fresh_group_with_both_scopes(scope, total):
    prompt = (
        "Pierwsze dwie notatki poprawiano przez 11 min. Trzecia korekta trwała "
        "4 min. Jaka jest suma?"
    )
    update = _DURATION_UPDATE.replace("9 minut", "6 min")
    confirm = f"Potwierdzam: 11 min to {scope}. Zsumuj z poprawionym czasem trzeciej."
    question = "Czy 11 min dotyczy obu korekt łącznie, czy każdej z osobna?"
    assert studio_followup(prompt, []) == question
    assert studio_followup(update, _history(prompt)) == question
    assert studio_followup(confirm, _history(prompt, update)) == total


@pytest.mark.parametrize(
    ("scope", "total"), [("łącznie ", "13 min"), ("po ", "23 min"), ("", None)]
)
def test_duration_initial_scope_or_short_question(scope, total):
    prompt = (
        f"Dwie kartki przeszły korektę w {scope}10 minut. Trzecia w 3 minuty. "
        "Ile czasu zajęła korekta wszystkich?"
    )
    assert studio_followup(prompt, []) == (
        total or "Czy 10 min dotyczy obu korekt łącznie, czy każdej z osobna?"
    )


def test_duration_does_not_infer_scope_from_assistant_or_an_unrelated_edit():
    assert studio_followup(_DURATION_CONFIRMED, _history(_DURATION)) is None
    mismatch = _DURATION_CONFIRMED.replace("16 minut", "15 minut")
    assert studio_followup(mismatch, _history(_DURATION, _DURATION_UPDATE)) is None
    assert (
        studio_followup(
            _DURATION_CONFIRMED, _history(_DURATION, "Spotkanie trwało 9 minut.")
        )
        is None
    )
    assert (
        studio_followup(
            _DURATION_CONFIRMED,
            _history("Czy jutro o 16 przyniesiesz książkę?", _DURATION_UPDATE),
        )
        is None
    )
    assert (
        studio_followup(
            _DURATION.replace("poprawiano przez", "czytano równolegle przez"), []
        )
        is None
    )
    assert (
        studio_followup(
            "W trzech pudłach jest po 4 sztuki. Czwarte zawiera 2 sztuki. Ile razem?",
            [],
        )
        is None
    )


def test_duration_explicit_each_count_cannot_claim_the_same_quantity_is_collective():
    prompt = (
        "Korekta każdego z pierwszych dwóch szkiców zajęła 6 minut. "
        "Korekta trzeciego zajęła 4 minuty. Ile czasu zajęła korekta wszystkich?"
    )
    assert studio_followup(prompt, []) == "16 min"
    assert studio_followup(prompt.replace("6 minut", "łącznie 6 minut"), []) is None
