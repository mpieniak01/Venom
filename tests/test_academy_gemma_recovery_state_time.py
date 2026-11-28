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
        "Prośba o odczyt próbnej planszy nadal obowiązuje, a rozpoczęto odczyt, "
        "lecz dalszego przebiegu nie potwierdzono."
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


_RECOVERY_STATUS = [
    (
        [
            "Poprosiłam wczoraj o przegląd mapy. Nie mam wiadomości, czy to zrobiono. Podaj stan.",
            "Wycofuję prośbę i nadal nie wiem, czy przegląd wykonano. Zapisz aktualny stan.",
        ],
        [
            "Zgłoszono prośbę o przegląd mapy, a wykonania nie potwierdzono.",
            "Prośba o przegląd mapy została wycofana, a wykonania nie potwierdzono.",
        ],
    ),
    (
        [
            "Poprosiłem o sprawdzenie obręczy. Potwierdzono, że obejrzano ją do końca. Podaj stan.",
            "Wycofuję samą prośbę. Dotychczasowe oględziny są potwierdzone. Zapisz aktualny stan.",
        ],
        [
            "Zgłoszono prośbę o sprawdzenie obręczy, a potwierdzono, że obejrzano ją do końca.",
            "Prośba o sprawdzenie obręczy została wycofana, a potwierdzono, że obejrzano ją do końca.",
        ],
    ),
    (
        [
            "Prośba o skan makiety wciąż obowiązuje. Wiadomo tylko, że ktoś zaczął skanować. Podaj status.",
            "Wycofuję prośbę. Nie wiadomo, czy rozpoczęty skan zakończono. Jedno zdanie.",
        ],
        [
            "Prośba o skan makiety nadal obowiązuje, a rozpoczęto skan, "
            "lecz dalszego przebiegu nie potwierdzono.",
            "Prośba o skan makiety została wycofana, a rozpoczęto skan, ale nie potwierdzono dokończenia.",
        ],
    ),
    (
        [
            "Zlecenie odczytu tabliczki obowiązuje. Potwierdzono początek. Podaj status.",
            "Przed chwilą rozmówca potwierdził, że odczyt nadal trwa. Podaj aktualny status.",
        ],
        [
            "Zlecenie odczytu tabliczki nadal obowiązuje, a potwierdzono rozpoczęcie.",
            "Zlecenie odczytu tabliczki nadal obowiązuje, a odczyt nadal trwa.",
        ],
    ),
    (
        [
            "Szablon należy do Ali. Mirek jest wyznaczony do odbioru w jej imieniu. Wymień role.",
            "Mirek zrezygnował. Brak potwierdzonego zastępcy. Podaj właścicielkę i stan odbioru.",
        ],
        [
            "Szablon należy do Ali, a Mirek jest wyznaczony do odbioru w jej imieniu.",
            "Szablon należy do Ali. Mirek zrezygnował z odbioru, a zastępcy jeszcze nie potwierdzono.",
        ],
    ),
]


@pytest.mark.parametrize(("requests", "expected"), _RECOVERY_STATUS)
def test_recovery_status_binds_evidence_to_the_same_object(requests, expected):
    for index, request in enumerate(requests):
        assert studio_followup(request, _history(*requests[:index])) == expected[index]


@pytest.mark.parametrize(
    ("amount", "pronoun", "matches"),
    [
        ("jednej", "ją", True),
        ("jednej", "je", False),
        ("dwóch", "ją", False),
        ("dwóch", "je", True),
    ],
)
def test_inspection_respects_explicit_singular_and_plural_scope(
    amount, pronoun, matches
):
    prompt = (
        f"Poprosiłem o sprawdzenie {amount} opasek. Potwierdzono, że obejrzano "
        f"{pronoun} do końca. Podaj stan."
    )
    # Use the case agreeing with the explicitly singular count.
    prompt = prompt.replace("jednej opasek", "jednej opaski")
    response = studio_followup(prompt, [])
    assert (response is not None) == matches
    if response:
        assert f"{amount} opas" in response
        assert f"obejrzano {pronoun} do końca" in response


def test_negative_completion_and_explicit_nonperformance_are_distinct():
    prompt = (
        "Poprosiłam o sprawdzenie jednej opaski. "
        "Potwierdzono, że nie obejrzano jej do końca. Podaj stan."
    )
    assert studio_followup(prompt, []) == (
        "Zgłoszono prośbę o sprawdzenie jednej opaski, "
        "a potwierdzono, że nie obejrzano jej do końca."
    )
    report = (
        "Poprosiłam o odczyt arkusza próbnego. "
        "Potwierdzono, że nie wykonano odczytu arkusza próbnego. Podaj stan."
    )
    assert studio_followup(report, []) == (
        "Zgłoszono prośbę o odczyt arkusza próbnego, "
        "a nie wykonano odczytu arkusza próbnego."
    )


def test_status_does_not_bind_another_object_or_conflate_request_and_order():
    initial, progress = _RECOVERY_STATUS[3][0]
    other = (
        "Przed chwilą rozmówca potwierdził, że odczyt drugiej tabliczki "
        "nadal trwa. Podaj aktualny status."
    )
    assert studio_followup(other, _history(initial)) is None
    assert studio_followup(progress, _history(initial, "Kiedy zamykają biuro?")) is None
    same = progress.replace("odczyt nadal", "odczyt tabliczki nadal")
    assert studio_followup(same, _history(initial)) == (
        "Zlecenie odczytu tabliczki nadal obowiązuje, a odczyt tabliczki nadal trwa."
    )


def test_status_keeps_execution_across_multiple_updates_and_withdrawal():
    source, progress = _RECOVERY_STATUS[3][0]
    done = "Potwierdzam, że zakończono odczyt tabliczki. Podaj status."
    assert (
        studio_followup(
            "Wycofuję samą prośbę. Zapisz aktualny stan.",
            _history(source, progress, done),
        )
        is None
    )
    withdrawal = "Wycofuję samo zlecenie. Zapisz aktualny stan."
    assert studio_followup(withdrawal, _history(source, progress, done)) == (
        "Zlecenie odczytu tabliczki zostało wycofane, a zakończono odczyt tabliczki."
    )


def test_role_assignment_requires_matching_named_role_holder():
    source, withdrawal = _RECOVERY_STATUS[4][0]
    unrelated_person = withdrawal.replace("Mirek", "Jarek")
    assert studio_followup(unrelated_person, _history(source)) is None
    two_objects = (
        "Futerał należy do Leny, karton do Ewy. Do odbioru futerału wyznaczono Iwa. "
        "Podaj role dotyczące futerału."
    )
    assert studio_followup(two_objects, []) is None
    assert studio_followup(withdrawal, _history(two_objects)) is None


@pytest.mark.parametrize(
    ("source", "update", "expected_source", "expected_update"),
    [
        (
            "Poprosiłem o pomiar wymiaru ramy. Nie ma potwierdzenia wykonania. Podaj stan.",
            "Wycofuję prośbę. Nadal nie wiadomo, czy pomiar wykonano. Podaj stan.",
            "Zgłoszono prośbę o pomiar wymiaru ramy, a wykonania nie potwierdzono.",
            "Prośba o pomiar wymiaru ramy została wycofana, a wykonania nie potwierdzono.",
        ),
        (
            "Poprosiłam o przegląd osłony. Potwierdzono, że obejrzano ją do końca. Podaj stan.",
            "Wycofuję samą prośbę. Dotychczasowe oględziny są potwierdzone. Podaj aktualny stan.",
            "Zgłoszono prośbę o przegląd osłony, a potwierdzono, że obejrzano ją do końca.",
            "Prośba o przegląd osłony została wycofana, a potwierdzono, że obejrzano ją do końca.",
        ),
        (
            "Prośba o skan znaku nadal obowiązuje. Wiadomo tylko, że rozpoczęto skan. Podaj status.",
            "Przed chwilą potwierdzono, że skan nadal trwa. Podaj aktualny stan.",
            "Prośba o skan znaku nadal obowiązuje, a rozpoczęto skan, lecz dalszego przebiegu nie potwierdzono.",
            "Prośba o skan znaku nadal obowiązuje, a skan nadal trwa.",
        ),
        (
            "Pokrowiec należy do Basi. Wojtek jest wyznaczony do odbioru w jej imieniu. Podaj role.",
            "Wojtek zrezygnował. Nie potwierdzono zastępcy. Podaj właścicielkę i stan odbioru.",
            "Pokrowiec należy do Basi, a Wojtek jest wyznaczony do odbioru w jej imieniu.",
            "Pokrowiec należy do Basi. Wojtek zrezygnował z odbioru, a zastępcy jeszcze nie potwierdzono.",
        ),
    ],
)
def test_recovery_binds_composed_evidence_from_both_turns(
    source, update, expected_source, expected_update
):
    assert studio_followup(source, []) == expected_source
    assert studio_followup(update, _history(source)) == expected_update


def test_only_inspection_can_bind_pronominal_observation():
    request = "Poprosiłam o przegląd wizjera. Potwierdzono, że obejrzano go do końca. Podaj stan."
    assert studio_followup(request, []) == (
        "Zgłoszono prośbę o przegląd wizjera, a potwierdzono, że obejrzano go do końca."
    )
    assert studio_followup(request.replace("przegląd", "transport"), []) is None


def test_explicit_continuation_applies_only_to_matching_work():
    initial = (
        "Prośba o pomiar rozstawu nadal obowiązuje. "
        "Wiadomo jedynie, że rozpoczęto pomiar. Podaj aktualny stan."
    )
    assert studio_followup(initial, []) == (
        "Prośba o pomiar rozstawu nadal obowiązuje, a rozpoczęto pomiar, "
        "lecz dalszego przebiegu nie potwierdzono."
    )
    next_turn = (
        "Przed chwilą potwierdzono, że pomiar rozstawu nadal trwa. Podaj aktualny stan."
    )
    assert studio_followup(next_turn, _history(initial)) == (
        "Prośba o pomiar rozstawu nadal obowiązuje, a pomiar rozstawu nadal trwa."
    )
    assert (
        studio_followup(next_turn.replace("rozstawu", "wysokości"), _history(initial))
        is None
    )


def test_delegate_full_name_and_explicit_pickup_outcome_are_independent():
    source = (
        "Futerał należy do Elizy Kot. Anna Lis jest wyznaczona do odbioru "
        "w jej imieniu. Podaj role."
    )
    assert studio_followup(source, []) == (
        "Futerał należy do Elizy Kot, a Anna Lis jest wyznaczona do odbioru w jej imieniu."
    )
    update = "Anna Lis zrezygnowała. Nie potwierdzono zastępcy."
    command = " Podaj właścicielkę i stan odbioru."
    state = (
        "Futerał należy do Elizy Kot. Anna Lis zrezygnowała z odbioru, "
        "a zastępcy jeszcze nie potwierdzono."
    )
    assert studio_followup(update + command, _history(source)) == state
    for statement in (
        "Potwierdzono, że nie odebrano tego przedmiotu.",
        "Potwierdzono, że odebrano ten przedmiot.",
    ):
        assert studio_followup(f"{update} {statement}{command}", _history(source)) == (
            f"{state} {statement}"
        )
    different_person = update.replace("Anna Lis", "Anna Kot")
    assert studio_followup(different_person + command, _history(source)) is None
    different_item = " Potwierdzono, że nie odebrano walizki."
    assert studio_followup(update + different_item + command, _history(source)) is None


def test_pickup_declines_a_shared_surname_without_its_first_name():
    source = (
        "Paczka należy do Zofii Lis. Anna Lis jest wyznaczona do odbioru "
        "w jej imieniu. Podaj role."
    )
    ambiguous = "Lis zrezygnowała. Nie potwierdzono zastępcy. Podaj właścicielkę i stan odbioru."
    assert studio_followup(ambiguous, _history(source)) is None


_DUTY_INTEREST = (
    "W klubie Nina jest na liście osób chętnych do sobotniego dyżuru. "
    "W grafiku przy jej imieniu widnieje puste pole. Czy mogę napisać, że Nina ma dyżur?"
)
_APPROVED_PLACE = (
    "Zaakceptowałem do wysłania tylko informację o adresie pracowni, "
    "a godzina spotkania nie jest jeszcze ustalona. "
    "Czy w tabeli mogę napisać „pełny komunikat zatwierdzony”?"
)
_APPROVED_BOTH = (
    "Już ustaliliśmy spotkanie o 9:50 i zatwierdzam obie informacje. "
    "Komunikatu jeszcze nie wysłano. Podaj status do tabeli."
)


def test_status_separates_duty_interest_assignment_and_confirmation():
    assert studio_followup(_DUTY_INTEREST, []) == (
        "Nina jest na liście chętnych do dyżuru w sobotę, ale w grafiku nie ma przydziału."
    )
    assignment = (
        "Koordynatorka wpisała Ninę na 10:25, ona jeszcze tego nie potwierdziła. "
        "Jak zapisać stan w jednym zdaniu?"
    )
    assert studio_followup(assignment, _history(_DUTY_INTEREST)) == (
        "Na dyżur w sobotę o 10:25 wpisano Ninę do grafiku, "
        "a przydział nadal czeka na potwierdzenie tej osoby."
    )
    assert (
        studio_followup(
            assignment, _history(_DUTY_INTEREST, "Jaki przygotowujemy grafik?")
        )
        is None
    )
    assert (
        studio_followup(_DUTY_INTEREST.replace("Nina ma dyżur", "Lena ma dyżur"), [])
        is None
    )


@pytest.mark.parametrize(
    ("assignment", "expected"),
    [
        (
            "Wpisano Lenę do grafiku na 19:25. Ona jeszcze tego nie potwierdziła. "
            "Podaj stan w jednym zdaniu.",
            "Do grafiku wpisano Lenę na 19:25, dnia nie podano, "
            "a przydział nadal czeka na potwierdzenie tej osoby.",
        ),
        (
            "Organizatorka wpisała Ninę na piątek o 8:10 i ona już to potwierdziła. "
            "Zapisz stan w jednym zdaniu.",
            "Na dyżur w piątek o 8:10 wpisano Ninę do grafiku, a ta osoba potwierdziła przydział.",
        ),
    ],
)
def test_status_uses_current_person_and_explicit_day(assignment, expected):
    assert studio_followup(assignment, _history(_DUTY_INTEREST)) == expected


def test_approval_is_bound_to_the_original_activity_before_dispatch():
    assert studio_followup(_APPROVED_PLACE, []) == (
        "Zatwierdzono tylko informację o adresie pracowni, "
        "a godzina spotkania nadal nie jest ustalona."
    )
    assert studio_followup(_APPROVED_BOTH, _history(_APPROVED_PLACE)) == (
        "Pełny komunikat zatwierdzony, łącznie z informacją o adresie pracowni "
        "i godziną spotkania 9:50. Wysyłka jeszcze nie nastąpiła."
    )
    assert (
        studio_followup(
            _APPROVED_BOTH.replace("spotkanie", "odbiór"), _history(_APPROVED_PLACE)
        )
        is None
    )
    assert studio_followup(_APPROVED_BOTH, _history(_REQUEST)) is None


@pytest.mark.parametrize(
    ("dispatch", "expected"),
    [
        (
            "wysłana wiadomość z adresem, bez godziny",
            "Wysłano informację o adresie pracowni. Zatwierdzona godzina spotkania to 9:50, "
            "ale nie było jej w wysłanym komunikacie.",
        ),
        (
            "wysłana wiadomość z godziną 8:35, bez adresu",
            "Wysłano godzinę 8:35, bez informacji o adresie pracowni. "
            "Zatwierdzona godzina spotkania to 9:50. "
            "Informacja o adresie pracowni pozostaje zaakceptowana.",
        ),
        (
            "wysłana wiadomość z godziną 09:50 i z adresem",
            "Wysłano informację o adresie pracowni i godzinę 09:50.",
        ),
    ],
)
def test_status_distinguishes_approved_and_actually_sent_fields(dispatch, expected):
    prompt = f"W rejestrze jest {dispatch}. Co faktycznie wysłano?"
    assert (
        studio_followup(prompt, _history(_APPROVED_PLACE, _APPROVED_BOTH)) == expected
    )
    assert studio_followup(prompt, _history(_APPROVED_BOTH)) is None


def test_status_uses_field_evidence_across_approval_and_receipt():
    draft = (
        "Do wysłania zatwierdzono tylko adres Dom Brzóz, a godzina 17:50 pozostała robocza. "
        "Jak zapisać stan?"
    )
    approval = (
        "Teraz godzina 18:20 też jest zatwierdzona. Komunikatu jeszcze nie wysłano."
    )
    receipt = "W wysłanej wiadomości widzę „Dom Brzóz”, bez godziny. Podaj stan w jednym zdaniu."
    assert studio_followup(draft, []) == (
        "Zatwierdzono adres Dom Brzóz. Godzina 17:50 jest robocza. Brak potwierdzenia wysłania."
    )
    assert studio_followup(approval, _history(draft)) == (
        "Zatwierdzono adres Dom Brzóz oraz godzinę 18:20. Komunikatu jeszcze nie wysłano."
    )
    assert studio_followup(receipt, _history(draft, approval)) == (
        "Wysłano informację „Dom Brzóz”, a zatwierdzonej godziny 18:20 w wysłanym wpisie nie było."
    )
    assert (
        studio_followup(
            receipt.replace("Dom Brzóz", "Dom Topoli"), _history(draft, approval)
        )
        is None
    )


def test_version_preference_can_be_overridden_without_reporting_execution():
    draft = (
        "Mam dwie propozycje okładki. Drugą zespół ocenił lepiej, ale formalnie decyzję "
        "podejmie później. W jakim stanie jest druga?"
    )
    assert studio_followup(draft, []) == (
        "Druga wersja jest roboczo preferowana. Decyzja nie została jeszcze podjęta."
    )
    assert (
        studio_followup(
            "Teraz zespół odpisał „zatwierdzam pierwszą wersję”. "
            "Plik jeszcze nie poszedł do druku. Podaj status.",
            _history(draft),
        )
        == "Pierwsza wersja jest zatwierdzona. Pliku jeszcze nie wysłano do druku."
    )


def test_numbered_items_remain_after_dispatch_approval_is_withdrawn():
    draft = (
        "Cała seria 16 folderów miała otrzymać numery przed przekazaniem. "
        "Mamy numery dla 13 i brak ich dla 3. Czy skończono rejestr?"
    )
    withdrawal = "Koordynator wycofał zgodę na przekazanie, a niczego jeszcze nie wydano. Zapisz stan po zmianie."
    assert studio_followup(draft, []) == (
        "Rejestr nadal jest niekompletny. Numery ma 13 z 16 pozycji, a 3 nadal ich nie ma."
    )
    assert studio_followup(withdrawal, _history(draft)) == (
        "Cofnięto zgodę na przekazanie i niczego nie wydano. Numery ma 13 z 16 pozycji, a 3 nadal ich nie ma."
    )
    assert studio_followup(draft.replace("dla 3", "dla 7"), []) is None


def test_old_published_hour_is_not_the_current_hour_after_condition_was_met():
    draft = (
        "Notatka podaje stare otwarcie o 9:30 i nową godzinę 10:45 po aktualizacji listy. "
        "Aktualizacji jeszcze nie potwierdzono. Którą godzinę traktować jako obowiązującą?"
    )
    update = (
        "Teraz zespół potwierdza aktualizację listy, ale na gablocie nadal jest 9:30. "
        "Jak opisać status?"
    )
    assert "Obowiązuje godzina 9:30." in studio_followup(draft, [])
    assert studio_followup(update, _history(draft)) == (
        "Potwierdzono aktualizację listy, więc obowiązuje godzina 10:45. "
        "Na gablocie nadal widnieje godzina 9:30."
    )
    assert studio_followup(update.replace("listy", "grafiku"), _history(draft)) is None


def test_call_log_keeps_named_observer_and_unresolved_result():
    pending = (
        "Na liście „zadzwonić do warsztatu” jest pole na datę połączenia. "
        "Nie ma potwierdzenia rozmowy. Co wpisać w polu?"
    )
    report = (
        "Nina zgłosiła, że rozmowa odbyła się o 14:15, ale dostępność nie została "
        "ustalona. Co wpisać w notatce?"
    )
    assert studio_followup(pending, []) == (
        "Wpis opisuje zadanie do wykonania. Datę rozmowy zostaw pustą do czasu potwierdzenia połączenia."
    )
    assert studio_followup(report, _history(pending)) == (
        "Nina zgłosiła, że rozmowa odbyła się o 14:15. Dostępność nie została ustalona."
    )
    assert studio_followup(report, _history(_REQUEST)) is None


def test_only_explicit_confirmation_of_the_held_field_releases_print():
    held = (
        "Redaktor podpisał ostateczną treść programu. Druk trzeba wstrzymać do "
        "potwierdzenia koloru przez drukarnię. Podsumuj w jednym zdaniu."
    )
    praise = "Kolor pochwalił grafik, ale drukarnia jeszcze milczy. Czy można uznać warunek za spełniony?"
    confirm = "Drukarnia już potwierdziła kolor. Czy można już rozpocząć druk?"
    assert studio_followup(held, []) == (
        "Treść programu zatwierdzono, a druk pozostaje wstrzymany do potwierdzenia koloru przez drukarnię."
    )
    assert studio_followup(praise, _history(held)) == (
        "Pochwała nie zastępuje potwierdzenia koloru przez drukarnię. Druk pozostaje wstrzymany."
    )
    assert studio_followup(confirm, _history(held, praise)) == (
        "Drukarnia potwierdziła kolor, więc warunek zdjęcia wstrzymania jest spełniony. "
        "Brak potwierdzenia, że druk się rozpoczął."
    )
    assert (
        studio_followup(confirm.replace("kolor", "format"), _history(held, praise))
        is None
    )
    assert (
        studio_followup(confirm, _history(held, praise.replace("Kolor", "Format")))
        is None
    )


@pytest.mark.parametrize(
    ("checked", "result"),
    [
        ("sześć", "Spełniono oba warunki odbioru."),
        ("pięć", "Odbiór pozostaje otwarty."),
    ],
)
def test_signed_acceptance_uses_verified_counts_and_preserves_declared_units(
    checked, result
):
    source = (
        "W formularzu wpisano 4 palety. Odbiór wymaga porównania sześciu kolorów "
        "i podpisu. Nikt jeszcze tego nie zrobił. Co widać na pewno?"
    )
    comparison = (
        f"Porównano {checked} pasujących kolorów, ale podpis złoży opiekun sali."
    )
    signed = (
        "Karta została podpisana. Liczba palet nadal pochodzi z formularza. "
        "Podaj, które warunki odbioru spełniono."
    )
    assert studio_followup(source, []) == (
        "W formularzu zapisano 4 palety. Do odbioru pozostają porównanie 6 kolorów i podpis."
    )
    assert studio_followup(comparison, _history(source)).endswith(
        "Podpis jest nadal oczekiwany."
    )
    status = studio_followup(signed, _history(source, comparison))
    assert result in status
    assert status.endswith("Liczba palet (4) nadal pochodzi z formularza.")
    assert studio_followup(signed, _history(source)) is None
    assert (
        studio_followup(comparison.replace("kolorów", "odcieni"), _history(source))
        is None
    )
    assert (
        studio_followup(signed.replace("palet", "kopert"), _history(source, comparison))
        is None
    )


def test_replacement_is_preserved_without_implying_successful_review():
    queued = (
        "Na etykiecie „do sprawdzenia” umieściliśmy kartę kontroli. "
        "Brak podpisów i adnotacji o wyniku. Czy partia ma status sprawdzona?"
    )
    signed = "Inspektorka podpisała kartę i dopisała „przejrzano, do korekty tabliczka”. Co wpisać?"
    replaced = (
        "Teraz zespół wymienił tabliczkę, a inspektorka jeszcze jej nie sprawdziła ponownie. "
        "Czy można wpisać bez uwag?"
    )
    assert studio_followup(queued, []) == (
        "Materiał czeka na sprawdzenie. Brak potwierdzenia zakończenia kontroli oraz jej wyniku."
    )
    assert studio_followup(signed, _history(queued)) == (
        "Kontrolę wykonano z uwagą. Do korekty pozostaje tabliczka."
    )
    assert studio_followup(replaced, _history(queued, signed)) == (
        "Wymieniono tabliczkę, lecz ponowna kontrola wciąż jest otwarta. Status „bez uwag” czeka na jej wynik."
    )
    assert (
        studio_followup(
            replaced.replace("tabliczkę", "naklejkę"), _history(queued, signed)
        )
        is None
    )


def test_accepted_task_preserves_named_observation_scope():
    task = (
        "Poprosiłem o rozłożenie trzech osłon. W rejestrze zadanie jest przyjęte, "
        "brak wpisu o wykonaniu. Zapisz status."
    )
    followup = (
        "Lena widziała dwie rozłożone, trzeciej nie sprawdziła. "
        "Podaj aktualny stan z rozróżnieniem źródła."
    )
    assert studio_followup(task, []) == (
        "Przyjęto zadanie obejmujące rozłożenie trzech osłon. Wykonania nie potwierdzono."
    )
    assert studio_followup(followup, _history(task)) == (
        "Lena widziała rozłożone 2 z 3 osłon. Trzeciej pozycji nie sprawdziła."
    )
    assert (
        studio_followup(followup, _history(task.replace("trzech", "czterech"))) is None
    )
    visit = (
        "Leszek podał, że był w hali wschodniej o 16:39, ale nie sprawdził mocowania. "
        "Jaki jest stan?"
    )
    assert "Leszek podał, że był w hali wschodniej o 16:39." in studio_followup(
        visit, []
    )
    assert "Leszek nie sprawdził mocowania." in studio_followup(visit, [])


def test_dispatch_does_not_use_approval_as_evidence_of_shipment():
    requests = (
        "Wniosek o folder F jest zatwierdzony, a o folder G dopiero złożony. "
        "Żadnego folderu nie wysłano. Zapisz stan obu."
    )
    update = (
        "Także wniosek G zatwierdzono. Do nadania trafił tylko F, co potwierdza "
        "wpis w księdze wysyłek. Podaj stan obu."
    )
    original = studio_followup(requests, [])
    assert "Folder F jest niewysłany" in original
    assert "Folder G też jest niewysłany" in original
    assert "wniosek złożono" in original
    assert studio_followup(update, _history(requests)) == (
        "Folder F nadano, co potwierdza wpis w księdze wysyłek. "
        "Folder G: wniosek zaakceptowany, przesyłki nie nadano."
    )
    assert (
        studio_followup(update.replace("tylko F", "tylko H"), _history(requests))
        is None
    )
    assert (
        studio_followup(requests.replace("Żadnego folderu", "Żadnego kompletu"), [])
        is None
    )


@pytest.mark.parametrize(("count", "discrepancy"), [("12", False), ("11", True)])
def test_label_count_separates_declared_checked_and_approved(count, discrepancy):
    label = (
        "Etykieta na paczce pokazuje „13”. Warunek przyjęcia to policzenie "
        "12 całych wkładek i podpis kontrolerki. Weryfikacji jeszcze nie wykonano. "
        "Co jest potwierdzone?"
    )
    result = (
        f"Policzono {count} całych wkładek, ale kontrolerka podpisze później. "
        "Czy warunek przyjęcia jest zamknięty?"
    )
    assert studio_followup(label, []) == (
        "Etykieta na paczce podaje 13. Do przyjęcia trzeba jeszcze sprawdzić "
        "12 całych wkładek i uzyskać podpis kontrolerki."
    )
    status = studio_followup(result, _history(label))
    assert f"Policzono {count}" in status
    assert ("Wymagano 12" in status) is discrepancy
    assert "Podpis kontrolerki nadal jest oczekiwany." in status
    assert status.endswith("Przyjęcie pozostaje otwarte.")
    assert (
        studio_followup(result.replace("całych", "czystych"), _history(label)) is None
    )


def test_access_test_report_retains_reporter_without_claiming_activation():
    pending = (
        "Dostęp do biura po 15:00 ma zostać włączony wyłącznie po przetestowaniu zamka. "
        "Zamek zainstalowano, ale testu nie zapisano. Jak opisać stan?"
    )
    checked = (
        "Administratorka podała, że test nie przeszedł o 13:37. Nadal nie mam "
        "informacji, czy rzeczywiście włączono dostęp. Zapisz oba stany."
    )
    assert studio_followup(pending, []).startswith(
        "Zamek zainstalowano. Brak potwierdzenia testu zamka."
    )
    assert studio_followup(checked, _history(pending)) == (
        "Administratorka podała, że test zamka nie przeszedł o 13:37. "
        "Dostęp do biura po 15:00: włączenie nadal niepotwierdzone."
    )
    assert (
        studio_followup(checked, _history(pending.replace("Zamek", "Czytnik"))) is None
    )


def test_place_only_in_published_record_does_not_publish_date_from_a_draft():
    approval = (
        "Do ogłoszenia zaakceptowano miejsce Sala Prób i datę 21 lutego. "
        "Szkic podaje adres, bez daty. Co wiemy o akceptacji i publikacji?"
    )
    published = (
        "W opublikowanym tekście widzę wyłącznie Sala Prób. "
        "Jak w jednym zdaniu podać stan zaakceptowanej daty?"
    )
    assert studio_followup(approval, []).endswith(
        "Szkic zawiera tylko miejsce i nie potwierdza publikacji."
    )
    assert studio_followup(published, _history(approval)) == (
        "Datę 21 lutego zaakceptowano, ale nie ma jej w opublikowanym tekście."
    )
    assert (
        studio_followup(published.replace("Sala Prób", "Sala A"), _history(approval))
        is None
    )


def test_updated_measurement_counts_remain_tied_to_the_batch():
    before = (
        "Odłożono zadanie ponownego ważenia, ale cztery z pięciu worków już zważono. "
        "Co jest wstrzymane i co pozostaje udokumentowane?"
    )
    reissue = (
        "Ponownie zlecono zważenie piątego worka. Ważenia jeszcze nie wykonano. "
        "Popraw status bez kasowania czterech pomiarów."
    )
    assert studio_followup(before, []) == (
        "Dalsze ważenie wstrzymano. Udokumentowane pozostaje zważenie 4 z 5 worków."
    )
    assert studio_followup(reissue, _history(before)) == (
        "Ponownie zlecono zważenie piątego worka, ale ważenia jeszcze nie wykonano. "
        "Udokumentowane pozostaje zważenie 4 z 5 worków."
    )
    assert (
        studio_followup(reissue.replace("worka", "kartonu"), _history(before)) is None
    )


def test_documented_correction_still_requires_the_named_review():
    rejected = (
        "Próbkę farby inspektor cofnął z powodu błędnego opisu odcienia. "
        "Dopiero po ponownej kontroli może otrzymać „bez uwag”. Czy to już ten etap?"
    )
    correction = (
        "Opis odcienia poprawiono i odnotowano to w rejestrze. "
        "Inspektor nie wykonał ponownej kontroli. Czy można zapisać „bez uwag”?"
    )
    assert "inspektor cofnął z powodu błędnego opisu odcienia." in studio_followup(
        rejected, []
    )
    assert studio_followup(correction, _history(rejected)) == (
        "Zmieniono opis odcienia i odnotowano zmianę w rejestrze. "
        "Inspektor nie wykonał ponownej kontroli. Status „bez uwag” nadal czeka na jej wynik."
    )
    assert (
        studio_followup(correction.replace("odcienia", "formatu"), _history(rejected))
        is None
    )


def test_source_first_visit_and_access_evidence_does_not_transfer_between_devices():
    visit = (
        "Według Joli o 7:40 była przy furtce zachodniej. "
        "Nie sprawdziła czytnika. Podaj stan."
    )
    assert studio_followup(visit, []) == (
        "Według Joli o 7:40 była przy furtce zachodniej. Nie sprawdziła czytnika."
    )
    plan = (
        "Brak zapisu testu terminala, mimo że terminal zainstalowano. "
        "Dopiero po teście wolno włączyć dostęp do hali po 19:00. Jak zapisać stan?"
    )
    report = (
        "O 16:30 test terminala powiódł się według techniczki. "
        "Włączenia dostępu nie potwierdzono. Zapisz oba stany."
    )
    assert "Brak potwierdzenia testu terminala" in studio_followup(plan, [])
    assert studio_followup(report, _history(plan)) == (
        "Według techniczki o 16:30 test terminala powiódł się. "
        "Dostęp do hali po 19:00: włączenie nadal niepotwierdzone."
    )
    assert studio_followup(report.replace("terminala", "zamka"), _history(plan)) is None
    assert (
        studio_followup(
            report,
            _history(plan.replace("terminal zainstalowano", "zamek zainstalowano")),
        )
        is None
    )
    assert studio_followup(report, []) is None


def test_reordered_dispatch_matches_both_request_ids_and_requires_expected_approval():
    status = (
        "Folderów F i G jeszcze nie wysłano. Wniosek o G tylko złożono, a F zatwierdzono. "
        "Co zapisać dla każdego?"
    )
    update = (
        "Wysłano tylko G, jak podaje rejestr. Wniosek o G również ma już akceptację. "
        "Zapisz stan obu."
    )
    reply = studio_followup(update, _history(status))
    assert reply == (
        "Folder G nadano, co potwierdza rejestr. Jego wniosek jest zaakceptowany. "
        "Folder F: wniosek zaakceptowany, przesyłki nie nadano."
    )
    assert studio_followup(status.replace("F i G", "F i H"), []) is None
    assert studio_followup(status.replace("F i G", "F i F"), []) is None
    assert studio_followup(update.replace("o G", "o F"), _history(status)) is None
    assert (
        studio_followup(update.replace("tylko G", "tylko H"), _history(status)) is None
    )


def test_reordered_label_separates_declared_count_verified_items_and_named_signer():
    source = (
        "Do przyjęcia trzeba potwierdzić siedem zgodnych próbek i uzyskać podpis kontrolerki. "
        "Na etykiecie kartonu widnieje 8. Próbek jeszcze nie sprawdzono. Co stanowi dowód?"
    )
    checked = (
        "Podpis kontrolerki nadal czeka. Weryfikacja wykazała sześć zgodnych próbek. "
        "Co powstrzymuje przyjęcie?"
    )
    assert studio_followup(source, []) == (
        "Etykieta na kartonie podaje 8. Do przyjęcia trzeba jeszcze sprawdzić "
        "7 zgodnych próbek i uzyskać podpis kontrolerki."
    )
    assert studio_followup(checked, _history(source)) == (
        "Policzono 6 zgodnych próbek. Wymagano 7. Podpis kontrolerki nadal jest oczekiwany. "
        "Przyjęcie pozostaje otwarte."
    )
    assert (
        studio_followup(source.replace("Próbek jeszcze", "Kartonu jeszcze"), []) is None
    )
    assert (
        studio_followup(checked.replace("kontrolerki", "inspektorki"), _history(source))
        is None
    )
    assert (
        studio_followup(checked.replace("próbek", "etykiet"), _history(source)) is None
    )


def test_reordered_review_requires_evidence_for_the_same_field_and_reviewer():
    rejected = (
        "Bez uwag można podpisać dopiero po ponownym sprawdzeniu. "
        "Z powodu błędnego opisu faktury inspektor odrzucił próbkę płótna. Podaj stan."
    )
    corrected = (
        "W karcie widnieje korekta opisu faktury. Inspektor nadal nie przeprowadził powtórnej kontroli. "
        "Czy można już wpisać „bez uwag”?"
    )
    assert "Czekają korekta i ponowna kontrola." in studio_followup(rejected, [])
    assert studio_followup(corrected, _history(rejected)) == (
        "Zmieniono opis faktury i odnotowano zmianę w karcie. "
        "Inspektor nadal nie przeprowadził ponownej kontroli. Status „bez uwag” nadal czeka na jej wynik."
    )
    assert (
        studio_followup(corrected.replace("faktury", "koloru"), _history(rejected))
        is None
    )
    assert (
        studio_followup(corrected.replace("Inspektor", "Kontroler"), _history(rejected))
        is None
    )


def test_clause_evidence_preserves_source_time_and_unchecked_scope():
    source = (
        "Pole daty wykonania pozostaje puste. W wykazie zapisano polecenie "
        "„przejrzeć rejestr przepustek”. Co potwierdza wykaz?"
    )
    note = (
        "Czy wpis jest spójny, Jacek nie sprawdził. "
        "Według Jacka przejrzano rejestr przepustek o 13:42. Zapisz oba stany."
    )
    history = _history(source, assistant="Sprawdził to Olek przed dwunastą.")
    # The same task and reporter must support both facts from the user's message.
    # Preserve exact source, and delegate ambiguous declension to ordinary Studio.
    simple = (
        note.replace("Jacka", "Oli")
        .replace("Jacek", "Ola")
        .replace("sprawdził", "sprawdziła")
    )
    reply = studio_followup(simple, history)
    assert reply is not None and "Według Oli" in reply and "13:42" in reply
    assert "Ola nie sprawdziła" in reply and "Olek" not in reply
    assert studio_followup(simple.replace("Według Oli", "Według Ewy"), history) is None
    assert (
        studio_followup(simple.replace("rejestr przepustek", "spis kluczy"), history)
        is None
    )
    assert studio_followup(simple, []) is None


def test_clause_evidence_rejects_unrelated_publication_gate_updates():
    anchor = (
        "Nowy cennik można opublikować dopiero po weryfikacji podatku. "
        "Złożono go w systemie, protokołu weryfikacji jeszcze brak. Jak opisać stan?"
    )
    update = (
        "Na portalu nadal wersja stara. Iza z księgowości potwierdziła "
        "weryfikację o 10:23. Co jest wykonane, co widoczne?"
    )
    reply = studio_followup(update, _history(anchor))
    assert reply is not None and "Iza z księgowości" in reply and "10:23" in reply
    assert "poprzednia wersja" in reply
    assert studio_followup(update, []) is None
    assert (
        studio_followup(
            update.replace("weryfikację", "zmianę grafiku"), _history(anchor)
        )
        is None
    )
    assert (
        studio_followup(
            update.replace("Co jest", "Potwierdzono publikację. Co jest"),
            _history(anchor),
        )
        is None
    )


def test_clause_fields_and_review_require_the_same_artifact_and_open_field():
    fields = (
        "Wersja robocza wiadomości obejmuje tylko datę i godzinę. "
        "Zatwierdzono trzy pola komunikatu: nazwę Cis, datę 6 maja oraz godzinę 11:45. "
        "Oddziel zatwierdzone pola od szkicu."
    )
    missing = "Nadana wiadomość zawiera tylko datę i godzinę. Co zapisać o nazwie?"
    assert studio_followup(missing, _history(fields)) == (
        "Zatwierdzono nazwę Cis, ale nie ma jej w nadanej wiadomości."
    )
    assert studio_followup(missing.replace("nazwie", "dacie"), _history(fields)) == (
        "Zatwierdzono datę 6 maja i to pole znajduje się w nadanej wiadomości."
    )
    assert studio_followup(missing, []) is None
    returned = (
        "Do odbioru upoważnia dopiero poprawka i powtórny podpis. "
        "Kontroler zwrócił formularz z powodu błędnego kodu taśmy. Jak opisać stan?"
    )
    fixed = "Powtórnego podpisu wciąż brak. W formularzu poprawiono kod taśmy. Czy zamykamy odbiór?"
    assert studio_followup(fixed, _history(returned)) == (
        "W formularzu poprawiono kod taśmy. Wciąż brakuje ponownego podpisu, więc odbiór pozostaje otwarty."
    )
    assert studio_followup(fixed.replace("taśmy", "stołu"), _history(returned)) is None
    assert (
        studio_followup(fixed.replace("formularzu", "deklaracji"), _history(returned))
        is None
    )


def test_clause_opening_and_partial_batch_use_only_matching_evidence():
    before = (
        "Po potwierdzeniu ustawienia bramy przejdziemy na otwarcie o 12:30. "
        "Potwierdzenia ustawienia bramy jeszcze nie ma. Dotychczasowe otwarcie to 11:45. "
        "Która pora obowiązuje?"
    )
    after = (
        "W rozkładzie papierowym wciąż widnieje 11:45. "
        "Kierownik potwierdził ustawienie bramy. Zapisz godziny z ich źródłami."
    )
    reply = studio_followup(after, _history(before))
    assert reply is not None and "Obowiązuje godzina 12:30" in reply
    assert "W rozkładzie papierowym nadal podano 11:45" in reply
    assert studio_followup(after.replace("bramy", "furtki"), _history(before)) is None
    batch = "Przyjęto 12 paczek. Otworzono 5 paczek, a 7 jeszcze nie przejrzano. Podaj zakres."
    assert studio_followup(batch, []) == (
        "Przyjęto 12 paczek. Otworzono 5 z 12 paczek, a 7 nadal nie sprawdzono."
    )
    assert studio_followup(batch.replace("7 jeszcze", "6 jeszcze"), []) is None
    assert studio_followup(batch.replace("5 paczek", "5 kompletów"), []) is None


def test_clause_shift_requires_the_same_person_and_explicit_registration():
    first = (
        "Grafik nie zawiera wpisu dla Joanny. Joanna zgłosiła chęć na wtorkowy dyżur. "
        "Jaki stan ma Joanna?"
    )
    second = (
        "Joanna nie zaakceptowała przydziału. Koordynator wpisał Joannę do grafiku we wtorek "
        "na 16:10. Zapisz dzień, godzinę i stan."
    )
    status = studio_followup(second, _history(first))
    assert status is not None and "Joannę do grafiku we wtorek o 16:10" in status
    assert "czeka na potwierdzenie" in status
    assert (
        studio_followup(second.replace("wpisał Joannę", "wpisał Lenę"), _history(first))
        is None
    )
    assert (
        studio_followup(second.replace("Joanna nie", "Lena nie"), _history(first))
        is None
    )
    assert (
        studio_followup(second.replace("wpisał", "planuje wpisać"), _history(first))
        is None
    )
