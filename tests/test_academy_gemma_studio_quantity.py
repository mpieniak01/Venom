from __future__ import annotations

import pytest

from venom_core.api.schemas.llm_simple import HistoryMessage
from venom_core.services.chat_policy.studio_dialog_compare import studio_comparison
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
    ],
)
def test_unconfirmed_scope_currency_vendor_or_collection_day_is_not_guessed(prompt):
    assert studio_quantity(prompt, _history(_BUNDLE)) is None


@pytest.mark.parametrize(
    ("question", "source", "names"),
    [
        ("A gdybym odebrała w sobotę?", _BUNDLE, ("Linorytu", "Pracowni Północ")),
        (
            "A gdybym odebrał w niedzielę?",
            _BUNDLE.replace("Linorytu", "Fali")
            .replace("Pracowni Północ", "Iskry")
            .replace("Wtorek mi pasuje", "Wtorek akceptuję"),
            ("Fali", "Iskry"),
        ),
    ],
)
def test_offer_followup_asks_for_pickup_availability(question, source, names):
    reply = studio_quantity(question, _history(source, "Punkt jest otwarty w weekend."))
    assert reply is not None
    assert all(name in reply for name in names)
    assert "jutro" in reply and "do wtorku" in reply and "datę" in reply
    assert "wydaje" in reply and "otwarty" not in reply
    assert "wybierz" not in reply.casefold()
    assert studio_quantity(question, _history("Chcę zamówić ramy.")) is None
    cancelled = source.rsplit(". ", 1)[0] + ". Druga oferta jest już nieaktualna."
    assert studio_quantity(question, _history(cancelled)) is None
    assert (
        studio_quantity(question, _history(source.replace(names[1], names[0]))) is None
    )
    assert (
        studio_quantity(question + " Punkt potwierdził odbiór.", _history(source))
        is None
    )


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


def test_route_to_explicit_destination_keeps_both_time_axes():
    prompt = (
        "Do hali przez park idę 4 minuty, a cała podróż trwa 31 minut. "
        "Przez most idę 12 minut, lecz cała podróż trwa 24 minuty. Porównaj oba warianty."
    )
    reply = studio_quantity(prompt, [])
    assert reply == (
        "Krótszy marsz jest przez park (4 min wobec 12 min). "
        "Krótszy dojazd jest przez most (24 min wobec 31 min)."
    )
    assert studio_quantity("W takim razie wybierz krótszą.", _history(prompt)) == (
        f"{reply} Chodzi Ci o marsz czy cały dojazd?"
    )
    assert (
        studio_quantity(prompt.replace("Przez most", "Do garażu przez most"), [])
        is None
    )


def test_duration_difference_uses_only_the_requested_measure():
    prompt = (
        "Trasa wschodnia zajmuje 10 minut pieszo i 48 minut łącznie. "
        "Zachodnia 20 minut pieszo i 34 łącznie. O ile różni się sam czas marszu?"
    )
    assert studio_quantity(prompt, []) == (
        "Czas marszu różni się o 10 min. Krócej jest na trasie: wschodnia."
    )
    assert studio_quantity(
        "A różnica czasu łącznego?", _history(prompt, "34 min.")
    ) == ("Czas całej podróży różni się o 14 min. Krócej jest na trasie: Zachodnia.")
    assert studio_quantity(prompt.replace("34 łącznie", "34 pieszo"), []) is None
    assert studio_quantity(prompt.replace("20 minut pieszo", "20 pieszo"), []) is None


def test_named_route_metrics_can_be_presented_in_reversed_order():
    prompt = (
        "Trasa podmiejska trwa 47 minut łącznie, a pieszo 9 minut. "
        "Trasa nad rzeką zajmuje 25 min łącznie, ale pieszo 14 min. "
        "O ile różni się czas łączny?"
    )
    assert studio_quantity(prompt, []) == (
        "Czas całej podróży różni się o 22 min. Krócej jest na trasie: nad rzeką."
    )
    assert studio_quantity("A różnica samego czasu marszu?", _history(prompt)) == (
        "Czas marszu różni się o 5 min. Krócej jest na trasie: podmiejska."
    )


def test_discount_is_not_free_and_second_item_is_not_every_later_item():
    prompt = (
        "„Bilety wydajemy w biurze do 13. Jeden bilet zniżkowy na osobę. "
        "Drugi można kupić za 7 zł.” Zrób z tego trzy krótkie komunikaty bez wykrzykników."
    )
    revised = "Usuń formę „my”, to kartka dla gości. Zachowaj wszystkie dane."
    assert studio_quantity(prompt, []) == "\n".join(
        [
            "Bilety wydajemy w biurze do 13:00.",
            "Jeden bilet zniżkowy na osobę.",
            "Drugi można kupić za 7 zł.",
        ]
    )
    assert studio_quantity(
        revised, _history(prompt, "Pierwszy bilet gratis.")
    ) == "\n".join(
        [
            "Bilety do odbioru w biurze do 13:00.",
            "Jeden bilet zniżkowy na osobę.",
            "Drugi można kupić za 7 zł.",
        ]
    )
    assert (
        studio_quantity(
            prompt.replace(
                "bilet zniżkowy na osobę", "bilet bezpłatny na osobę jest zniżkowy"
            ),
            [],
        )
        is None
    )


def test_clock_correction_preserves_entitlement_and_scope_of_paid_price():
    prompt = (
        "„Torby odbieramy w portierni do 18. Pierwsza torba na rodzinę jest bezpłatna. "
        "Każda następna kosztuje 4 zł.” Podaj trzy krótkie komunikaty bez wykrzykników."
    )
    draft = studio_quantity(prompt, [])
    assert draft == "\n".join(
        [
            "Torby odbieramy w portierni do 18:00.",
            "Pierwsza torba na rodzinę jest bezpłatna.",
            "Każda następna kosztuje 4 zł.",
        ]
    )
    corrected = studio_quantity(
        "Zmień tylko godzinę odbioru na 17.", _history(prompt, "Każda torba za 4 zł.")
    )
    assert corrected == draft.replace("18:00", "17:00")
    assert (
        studio_quantity("Zmień tylko godzinę odbioru na 27.", _history(prompt)) is None
    )


@pytest.mark.parametrize(
    ("service", "entitlement", "charge"),
    [
        ("Żetony", "Jeden zniżkowy żeton na osobę", "Drugi kosztuje 7 zł"),
        (
            "Nalepki",
            "Jedna bezpłatna nalepka na rodzinę",
            "Każda następna kosztuje 5 zł",
        ),
    ],
)
def test_unlisted_notice_items_preserve_status_and_ordinal(
    service, entitlement, charge
):
    source = (
        f"„{service} wydajemy w bibliotece do 17. {entitlement}. {charge}.” "
        "Zrób z tego trzy krótkie komunikaty bez wykrzykników."
    )
    assert studio_quantity(source, []) == (
        f"{service} wydajemy w bibliotece do 17:00.\n{entitlement}.\n{charge}."
    )
    assert (
        studio_quantity(
            "Usuń formę „my”, to kartka dla gości. Zachowaj wszystkie dane.",
            _history(source),
        )
        == f"{service} do odbioru w bibliotece do 17:00.\n{entitlement}.\n{charge}."
    )


def test_pickup_notice_updates_only_location_from_the_user():
    request = (
        "Napisz jednolinijkową informację z faktów: identyfikatory do odbioru "
        "od 11:30 przy bramie, każdy bierze po dwa. Bez nagłówka."
    )
    assert studio_quantity(request, []) == (
        "Identyfikatory do odbioru od 11:30 przy bramie, każdy bierze po dwa."
    )
    assert studio_quantity(
        "Zmień tylko miejsce na gablotę w wejściu.", _history(request)
    ) == (
        "Identyfikatory do odbioru od 11:30, każdy bierze po dwa "
        "(zmiana miejsca na gablotę w wejściu)."
    )
    assert studio_quantity("Zmień tylko miejsce na gablotę w wejściu.", []) is None


def test_travel_comparison_keeps_protection_for_each_item():
    prompt = (
        "Na wystawie można wybrać miskę ceramiczną albo papierowy rysunek. "
        "Obie rzeczy kosztują 17 zł. Do domu goście jadą autobusem. "
        "Jak porównać ryzyko w podróży?"
    )
    assert studio_quantity(prompt, []) == (
        "Obie rzeczy kosztują 17 zł. Miska ceramiczna: chroń przed uderzeniem i stłuczeniem. "
        "Papierowy rysunek: zabezpiecz przed zgięciem."
    )
    colors = prompt.replace("porównać ryzyko w podróży", "pokazać różnice w kolorach")
    assert studio_quantity(colors, []) == (
        "Jakie kolory mają obie rzeczy? Podaj je, żebym mógł opisać różnicę."
    )
    assert (
        studio_quantity(
            colors.replace("miskę ceramiczną", "czerwoną miskę ceramiczną"), []
        )
        is None
    )
    assert (
        studio_quantity(prompt.replace("Obie rzeczy kosztują 17 zł.", ""), []) is None
    )


def test_new_pickup_day_uses_only_the_seller_that_confirmed_it():
    prior = (
        "Chcę zamówić dwa albumy. U Fali komplet kosztuje 70 zł, jest gotowy jutro. "
        "U Iskry komplet kosztuje 41 zł i czeka się do środy. "
        "Środę akceptuję, zależy mi na najniższej cenie."
    )
    prompt = (
        "Chodzi o czwartek po tej środzie. Iskra potwierdziła, że tego dnia wydaje "
        "zamówienia. Która opcja mieści się w 50 zł?"
    )
    assert studio_quantity(prompt, _history(prior)) == (
        "Odbiór w czwartek jest potwierdzony u Iskry. Komplet kosztuje 41 zł i mieści się w budżecie."
    )
    assert studio_quantity(prompt.replace("50 zł", "40 zł"), _history(prior)) == (
        "Odbiór w czwartek jest potwierdzony u Iskry. Komplet za 41 zł przekracza budżet o 1 zł."
    )
    assert studio_quantity(prompt.replace("Iskra", "Fala"), _history(prior)) == (
        "Odbiór w czwartek jest potwierdzony u Fali. Komplet za 70 zł przekracza budżet o 20 zł."
    )
    assert studio_quantity(prompt.replace("Iskra", "Kreska"), _history(prior)) is None
    assert (
        studio_quantity(
            prompt,
            _history(
                prior.replace(
                    "Środę akceptuję, zależy mi na najniższej cenie",
                    "Druga oferta została anulowana",
                )
            ),
        )
        is None
    )


def test_support_changes_weight_priority_instead_of_copying_previous_choice():
    prompt = (
        "Paproć jest sztywna i waży 580 g, a Śnieg jest elastyczna i waży 410 g. "
        "Bez stolika, rysuję na kolanach. Która lepsza?"
    )
    initial = studio_comparison(prompt, [])
    assert initial is not None and "sztywny wariant „Paproć”" in initial
    change = "A gdy pojawi się stół?"
    history = _history(prompt, "Nadal konieczna będzie Paproć.")
    reply = studio_comparison(change, history)
    assert reply is not None and "lżejszy wariant „Śnieg” może wystarczyć" in reply
    assert "pełnym podparciu" in reply
    same = prompt.replace("410 g", "580 g")
    assert studio_comparison(change, _history(same)) == (
        "Przy pełnym podparciu na blacie oba warianty mogą wystarczyć, a różnicy w wadze nie ma."
    )
    reverse = prompt.replace("410 g", "600 g")
    response = studio_comparison(change, _history(reverse))
    assert response is not None and "lżejszy wariant „Paproć”" in response
    assert studio_comparison(change, _history("Mam tylko jedną podkładkę.")) is None


def test_square_fit_keeps_equal_price_and_treats_cleaning_as_secondary():
    prompt = (
        "Mam matę z aksamitem, 24,5 × 24,5 cm, i drugą z lnem, 33 × 33 cm. "
        "Obie kosztują 21 zł. Podstawa ma 26 × 26 cm. Która zmieści się w całości?"
    )
    result = studio_comparison(prompt, [])
    assert result is not None and "pierwsza opcja" in result
    assert all(
        value in result for value in ("z aksamitem", "24,5 × 24,5 cm", "33 cm", "21 zł")
    )
    clean = (
        "Ale z lnem czyści się łatwiej. Co wybrać, jeśli nie chcę wystających brzegów?"
    )
    chosen = studio_comparison(clean, _history(prompt, "Zamówiono lnianą."))
    assert chosen is not None and "pierwszą" in chosen
    assert "z lnem łatwiej czyścić, ale jej brzegi będą wystawać" in chosen
    assert (
        studio_comparison(clean.replace("z lnem", "ze skórą"), _history(prompt)) is None
    )
    same = studio_comparison(clean.replace("z lnem", "z aksamitem"), _history(prompt))
    assert same is not None and "też łatwiejsza do czyszczenia" in same
    both = prompt.replace("26 × 26", "33 × 33")
    assert studio_comparison(both, []) == (
        "Obie opcje mieszczą się w całości. Bok dostępnej powierzchni ma 33 cm. Obie opcje kosztują 21 zł."
    )
    neither = prompt.replace("26 × 26", "20 × 20")
    denied = studio_comparison(neither, [])
    assert denied is not None and denied.startswith("Żadna opcja nie mieści się")
    assert studio_comparison(clean, _history(both)) is None
    assert studio_comparison(prompt.replace("26 × 26", "26 × 22"), []) is None
    assert studio_comparison(prompt.replace("Obie", "Jedna"), []) is None


def test_material_roles_survive_selective_pdf_availability():
    prompt = (
        "W czytelni jest wykaz wydań do wyboru mapy i osobny przewodnik do opisów legendy. "
        "Oba chcę udostępnić, ale tylko przewodnik będzie pojutrze drukowany. "
        "Jak opisać te dwa materiały na liście dla zespołu?"
    )
    assert studio_comparison(prompt, []) == (
        "1. Wykaz wydań do wyboru mapy — do udostępnienia.\n"
        "2. Przewodnik do opisów legendy — do udostępnienia, do druku pojutrze."
    )
    change = "Dopisz przy tym pierwszym, że można go pobrać jako PDF."
    assert studio_comparison(change, _history(prompt, "Przewodnik z PDF.")) == (
        "1. Wykaz wydań do wyboru mapy — do udostępnienia, do pobrania jako PDF.\n"
        "2. Przewodnik do opisów legendy — do udostępnienia, do druku pojutrze."
    )
    assert (
        studio_comparison(prompt.replace("tylko przewodnik", "tylko legenda"), [])
        is None
    )
    assert (
        studio_comparison(
            change, _history("W czytelni niczego jeszcze nie zestawiono.")
        )
        is None
    )


def test_definitions_are_selected_from_meaning_for_each_user_goal():
    prompt = (
        "Porównano dwa terminy: pole tekstu i obszar pieczęci. Pole określa miejsce na tekst, "
        "a obszar pieczęci oznacza wymiar całej odbitki. Jak to prosto wyjaśnić?"
    )
    assert studio_comparison(prompt, []) == (
        "Pole tekstu określa miejsce na tekst. Obszar pieczęci oznacza wymiar całej odbitki."
    )
    previous = _history(prompt, "Mylący opis wielkości uchwytu.")
    assert (
        studio_comparison(
            "Czy na oszacowanie rozmiaru odbitki patrzeć pod tym pierwszym czy drugim?",
            previous,
        )
        == "Wybierz drugie pojęcie, „obszar pieczęci”. Obszar pieczęci oznacza wymiar całej odbitki."
    )
    assert (
        studio_comparison(
            "Czy na długość napisu patrzeć pod tym pierwszym czy drugim?",
            previous,
        )
        == "Wybierz pierwsze pojęcie, „pole tekstu”. Pole tekstu określa miejsce na tekst."
    )
    assert (
        studio_comparison(
            "Czy na wygląd uchwytu patrzeć pod tym pierwszym czy drugim?", previous
        )
        is None
    )
    assert (
        studio_comparison(prompt.replace("obszar pieczęci", "pole pieczęci"), [])
        is None
    )
