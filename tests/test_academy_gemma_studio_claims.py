from collections.abc import Sequence

import pytest

from venom_core.api.schemas.llm_simple import HistoryMessage
from venom_core.services.chat_policy.studio_claims import prepare_studio_claim_check

_SMS = (
    "Napisz krótki SMS do Kai, że kolacja jest przełożona na 20. "
    "Na tym etapie chcę zobaczyć treść, wysyłkę robię sama."
)
_SMS_NOTE = "Czy mogę w notatce zaznaczyć, że SMS poszedł?"
_LEDGER = (
    "Na papierowej liście wypożyczeń mam: statyw — zwrot wpisany, rzutnik — termin "
    "jutro, kabel HDMI — bez wpisu o zwrocie. Czy wszystkie trzy sprzęty są "
    "już z powrotem w pracowni?"
)
_PUT_BACK = "Przed chwilą odłożyłam kabel na półkę. Czego jeszcze nie potwierdziliśmy?"
_POSTERS = "Na plakaty mamy tuby. Jak to dopisać jednym zdaniem?"
_CUPS = "A z kubkami pod tym samym względem?"


def _history(
    *users: str, assistant: str = "SMS wysłany. Rzutnik jest w pracowni."
) -> Sequence[HistoryMessage]:
    return [
        item
        for user in users
        for item in (
            HistoryMessage(role="user", content=user),
            HistoryMessage(role="assistant", content=assistant),
        )
    ]


def test_phone_call_does_not_license_sms_inclusion_in_note():
    check = prepare_studio_claim_check(
        f"Zdążyłam jednak zadzwonić. {_SMS_NOTE}", _history(_SMS)
    )
    assert check is not None
    draft = (
        "Tak, możesz to zrobić. Oto propozycja: SMS do Kai wysłany. "
        "Zadzwoniłam do Kai, SMS wysłany."
    )
    assert check.publish(draft) == (
        "Możesz odnotować telefon do Kai. Sam telefon nie potwierdza wysłania SMS-u."
    )
    safe = (
        "Telefon do Kai nie potwierdza, że SMS wysłano. Zapisz w notatce sam telefon."
    )
    assert check.publish(safe) == safe


def test_messaging_evidence_must_agree_on_recipient_and_action():
    history = _history(_SMS, assistant="SMS do Kai został wysłany.")
    phone_to_someone_else = f"Zadzwoniłam do Oli. Wysłałam SMS do Oli. {_SMS_NOTE}"
    check = prepare_studio_claim_check(phone_to_someone_else, history)
    assert check is not None
    approved = "SMS do Oli wysłany."
    assert check.publish(approved) == approved
    unsupported = "Potwierdzam: SMS do Kai wysłany."
    assert check.publish(unsupported) == (
        "Telefon nie potwierdza wysłania SMS-u. Zapisz wysłanie dopiero po jego potwierdzeniu."
    )
    sent = prepare_studio_claim_check(f"Wysłałam SMS do Kai. {_SMS_NOTE}", history)
    assert sent is not None
    assert sent.publish(unsupported) == unsupported
    assert (
        sent.publish("SMS do Oli został wysłany.")
        == "Potwierdzono wysłanie SMS-u do Kai."
    )


def test_return_entries_and_due_dates_support_only_register_status():
    check = prepare_studio_claim_check(_LEDGER, [])
    assert check is not None
    draft = (
        "Nie, nie wszystkie trzy sprzęty są już w pracowni.\n"
        "Statyw – jest w pracowni (wpisano zwrot).\n"
        "Rzutnik – nie jest w pracowni (termin zwrotu to jutro).\n"
        "Kabel HDMI – brak wpisu o zwrocie."
    )
    corrected = (
        "Statyw: zwrot wpisany na liście. Rzutnik: zwrot niepotwierdzony (termin jutro). "
        "Kabel HDMI: brak wpisu potwierdzającego zwrot."
    )
    assert check.publish(draft) == corrected
    assert check.publish("Statyw jest w pracowni (wpisano zwrot).") == corrected
    assert (
        check.publish("Rzutnik jest poza pracownią i nie wiadomo, kiedy wróci.")
        == corrected
    )
    query = "Czy możesz sprawdzić, czy rzutnik jest w pracowni?"
    assert check.publish(query) == query
    safe = (
        "Przy statywie wpisano zwrot, przy rzutniku jest tylko termin, "
        "a przy kablu HDMI brak wpisu. Nie można potwierdzić, czy wszystkie są w pracowni."
    )
    assert check.publish(safe) == safe


def test_return_of_one_named_item_cannot_confirm_another_location():
    check = prepare_studio_claim_check(_PUT_BACK, _history(_LEDGER))
    assert check is not None
    draft = (
        "Skoro kabel HDMI jest już na półce, to jedynym sprzętem, którego statusu "
        "nie potwierdziliśmy, jest rzutnik. Zgodnie z listą, jego termin to jutro, "
        "więc obecnie wciąż jest on poza pracownią."
    )
    only_open = (
        "Rzutnik: zwrot niepotwierdzony (termin jutro). "
        "Kabel HDMI jest na półce według Twojej informacji."
    )
    assert check.publish(draft) == only_open
    safe = "Kabel HDMI jest na półce. Do potwierdzenia pozostaje tylko rzutnik."
    assert check.publish(safe) == safe
    assert check.publish("Kabel HDMI nie jest na półce.") == only_open
    assert check.publish("Sprawdziłem półkę. Kabel HDMI jest na półce.") == only_open


def test_ambiguous_item_shortcut_does_not_claim_either_cable():
    two_cables = _LEDGER.replace(
        "statyw — zwrot wpisany,", "kabel LAN — zwrot wpisany,"
    )
    assert prepare_studio_claim_check(_PUT_BACK, _history(two_cables)) is None
    specific = _PUT_BACK.replace("kabel na", "kabel HDMI na")
    assert prepare_studio_claim_check(specific, _history(two_cables)) is not None


@pytest.mark.parametrize(
    "bad_draft",
    [
        'Jeśli chcesz zachować spójność, dopisz:\n"Kubki są pakowane w bezpieczne pudełka."',
        "Kubki dostają tuby.",
        "Kubki są już zapakowane.",
    ],
)
def test_packaging_for_one_product_does_not_transfer_to_another(bad_draft):
    check = prepare_studio_claim_check(
        _CUPS, _history(_POSTERS, assistant="Dla kubków mamy pudełka.")
    )
    assert check is not None
    assert check.publish(bad_draft) == (
        "Czy macie papier ochronny albo pudełka, żeby zabezpieczyć je na czas podróży?"
    )
    safe = (
        "Warto zabezpieczyć kubki przed stłuczeniem. Jeśli macie pudełka, "
        "możecie dopisać, że kubki są w nich pakowane."
    )
    assert check.publish(safe) == safe


def test_keeps_confirmed_packaging_of_the_exact_product():
    check = prepare_studio_claim_check(
        _CUPS, _history("Na kubki mamy pudełka.", _POSTERS)
    )
    assert check is not None
    good = "Do kubków dostępne są pudełka. Do plakatów dostępne są tuby."
    assert check.publish(good) == good
    assert check.publish("Kubki dostają tuby.") == (
        "Dostępne opakowanie dla tych rzeczy: pudełko."
    )
    assert check.publish("Kubki są już zapakowane w pudełka.") == (
        "Dostępne opakowanie dla tych rzeczy: pudełko."
    )


@pytest.mark.parametrize(
    ("text", "history"),
    [
        ("Możesz pomóc z listą zakupów?", _history(_LEDGER)),
        (_SMS_NOTE, _history(_SMS)),
        (_CUPS, _history("Wczoraj miałem długą podróż.")),
        (_CUPS, [HistoryMessage(role="assistant", content=_POSTERS)]),
    ],
)
def test_claim_check_requires_relevant_user_evidence(text, history):
    assert prepare_studio_claim_check(text, history) is None


def test_spoken_phone_channel_fixes_sms_draft_without_marking_sms_sent():
    initial = "Napisz krótki SMS do Oli, że zbiórka jest o 18. Chcę tylko szkic, wysyłkę zrobię sama."
    update = "Zdążyłam już porozmawiać z Olą przez telefon. Czy mogę zapisać, że SMS wysłany?"
    draft = "Tak, oczywiście! Możesz to zapisać w dowolny sposób, np.:\n\n*   **SMS wysłany**\n*   **Zbiórka potwierdzona z Olą**\n*   **Ola poinformowana**\n\nJeśli potrzebujesz, żeby pomóc Ci w czymś jeszcze, daj znać!"
    check = prepare_studio_claim_check(update, _history(initial))
    assert check is not None
    assert check.publish(draft) == (
        "Możesz odnotować rozmowę telefoniczną z Olą. "
        "Rozmowa nie potwierdza wysłania SMS-u."
    )


def test_instrumental_name_must_agree_on_the_entire_recipient_name():
    initial = "Napisz SMS do Oli Nowak, że zbiórka jest o 18."
    good_update = "Rozmawiałam przez telefon z Olą Nowak."
    bad_update = good_update.replace("Nowak", "Lis")
    good = prepare_studio_claim_check(f"{good_update} {_SMS_NOTE}", _history(initial))
    other = prepare_studio_claim_check(f"{bad_update} {_SMS_NOTE}", _history(initial))
    assert good is not None and other is not None
    assert good.publish("SMS wysłany.") == (
        "Możesz odnotować rozmowę telefoniczną z Olą Nowak. "
        "Rozmowa nie potwierdza wysłania SMS-u."
    )
    masculine = good_update.replace("Olą", "Olem")
    same_stem = prepare_studio_claim_check(
        f"{masculine} {_SMS_NOTE}", _history(initial)
    )
    assert same_stem is not None
    assert same_stem.publish("SMS wysłany.") == other.publish("SMS wysłany.")
    assert other.publish("SMS wysłany.") == (
        "Telefon nie potwierdza wysłania SMS-u. Zapisz wysłanie dopiero po jego potwierdzeniu."
    )


def test_list_is_not_evidence_of_a_room_and_true_shelf_update_is_kept():
    initial = "Na papierowej liście wypożyczeń mam: mikrofon — zwrot wpisany, projektor — termin jutro, statyw — bez wpisu o zwrocie. Czy wszystkie trzy sprzęty są już z powrotem w sali?"
    followup = (
        "Przed chwilą odłożyłem statyw na półkę. Czego jeszcze nie potwierdziliśmy?"
    )
    draft = "Nie, nie wszystkie trzy sprzęty są już z powrotem w sali.\n\nOto status sprzętów na podstawie Twojej listy:\n1. **Mikrofon** – jest w sali (masz wpis o zwrocie).\n2. **Projektor** – nie jest w sali (termin zwrotu przypada na jutro).\n3. **Statyw** – status jest niejasny (brak wpisu o zwrocie), więc nie można potwierdzić, czy jest już w sali."
    safe = "Skoro statyw jest już na półce, to potwierdziliśmy jego zwrot.\n\nJedynym sprzętem, którego zwrotu jeszcze nie potwierdziliśmy, jest **projektor** (jego termin zwrotu przypada na jutro)."
    check = prepare_studio_claim_check(initial, [])
    checked_followup = prepare_studio_claim_check(followup, _history(initial))
    assert check is not None and checked_followup is not None
    assert check.publish(draft) == (
        "Mikrofon: zwrot wpisany na liście. Projektor: zwrot niepotwierdzony "
        "(termin jutro). Statyw: brak wpisu potwierdzającego zwrot."
    )
    assert check.publish("Projektor jest w sali.") == check.publish(draft)
    assert check.publish("Projektor jest poza salą.") == check.publish(draft)
    assert checked_followup.publish(safe) == safe


@pytest.mark.parametrize("place", ["w czytelni", "we wnęce", "na regale w holu"])
def test_missing_location_evidence_generalizes_across_explicit_places(place):
    text = (
        "Na karcie wypożyczeń mam: czytnik — zwrot wpisany, "
        "mikrofon — termin jutro. Czy oba sprzęty są " + place + "?"
    )
    check = prepare_studio_claim_check(text, [])
    assert check is not None
    assert check.publish(f"Czytnik jest {place}.") == (
        "Czytnik: zwrot wpisany na liście. Mikrofon: zwrot niepotwierdzony (termin jutro)."
    )
    question = f"Nie można potwierdzić, czy czytnik jest {place}."
    assert check.publish(question) == question


def test_only_sketchbooks_have_the_reported_covers():
    initial = (
        "Na tabliczce przy stoisku piszę o szklankach i szkicownikach. "
        "Do szkicowników są papierowe obwoluty. Jak doradzić zabranie szkicownika w podróż?"
    )
    check = prepare_studio_claim_check(
        "A ze szklankami pod tym samym względem?", _history(initial)
    )
    assert check is not None
    unsupported = "Szklanki dostają papierowe obwoluty."
    assert check.publish(unsupported) == (
        "Czy macie papier ochronny albo pudełka, żeby zabezpieczyć je na czas podróży?"
    )
    known = "Do szkicowników dostępne są papierowe obwoluty."
    assert check.publish(known) == known
    advice = "Szklanki warto zabezpieczyć w drodze. Czy macie papier ochronny?"
    assert check.publish(advice) == advice
    truncated = "Odpowiedź przekroczyła limit długości."
    assert check.publish(truncated) == truncated


def test_inventory_draft_keeps_observation_separate_from_the_register():
    check = prepare_studio_claim_check(_PUT_BACK, _history(_LEDGER))
    assert check is not None
    draft = "Do potwierdzenia pozostaje rzutnik."
    assert check.publish(draft) == (
        f"{draft} Kabel HDMI jest na półce według Twojej informacji."
    )


def test_sms_question_after_phone_resolves_generic_yes_against_user_evidence():
    question = "Porozmawiałem z Martą przez telefon. Mam odnotować, że SMS wysłany?"
    check = prepare_studio_claim_check(
        question, _history("Ułóż SMS do Marty o spotkaniu.")
    )
    assert check is not None
    assert check.publish("Tak, możesz to odnotować. Zapisz to w notatkach.") == (
        "Możesz odnotować rozmowę telefoniczną z Martą. "
        "Rozmowa nie potwierdza wysłania SMS-u."
    )
    safe = "Nie. Rozmowa telefoniczna nie potwierdza wysłania SMS-u."
    assert check.publish(safe) == safe

    sent = prepare_studio_claim_check(
        "Wysłałem SMS do Marty. Czy odnotować wysłanie SMS-u?",
        _history("Ułóż SMS do Marty o spotkaniu."),
    )
    assert sent is not None
    assert sent.publish("Tak, możesz to odnotować.") == "Tak, możesz to odnotować."
