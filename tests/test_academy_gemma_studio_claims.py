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
    only_open = "Rzutnik: zwrot niepotwierdzony (termin jutro)."
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
