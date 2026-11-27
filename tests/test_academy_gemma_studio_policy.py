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
