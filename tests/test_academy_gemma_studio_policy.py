"""Verify claim and quantity policies through the Studio HTTP entry point."""

import pytest

from tests.test_academy_qualified_chat import native, streamed
from tests.test_academy_qualified_chat import studio_chat as qualified_studio_chat
from venom_core.services import llm_simple_service
from venom_core.services.chat_policy.qualified_chat import GENERATION_TRUNCATED
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
