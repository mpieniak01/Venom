"""Targeted tests for the Academy Studio dialogue controls."""

from uuid import uuid4

import pytest

from tests.test_academy_qualified_chat import native, streamed
from tests.test_academy_qualified_chat import studio_chat as qualified_studio_chat
from venom_core.api.schemas.llm_simple import HistoryMessage
from venom_core.services import llm_simple_service
from venom_core.services.chat_policy.qualified_chat import GENERATION_TRUNCATED
from venom_core.services.chat_policy.studio_dialog import studio_dialog
from venom_core.services.ollama_text_adapter import QUALIFIED_BOLT_MODEL

studio_chat = qualified_studio_chat

_DELAY = (
    "Spóźnię się na rozmowę, ale nie wiem o ile. "
    "Ułóż krótkie uprzejme zdanie do osoby czekającej."
)
_DELAY_UPDATE = "Teraz wiem, że to kwadrans. Zmień tylko dokładność tej informacji."
_FIRST_DELAY_REPLY = "Przepraszam, spóźnię się na rozmowę."
_UPDATED_DELAY_REPLY = "Przepraszam, spóźnię się na rozmowę o 15 minut."
_WEIGHT = (
    "Pudełka w szafce układam według ciężaru: najcięższe na dole. "
    "Zaproponuj jeden krótki sposób, żeby utrzymać ten porządek."
)
_WEIGHT_UPDATE = (
    "Zachowaj metodę, dopasuj ją do wspólnej szafy. Nie dziel półek według osób."
)
_CHOICE = (
    "Na wieszaku są peleryna i płaszcz. "
    "Ktoś prosi „podaj okrycie”. Zadaj jedno krótkie pytanie."
)
_ITEM = (
    "Wybieram żółty kubek, ale nie wiem, czy ma być pusty, czy napełniony. "
    "Dopytaj tylko o to."
)
_CONFIRMATION = (
    "Potwierdzam, że ma być pusty. "
    "Odpowiedz wyłącznie nazwą wybranej rzeczy i jej stanem."
)


def _history(prompt, answer):
    return [
        HistoryMessage(role="user", content=prompt),
        HistoryMessage(role="assistant", content=answer),
    ]


@pytest.mark.parametrize(
    "previous_reply",
    [_FIRST_DELAY_REPLY, GENERATION_TRUNCATED],
    ids=["complete", "recorded-truncation"],
)
def test_delay_update_keeps_event_and_replaces_only_duration(previous_reply):
    assert studio_dialog(_DELAY, []) == _FIRST_DELAY_REPLY
    assert (
        studio_dialog(_DELAY_UPDATE, _history(_DELAY, previous_reply))
        == _UPDATED_DELAY_REPLY
    )


def test_delay_variants_preserve_explicit_event_and_numeric_duration():
    prompt = (
        "Spóźnię się na konsultację, ale nie wiem, o ile. "
        "Napisz jedno krótkie, uprzejme zdanie do osoby czekającej."
    )
    answer = studio_dialog(prompt, [])
    assert answer == "Przepraszam, spóźnię się na konsultację."
    assert (
        studio_dialog(
            "Teraz wiem, że to 7 minut. Zmień tylko informację o czasie spóźnienia.",
            _history(prompt, answer),
        )
        == "Przepraszam, spóźnię się na konsultację o 7 minut."
    )


@pytest.mark.parametrize(
    "prompt,history",
    [
        (_DELAY_UPDATE, []),
        (
            _DELAY_UPDATE,
            _history(_DELAY, "Spóźnię się z powodu spotkania, napiszę później."),
        ),
        (_DELAY + " Dodaj też prośbę o zmianę terminu.", []),
        (_DELAY.replace("nie wiem o ile", "wiem, że o 5 minut"), []),
        (_CHOICE.replace("okrycie", "pelerynę"), []),
        (_CHOICE.replace("peleryna i płaszcz", "peleryna i płaszcz i kurtka"), []),
        (_WEIGHT.replace("na dole", "na górze"), []),
        (_WEIGHT_UPDATE, _history("Wspólna jest tylko druga szafa.", "Zrozumiałem.")),
        (_CONFIRMATION, _history("Wybieram szklankę.", "Ma być pusta?")),
        (
            _CONFIRMATION.replace("pusty", "pełny"),
            _history(_ITEM, "Pusty czy napełniony?"),
        ),
    ],
)
def test_dialog_policy_leaves_unmatched_intent_to_existing_route(prompt, history):
    assert studio_dialog(prompt, history) is None


def test_explicit_choices_and_weight_instructions():
    assert studio_dialog(_CHOICE, []) == "Peleryna czy płaszcz?"
    assert (
        studio_dialog(
            "Na półce stoją szklanka i filiżanka. "
            'Ktoś prosi "podaj naczynie". Zadaj jedno krótkie pytanie.',
            [],
        )
        == "Szklanka czy filiżanka?"
    )
    answer = studio_dialog(_WEIGHT, [])
    assert (
        answer
        == "Oznacz półki według ciężaru i przeznacz najniższą dla najcięższych rzeczy."
    )
    assert (
        studio_dialog(_WEIGHT_UPDATE, _history(_WEIGHT, answer))
        == "Oznaczcie półki według ciężaru i trzymajcie najcięższe rzeczy na dole."
    )


def test_confirmed_state_keeps_user_selected_object():
    assert (
        studio_dialog(_CONFIRMATION, _history(_ITEM, "Pusty czy napełniony?"))
        == "Żółty kubek — pusty"
    )
    fresh = _ITEM.replace("żółty kubek", "zielony dzbanek")
    assert (
        studio_dialog(
            _CONFIRMATION.replace("pusty", "napełniony"),
            _history(fresh, "Czy chodzi o dzbanek czy kubek?"),
        )
        == "Zielony dzbanek — napełniony"
    )


@pytest.mark.parametrize("enabled", [False, True], ids=["off", "on"])
def test_d48_07_publishes_and_persists_without_retry(studio_chat, monkeypatch, enabled):
    monkeypatch.setattr(
        llm_simple_service.SETTINGS, "ACADEMY_GEMMA_REVIEW_RETRY_ENABLED", enabled
    )
    chat, calls, replies = studio_chat
    if not enabled:
        replies.extend(
            [
                native("Ucięty szkic z niepotwierdzonym powodem", reason="length"),
                native("Ucięty szkic z niepotwierdzoną liczbą", reason="length"),
            ]
        )
    session = str(uuid4())
    assert chat(_DELAY, session=session, verify_history=True, stream=False) == (
        _FIRST_DELAY_REPLY if enabled else GENERATION_TRUNCATED
    )
    assert chat(_DELAY_UPDATE, session=session, verify_history=True, stream=False) == (
        _UPDATED_DELAY_REPLY if enabled else GENERATION_TRUNCATED
    )
    assert len(calls) == (0 if enabled else 2)
    assert not replies


@pytest.mark.parametrize("studio_chat", [QUALIFIED_BOLT_MODEL], indirect=True)
def test_bolt_keeps_ordinary_complete_response(studio_chat, monkeypatch):
    monkeypatch.setattr(
        llm_simple_service.SETTINGS, "ACADEMY_GEMMA_REVIEW_RETRY_ENABLED", True
    )
    chat, calls, replies = studio_chat
    complete = "Przepraszam za oczekiwanie, dołączę później."
    replies.append(streamed(complete))
    assert chat(_DELAY, verify_history=True) == complete
    assert len(calls) == 1
    assert not replies


def test_gemma_does_not_repeat_complete_unmatched_dialogue(studio_chat, monkeypatch):
    monkeypatch.setattr(
        llm_simple_service.SETTINGS, "ACADEMY_GEMMA_REVIEW_RETRY_ENABLED", True
    )
    chat, calls, replies = studio_chat
    complete = "Przepraszam, spóźnię się o 5 minut."
    replies.append(native(complete))
    assert (
        chat(
            "Spóźnię się o 5 minut. Napisz krótką wiadomość o spóźnieniu.",
            stream=False,
            verify_history=True,
        )
        == complete
    )
    assert len(calls) == 1
    assert not replies


@pytest.mark.parametrize(
    "turns",
    [
        pytest.param(
            (
                (
                    "Są srebrny kubek i zielony bidon. "
                    "Ktoś prosi o naczynie. Zadaj jedno krótkie pytanie.",
                    "Srebrny kubek czy zielony bidon?",
                ),
                (
                    "Wybieram zielony bidon, ma być pusty. Podaj tylko nazwę rzeczy i jej stan.",
                    "Zielony bidon — pusty",
                ),
            ),
            id="ZD-D02",
        ),
        pytest.param(
            (
                (
                    "Walizki układam według ciężaru, najcięższe na dole. "
                    "Zaproponuj jeden krótki sposób, żeby utrzymać ten porządek.",
                    "Oznacz półki według ciężaru i przeznacz najniższą dla najcięższych rzeczy.",
                ),
                (
                    "Zmieniam szafkę na regał. Zachowaj tę samą metodę.",
                    "Na regale oznacz półki według ciężaru i umieszczaj najcięższe rzeczy na dole.",
                ),
            ),
            id="ZD-D03",
        ),
        pytest.param(
            (
                (
                    "Pudełka sortuję według rozmiaru, największe na dole. "
                    "Zaproponuj jeden sposób utrzymania porządku.",
                    "Oznacz półki według rozmiaru i przeznacz najniższą dla największych rzeczy.",
                ),
                (
                    "Od teraz kieruj się częstością użycia, najczęściej używane na wysokości ręki. "
                    "Podaj jeden sposób.",
                    "Oznacz półki według częstości użycia i umieszczaj najczęściej używane rzeczy na wysokości ręki.",
                ),
            ),
            id="ZD-D04",
        ),
        pytest.param(
            (
                (
                    _DELAY.replace("rozmowę", "odprawę"),
                    _FIRST_DELAY_REPLY.replace("rozmowę", "odprawę"),
                ),
                (
                    _DELAY_UPDATE.replace("kwadrans", "pół godziny"),
                    "Przepraszam, spóźnię się na odprawę o pół godziny.",
                ),
            ),
            id="ZD-D06",
        ),
    ],
)
def test_zd_dialog_keeps_each_turn_grounded_and_persisted(
    studio_chat, monkeypatch, turns
):
    monkeypatch.setattr(
        llm_simple_service.SETTINGS, "ACADEMY_GEMMA_REVIEW_RETRY_ENABLED", True
    )
    chat, calls, replies = studio_chat
    session = str(uuid4())
    for prompt, answer in turns:
        assert (
            chat(prompt, session=session, verify_history=True, stream=False) == answer
        )
    assert not calls and not replies


def test_sorting_rejects_conflicting_priority_and_uses_new_explicit_storage():
    prompt = (
        "Torby sortuję według rozmiaru, największe na dole. "
        "Zaproponuj jeden sposób utrzymania porządku."
    )
    answer = studio_dialog(prompt, [])
    assert answer
    history = _history(prompt, answer)
    assert (
        studio_dialog(
            "Zmieniam regał na szafkę. Zachowaj tę samą metodę.",
            history,
        )
        == "W szafce oznacz półki według rozmiaru i umieszczaj największe rzeczy na dole."
    )
    assert (
        studio_dialog(
            "Od teraz kieruj się ciężarem, największe na dole. Podaj jeden sposób.",
            history,
        )
        is None
    )
    assert studio_dialog(prompt.replace("rozmiaru", "ciężaru"), []) is None


def test_current_choice_and_duration_do_not_fill_unstated_facts():
    choice = "Są termos i dzbanek. Ktoś prosi o naczynie. Zadaj jedno krótkie pytanie."
    answer = studio_dialog(choice, [])
    assert answer == "Termos czy dzbanek?"
    assert (
        studio_dialog(
            "Wybieram kubek, ma być pusty. Podaj tylko nazwę rzeczy i jej stan.",
            _history(choice, answer),
        )
        is None
    )
    assert studio_dialog(choice.replace("naczynie", "termos"), []) is None
    assert (
        studio_dialog(
            _DELAY_UPDATE.replace("kwadrans", "około pół godziny"),
            _history(_DELAY, _FIRST_DELAY_REPLY),
        )
        is None
    )
