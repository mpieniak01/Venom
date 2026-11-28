"""Targeted tests for the Academy Studio dialogue controls."""

from uuid import uuid4

import pytest

from tests.test_academy_qualified_chat import native, streamed
from tests.test_academy_qualified_chat import studio_chat as qualified_studio_chat
from venom_core.api.schemas.llm_simple import HistoryMessage
from venom_core.services import llm_simple_service
from venom_core.services.chat_policy.qualified_chat import GENERATION_TRUNCATED
from venom_core.services.chat_policy.studio_dialog import studio_dialog
from venom_core.services.chat_policy.studio_dialog_compare import studio_comparison
from venom_core.services.chat_policy.studio_revision import studio_revision
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


_SHARED_REFERENCES = (
    "Do wspólnego użytku jest słownik podpisów oraz mapa symboli. "
    "Słownik objaśnia skróty, mapa pokazuje, gdzie są na planszy. "
    "Oba dostaną kopię, ale tylko mapa ma mieć dużą wersję. Jak to przekazać kolegom?"
)
_CARRY_OPTIONS = (
    "W ofercie Fala jest długi uchwyt i niewielki worek, a w ofercie Kamyk "
    "krótki uchwyt i duży worek. Obydwie kosztują 38 zł. "
    "Potrzebuję zmieścić ręczniki i nie zależy mi na długości uchwytu. Który wariant?"
)
_PROJECT_ROW = (
    "Na wydarzenie są dwa projekty: Tor to jedna kolejka stanowisk, Krąg to kilka "
    "stołów w dwóch pokojach. Zależy mi na tym, żeby osoba pierwszy raz łatwo "
    "zobaczyła wszystkie stanowiska. Co wybrać?"
)
_PROJECT_DOORS = "Do Toru wchodzi się z dwóch końców. Czy informacja „zacznij przy drzwiach” wystarczy?"
_NEUTRAL_MAP = (
    "Daj jeden neutralny sposób na pokazanie układu bez narzucania kolejności."
)
_THEMES = (
    "Przeglądający plakaty mogą szukać konkretnego autora albo poznawać temat, "
    "którego wcześniej nie widzieli. Po co grupować według autorów, a po co "
    "według tematów?"
)


def test_studio_copy_and_download_are_bound_to_the_correct_sources():
    summary = studio_comparison(_SHARED_REFERENCES, [])
    assert summary == (
        "Słownik podpisów objaśnia skróty. Mapa symboli pokazuje, gdzie są na planszy. "
        "Dla obu przewidziano po kopii. Tylko „mapa symboli” ma mieć dużą wersję."
    )
    history = _history(_SHARED_REFERENCES, "Oba pliki można pobrać jako PDF.")
    assert (
        studio_comparison(
            "Dodaj informację, że ten pierwszy można też pobrać jako plik tekstowy.",
            history,
        )
        == summary + " Materiał „słownik podpisów” można też pobrać jako plik tekstowy."
    )
    assert (
        studio_comparison("Dopisz, że drugą można również pobrać jako PDF.", history)
        == summary + " Materiał „mapa symboli” można też pobrać jako PDF."
    )
    assert (
        studio_comparison(
            _SHARED_REFERENCES.replace("tylko mapa ma mieć", "tylko plansza ma mieć"),
            [],
        )
        is None
    )


def test_studio_changed_carrying_requirement_does_not_infer_fit():
    assert studio_comparison(_CARRY_OPTIONS, []) == (
        "Wybierz wariant Kamyk. Ma większy worek, a cena obu jest taka sama."
    )
    followup = (
        "Jeżeli zamiast ręczników zabraliśmy jedną małą ściereczkę, a teraz "
        "zależy mi na noszeniu przez ramię, którą cechę porównać?"
    )
    history = _history(_CARRY_OPTIONS, "Fala na pewno pasuje na ramię.")
    assert studio_comparison(followup, history) == (
        "Porównaj długość uchwytów. Sprawdź, czy któryś z uchwytów "
        "pozwala wygodnie nosić worek na ramieniu."
    )
    assert studio_comparison(followup, _history("Wybieram koszyk.", "Jasne.")) is None
    assert (
        studio_comparison(_CARRY_OPTIONS.replace("duży worek", "mały worek"), [])
        is None
    )


def test_studio_theme_labels_follow_explicit_display_choice():
    comparison = studio_dialog(_THEMES, [])
    assert (
        comparison
        and "prace konkretnej osoby" in comparison
        and "odkrywać nowe tematy" in comparison
    )
    history = _history(_THEMES, comparison)
    change = "Zostajemy przy tematach. Na płaskim stole chcę prosty sposób orientacji."
    label = "Ustaw na stole przy każdej grupie kartę z nazwą tematu."
    assert studio_dialog(change, history) == label
    assert (
        studio_dialog(
            "Wybierz jeden sposób, bez aplikacji, wiszących tablic i strzałek.",
            history + _history(change, "Zawieś strzałkę."),
        )
        == label
    )
    assert (
        studio_dialog(
            "Wybierz jeden sposób, bez aplikacji, wiszących tablic i strzałek.", history
        )
        is None
    )


def test_studio_two_ended_project_needs_a_plan_of_the_actual_row(
    studio_chat, monkeypatch
):
    monkeypatch.setattr(
        llm_simple_service.SETTINGS, "ACADEMY_GEMMA_REVIEW_RETRY_ENABLED", True
    )
    chat, calls, replies = studio_chat
    session = str(uuid4())
    for prompt, expected in [
        (_PROJECT_ROW, "Wariant Tor"),
        (_PROJECT_DOORS, "Są dwa wejścia"),
        (
            _NEUTRAL_MAP,
            "Umieść przy obu wejściach ten sam prosty plan jednego rzędu stanowisk.",
        ),
    ]:
        answer = chat(prompt, session=session, verify_history=True, stream=False)
        assert expected in answer
    assert not calls and not replies
    history = _history(_PROJECT_ROW, "Wariant Tor.")
    assert studio_dialog(_PROJECT_DOORS.replace("Toru", "Kręgu"), history) is None
    assert studio_dialog(_NEUTRAL_MAP, history) is None


_PICKUP_NOTICE = (
    "Napisz informację bez dopisków: „Osoby z rezerwacją odbierają plakiety "
    "przy kantorku, pozostali przy okienku. Odbiór od 12:00 do 16:00”."
)
_PICKUP_RESERVED_UPDATE = (
    "Tylko dla osób z rezerwacją nowe miejsce to czytelnia. "
    "Podaj całą informację nadal bez dopisków."
)
_PICKUP_OTHER_UPDATE = "Osoby bez rezerwacji odbierają teraz przy recepcji."


def test_studio_pickup_replaces_the_location_for_one_group(studio_chat, monkeypatch):
    monkeypatch.setattr(
        llm_simple_service.SETTINGS, "ACADEMY_GEMMA_REVIEW_RETRY_ENABLED", True
    )
    chat, calls, _ = studio_chat
    session = str(uuid4())
    assert chat(_PICKUP_NOTICE, session=session, verify_history=True) == (
        "Osoby z rezerwacją odbierają plakiety przy kantorku, pozostali przy okienku. "
        "Odbiór od 12:00 do 16:00."
    )
    assert chat(_PICKUP_RESERVED_UPDATE, session=session, verify_history=True) == (
        "Osoby z rezerwacją odbierają plakiety — miejsce odbioru to czytelnia. "
        "Pozostali odbierają plakiety przy okienku. Odbiór od 12:00 do 16:00."
    )
    assert chat(_PICKUP_OTHER_UPDATE, session=session, verify_history=True) == (
        "Osoby z rezerwacją odbierają plakiety — miejsce odbioru to czytelnia. "
        "Pozostali odbierają plakiety przy recepcji. Odbiór od 12:00 do 16:00."
    )
    assert not calls


def test_studio_pickup_uses_latest_user_update_for_each_group():
    history = _history(_PICKUP_NOTICE, "Wszyscy przy okienku od 13:00.")
    history += _history(_PICKUP_RESERVED_UPDATE, "Ciągle przy kantorku.")
    history += _history(_PICKUP_OTHER_UPDATE, "Czytelnię zamknięto.")
    result = studio_revision("Osoby z rezerwacją odbierają teraz w sali Mchu.", history)
    assert result == (
        "Osoby z rezerwacją odbierają plakiety w sali Mchu. "
        "Pozostali odbierają plakiety przy recepcji. Odbiór od 12:00 do 16:00."
    )


@pytest.mark.parametrize(
    ("correction", "prompts"),
    [
        (_PICKUP_RESERVED_UPDATE, []),
        (
            _PICKUP_RESERVED_UPDATE,
            [_PICKUP_NOTICE, "Zmieniam godziny na 16:00–18:00."],
        ),
        (
            "Tylko dla osób z rezerwacją nowe miejsce to czytelnia lub hol.",
            [_PICKUP_NOTICE],
        ),
        ("Dla wszystkich nowe miejsce to czytelnia.", [_PICKUP_NOTICE]),
    ],
)
def test_studio_pickup_defers_when_scope_or_source_is_unclear(correction, prompts):
    history = [
        message for prompt in prompts for message in _history(prompt, "Roboczo.")
    ]
    assert studio_revision(correction, history) is None
