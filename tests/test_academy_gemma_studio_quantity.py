from __future__ import annotations

import pytest

from venom_core.api.schemas.llm_simple import HistoryMessage
from venom_core.services.chat_policy.studio_quantity import studio_quantity

_BUNDLE = (
    "Na dwa zdjęcia na wystawę chcę zamówić identyczne ramy. "
    "U Linorytu komplet kosztuje 118 zł, jest gotowy jutro. "
    "U Pracowni Północ kosztuje 96 zł i czeka się do wtorku. "
    "Wtorek mi pasuje, liczę każdy grosz."
)
_ROUTE = (
    "Na dojazd do pracowni mam dwa warianty. "
    "Przez rynek idę 6 minut i jestem na miejscu po 35 minutach. "
    "Przez wiadukt idę 13 minut, ale jestem po 27 minutach. "
    "Wypisz różnicę, żebym mógł podjąć decyzję."
)
_NOTICE = (
    "„Wydajemy mapy w recepcji do 16. Jedna bezpłatna mapa na rodzinę. "
    "Drugą można pobrać za 8 zł.” Zrób z tego trzy krótkie komunikaty, "
    "bez wykrzykników, do wydruku na kartce."
)
_NO_WE = "Zapomniałem, że to kartka dla gości. Usuń formę „my”."


def _history(
    text: str, prior_draft: str = "Poprzednia odpowiedź."
) -> list[HistoryMessage]:
    return [
        HistoryMessage(role="user", content=text),
        HistoryMessage(role="assistant", content=prior_draft),
    ]


def test_bundle_prices_are_subtracted_once_for_the_whole_order():
    reply = studio_quantity(_BUNDLE, [])
    assert reply is not None
    assert "Pracowni Północ" in reply
    assert "96 zł" in reply and "22 zł" in reply and "44 zł" not in reply
    assert "termin Ci odpowiada" in reply


def test_explicit_per_item_price_is_compared_only_after_resolving_count():
    prompt = (
        "Chcę zamówić trzy identyczne oprawy. "
        "U Nagietka zestaw kosztuje 99,50 zł, jest gotowy jutro. "
        "U Wrzosu sztuka kosztuje 24,25 zł i czeka się do piątku. "
        "Piątek mi pasuje, zależy mi na najniższej cenie."
    )
    reply = studio_quantity(prompt, [])
    assert reply is not None
    assert "72,75 zł" in reply and "26,75 zł" in reply and "Wrzosu" in reply
    assert studio_quantity(prompt.replace("trzy identyczne", "identyczne"), []) is None
    assert (
        studio_quantity(
            prompt.replace("sztuka kosztuje", "kosztuje").replace("zestaw", "sztuka"),
            [],
        )
        is None
    )


@pytest.mark.parametrize(
    "prompt",
    [
        _BUNDLE.replace("komplet kosztuje", "kosztuje"),
        _BUNDLE.replace("96 zł", "96 euro"),
        _BUNDLE.replace("96 zł", "118 zł"),
        _BUNDLE.replace("Wtorek mi pasuje", "Sobota mi pasuje"),
        _BUNDLE.replace("U Pracowni Północ", "U Linorytu"),
        "A gdybym odebrała w sobotę?",
    ],
)
def test_unconfirmed_scope_currency_vendor_or_collection_day_is_not_guessed(prompt):
    assert studio_quantity(prompt, _history(_BUNDLE)) is None


def test_route_comparison_keeps_walking_time_separate_from_entire_trip():
    first = studio_quantity(_ROUTE, [])
    assert first is not None
    walk, whole, _ = first.split(".")
    assert "marsz" in walk and "rynek" in walk and "6 min" in walk and "13 min" in walk
    assert (
        "dojazd" in whole
        and "wiadukt" in whole
        and "27 min" in whole
        and "35 min" in whole
    )
    answer = studio_quantity("No to tę krótszą.", _history(_ROUTE, "Jedź przez rynek."))
    assert answer == f"{first} Chodzi Ci o marsz czy cały dojazd?"


def test_new_route_names_and_explicit_full_trip_phrasing():
    prompt = (
        "Na dojazd do kina mam dwa warianty. "
        "Przez rondo idę 18 minut i cały dojazd trwa 31 minut. "
        "Przez park idę 9 minut, ale jestem po 42 minutach. "
        "Porównaj obie trasy."
    )
    first = studio_quantity(prompt, [])
    assert first is not None
    assert "marsz jest przez park" in first and "dojazd jest przez rondo" in first
    assert studio_quantity(prompt.replace("31 minut", "8 minut"), []) is None
    assert (
        studio_quantity(
            prompt.replace("przez park", "przez rondo").replace(
                "Przez park", "Przez rondo"
            ),
            [],
        )
        is None
    )
    assert (
        studio_quantity(
            prompt.replace("jestem po 42 minutach", "nie znam całego czasu"), []
        )
        is None
    )


def test_printed_notice_keeps_exact_second_item_and_all_facts_after_revision():
    draft = studio_quantity(_NOTICE, [])
    expected = [
        "Wydajemy mapy w recepcji do 16:00.",
        "Jedna bezpłatna mapa na rodzinę.",
        "Drugą można pobrać za 8 zł.",
    ]
    assert draft == "\n".join(expected)
    revised = studio_quantity(_NO_WE, _history(_NOTICE, "Dodatkowe mapy: 8 zł."))
    assert revised == "\n".join(["Mapy do odbioru w recepcji do 16:00.", *expected[1:]])
    assert revised.count("\n") == 2 and "!" not in revised


def test_every_later_item_stays_every_later_if_that_is_what_source_says():
    prompt = _NOTICE.replace("mapy w recepcji do 16", "broszury przy wejściu do 9:30")
    prompt = prompt.replace("mapa na rodzinę", "broszura na parę")
    prompt = prompt.replace(
        "Drugą można pobrać za 8 zł", "Każdą kolejną można odebrać za 4,50 zł"
    )
    answer = studio_quantity(_NO_WE, _history(prompt))
    assert answer is not None
    assert answer.splitlines() == [
        "Broszury do odbioru przy wejściu do 09:30.",
        "Jedna bezpłatna broszura na parę.",
        "Każdą kolejną można odebrać za 4,50 zł.",
    ]


@pytest.mark.parametrize(
    "prompt",
    [
        _NOTICE.replace("mapa na rodzinę", "opaska na rodzinę"),
        _NOTICE.replace("Drugą", "Drugi"),
        _NOTICE.replace("do 16", "do 25:65"),
        _NOTICE.replace("8 zł", "8 USD"),
        _NOTICE.replace("trzy krótkie", "cztery krótkie"),
        _NOTICE + " Wyślij to do uczestników.",
    ],
)
def test_notice_rejects_unbound_subjects_unsupported_units_and_extra_operations(prompt):
    assert studio_quantity(prompt, []) is None


@pytest.mark.parametrize("followup", [_NO_WE, "No to tę krótszą."])
def test_followup_uses_only_the_adjacent_user_source_and_never_the_prior_draft(
    followup,
):
    relevant = _NOTICE if followup == _NO_WE else _ROUTE
    wrong_context = _history(relevant) + _history("Inny temat.", relevant)
    assert studio_quantity(followup, wrong_context) is None
    assert studio_quantity(followup, _history("Inny temat.", relevant)) is None
    messages = _history(relevant)
    messages[0].material_ids = ["not_available_to_this_contract"]
    assert studio_quantity(followup, messages) is None
