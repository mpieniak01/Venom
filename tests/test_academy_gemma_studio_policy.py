"""Verify claim and quantity policies through the Studio HTTP entry point."""

import pytest

from tests.test_academy_qualified_chat import native, streamed
from tests.test_academy_qualified_chat import studio_chat as qualified_studio_chat
from venom_core.api.schemas.llm_simple import HistoryMessage
from venom_core.services import llm_simple_service
from venom_core.services.chat_policy.qualified_chat import GENERATION_TRUNCATED
from venom_core.services.chat_policy.studio_calculator import plan_studio_calculation
from venom_core.services.chat_policy.studio_publication import publication_check
from venom_core.services.chat_policy.studio_revision import studio_revision
from venom_core.services.chat_policy.studio_visibility import studio_visibility
from venom_core.services.ollama_text_adapter import QUALIFIED_BOLT_MODEL

studio_chat = qualified_studio_chat

_SMS = "Zdążyłam jednak zadzwonić. Czy mogę w notatce zaznaczyć, że SMS poszedł?"
_HISTORY = (
    {
        "role": "user",
        "content": (
            "Napisz krótki SMS do Kai, że kolacja jest przełożona na 20. "
            "Na tym etapie chcę zobaczyć treść, wysyłkę robię sama."
        ),
    },
    {"role": "assistant", "content": "Cześć Kaju, kolacja jest o 20."},
)
_UNSUPPORTED = "SMS do Kai wysłany."
_GROUNDED = (
    "Możesz odnotować telefon do Kai. Sam telefon nie potwierdza wysłania SMS-u."
)
_ROUTE = (
    "Na dojazd do pracowni mam dwa warianty. Przez rynek idę 6 minut i jestem na miejscu "
    "po 35 minutach. Przez wiadukt idę 13 minut, ale jestem po 27 minutach. Wypisz różnicę, "
    "żebym mógł podjąć decyzję."
)


@pytest.mark.parametrize(("requested", "actual"), [(None, 256), (160, 160)])
def test_studio_buffers_claim_and_respects_the_client_limit(
    studio_chat, monkeypatch, requested, actual
):
    monkeypatch.setattr(
        llm_simple_service.SETTINGS, "ACADEMY_GEMMA_REVIEW_RETRY_ENABLED", True
    )
    chat, sent, replies = studio_chat
    replies.append(native(_UNSUPPORTED))
    output = chat(_SMS, _HISTORY, verify_history=True, max_tokens=requested)
    assert output == _GROUNDED
    assert len(sent) == 1 and not replies
    assert sent[0]["payload"]["options"]["num_predict"] == actual
    assert sent[0]["payload"]["stream"] is False


@pytest.mark.parametrize(
    ("draft", "finish", "expected"),
    [
        (
            "Odnotuj rozmowę telefoniczną z Kają.",
            "stop",
            "Odnotuj rozmowę telefoniczną z Kają.",
        ),
        (_UNSUPPORTED, "length", GENERATION_TRUNCATED),
    ],
)
def test_studio_preserves_good_drafts_and_does_not_retry_a_claim(
    studio_chat, monkeypatch, draft, finish, expected
):
    monkeypatch.setattr(
        llm_simple_service.SETTINGS, "ACADEMY_GEMMA_REVIEW_RETRY_ENABLED", True
    )
    chat, sent, replies = studio_chat
    replies.append(native(draft, reason=finish))
    assert chat(_SMS, _HISTORY, verify_history=True, max_tokens=160) == expected
    assert len(sent) == 1 and not replies


def test_studio_flag_controls_quantity_and_claims(studio_chat, monkeypatch):
    chat, sent, replies = studio_chat
    monkeypatch.setattr(
        llm_simple_service.SETTINGS, "ACADEMY_GEMMA_REVIEW_RETRY_ENABLED", True
    )
    result = chat(_ROUTE, verify_history=True, stream=False)
    assert "6 min" in result and "27 min" in result
    assert not sent
    monkeypatch.setattr(
        llm_simple_service.SETTINGS, "ACADEMY_GEMMA_REVIEW_RETRY_ENABLED", False
    )
    replies.append(native(_UNSUPPORTED))
    assert chat(_SMS, _HISTORY, verify_history=True, stream=False) == _UNSUPPORTED
    assert len(sent) == 1 and sent[0]["payload"]["options"]["num_predict"] == 256


@pytest.mark.parametrize("studio_chat", [QUALIFIED_BOLT_MODEL], indirect=True)
def test_studio_claim_policy_keeps_bolt_streaming(studio_chat, monkeypatch):
    monkeypatch.setattr(
        llm_simple_service.SETTINGS, "ACADEMY_GEMMA_REVIEW_RETRY_ENABLED", True
    )
    chat, sent, replies = studio_chat
    replies.append(streamed(_UNSUPPORTED))
    assert chat(_SMS, _HISTORY, verify_history=True) == _UNSUPPORTED
    assert len(sent) == 1 and sent[0]["payload"]["stream"] is True


@pytest.mark.parametrize(
    ("prompt", "topic"),
    [
        ("Przygotuj SMS do Ady o paczce. Chcę samą treść.", "paczce"),
        ("Napisz SMS do Łucji o wizycie. Chcę zobaczyć samą treść.", "wizycie"),
        ("Ułóż krótki SMS do Leny o spotkaniu zespołu.", "spotkaniu zespołu"),
    ],
)
def test_studio_topic_only_sms_adds_no_claims(studio_chat, monkeypatch, prompt, topic):
    monkeypatch.setattr(
        llm_simple_service.SETTINGS, "ACADEMY_GEMMA_REVIEW_RETRY_ENABLED", True
    )
    chat, sent, replies = studio_chat
    assert chat(prompt, verify_history=True) == f"Cześć, piszę o {topic}."
    assert not sent and not replies


def test_studio_topic_sms_preserves_explicit_facts(studio_chat, monkeypatch):
    monkeypatch.setattr(
        llm_simple_service.SETTINGS, "ACADEMY_GEMMA_REVIEW_RETRY_ENABLED", True
    )
    chat, sent, replies = studio_chat
    draft = "Cześć, paczka jest gotowa do odbioru w aptece po 17."
    replies.append(streamed(draft))
    result = chat(
        "Napisz SMS do Leny o paczce. Jest gotowa do odbioru w aptece po 17.",
        verify_history=True,
    )
    assert result == draft
    assert len(sent) == 1 and not replies


def test_pump_explanation_uses_the_named_part_and_preserves_it_when_shortened(
    studio_chat,
):
    chat, sent, replies = studio_chat
    first = "Po co jest zawór zwrotny wewnątrz ręcznej pompki do materaca? Wyjaśnij krótko początkującemu."
    expected = "Zawór zwrotny w pompce przepuszcza powietrze w jednym kierunku. Zamyka się, gdy powietrze próbuje się cofnąć."
    history = [
        {"role": "user", "content": first},
        {"role": "assistant", "content": "Zawór materaca trzyma ciśnienie."},
    ]
    assert chat(first, verify_history=True) == expected
    assert chat("Teraz prościej, bez analogii i w dwóch zdaniach.", history) == expected
    assert not sent and not replies
    target = "Zawór materaca wpuszcza powietrze. Po zamknięciu utrzymuje szczelność."
    replies.append(streamed(target))
    correction = "Pomyliłam element. Chodzi o zawór na materacu. Odpowiedz w dwóch prostych zdaniach."
    assert chat(correction, history) == target
    assert len(sent) == 1 and not replies


def test_packaging_uses_the_declared_subject_and_asks_for_missing_material(
    studio_chat, monkeypatch
):
    monkeypatch.setattr(
        llm_simple_service.SETTINGS, "ACADEMY_GEMMA_REVIEW_RETRY_ENABLED", True
    )
    chat, sent, replies = studio_chat
    assert (
        chat("Na plakaty mamy tuby. Jak to dopisać jednym zdaniem?", max_tokens=160)
        == "Na plakaty mamy tuby."
    )
    source = "Na tabliczce przy stoisku piszę o szklankach i szkicownikach. Do szkicowników są papierowe obwoluty. Jak doradzić zabranie szkicownika w podróż?"
    response = "Do szkicowników są papierowe obwoluty. Skorzystaj z tego zabezpieczenia w podróży."
    assert chat(source, verify_history=True) == response
    history = [
        {"role": "user", "content": source},
        {"role": "assistant", "content": response},
    ]
    assert chat("A ze szklankami pod tym samym względem?", history) == (
        "Czy macie papier ochronny albo pudełka, żeby zabezpieczyć je na czas podróży?"
    )
    assert not sent and not replies


def test_packaging_does_not_infer_size_from_missing_package(studio_chat, monkeypatch):
    monkeypatch.setattr(
        llm_simple_service.SETTINGS, "ACADEMY_GEMMA_REVIEW_RETRY_ENABLED", True
    )
    chat, sent, replies = studio_chat
    history = [
        {
            "role": "user",
            "content": "Na wyjeździe są ceramiczne miseczki i długopisy. Do długopisów mamy pokrowce. Jak je zabezpieczyć?",
        },
        {"role": "assistant", "content": "Długopisy można zabrać w pokrowcu."},
    ]
    replies.append(
        native("Miseczek nie można zabezpieczyć w pokrowcu, ponieważ są zbyt duże.")
    )
    assert chat("A z miseczkami pod tym samym względem?", history) == (
        "Czy macie papier ochronny albo pudełka, żeby zabezpieczyć je na czas podróży?"
    )
    assert len(sent) == 1 and not replies


@pytest.mark.parametrize(
    ("flag", "finish", "replacement", "expected"),
    [
        (False, "length", None, GENERATION_TRUNCATED),
        (True, "stop", None, "Zadaszenie chroni przed deszczem."),
        (True, "length", native("Gotowa informacja."), "Gotowa informacja."),
        (
            True,
            "length",
            native("Drugi urwany tekst", reason="length"),
            GENERATION_TRUNCATED,
        ),
    ],
)
def test_studio_retries_only_truncated_plain_draft_once(
    studio_chat, monkeypatch, flag, finish, replacement, expected
):
    monkeypatch.setattr(
        llm_simple_service.SETTINGS,
        "ACADEMY_GEMMA_STUDIO_TRUNCATION_RETRY_ENABLED",
        flag,
    )
    chat, sent, replies = studio_chat
    replies.append(native("Zadaszenie chroni przed deszczem.", reason=finish))
    if replacement is not None:
        replies.append(replacement)
    prompt = "Czemu zadaszenie się sprawdza przy wejściu? Odpowiedz krótko."
    assert chat(prompt, verify_history=True, stream=False, max_tokens=160) == expected
    assert len(sent) == (2 if replacement is not None else 1) and not replies
    if len(sent) == 2:
        first, second = (call["payload"] for call in sent)
        assert first["options"] == second["options"]
        assert first["messages"][1:] == second["messages"][1:]
        assert first["messages"][0]["content"] != second["messages"][0]["content"]


def test_studio_retries_a_truncated_draft_with_default_transport(
    studio_chat, monkeypatch
):
    monkeypatch.setattr(
        llm_simple_service.SETTINGS,
        "ACADEMY_GEMMA_STUDIO_TRUNCATION_RETRY_ENABLED",
        True,
    )
    chat, sent, replies = studio_chat
    replies.extend(
        [native("Urwany szkic", reason="length"), native("Pod dachem jest sucho.")]
    )
    assert (
        chat("Po co jest zadaszenie?", verify_history=True) == "Pod dachem jest sucho."
    )
    assert len(sent) == 2 and all(not call["payload"]["stream"] for call in sent)
    instruction = sent[0]["payload"]["messages"][0]["content"]
    assert "zachowaj wszystkie pozostałe ustalenia, liczby i warunki" in instruction
    assert "Plan, warunkowa zgoda, brak dowodu i wykonanie" in instruction


@pytest.mark.parametrize(
    ("prior", "current", "expected"),
    [
        (
            (
                "Mam cztery listwy po 27 cm i trzy listwy po 18 cm. Ile razem centymetrów?",
                "Każda krótka ma 19 cm. Odciąłem 1,6 m. Ile centymetrów brakuje?",
            ),
            "Jest odcięte 1,55 m. Ile centymetrów brakuje?",
            "Brakuje 10 cm (3 × 19 cm + 4 × 27 cm − 155 cm).",
        ),
        (
            (
                "Na pokaz poszło 12 biletów normalnych po 5 zł i 3 ulgowe po 4 zł. Podaj tylko za normalne.",
            ),
            "Ulgowe były jednak po 6 zł. Jaka jest kwota za wszystkie bilety?",
            "60 zł + 18 zł = 78 zł.",
        ),
        (
            (
                "Ile cm wstążki na pięć długich pasków po 31 cm i dwa krótkie po 10 cm?",
                "Każdy krótki zmieniam na 0,15 m. Długich nie zmieniam.",
            ),
            "Odmierzyłam 184 cm. Ile brakuje?",
            "Brakuje 1 cm (5 × 31 cm + 2 × 15 cm − 184 cm).",
        ),
        (
            (
                "9 wejść zwykłych kosztuje po 7 zł, 4 ulgowe po 3 zł. Ile koszt samych zwykłych?",
            ),
            "Ulgowe teraz po 5 zł. Ile łącznie za obie grupy?",
            "63 zł + 20 zł = 83 zł.",
        ),
        (
            (
                "Odczyt szerokości desek: Runa 20 cm, Tara 0,25 m, Arka 265 mm. Wskaż najwęższą.",
            ),
            "Deskę Runa wymieniliśmy na 28 cm. Która jest teraz najszersza?",
            "Największa szerokość: Runa, 28 cm. Porównanie: Runa 28 cm, Tara 25 cm, Arka 26,5 cm.",
        ),
        (
            (
                "Z 62 kartek 6 odkładamy. Resztę dzielimy równo na 7 szuflad. Ile kartek w każdej?",
            ),
            "Jedną pełną szufladę odłożyliśmy na zapas. Ile kartek jest w pozostałych?",
            "W pozostałych jest 48 kartek (6 × 8).",
        ),
        (
            (
                "Zużycie rękawiczek w czterech aktywnych grupach to 5, 8, 6 i 9. Jaka jest średnia?",
            ),
            "Drugiej grupie odejmij jedną rękawiczkę. Podaj średnią do jednego miejsca.",
            "Średnia z 4 grup to 6,8 ((5 + 7 + 6 + 9) ÷ 4).",
        ),
        (
            (
                "W piątek było 15 zgłoszeń dla sali A i 17 dla B. W sobotę A 21, B 12. "
                "Ile zgłoszeń dla B w oba dni?",
                "W sobotę sześć zgłoszeń było błędnie w A, przenieś je do B. Podaj poprawną sobotę.",
            ),
            "A teraz ile A po dwóch dniach?",
            "Dla A w oba dni: 15 + 15 = 30 zgłoszeń.",
        ),
        (
            (
                "Są 5 wielopaków czarnych po 8 sztuk i 4 wielopaki szarych po 7 sztuk. Ile szarych?",
                "W ostatnim wielopaku szarych było tylko 2, a pozostałe są bez zmiany. Ile sztuk łącznie?",
            ),
            "Oddaliśmy trzy czarnych. Podaj pozostałe czarne i szare oddzielnie.",
            "Pozostałe: czarne 37 szt., szare 23 szt.",
        ),
        (
            (
                "Z 48 par 6 odkładamy. Resztę dzielimy równo na 6 kieszeni. Ile par w każdej?",
            ),
            "Jedną pełną kieszeń zamknęliśmy na zapas. Ile par jest w otwartych?",
            "W pozostałych jest 35 par (5 × 7).",
        ),
        (
            ("Zużycie gąbek w trzech grupach to 6, 11 i 4. Jaka jest średnia?",),
            "Drugiej grupie odejmij dwie gąbki. Podaj średnią do dwóch miejsc.",
            "Średnia z 3 grup to 6,33 ((6 + 9 + 4) ÷ 3).",
        ),
        (
            (
                "We wtorek było 17 wpisów dla sali B i 8 dla C. W piątek B 5, C 9. Ile wpisów dla B w oba dni?",
                "We wtorek cztery wpisy były błędnie w B, przenieś je do C. Podaj poprawny wtorek.",
            ),
            "Teraz ile C w oba dni?",
            "Dla C w oba dni: 12 + 9 = 21 wpisów.",
        ),
        (
            (
                "Pakuję odważniki. Czerwony waży 1,2 kg, niebieski 670 g, "
                "sztywne etui 115 g. Ile ważą same odważniki w gramach?",
            ),
            "Czerwony waży teraz 1,05 kg. Podaj masę kompletu z etui.",
            "1050 g + 670 g + 115 g = 1835 g.",
        ),
        (
            (
                "Odczyty szerokości: Sowa 0,7 m, Sroka 685 mm i Jaskółka 69 cm. Wskaż najszerszą.",
            ),
            "Poszerzono Srokę do 71 cm. Która jest teraz najwęższa?",
            "Najmniejsza szerokość: Jaskółka, 69 cm. Porównanie: Sowa 70 cm, Sroka 71 cm, Jaskółka 69 cm.",
        ),
    ],
)
def test_studio_calculation_rebuilds_from_user_facts_only(
    studio_chat, monkeypatch, prior, current, expected
):
    monkeypatch.setattr(
        llm_simple_service.SETTINGS, "ACADEMY_GEMMA_REVIEW_RETRY_ENABLED", True
    )
    chat, sent, replies = studio_chat
    history = [
        turn
        for text in prior
        for turn in (
            {"role": "user", "content": text},
            {"role": "assistant", "content": "Sprawdzone, wynik 999 zł i 999 cm."},
        )
    ]
    assert chat(current, history, verify_history=True) == expected
    assert not sent and not replies


@pytest.mark.parametrize(
    "prompt",
    [
        "Ile cm folii potrzeba na dwa długie paski po 55 cm i trzy krótkie po 18 cm? Dodaj 10% zapasu.",
        "Mam cztery listwy po 27 cm i około trzy listwy po 18 cm. Ile razem centymetrów?",
        "Ile razem metrów na dwa długie paski po 55 cm i trzy krótkie po 18 cm?",
        "Przeredaguj ten tekst: „Odczyty szerokości: Sowa 0,7 m i Sroka 685 mm. Wskaż najszerszą.”",
    ],
)
def test_studio_calculator_defers_unbound_inputs(prompt):
    assert plan_studio_calculation(prompt, ()) is None


def test_studio_preserves_conditions_during_literal_point_edits(
    studio_chat, monkeypatch
):
    monkeypatch.setattr(
        llm_simple_service.SETTINGS, "ACADEMY_GEMMA_REVIEW_RETRY_ENABLED", True
    )
    chat, sent, replies = studio_chat
    source = (
        "Dwa warunki do instrukcji: „Dzieci poniżej 12 lat wchodzą z opiekunem. "
        "Osoby bez własnych opasek odbierają je przy bramce.” "
        "Zapisz po jednym krótkim punkcie. Zachowaj oba warunki."
    )
    correction = (
        "Opaski będą przy recepcji, nie przy bramce. "
        "Zmień tylko drugi punkt, zwróć oba."
    )
    initial = (
        "- Dzieci poniżej 12 lat wchodzą z opiekunem.\n"
        "- Osoby bez własnych opasek odbierają je przy bramce."
    )
    updated = initial.replace("przy bramce", "przy recepcji")
    assert chat(source, verify_history=True) == initial
    assert (
        chat(
            correction,
            [
                {"role": "user", "content": source},
                {"role": "assistant", "content": initial},
            ],
            verify_history=True,
        )
        == updated
    )
    assert chat(
        "Od teraz zajęcia są dla osób od 12 lat. "
        "Zmień pierwszy punkt, a drugi zachowaj słowo w słowo.",
        [
            {"role": "user", "content": source},
            {"role": "assistant", "content": initial},
            {"role": "user", "content": correction},
            {"role": "assistant", "content": updated},
        ],
        verify_history=True,
    ) == updated.replace(
        "Dzieci poniżej 12 lat wchodzą z opiekunem.",
        "Zajęcia są dla osób od 12 lat.",
    )
    assert not sent and not replies


@pytest.mark.parametrize(
    ("prompt", "expected"),
    [
        (
            "W pliku mam wpis „sprawdzić działanie lampy” bez potwierdzenia wykonania. "
            "Czy mogę wpisać wykonano?",
            "Wpis oznacza zadanie do zrobienia. Wykonanie pozostaje niepotwierdzone.",
        ),
        (
            "Na etykiecie paczki widnieje 8 sztuk. Przed przyjęciem trzeba sprawdzić "
            "wszystkie odcienie i podpis. Niczego jeszcze nie porównaliśmy ani nie podpisaliśmy. "
            "Co wpisujemy?",
            "Na etykiecie podano 8 sztuk. Zgodność odcieni i podpis karty nadal wymagają potwierdzenia.",
        ),
        (
            "Wpisaliśmy 7 z 9. Potem zgodę cofnięto, nic nie wydano. Podaj stan.",
            "Zgoda została cofnięta i nic nie wydano. Jest 7 wpisów z 9. "
            "Liczba pozycji bez wpisu to 2.",
        ),
        (
            "Są dwie koperty. Zielona zawiera umowę dla Ewy, szara notatkę dla Jana. "
            "Potrzebuję dla obu etykiet bez informacji o treści z przodu. Co napisać?",
            "Zielona — „Dla Ewy”.\nSzara — „Dla Jana”.",
        ),
        (
            "Na karcie widnieje „przekazano do weryfikacji”, bez potwierdzenia wykonania. "
            "W raporcie jest pole „zweryfikowano”. Co wpisać?",
            "Przekazano do weryfikacji. Pole „zweryfikowano” pozostaje otwarte do potwierdzenia wyniku.",
        ),
        (
            "Potrzebuję trzech długich listew po 450 mm i czterech krótkich po 19 cm. "
            "Ile cm razem?",
            "3 × 45 cm + 4 × 19 cm = 211 cm.",
        ),
    ],
)
def test_studio_publishes_only_verified_fields_and_values(
    studio_chat, monkeypatch, prompt, expected
):
    monkeypatch.setattr(
        llm_simple_service.SETTINGS, "ACADEMY_GEMMA_REVIEW_RETRY_ENABLED", True
    )
    chat, sent, replies = studio_chat
    assert chat(prompt, verify_history=True) == expected
    assert not sent and not replies


def test_neutral_labels_do_not_override_additional_restrictions():
    assert (
        studio_visibility(
            "Są dwie koperty. Zielona zawiera umowę dla Ewy, szara notatkę dla Jana. "
            "Potrzebuję dla obu etykiet bez informacji o treści z przodu. "
            "Nie umieszczaj imion na etykietach.",
            (),
        )
        is None
    )


_BULLETIN = (
    "Skróć do dwóch zdań: „Wstępnie naliczyliśmy około 28 kart. "
    "Trzy karty bez adresu jeszcze sprawdzamy. Wynik zamierzamy ogłosić w sobotę.” "
    "Nie używaj pierwszej osoby."
)
_VALID_BULLETIN = (
    "Wstępnie naliczono około 28 kart, a trzy karty bez adresu są w trakcie sprawdzania. "
    "Wynik planuje się ogłosić w sobotę."
)
_SAFE_BULLETIN = (
    "Wstępnie naliczono około 28 kart, a nadal sprawdza się trzy karty bez adresu. "
    "Wynik planuje się ogłosić w sobotę."
)


@pytest.mark.parametrize("destination", ["", " na tablicę"])
@pytest.mark.parametrize(
    ("draft", "expected"),
    [
        (_VALID_BULLETIN, _VALID_BULLETIN),
        (
            "Wstępnie naliczono 28 kart, w tym trzy karty bez adresu. "
            "Wynik zostanie ogłoszony w sobotę.",
            _SAFE_BULLETIN,
        ),
        (
            "Wstępnie naliczono około 28 kart i planuje się dodatkową kontrolę. "
            "Wynik ogłosimy w sobotę.",
            _SAFE_BULLETIN,
        ),
    ],
)
def test_studio_checks_a_publication_plan_before_publishing(
    studio_chat, monkeypatch, destination, draft, expected
):
    monkeypatch.setattr(
        llm_simple_service.SETTINGS, "ACADEMY_GEMMA_REVIEW_RETRY_ENABLED", True
    )
    chat, sent, replies = studio_chat
    replies.append(native(draft))
    prompt = _BULLETIN.replace("dwóch zdań:", f"dwóch zdań{destination}:")
    assert chat(prompt, verify_history=True) == expected
    assert len(sent) == 1 and not replies


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        (
            9,
            "Przyjęcie zakończone. Potwierdzono 9 właściwych kolorów, kartę podpisano.",
        ),
        (
            8,
            "Przyjęcie pozostaje otwarte. Wymagana liczba to 9, na etykiecie podano 8, "
            "a po sprawdzeniu potwierdzono 9. Kartę podpisano.",
        ),
    ],
)
def test_studio_matches_verified_count_to_checklist_requirement(
    studio_chat, monkeypatch, label, expected
):
    monkeypatch.setattr(
        llm_simple_service.SETTINGS, "ACADEMY_GEMMA_REVIEW_RETRY_ENABLED", True
    )
    chat, sent, replies = studio_chat
    history = [
        {
            "role": "user",
            "content": (
                "Przed przyjęciem trzeba sprawdzić komplet dziewięciu kolorów i podpisać kartę. "
                f"Na paczce widnieje „{label} sztuk”, a karty nie widzę. "
                "Co wpisać na liście kontrolnej?"
            ),
        },
        {"role": "assistant", "content": "Brak danych do zamknięcia."},
        {
            "role": "user",
            "content": (
                "Przeliczyliśmy kolory, jest dziewięć właściwych. "
                "Kartę podpisze osoba dyżurna po 17."
            ),
        },
        {"role": "assistant", "content": "Wszystkie warunki natychmiast spełnione."},
    ]
    user = "Kartę już podpisano. Podaj finalny status na podstawie dwóch warunków."
    assert chat(user, history, verify_history=True) == expected
    assert not sent and not replies


def test_studio_code_recipient_is_not_inferred_as_collection_actor(
    studio_chat, monkeypatch
):
    monkeypatch.setattr(
        llm_simple_service.SETTINGS, "ACADEMY_GEMMA_REVIEW_RETRY_ENABLED", True
    )
    chat, sent, replies = studio_chat
    history = [
        {
            "role": "user",
            "content": (
                "Mam potwierdzenie, że Ola pobrała kod z automatu, ale skrytka się nie otworzyła. "
                "Czy odnotować odbiór?"
            ),
        },
        {"role": "assistant", "content": "Odbiór pozostaje niepotwierdzony."},
    ]
    assert (
        chat(
            "Automat pokazuje „Skrytka otwarta, odbiór zarejestrowany o 19:21”. "
            "Podaj gotowy wpis do ewidencji.",
            history,
            verify_history=True,
        )
        == "Odbiór zarejestrowany o 19:21."
    )
    assert not sent and not replies


def test_studio_notice_variants_preserve_the_same_place(studio_chat, monkeypatch):
    monkeypatch.setattr(
        llm_simple_service.SETTINGS, "ACADEMY_GEMMA_REVIEW_RETRY_ENABLED", True
    )
    chat, sent, replies = studio_chat
    assert chat(
        "Ułóż w rozmowie dwie propozycje tabliczki „Plecaki zostawiamy przy kasie”. "
        "Są dla kierowniczki do obejrzenia, decyzja o użyciu później.",
        verify_history=True,
    ) == ("1. Plecaki zostawiamy przy kasie.\n2. Plecaki prosimy zostawiać przy kasie.")
    assert not sent and not replies


_PENDING_TEASER = (
    "Źródło do zajawki „Wstępnie zapisano około 41 osób. "
    "Sześć wpisów bez pieczęci jest jeszcze sprawdzanych. "
    "Listę zamierzamy opublikować w niedzielę”. Napisz dwa zdania w bezosobowym stylu."
)
_WRONG_TEASER = (
    "Wstępnie zapisano około 41 osób, w tym sześć wpisów bez pieczęci. "
    "Listę planuje się opublikować w niedzielę."
)
_SAFE_TEASER = (
    "Wstępnie zapisano około 41 osób, a nadal sprawdza się sześć wpisów bez pieczęci. "
    "Listę planuje się opublikować w niedzielę."
)
_TEASER_DATE_EDIT = (
    "Nie zmieniaj liczb ani liczby zdań. Wtorek zastąpi niedzielę w planie publikacji."
)


def test_teaser_publication_requires_the_pending_clause_and_updated_date(
    studio_chat, monkeypatch
):
    monkeypatch.setattr(
        llm_simple_service.SETTINGS, "ACADEMY_GEMMA_REVIEW_RETRY_ENABLED", True
    )
    chat, sent, replies = studio_chat
    replies.extend((native(_WRONG_TEASER), native(_SAFE_TEASER)))
    assert chat(_PENDING_TEASER, verify_history=True) == _SAFE_TEASER
    history = [
        {"role": "user", "content": _PENDING_TEASER},
        {"role": "assistant", "content": _WRONG_TEASER},
    ]
    updated = _SAFE_TEASER.replace("w niedzielę", "we wtorek")
    assert chat(_TEASER_DATE_EDIT, history, verify_history=True) == updated
    assert len(sent) == 2 and not replies
    assert publication_check(_TEASER_DATE_EDIT, []) is None
    bound = [HistoryMessage(**turn) for turn in history]
    assert (
        publication_check(_TEASER_DATE_EDIT.replace("niedzielę", "środę"), bound)
        is None
    )
    checked = publication_check(_TEASER_DATE_EDIT, bound)
    assert checked is not None and checked.publish(updated) == updated
    assert (
        checked.publish(updated.replace("we wtorek", "we wtorek lub w niedzielę"))
        == updated
    )


_SMS_DRAFT = (
    "Przygotuj SMS bez powitania i podpisu. Kurier ma przyjechać około 8:55 i zadzwoni od bramy. "
    "Gdy podjazd będzie zajęty, dostawę można przesunąć. Użyj dokładnie trzech zdań."
)
_EXPECTED_SMS = (
    "Kurier ma przyjechać około 8:55. Zadzwoni od bramy. "
    "Gdy podjazd będzie zajęty, dostawę można przesunąć."
)
_NOTICE = (
    "Przygotuj zapowiedź bez ocen. Pokaz odbędzie się rano i potrwa do 30 minut. "
    "Jeśli wystarczy czasu, pokażemy formę, a po zakończeniu można zadawać pytania przy recepcji."
)
_EXPECTED_NOTICE = (
    "Pokaz odbędzie się rano i potrwa do 30 minut. Jeśli wystarczy czasu, pokażemy formę. "
    "Po zakończeniu można zadawać pytania przy recepcji."
)
_PARAGRAPH = (
    "Podaj tę samą treść w jednym akapicie, bez zapowiadania dodatkowego spotkania."
)


@pytest.mark.parametrize(
    ("source", "base", "edits"),
    [
        (
            _SMS_DRAFT,
            _EXPECTED_SMS,
            [
                (
                    "Dodaj, że kurier jest z firmy Dąb i Las, resztę zachowaj.",
                    _EXPECTED_SMS.replace("Kurier", "Kurier z firmy Dąb i Las"),
                )
            ],
        ),
        (
            _NOTICE,
            _EXPECTED_NOTICE,
            [
                (_PARAGRAPH, _EXPECTED_NOTICE),
                (
                    "Zamień recepcję na foyer. Podaj cały akapit.",
                    _EXPECTED_NOTICE.replace("przy recepcji", "w foyer"),
                ),
            ],
        ),
    ],
)
def test_studio_revises_source_clauses_without_inventing_actions(
    studio_chat, monkeypatch, source, base, edits
):
    monkeypatch.setattr(
        llm_simple_service.SETTINGS, "ACADEMY_GEMMA_REVIEW_RETRY_ENABLED", True
    )
    chat, sent, replies = studio_chat
    history = []
    for prompt, expected in [(source, base), *edits]:
        assert chat(prompt, history, stream=False, verify_history=True) == expected
        history.extend(
            (
                {"role": "user", "content": prompt},
                {
                    "role": "assistant",
                    "content": "Potwierdzam dodatkowe spotkanie przy kasie.",
                },
            )
        )
    assert not sent and not replies


def test_studio_rejects_mismatched_source_edits():
    sms = [
        HistoryMessage(role="user", content=_SMS_DRAFT),
        HistoryMessage(role="assistant", content="Odbiór przy bramie."),
    ]
    notice = [
        HistoryMessage(role="user", content=_NOTICE),
        HistoryMessage(role="assistant", content=_EXPECTED_NOTICE),
        HistoryMessage(role="user", content=_PARAGRAPH),
        HistoryMessage(role="assistant", content=_EXPECTED_NOTICE),
    ]
    assert (
        studio_revision("Dodaj, że dostawca jest z firmy Spokój, resztę zachowaj.", sms)
        is None
    )
    assert studio_revision("Zamień kasę na foyer. Podaj cały akapit.", notice) is None
    assert (
        studio_revision("Zamień recepcję na foyer. Podaj cały akapit.", notice[:2])
        is None
    )


@pytest.mark.parametrize(
    "steps",
    [
        [
            (
                "Do remontu trzeba 6 dłuższych listew po 31 cm i 3 krótsze po 11,5 cm. Ile cm potrzeba "
                "łącznie?",
                "6 × 31 cm + 3 × 11,5 cm = 220,5 cm.",
                "220.5",
                "cm",
            ),
            (
                "Krótsze mają teraz po 13 cm, reszta bez zmian. Mam już 1,8 m. Ile cm brakuje?",
                "Brakuje 45 cm (6 × 31 cm + 3 × 13 cm − 180 cm).",
                "45",
                "cm",
            ),
        ],
        [
            (
                "Opłaty: 7 skrytek ma po 12 zł, 4 ma po 7 zł. Ile zapłacę tylko za tańsze?",
                "4 × 7 zł = 28 zł.",
                "28",
                "zł",
            ),
            (
                "Opłata za droższą skrytkę spada z 12 zł do 10 zł. Jaka jest suma obu stawek?",
                "Razem 98 zł: (4 × 7 zł) + (7 × 10 zł).",
                "98",
                "zł",
            ),
        ],
        [
            (
                "Na liście wymieniono cztery tabliczki: Chmura o szerokości 0,51 m, Wrzos 505 mm, Jantar "
                "52 cm i Topaz 50 cm. Która jest najwęższa?",
                "Najmniejsza szerokość: Topaz, 50 cm. Porównanie: Chmura 51 cm, Wrzos 50,5 cm, Jantar 52 "
                "cm, Topaz 50 cm.",
                "50",
                "cm",
            ),
            (
                "Topaz wymieniono na tabliczkę o szerokości 0,55 m. Która jest teraz najwęższa?",
                "Najmniejsza szerokość: Wrzos, 50,5 cm. Porównanie: Chmura 51 cm, Wrzos 50,5 cm, Jantar "
                "52 cm, Topaz 55 cm.",
                "50.5",
                "cm",
            ),
        ],
        [
            (
                "Cztery paczki ważą 270 g, 0,62 kg, 305 g i 760 g. Pusty pojemnik waży 115 g. Ile ważą "
                "same paczki, w gramach?",
                "270 g + 620 g + 305 g + 760 g = 1955 g.",
                "1955",
                "g",
            ),
            (
                "Trzecia paczka waży teraz 0,4 kg. Podaj masę paczek razem z pojemnikiem, w gramach.",
                "270 g + 620 g + 400 g + 760 g + 115 g = 2165 g.",
                "2165",
                "g",
            ),
        ],
        [
            (
                "Pięć wyników temperatury: -4, 5,5, 6, 10 i 2. Podaj medianę.",
                "Mediana: 5,5.",
                "5.5",
                None,
            ),
            (
                "Wynik 2 był duplikatem i znika z listy. Oblicz medianę.",
                "Środkowe wartości: 5,5 i 6. Mediana: 5,75.",
                "5.75",
                None,
            ),
        ],
        [
            (
                "Zakres od 0,45 m bez punktu granicznego do 56 cm włącznie. Próbki: A 450 mm, B 0,46 m, "
                "C 56 cm, D 570 mm. Wskaż pasujące próbki.",
                "Zakres spełniają: B, C (2 szt.).",
                "2",
                "szt.",
            ),
            (
                "Dolna granica włącznie, górna bez punktu granicznego. Wskaż ponownie.",
                "Zakres spełniają: A, B (2 szt.).",
                "2",
                "szt.",
            ),
        ],
        [
            (
                "Zużyto 9, 12 i 15 ml lakieru w trzech próbach. Pomiń niewykonaną czwartą próbę i oblicz "
                "średnią.",
                "Średnia z 3 pomiarów: 12 ml ((9 + 12 + 15) ÷ 3).",
                "12",
                "ml",
            ),
            (
                "Zmniejsz wartość drugiego odczytu o 0,004 l. Oblicz średnią do dwóch miejsc po "
                "przecinku.",
                "Średnia z 3 pomiarów: 10,67 ml ((9 + 8 + 15) ÷ 3).",
                "10.66666666666666666666666667",
                "ml",
            ),
        ],
        [
            (
                "W koszu jest 4 opakowania niebieskich po 9 i 3 opakowania białych po 10. Ile "
                "niebieskich sztuk?",
                "Niebieskich: 36 szt.",
                "36",
                "szt.",
            ),
            (
                "Ostatnie białe opakowanie ma tylko 7. Ile sztuk razem?",
                "Razem 63 szt. (niebieskich: 36, białych: 27).",
                "63",
                "szt.",
            ),
            (
                "Oddaliśmy 6 niebieskich. Podaj osobno, ile zostało obu kolorów.",
                "Pozostałe: niebieskie 30 szt., białe 27 szt.",
                "30",
                "szt.",
            ),
        ],
        [
            (
                "Na osłonę idzie pięć długich taśm po 28 cm oraz cztery krótsze po 17 cm. Podaj sumę długości w centymetrach.",
                "5 × 28 cm + 4 × 17 cm = 208 cm.",
                "208",
                "cm",
            ),
            (
                "Po korekcie krótsze odcinki mierzą po 19 cm. Odłożono już 1,65 m. Jaki jest niedobór w cm?",
                "Brakuje 51 cm (5 × 28 cm + 4 × 19 cm − 165 cm).",
                "51",
                "cm",
            ),
        ],
        [
            (
                "Stawki: 5 szafek po 14 zł i 3 szafki po 9 zł. Jaki jest koszt samych tańszych?",
                "3 × 9 zł = 27 zł.",
                "27",
                "zł",
            ),
            (
                "Za droższą szafkę stawka wynosi teraz 12 zł zamiast 14 zł. Ile wyniesie łączna kwota?",
                "Razem 87 zł: (3 × 9 zł) + (5 × 12 zł).",
                "87",
                "zł",
            ),
        ],
        [
            (
                "Szerokości: Klon 485 mm, Buk 0,49 m oraz Grab 51 cm. Która deska ma najmniejszą szerokość?",
                "Najmniejsza szerokość: Klon, 48,5 cm. Porównanie: Klon 48,5 cm, Buk 49 cm, Grab 51 cm.",
                "48.5",
                "cm",
            ),
            (
                "Korekta pomiaru: szerokość Klon to 52 cm. Która deska ma teraz najmniejszą szerokość?",
                "Najmniejsza szerokość: Buk, 49 cm. Porównanie: Klon 52 cm, Buk 49 cm, Grab 51 cm.",
                "49",
                "cm",
            ),
        ],
        [
            (
                "Pusty kosz waży 110 g. Masy trzech worków w kolejności to 0,44 kg, 325 g oraz 0,68 kg. Ile w gramach ważą bez kosza?",
                "440 g + 325 g + 680 g = 1445 g.",
                "1445",
                "g",
            ),
            (
                "W drugim worku jest teraz 0,295 kg. Ile w gramach waży komplet razem z koszem?",
                "440 g + 295 g + 680 g + 110 g = 1525 g.",
                "1525",
                "g",
            ),
        ],
        [
            (
                "Zapisane odczyty to 8, 13, -2, 6 i 20. Jaka jest mediana tego szeregu?",
                "Mediana: 8.",
                "8",
                None,
            ),
            (
                "Skreśl wynik 6 jako duplikat i podaj medianę jeszcze raz.",
                "Środkowe wartości: 8 i 13. Mediana: 10,5.",
                "10.5",
                None,
            ),
        ],
        [
            (
                "Dopuszczam powyżej 0,38 m oraz do 54 cm włącznie. Próbki: A 380 mm, B 0,42 m, C 54 cm, D 550 mm. Wskaż pasujące próbki.",
                "Zakres spełniają: B, C (2 szt.).",
                "2",
                "szt.",
            ),
            (
                "Zamień zasady dotyczące krańców: dolny włącznie, górny wyłącznie. Podaj listę jeszcze raz.",
                "Zakres spełniają: A, B (2 szt.).",
                "2",
                "szt.",
            ),
        ],
        [
            (
                "Wykonano trzy pomiary zużycia: 12, 20 i 37 ml. Oblicz średnią bez brakującej czwartej próby.",
                "Średnia z 3 pomiarów: 23 ml ((12 + 20 + 37) ÷ 3).",
                "23",
                "ml",
            ),
            (
                "Drugi pomiar zawyżono o 0,004 l. Podaj nową średnią z dokładnością do dwóch miejsc po przecinku.",
                "Średnia z 3 pomiarów: 21,67 ml ((12 + 16 + 37) ÷ 3).",
                "21.66666666666666666666666667",
                "ml",
            ),
        ],
        [
            (
                "Mam 4 brązowe opakowania, po 9 sztuk każde, oraz 3 czerwone, po 8 sztuk każde. Policz tylko czerwone sztuki.",
                "Czerwonych: 24 szt.",
                "24",
                "szt.",
            ),
            (
                "Tylko ostatnie czerwone opakowanie zawiera 5 sztuk. Ile jest sztuk wszystkich kolorów łącznie?",
                "Razem 57 szt. (brązowych: 36, czerwonych: 21).",
                "57",
                "szt.",
            ),
            (
                "Zużyliśmy 4 brązowe sztuki. Podaj pozostałe sztuki osobno dla każdego koloru.",
                "Pozostałe: brązowe 32 szt., czerwone 21 szt.",
                "32",
                "szt.",
            ),
        ],
    ],
    ids=(
        "length",
        "relative-rate",
        "width",
        "mass",
        "median",
        "interval",
        "mean",
        "packs",
        "paraphrase-length",
        "paraphrase-relative-rate",
        "paraphrase-width",
        "paraphrase-mass",
        "paraphrase-median",
        "paraphrase-interval",
        "paraphrase-mean",
        "paraphrase-packs",
    ),
)
def test_studio_binds_operands_and_publishes_calculator_result(
    studio_chat, monkeypatch, steps
):
    monkeypatch.setattr(
        llm_simple_service.SETTINGS, "ACADEMY_GEMMA_REVIEW_RETRY_ENABLED", True
    )
    chat, sent, replies = studio_chat
    native_history = []
    for prompt, expected_answer, amount, unit in steps:
        history = [HistoryMessage(**message) for message in native_history]
        plan = plan_studio_calculation(prompt, history)
        assert plan is not None
        receipt = plan.publish()
        assert receipt["response_source"] == "calculator"
        assert receipt["tool_result"] == {
            "tool": "calculator",
            "status": "succeeded",
            "value": amount,
            "unit": unit,
            "recomputed": False,
        }
        assert chat(prompt, native_history, verify_history=True) == expected_answer
        native_history.extend(
            [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": "Wcześniejszy wynik to 999."},
            ]
        )
    assert not sent and not replies


@pytest.mark.parametrize(
    ("source", "current"),
    [
        (
            (),
            "Opłaty: 7 skrytek ma po 12 zł, 4 ma po 12 zł. Ile zapłacę tylko za tańsze?",
        ),
        (
            (),
            "Opłaty: 7 skrytek ma po 12 zł, 4 półki ma po 7 zł. Ile zapłacę tylko za tańsze?",
        ),
        (
            (
                "Opłaty: 7 skrytek ma po 12 zł, 4 ma po 7 zł. Ile zapłacę tylko za tańsze?",
            ),
            "Opłata za droższą skrytkę spada z 11 zł do 10 zł. Jaka jest suma obu stawek?",
        ),
        (
            (
                "Opłaty: 7 skrytek ma po 12 zł, 4 ma po 7 zł. Ile zapłacę tylko za tańsze?",
            ),
            "Opłata za droższą półkę spada z 12 zł do 10 zł. Jaka jest suma obu stawek?",
        ),
        (
            (
                "Opłaty: 7 skrytek ma po 12 zł, 4 ma po 7 zł. Ile zapłacę tylko za tańsze?",
            ),
            "Opłata za droższą skrytkę spada z 12 zł do 13 zł. Jaka jest suma obu stawek?",
        ),
        (
            (
                "Opłaty: 7 skrytek ma po 12 zł, 4 ma po 7 zł. Ile zapłacę tylko za tańsze?",
            ),
            "Opłata za tańszą skrytkę rośnie z 7 zł do 6 zł. Jaka jest suma obu stawek?",
        ),
        (
            (
                "Opłaty: 7 skrytek ma po 12 zł, 4 ma po 7 zł. Ile zapłacę tylko za tańsze?",
            ),
            "Kaucja za droższą skrytkę spada z 12 zł do 10 zł. Jaka jest suma obu stawek?",
        ),
        (
            (),
            "Opłaty: 7 skrytek ma po 12 zł, 4 ma po 7 zł. Ile zapłacę za jedną wybraną?",
        ),
        (
            (),
            "Na liście są trzy rury: M 35 cm, N 36 cm i O 47 cm. Która jest najwęższa?",
        ),
        (
            (
                "Na liście wymieniono cztery tabliczki: Chmura o szerokości 0,51 m, Wrzos 505 mm, Jantar "
                "52 cm i Topaz 50 cm. Która jest najwęższa?",
            ),
            "Amber wymieniono na tabliczkę o szerokości 55 cm. Która jest teraz najwęższa?",
        ),
        (
            (),
            "Trzy paczki ważą 270 g, 0,62 kg, 305 g i 760 g. Pusty pojemnik waży 115 g. Ile ważą same "
            "paczki, w gramach?",
        ),
        (
            (
                "Cztery paczki ważą 270 g, 0,62 kg, 305 g i 760 g. Pusty pojemnik waży 115 g. Ile ważą "
                "same paczki, w gramach?",
            ),
            "Piąta paczka waży teraz 320 g. Podaj masę paczek razem z pojemnikiem, w gramach.",
        ),
        (
            (
                "Cztery paczki ważą 270 g, 0,62 kg, 305 g i 760 g. Pusty pojemnik waży 115 g. Ile ważą "
                "same paczki, w gramach?",
            ),
            "Trzecia paczka waży teraz 320 g. Podaj masę paczek razem z kufrem, w gramach.",
        ),
        ((), "Cztery wyniki temperatury: -4, 5,5, 6, 10 i 2. Podaj medianę."),
        (
            ("Pięć wyników temperatury: -4, 5,5, 6, 10 i 6. Podaj medianę.",),
            "Wynik 6 był duplikatem i znika z listy. Oblicz medianę.",
        ),
        (
            ("Pięć wyników temperatury: -4, 5,5, 6, 10 i 2. Podaj medianę.",),
            "Wynik 8 był duplikatem i znika z listy. Oblicz medianę.",
        ),
        (
            ("Pięć wyników temperatury: -4, 5,5, 6, 10 i 2. Podaj medianę.",),
            "Zastosuj drugi algorytm i nie podawaj wyniku.",
        ),
        (
            (),
            "Zakres od 0,45 m bez punktu granicznego do 56 cm. Próbki: A 450 mm, B 0,46 m, C 56 cm, D "
            "570 mm. Wskaż pasujące próbki.",
        ),
        (
            (),
            "Zakres od 0,45 m bez punktu granicznego do mniej niż 56 cm włącznie. Próbki: A 450 mm, B "
            "0,46 m, C 56 cm, D 570 mm. Wskaż pasujące próbki.",
        ),
        (
            (),
            "Zakres od 0,6 m bez punktu granicznego do 56 cm włącznie. Próbki: A 450 mm, B 0,46 m, C 56 "
            "cm, D 570 mm. Wskaż pasujące próbki.",
        ),
        (
            (),
            "Zakres od 0,45 m bez punktu granicznego do 56 cm włącznie. Próbki: A 450 mm, B 0,46 m, A "
            "56 cm, D 570 mm. Wskaż pasujące próbki.",
        ),
        (
            (),
            "Zakres od 0,45 m bez punktu granicznego do 56 cm włącznie. Próbki: A 450 mm, B 0,46 m, C o "
            "nieznanej szerokości, D 570 mm. Wskaż pasujące próbki.",
        ),
        (
            (
                "Zakres od 0,45 m bez punktu granicznego do 56 cm włącznie. Próbki: A 450 mm, B 0,46 m, C "
                "56 cm, D 570 mm. Wskaż pasujące próbki.",
            ),
            "Dolna granica włącznie, górna do wartości opisanej wcześniej. Wskaż ponownie.",
        ),
        (
            (),
            "Zużyto 9, 12 i 15 ml lakieru w czterech próbach. Pomiń niewykonaną czwartą próbę i oblicz "
            "średnią.",
        ),
        (
            (
                "Zużyto 9, 12 i 15 ml lakieru w trzech próbach. Pomiń niewykonaną czwartą próbę i oblicz "
                "średnią.",
            ),
            "Zwiększ wartość drugiego odczytu o 2 g. Oblicz średnią do dwóch miejsc.",
        ),
        (
            (
                "Zużyto 9, 12 i 15 ml lakieru w trzech próbach. Pomiń niewykonaną czwartą próbę i oblicz "
                "średnią.",
            ),
            "Zmniejsz wartość drugiego odczytu o 13 ml. Oblicz średnią.",
        ),
        (
            (
                "Zużyto 9, 12 i 15 ml lakieru w trzech próbach. Pomiń niewykonaną czwartą próbę i oblicz "
                "średnią.",
            ),
            "Zmniejsz wartość czwartego odczytu o 3 ml. Oblicz średnią.",
        ),
        (
            (
                "Zużyto 9, 12 i 15 ml lakieru w trzech próbach. Pomiń niewykonaną czwartą próbę i oblicz "
                "średnią.",
            ),
            "Podaj średnią do czterech miejsc po przecinku.",
        ),
        (
            (
                "W koszu jest 4 opakowania niebieskich po 9 i 3 opakowania białych po 10. Ile niebieskich "
                "sztuk?",
            ),
            "Ostatnie czerwone opakowanie ma tylko 7. Ile sztuk razem?",
        ),
        (
            (
                "W koszu jest 4 opakowania niebieskich po 9 i 3 opakowania białych po 10. Ile niebieskich "
                "sztuk?",
            ),
            "Ostatnie białe opakowanie ma tylko 11. Ile sztuk razem?",
        ),
        (
            (
                "W koszu jest 4 opakowania niebieskich po 9 i 3 opakowania białych po 10. Ile niebieskich "
                "sztuk?",
                "Ostatnie białe opakowanie ma tylko 7. Ile sztuk razem?",
            ),
            "Oddaliśmy 37 niebieskich. Podaj osobno, ile zostało obu kolorów.",
        ),
        (
            (
                "Na osłonę idzie pięć długich taśm po 28 cm oraz cztery krótsze po 17 cm. Podaj sumę długości w centymetrach.",
            ),
            "Nie wszystkie krótsze odcinki mierzą po 19 cm. Odłożono już 1,65 m. Jaki jest niedobór w cm?",
        ),
        (
            (
                "Stawki: 5 szafek po 14 zł i 3 szafki po 9 zł. Jaki jest koszt samych tańszych?",
            ),
            "Za droższą szafkę stawka wynosi teraz 12 zł zamiast 13 zł. Ile wyniesie łączna kwota?",
        ),
        (
            (
                "Szerokości: Klon 485 mm, Buk 0,49 m oraz Grab 51 cm. Która deska ma najmniejszą szerokość?",
            ),
            "Korekta pomiaru: szerokość Dąb to 52 cm. Która deska ma teraz najmniejszą szerokość?",
        ),
        (
            (
                "Szerokości: Klon 485 mm, Buk 0,49 m oraz Grab 51 cm. Która deska ma najmniejszą szerokość?",
            ),
            "Korekta pomiaru: szerokość Klon to 49 cm. Która deska ma teraz najmniejszą szerokość?",
        ),
        (
            (),
            "Pusty kosz waży 110 g. Masy trzech worków w kolejności to 0,44 kg, 325 g oraz 0,68 kg. Ile w gramach ważą bez pojemnika?",
        ),
        (
            (
                "Pusty kosz waży 110 g. Masy trzech worków w kolejności to 0,44 kg, 325 g oraz 0,68 kg. Ile w gramach ważą bez kosza?",
            ),
            "W czwartym worku jest teraz 0,295 kg. Ile w gramach waży komplet razem z koszem?",
        ),
        (
            (
                "Pusty kosz waży 110 g. Masy trzech worków w kolejności to 0,44 kg, 325 g oraz 0,68 kg. Ile w gramach ważą bez kosza?",
            ),
            "W drugim worku jest teraz 0,295 kg. Ile w gramach waży komplet razem z kufrem?",
        ),
        (
            ("Zapisane odczyty to 8, 13, -2, 6 i 20. Jaka jest mediana tego szeregu?",),
            "Skreśl wynik 4 jako duplikat i podaj medianę jeszcze raz.",
        ),
        (
            (),
            "Dopuszczam powyżej 0,38 m oraz do 54 cm. Próbki: A 380 mm, B 0,42 m, C 54 cm, D 550 mm. Wskaż pasujące próbki.",
        ),
        (
            (
                "Dopuszczam powyżej 0,38 m oraz do 54 cm włącznie. Próbki: A 380 mm, B 0,42 m, C 54 cm, D 550 mm. Wskaż pasujące próbki.",
            ),
            "Zamień zasady dotyczące krańców: dolny włącznie, górny podobnie jak wcześniej. Podaj listę jeszcze raz.",
        ),
        (
            (
                "Wykonano trzy pomiary zużycia: 12, 20 i 37 ml. Oblicz średnią bez brakującej czwartej próby.",
            ),
            "Drugi pomiar zawyżono o 4 g. Podaj nową średnią z dokładnością do dwóch miejsc po przecinku.",
        ),
        (
            (
                "Wykonano trzy pomiary zużycia: 12, 20 i 37 ml. Oblicz średnią bez brakującej czwartej próby.",
            ),
            "Drugi pomiar zawyżono o 0,03 l. Podaj nową średnią z dokładnością do dwóch miejsc po przecinku.",
        ),
        (
            (
                "Mam 4 brązowe opakowania, po 9 sztuk każde, oraz 3 czerwone, po 8 sztuk każde. Policz tylko czerwone sztuki.",
            ),
            "Tylko ostatnie zielone opakowanie zawiera 5 sztuk. Ile jest sztuk wszystkich kolorów łącznie?",
        ),
        (
            (
                "Mam 4 brązowe opakowania, po 9 sztuk każde, oraz 3 czerwone, po 8 sztuk każde. Policz tylko czerwone sztuki.",
                "Tylko ostatnie czerwone opakowanie zawiera 5 sztuk. Ile jest sztuk wszystkich kolorów łącznie?",
            ),
            "Zużyliśmy 40 brązowych sztuki. Podaj pozostałe sztuki osobno dla każdego koloru.",
        ),
    ],
)
def test_studio_calculator_defers_ambiguous_or_inconsistent_corrections(
    source, current
):
    history = [HistoryMessage(role="user", content=prompt) for prompt in source]
    assert plan_studio_calculation(current, history) is None


@pytest.mark.parametrize(
    "steps",
    [
        pytest.param(
            [
                (
                    "Potrzebuję pięciu krótkich listewek po 19 cm oraz trzech dłuższych po 24 cm. Ile listewki "
                    "trzeba w sumie?",
                    "167",
                    "cm",
                    "5 × 19 cm + 3 × 24 cm = 167 cm.",
                ),
                (
                    "Krótkie mają po 17 cm. Mam odcinek długości 1,4 m. Podaj niedobór w cm.",
                    "17",
                    "cm",
                    "Brakuje 17 cm (5 × 17 cm + 3 × 24 cm − 140 cm).",
                ),
            ],
            id="cut-list",
        ),
        pytest.param(
            [
                (
                    "Wynajęto 6 statywów bez pokrowca po 11 zł oraz 5 z pokrowcem po 16 zł. Podaj koszt samych "
                    "statywów bez pokrowca.",
                    "66",
                    "zł",
                    "6 × 11 zł = 66 zł.",
                ),
                (
                    "Statyw bez pokrowca kosztuje teraz po 14 zł. Policz łączną opłatę.",
                    "164",
                    "zł",
                    "Razem 164 zł: (6 × 14 zł) + (5 × 16 zł).",
                ),
            ],
            id="accessory-tariff",
        ),
        pytest.param(
            [
                (
                    "Wymiary szerokości trzech desek: Nurt 360 mm, Piasek 0,355 m i Wrzos 35,8 cm. Która jest "
                    "najwęższa?",
                    "35.5",
                    "cm",
                    "Najmniejsza szerokość: Piasek, 35,5 cm. Porównanie: Nurt 36 cm, Piasek 35,5 cm, Wrzos 35,8 "
                    "cm.",
                ),
                (
                    "Wymieniono Piasek na deskę mierzącą 0,37 m. Wskaż nowy wynik porównania.",
                    "35.8",
                    "cm",
                    "Najmniejsza szerokość: Wrzos, 35,8 cm. Porównanie: Nurt 36 cm, Piasek 37 cm, Wrzos 35,8 "
                    "cm.",
                ),
            ],
            id="width-replacement",
        ),
        pytest.param(
            [
                (
                    "Zważyłem trzy woreczki, 180 g, 0,24 kg i 315 g, oraz płytkę 380 g. Pojemnik osobno waży 145 "
                    "g. Podaj łączną masę samej zawartości w gramach.",
                    "1115",
                    "g",
                    "180 g + 240 g + 315 g + 380 g = 1115 g.",
                ),
                (
                    "W drugim woreczku jest teraz 0,31 kg. Podaj masę razem z pojemnikiem.",
                    "1330",
                    "g",
                    "180 g + 310 g + 315 g + 380 g + 145 g = 1330 g.",
                ),
            ],
            id="mixed-mass",
        ),
        pytest.param(
            [
                (
                    "Oceny zapisane w kolejności: 3, 4, 8, 12 i 16. Wyznacz medianę.",
                    "8",
                    None,
                    "Mediana: 8.",
                ),
                (
                    "Usuń 16, należało do innej próby. Podaj teraz medianę.",
                    "6",
                    None,
                    "Środkowe wartości: 4 i 8. Mediana: 6.",
                ),
            ],
            id="median-subset",
        ),
        pytest.param(
            [
                (
                    "Dopuszczam próbki szersze niż 31 cm i najwyżej 36 cm. Z1 310 mm, Z2 0,345 m, Z3 36 cm, Z4 "
                    "361 mm. Wskaż, które pasują.",
                    "2",
                    "szt.",
                    "Zakres spełniają: Z2, Z3 (2 szt.).",
                ),
                (
                    "Teraz 31 cm także dopuszczamy, zaś 36 cm wykluczamy. Które pasują?",
                    "2",
                    "szt.",
                    "Zakres spełniają: Z1, Z2 (2 szt.).",
                ),
            ],
            id="bound-endpoints",
        ),
        pytest.param(
            [
                (
                    "Mam trzy wykonane odczyty: 3, 8 i 6 ml. Następnego odczytu jeszcze nie mamy. Oblicz średnią "
                    "do dwóch miejsc po przecinku.",
                    "5.666666666666666666666666667",
                    "ml",
                    "Średnia z 3 pomiarów: 5,67 ml ((3 + 8 + 6) ÷ 3).",
                ),
                (
                    "W drugim odczycie zapisuję 9 zamiast 8 ml. Podaj średnią z tą samą precyzją.",
                    "6",
                    "ml",
                    "Średnia z 3 pomiarów: 6,00 ml ((3 + 9 + 6) ÷ 3).",
                ),
            ],
            id="mean-precision",
        ),
        pytest.param(
            [
                (
                    "W zasobniku mamy 3 paczki czarnych po 11 i 4 paczki granatowych po 8 sztuk. Ile granatowych "
                    "sztuk?",
                    "32",
                    "szt.",
                    "Granatowych: 32 szt.",
                ),
                (
                    "Jedna granatowa paczka zawiera 6 zamiast 8. Ile teraz sztuk razem?",
                    "63",
                    "szt.",
                    "Razem 63 szt. (czarnych: 33, granatowych: 30).",
                ),
                (
                    "Wydano 4 czarnych. Podaj osobno pozostałe liczby obu kolorów.",
                    "29",
                    "szt.",
                    "Pozostałe: czarne 29 szt., granatowe 30 szt.",
                ),
            ],
            id="pack-ledger",
        ),
        pytest.param(
            [
                (
                    "Jest 54 l. Rezerwuję 10 l dla oddzielnego odbiorcy. Z reszty daję po 11 l na trzy "
                    "stanowiska. Ile zostaje bez rezerwy?",
                    "11",
                    "l",
                    "Po odjęciu rezerwy i rozlanych porcji zostaje 11 l.",
                ),
                (
                    "Jedno stanowisko wzięło 8 l, pozostałe dwa nadal po 11 l. Ile teraz zostaje?",
                    "14",
                    "l",
                    "Po odjęciu rezerwy i rozlanych porcji zostaje 14 l.",
                ),
            ],
            id="allocation",
        ),
        pytest.param(
            [
                (
                    "Trzy odcinki zajęły 244, 319 i 397 sekund. Ile to razem w minutach?",
                    "16",
                    "min",
                    "Suma: 960 sekund, czyli 16 min.",
                ),
                (
                    "Drugi odcinek: 259 sekund zamiast 319. Podaj zaktualizowaną sumę w minutach.",
                    "15",
                    "min",
                    "Suma: 900 sekund, czyli 15 min.",
                ),
            ],
            id="time-series",
        ),
    ],
)
def test_structural_studio_calculation_uses_current_operands(
    studio_chat, monkeypatch, steps
):
    monkeypatch.setattr(
        llm_simple_service.SETTINGS, "ACADEMY_GEMMA_REVIEW_RETRY_ENABLED", True
    )
    chat, sent, replies = studio_chat
    history = []
    for prompt, amount, unit, text in steps:
        plan = plan_studio_calculation(
            prompt, [HistoryMessage(**entry) for entry in history]
        )
        assert plan is not None
        answer = plan.publish()
        assert answer["response_source"] == "calculator"
        assert answer["tool_result"]["value"] == amount
        assert answer["tool_result"]["unit"] == unit
        assert answer["tool_result"]["status"] == "succeeded"
        assert chat(prompt, history, verify_history=True) == text
        history.extend(
            (
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": "Wcześniejsza odpowiedź podała 999."},
            )
        )
    assert not sent and not replies


def test_scoped_session_reclassification_preserves_sum_and_other_session(
    studio_chat, monkeypatch
):
    monkeypatch.setattr(
        llm_simple_service.SETTINGS, "ACADEMY_GEMMA_REVIEW_RETRY_ENABLED", True
    )
    chat, sent, replies = studio_chat
    source = "Po pierwszej sesji zanotowano 8 poprawnych i 4 do sprawdzenia, po drugiej 9 poprawnych i 7 do sprawdzenia. Ile poprawnych z obu?"
    correction = "Trzy wpisy z poprawnych po pierwszej sesji przenoszę do „do sprawdzenia”. Podaj oba liczniki tej sesji."
    repeat = "Ile teraz poprawnych w obu sesjach?"
    history = []
    for prompt, answer in (
        (source, "Z obu sesji: 8 + 9 = 17 poprawnych."),
        (correction, "5 poprawnych i 7 do sprawdzenia. Łącznie 12."),
        (repeat, "Z obu sesji: 5 + 9 = 14 poprawnych."),
    ):
        assert chat(prompt, history, verify_history=True) == answer
        history.extend(
            (
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": "Wynik to 99."},
            )
        )
    assert not sent and not replies


@pytest.mark.parametrize(
    ("sources", "current"),
    [
        (
            (),
            "Porównaj szerokość trzech płytek: „Ryś 0,5 m, Socha 530 mm, Łan 49 cm”. Która jest najwęższa?",
        ),
        (
            (),
            "Porównaj szerokość czterech płytek: Ryś 0,5 m, Socha 530 mm, Łan 49 cm. Która jest najwęższa?",
        ),
        (
            (),
            "Porównaj szerokość trzech płytek: Ryś około 0,5 m, Socha 530 mm, Łan 49 cm. Która jest najwęższa?",
        ),
        (
            (),
            "Wynajęto 6 statywów bez pokrowca po 11 zł oraz 5 z pilotem po 16 zł. Podaj koszt samych statywów bez pokrowca.",
        ),
        (
            (
                "Wynajęto 6 statywów bez pokrowca po 11 zł oraz 5 z pokrowcem po 16 zł. Podaj koszt samych statywów bez pokrowca.",
            ),
            "Statyw bez pokrowca kosztuje teraz 14 zł lub 15 zł. Policz łączną opłatę.",
        ),
        (
            (),
            "Zważyłem trzy woreczki, 180 g, 0,24 kg i 315 g, oraz płytkę 380 g. Pojemnik osobno waży 145 g. Podaj łączną masę samych woreczków w gramach.",
        ),
        (
            ("Oceny zapisane w kolejności: 3, 4, 8, 12 i 16. Wyznacz medianę.",),
            "Usuń 13, należało do innej próby. Podaj teraz medianę.",
        ),
        (
            (
                "Mam trzy wykonane odczyty: 3, 8 i 6 ml. Następnego odczytu jeszcze nie mamy. Oblicz średnią do dwóch miejsc po przecinku.",
            ),
            "W drugim odczycie zapisuję 9 zamiast 6 ml. Podaj średnią z tą samą precyzją.",
        ),
        (
            (
                "Mam trzy wykonane odczyty: 3, 8 i 6 ml. Następnego odczytu jeszcze nie mamy. Oblicz średnią do dwóch miejsc po przecinku.",
            ),
            "W drugim odczycie zapisuję 9 zamiast 8 g. Podaj średnią z tą samą precyzją.",
        ),
        (
            (
                "Dopuszczam próbki szersze niż 31 cm i najwyżej 36 cm. Z1 310 mm, Z2 0,345 m, Z3 36 cm, Z4 361 mm. Wskaż, które pasują.",
            ),
            "Teraz 32 cm także dopuszczamy, zaś 36 cm wykluczamy. Które pasują?",
        ),
        (
            (
                "W zasobniku mamy 3 paczki czarnych po 11 i 4 paczki granatowych po 8 sztuk. Ile granatowych sztuk?",
            ),
            "Jedna granatowa paczka zawiera 6 zamiast 9. Ile teraz sztuk razem?",
        ),
        (
            (),
            "Jest 54 l. Rezerwuję 10 l dla oddzielnego odbiorcy. Z reszty daję po 11 l na trzy stanowiska. Ile zostaje dla oddzielnego odbiorcy?",
        ),
        (
            (
                "Jest 54 l. Rezerwuję 10 l dla oddzielnego odbiorcy. Z reszty daję po 11 l na trzy stanowiska. Ile zostaje bez rezerwy?",
            ),
            "Jedno stanowisko wzięło 8 l, pozostałe trzy nadal po 11 l. Ile teraz zostaje?",
        ),
        (
            ("Trzy odcinki zajęły 244, 319 i 397 sekund. Ile to razem w minutach?",),
            "Drugi odcinek: 259 sekund zamiast 397. Podaj zaktualizowaną sumę w minutach.",
        ),
        (
            (
                "Po pierwszej sesji zanotowano 3 poprawnych i 4 do sprawdzenia, po drugiej 9 poprawnych i 7 do sprawdzenia. Ile poprawnych z obu?",
            ),
            "Cztery wpisy z poprawnych po pierwszej sesji przenoszę do „do sprawdzenia”. Podaj oba liczniki tej sesji.",
        ),
        (
            (
                "Po pierwszej sesji zanotowano 8 poprawnych i 4 do sprawdzenia, po drugiej 9 poprawnych i 7 do sprawdzenia. Ile poprawnych z obu?",
            ),
            "Trzy wpisy z poprawnych po pierwszej sesji przenoszę do „usunąć”. Podaj oba liczniki tej sesji.",
        ),
    ],
)
def test_structural_studio_calculation_defers_unbound_revisions(sources, current):
    history = [HistoryMessage(role="user", content=message) for message in sources]
    assert plan_studio_calculation(current, history) is None


_COMMUNICATION_QUEUE = (
    "Notatka do komunikatu: „Wstępnie zgłoszono około 35 zespołów. "
    "Cztery zgłoszenia bez numeru nadal czekają na sprawdzenie. "
    "Podsumowanie zamierzamy podać w sobotę”. Oddaj to w dwóch zdaniach bezosobowych."
)
_QUEUE_REPLY = (
    "Wstępnie zgłoszono około 35 zespołów, a cztery zgłoszenia bez numeru "
    "nadal czekają na sprawdzenie. Podsumowanie planuje się podać w sobotę."
)
_QUEUE_EDIT = (
    "Podsumowanie planujemy w środę zamiast w sobotę. Liczb i dwóch zdań nie zmieniaj."
)
_SCOPED_CARD = (
    "Zapisz dwa punkty na kartę. „Osoby poniżej 15 lat potrzebują zgody opiekuna. "
    "Do hali wchodzi się z przepustką”. Drugi ma dotyczyć hali."
)
_CARD_EDIT = (
    "Przepustka przestała być wymagana. "
    "Drugi punkt ma brzmieć „Hala czynna do 17:00”. Pierwszego nie zmieniaj."
)
_SEPARATE_NOTICE = (
    "Napisz krótką informację. Odbiór odbędzie się wieczorem i potrwa nie dłużej niż 23 minuty. "
    "Gdy dopisze pogoda, pokażemy przykładową osłonę. Pytania po odbiorze przy portierni. "
    "Treść bez ocen."
)
_NOTICE_AS_PARAGRAPH = (
    "Wersja w jednym akapicie, bez nowego spotkania. Zachowaj wszystkie fakty."
)


@pytest.mark.parametrize(
    ("source", "initial", "change", "updated"),
    [
        (
            _COMMUNICATION_QUEUE,
            _QUEUE_REPLY,
            _QUEUE_EDIT,
            _QUEUE_REPLY.replace("w sobotę", "w środę"),
        ),
        (
            _SCOPED_CARD,
            "- Osoby poniżej 15 lat potrzebują zgody opiekuna.\n- Do hali wchodzi się z przepustką",
            _CARD_EDIT,
            "- Osoby poniżej 15 lat potrzebują zgody opiekuna.\n- Hala czynna do 17:00",
        ),
        (
            _SEPARATE_NOTICE,
            "Odbiór odbędzie się wieczorem i potrwa do 23 minut. "
            "Gdy dopisze pogoda, pokażemy przykładową osłonę. "
            "Po odbiorze można zadawać pytania przy portierni.",
            _NOTICE_AS_PARAGRAPH,
            "Odbiór odbędzie się wieczorem i potrwa do 23 minut. "
            "Gdy dopisze pogoda, pokażemy przykładową osłonę. "
            "Po odbiorze można zadawać pytania przy portierni.",
        ),
    ],
)
def test_local_revision_keeps_scope_and_modality_after_explicit_edits(
    studio_chat, monkeypatch, source, initial, change, updated
):
    monkeypatch.setattr(
        llm_simple_service.SETTINGS, "ACADEMY_GEMMA_REVIEW_RETRY_ENABLED", True
    )
    chat, sent, replies = studio_chat
    assert chat(source, stream=False, verify_history=True) == initial
    history = [
        {"role": "user", "content": source},
        {
            "role": "assistant",
            "content": "Ogłoszono termin i wymagania w obu punktach.",
        },
    ]
    assert chat(change, history, stream=False, verify_history=True) == updated
    assert not sent and not replies


@pytest.mark.parametrize(
    ("source", "edit"),
    [
        (
            _COMMUNICATION_QUEUE,
            _QUEUE_EDIT.replace("zamiast w sobotę", "zamiast w piątek"),
        ),
        (_COMMUNICATION_QUEUE, _QUEUE_EDIT.replace("Podsumowanie", "Odbiór")),
        (_SCOPED_CARD, _CARD_EDIT.replace("Pierwszego", "Drugiego")),
        (_SCOPED_CARD, _CARD_EDIT.replace("Przepustka", "Karta")),
        (
            _SCOPED_CARD,
            _CARD_EDIT.replace("Hala czynna do 17:00", "Hala otwarta z przepustką"),
        ),
        (_SEPARATE_NOTICE.replace("nie dłużej niż", "dokładnie"), _NOTICE_AS_PARAGRAPH),
    ],
)
def test_local_revision_defers_an_edit_without_matching_source_evidence(source, edit):
    history = [
        HistoryMessage(role="user", content=source),
        HistoryMessage(
            role="assistant", content="Sprzeczna odpowiedź z wcześniejszego szkicu."
        ),
    ]
    assert studio_revision(edit, history) is None
