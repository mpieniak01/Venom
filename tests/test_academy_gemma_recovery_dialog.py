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


def test_ev_d02_keeps_explicit_top_and_replaces_criterion_in_the_same_session(
    studio_chat, monkeypatch
):
    monkeypatch.setattr(
        llm_simple_service.SETTINGS, "ACADEMY_GEMMA_REVIEW_RETRY_ENABLED", True
    )
    chat, calls, replies = studio_chat
    session = str(uuid4())
    assert (
        chat(
            "Skrzynki sortuję według rozmiaru, najmniejsze na górze. "
            "Zaproponuj jeden sposób utrzymania porządku.",
            session=session,
            verify_history=True,
            stream=False,
        )
        == "Oznacz półki według rozmiaru i umieszczaj najmniejsze rzeczy na górze."
    )
    assert (
        chat(
            "Od teraz kieruj się częstością użycia, najczęściej używane na wysokości ręki. "
            "Podaj jeden sposób.",
            session=session,
            verify_history=True,
            stream=False,
        )
        == "Oznacz półki według częstości użycia i umieszczaj najczęściej używane rzeczy na wysokości ręki."
    )
    assert not calls and not replies


@pytest.mark.parametrize(
    "placement, expected",
    [
        ("najmniejsze na górze", "najmniejsze rzeczy na górze"),
        ("największe na dole", "największych rzeczy"),
        ("mniejsze na górze", "mniejsze rzeczy na górze"),
        ("najmniejsze na wysokości ręki", None),
        ("najcięższe na górze", None),
    ],
)
def test_sorting_checks_size_and_explicit_placement_together(placement, expected):
    answer = studio_dialog(
        f"Torby sortuję według wielkości, {placement}. "
        "Zaproponuj jeden sposób utrzymania porządku.",
        [],
    )
    if expected is None:
        assert answer is None
    else:
        assert answer is not None and "według rozmiaru" in answer and expected in answer


_ROW_PLAN = (
    "Wariant Wichura ma dwanaście plansz w jednym rzędzie, "
    "a wariant Mgła ma dziewięć plansz w dwóch osobnych salach. "
    "Zależy mi na prostej orientacji. Który wariant bardziej do tego pasuje?"
)
_ROW_ENTRANCES = (
    "W Wichurze da się wejść do rzędu z obu stron. "
    "Czy strzałka od wejścia nadal jest dobrym pomysłem?"
)
_GATE_LAYOUT = (
    "Wyjaśnij różnicę między dziedzińcem otwartym od ulicy "
    "a zamkniętym bramą w dwóch zdaniach."
)
_STYLE_OPTIONS = (
    "Alicja chce ułożyć na stole nagrania alfabetycznie według wykonawców. "
    "Tomek chce pogrupować płyty według gatunku. Jakie są zalety obu układów?"
)


def test_studio_layout_publishes_undirected_scheme_for_both_entrances(
    studio_chat, monkeypatch
):
    monkeypatch.setattr(
        llm_simple_service.SETTINGS, "ACADEMY_GEMMA_REVIEW_RETRY_ENABLED", True
    )
    chat, calls, replies = studio_chat
    session = str(uuid4())
    turns = (
        (_ROW_PLAN, "Wariant Wichura"),
        (_ROW_ENTRANCES, "Przy obu wejściach"),
        (
            "Bez kierunku i bez numerów. Podaj jeden sposób oznaczenia.",
            "Umieść przy obu wejściach ten sam prosty schemat pokazujący układ ekspozycji w jednym rzędzie.",
        ),
    )
    for prompt, expected in turns:
        answer = chat(prompt, session=session, verify_history=True, stream=False)
        assert expected in answer
    assert not calls and not replies


def test_studio_courtyard_distinguishes_layout_from_temporary_gate_state():
    layout = studio_dialog(_GATE_LAYOUT, [])
    assert layout and "z ulicy" in layout and "przez bramę" in layout
    boundary = "Nie zakładaj, że goście nie mogą wejść."
    history = _history(_GATE_LAYOUT, layout)
    assert studio_dialog(boundary, history) == layout
    history += _history(boundary, "Teren jest prywatny.")
    answer = studio_dialog("A jeśli brama jest otwarta?", history)
    assert answer and "układu wejścia" in answer and "chwilowe" in answer
    assert "prywatn" not in answer


def test_studio_catalog_switch_retains_genre_for_one_table_sign():
    comparison = studio_dialog(_STYLE_OPTIONS, [])
    assert comparison and "według wykonawców" in comparison and "gatunku" in comparison
    selection = "Zachowujemy tylko układ Tomka. Jak oznaczyć grupy?"
    history = _history(_STYLE_OPTIONS, comparison)
    labels = studio_dialog(selection, history)
    assert labels and "stojące przekładki z nazwami stylów" in labels
    history += _history(selection, labels)
    assert (
        studio_dialog(
            "Bez tablic wiszących. Jeden sposób, który mieści się na stole.",
            history,
        )
        == "Ustaw między grupami na stole stojące przekładki z nazwami stylów."
    )


@pytest.mark.parametrize(
    "prompt,history",
    [
        (
            "Dziś brama jest otwarta i mam pozwolenie wejścia. Czy dostęp jest potwierdzony?",
            _history(_GATE_LAYOUT, "Są dwa układy wejścia."),
        ),
        (
            "Bez strzałek ani numerów. Podaj jeden sposób orientacji.",
            _history(_ROW_PLAN, "Wariant Wichura."),
        ),
        (
            "Zachowujemy tylko układ Alicji. Jak oznaczyć grupy?",
            _history(_STYLE_OPTIONS, "Alfabet i gatunek porządkują nagrania inaczej."),
        ),
        ('Przetłumacz: "' + _GATE_LAYOUT + '"', []),
    ],
)
def test_studio_layout_defers_unbound_or_changed_scope(prompt, history):
    assert studio_dialog(prompt, history) is None


def test_studio_replaces_the_clarified_field_only(studio_chat, monkeypatch):
    monkeypatch.setattr(
        llm_simple_service.SETTINGS, "ACADEMY_GEMMA_REVIEW_RETRY_ENABLED", True
    )
    chat, sent, _ = studio_chat
    source = (
        "Do witryny pasuje etykieta z nazwą rośliny i godziną, "
        "a do rejestru nazwa i numer partii. Przygotuj osobne listy."
    )
    select = "Pokaż mi tylko część dla witryny."
    edit = "W witrynie numer partii zastąp kodem kolekcji? Chodzi mi o godzinę, resztę zostaw."
    assert (
        chat(source)
        == "Witryna:\n- Nazwa rośliny\n- Godzina\n\nRejestr:\n- Nazwa\n- Numer partii"
    )
    history = [
        {"role": "user", "content": source},
        {"role": "assistant", "content": "Zła lista z dopisanym numerem partii."},
        {"role": "user", "content": select},
        {"role": "assistant", "content": "Witryna: godzina i numer partii."},
    ]
    assert chat(select, history[:2]) == "Witryna:\n- Nazwa rośliny\n- Godzina"
    assert (
        chat(edit, history, verify_history=True)
        == "Witryna:\n- Nazwa rośliny\n- Kod kolekcji"
    )
    assert not sent


def test_studio_tracks_shared_and_exclusive_items_after_addition(
    studio_chat, monkeypatch
):
    monkeypatch.setattr(
        llm_simple_service.SETTINGS, "ACADEMY_GEMMA_REVIEW_RETRY_ENABLED", True
    )
    chat, sent, _ = studio_chat
    source = (
        "We wtorek potrzebne są aparat, statyw i gimbal, "
        "a w środę statyw, rejestrator i gimbal. Co jest wspólne?"
    )
    add = "We wtorek dodajemy rejestrator, reszta bez zmian. Co jest teraz wspólne?"
    only = "Co zostało tylko we wtorek po zmianie?"
    history = [
        {"role": "user", "content": source},
        {"role": "assistant", "content": "Wspólny jest aparat."},
    ]
    assert chat(source) == "Wspólne: statyw, gimbal."
    assert (
        chat(add, history, verify_history=True)
        == "Wspólne: statyw, gimbal, rejestrator."
    )
    history += [
        {"role": "user", "content": add},
        {"role": "assistant", "content": "Wspólny jest wyłącznie aparat."},
    ]
    assert chat(only, history, verify_history=True) == "Tylko we wtorek: aparat."
    assert not sent


def test_studio_replays_removal_before_moving_only_the_loan_location(
    studio_chat, monkeypatch
):
    monkeypatch.setattr(
        llm_simple_service.SETTINGS, "ACADEMY_GEMMA_REVIEW_RETRY_ENABLED", True
    )
    chat, sent, _ = studio_chat
    source = (
        "Dwa punkty na kartę dostępu. Wiek od 16 lat i do kabiny tylko z karnetem. "
        "Osoby bez własnego kasku wypożyczają go przy ladzie."
    )
    dropped = "W pierwszym punkcie usuń tylko wymóg karnetu."
    # The version without the access requirement remains the source for later edits.
    original = "1. Wiek od 16 lat i do kabiny tylko z karnetem.\n2. Osoby bez własnego kasku wypożyczają go przy ladzie."
    assert chat(source) == original
    history = [
        {"role": "user", "content": source},
        {"role": "assistant", "content": original},
    ]
    assert (
        chat(dropped, history)
        == "1. Wiek od 16 lat.\n2. Osoby bez własnego kasku wypożyczają go przy ladzie."
    )
    final = "Teraz kask przy biurku. Zachowaj ograniczenie użytkowników kasku."
    history += [
        {"role": "user", "content": dropped},
        {"role": "assistant", "content": original},
    ]
    assert (
        chat(final, history, verify_history=True)
        == "1. Wiek od 16 lat.\n2. Osoby bez własnego kasku wypożyczają go przy biurku."
    )
    assert not sent
