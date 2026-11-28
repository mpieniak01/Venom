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
