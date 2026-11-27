from __future__ import annotations

import pytest

from venom_core.api.schemas.llm_simple import HistoryMessage
from venom_core.services.chat_policy.review_draft import parse_review_draft
from venom_core.services.chat_policy.studio_revision import studio_revision

_REVIEW = (
    "Napisz krótką wiadomość do kolegi o wspólnym przeglądzie opisu ekspozycji. "
    "Poproś wprost o uwagi do opisu. Bez ustalania terminu."
)
_WITHDRAW = (
    "Zrezygnuj z prośby o uwagi. Podaj jedno zaproszenie bez dodatkowych poleceń."
)
_PLAN = (
    "Miłosz opracował plan rozstawienia stołów. Na razie zaproś zespół do wspólnego "
    "przeglądu, bez zbierania opinii. Napisz krótkie zaproszenie."
)
_PLAN_QUESTION = (
    "Zamieniam zasadę: poproś wprost o jedno krótkie pytanie do planu, nadal bez "
    "zbierania ogólnych opinii."
)
_PLAN_RESTORE = (
    "Wycofuję prośbę o pytanie. Wracamy do samego zaproszenia w jednym zdaniu."
)


def _history(*pairs: tuple[str, str]) -> list[HistoryMessage]:
    return [
        message
        for user, assistant in pairs
        for message in (
            HistoryMessage(role="user", content=user),
            HistoryMessage(role="assistant", content=assistant),
        )
    ]


@pytest.mark.parametrize(
    "initial, followup, required",
    [
        (
            "Uprość zdanie „Po odsunięciu zasłony w przejściu zrobiło się jaśniej”. "
            "Podaj jeden tekst.",
            "Zachowaj przejście i napisz jeszcze krócej. Tylko jedna wersja bez komentarza.",
            ("odsunięciu zasłony", "w przejściu", "pojaśniało"),
        ),
        (
            "Skróć „Po wyłączeniu wentylatora szum w czytelni ustał”, bez zmiany "
            "przyczyny. Tylko jedno zdanie.",
            "Skróć jeszcze bardziej i zachowaj czytelnię w zdaniu.",
            ("wyłączono wentylator", "szum w czytelni ustał"),
        ),
        (
            "Skróć „Po wyłączeniu projektora buczenie w sali ustało”. Jedna wersja.",
            "Zachowaj salę i napisz jeszcze krócej.",
            ("wyłączono projektor", "buczenie w sali ustało"),
        ),
    ],
)
def test_rewrite_remains_grounded_when_prior_draft_omits_the_event(
    initial, followup, required
):
    draft = studio_revision(initial, [])
    assert draft is not None
    assert len(draft) <= len(initial.split("„")[1].split("”")[0]) + 1
    short = studio_revision(followup, _history((initial, "Sam wynik, bez zdarzenia.")))
    assert short is not None
    assert len(short) < len(draft)
    assert all(part in short.casefold() for part in required)
    assert short.count(".") == 1


@pytest.mark.parametrize(
    "source, current, old_item, new_place",
    [
        (
            "Po zabraniu płyty z górnej półki regał przestał skrzypieć",
            "Korekta: płyta była na dolnej półce. Zmień tylko to i podaj jedną gotową wersję.",
            "płytę",
            "dolnej",
        ),
        (
            "Po zabraniu książki z górnej półki stelaż przestał skrzypieć",
            "Poprawka: książka była na środkowej półce. Zmień tylko to i podaj jedną gotową wersję.",
            "książkę",
            "środkowej",
        ),
    ],
)
def test_shelf_correction_updates_location_without_changing_removed_object(
    source, current, old_item, new_place
):
    first = f"Skróć „{source}”. Nie dodawaj wyjaśnienia. Jedna wersja."
    second = "Zachowaj górną półkę. Napisz jeszcze krócej."
    draft = studio_revision(first, [])
    assert draft and f"Zabrano {old_item} z górnej półki" in draft
    short = studio_revision(second, _history((first, draft)))
    assert short and len(short) < len(draft)
    assert f"Zabrano {old_item} z górnej półki" in short
    history = _history((first, draft), (second, "Zabrano górną półkę."))
    fixed = studio_revision(current, history)
    assert fixed and f"Zabrano {old_item} z {new_place} półki" in fixed
    assert "nie skrzypi" in fixed and "górnej" not in fixed
    assert (
        studio_revision(
            current.replace("płyta", "teczka").replace("książka", "teczka"), history
        )
        is None
    )


@pytest.mark.parametrize(
    "unsafe",
    [
        "Cześć, przesyłam opis ekspozycji do wspólnego przeglądu. Proszę o uwagi do opisu.",
        "Proponuję wspólny przegląd opisu ekspozycji. Proszę o uwagi do plakatu.",
        "Proponuję wspólny przegląd opisu ekspozycji. Nie znam terminu i wysłałam plik.",
    ],
)
def test_initial_review_repairs_unsourced_transfer_or_misdirected_feedback(unsafe):
    review = parse_review_draft(_REVIEW)
    assert review is not None
    valid = (
        "Cześć, proponuję wspólny przegląd opisu ekspozycji. Proszę o uwagi do opisu."
    )
    assert review.publish_initial(valid) == valid
    assert (
        review.publish_initial(unsafe)
        == f"{review.invitation()} Proszę o uwagi do opisu."
    )
    assert (
        studio_revision(_WITHDRAW, _history((_REVIEW, unsafe))) == review.invitation()
    )


def test_transfer_reported_by_user_remains_outside_pending_invitation_rule():
    confirmed = f"Właśnie wysłałem opis. {_REVIEW}"
    assert parse_review_draft(confirmed) is None
    assert studio_revision(_WITHDRAW, _history((confirmed, "Przesyłam opis."))) is None
    quote = "Usuń frazę „przesyłam opis” z tekstu i niczego nie wysyłaj."
    assert parse_review_draft(quote) is None
    assert studio_revision(quote, _history((_REVIEW, "Szkic."))) is None


def test_confirmed_purpose_keeps_pdf_permission_and_blocks_existing_transfer():
    request = (
        "PDF z kartą warsztatu mam gotowy, ale jeszcze nie jest dołączony ani wysłany. "
        "Napisz do zespołu krótką wiadomość z zaproszeniem do wspólnego przeglądu karty. "
        "Powiedz, że plik mogę dołączyć po ich zgodzie. Bez ustalania terminu."
    )
    review = parse_review_draft(request)
    assert review is not None
    valid = (
        "Przejrzyjmy wspólnie kartę warsztatu. Plik mogę dołączyć po Waszej zgodzie."
    )
    assert review.publish_initial(valid) == valid
    unsafe = "Proponuję wspólny przegląd karty warsztatu. PDF załączyłam."
    assert review.publish_initial(unsafe) == (
        "Proponuję wspólny przegląd karty warsztatu. Plik PDF mogę dołączyć po Waszej zgodzie."
    )


def test_plan_review_replaces_prior_purpose_then_restores_only_the_invitation():
    assert studio_revision(_PLAN_QUESTION, _history((_PLAN, "Pominięty plan."))) == (
        "Proszę o jedno krótkie pytanie do planu."
    )
    assert (
        studio_revision(
            _PLAN_RESTORE,
            _history(
                (_PLAN, "Pierwotne zaproszenie."), (_PLAN_QUESTION, "Wadliwy szkic.")
            ),
        )
        == "Proponuję wspólny przegląd planu rozstawienia stołów."
    )
    assert studio_revision(_PLAN_RESTORE, _history((_PLAN, "Zwykły szkic."))) is None


def test_unsupported_rewrite_or_mismatched_history_lets_other_routes_continue():
    initial = (
        "Uprość zdanie „Po odsunięciu zasłony w korytarzu zrobiło się jaśniej”. "
        "Podaj jeden tekst."
    )
    conflict = "Zachowaj czytelnię i napisz jeszcze krócej."
    assert (
        studio_revision(
            conflict, _history((initial, "W czytelni zrobiło się jaśniej."))
        )
        is None
    )
    assert studio_revision("Zachowaj korytarz i napisz jeszcze krócej.", []) is None
    assert (
        studio_revision(
            "Skróć „Po wyłączeniu wentylatora szum w czytelni ustał”. Pomiń informację o źródle.",
            [],
        )
        is None
    )


def test_opening_and_fall_retains_both_events_and_the_named_surface():
    first = (
        "Uprość zdanie „Po otwarciu okna z półki spadła kartka”. "
        "Podaj tylko jeden tekst."
    )
    second = (
        "Zachowaj słowo „półka” w odpowiedniej odmianie. "
        "Napisz krócej, tylko jedno zdanie."
    )
    initial = studio_revision(first, [])
    assert initial == "Z półki spadła kartka po otwarciu okna."
    short = studio_revision(second, _history((first, initial)))
    assert short == "Otwarto okno, z półki spadła kartka."
    assert len(short) < len(initial)
    assert (
        studio_revision(second, _history((first, "Po otwarciu okna spadła kartka.")))
        == short
    )
    fresh_first = first.replace(
        "okna z półki spadła kartka", "drzwi z ławki spadło pudełko"
    )
    fresh_second = second.replace("„półka”", "„ławka”")
    fresh_initial = studio_revision(fresh_first, [])
    assert fresh_initial == "Z ławki spadło pudełko po otwarciu drzwi."
    assert studio_revision(fresh_second, _history((fresh_first, fresh_initial))) == (
        "Otwarto drzwi, z ławki spadło pudełko."
    )


def test_feedback_withdrawal_accepts_a_new_audience_and_topic():
    initial = _REVIEW.replace("do kolegi", "do koleżanki").replace(
        "ekspozycji", "konkursu"
    )
    assert (
        studio_revision(
            "Wycofaj prośbę o uwagi. Zostaw samo zaproszenie do wspólnego przeglądu.",
            _history((initial, "Przesyłam opis konkursu i czekam na uwagi.")),
        )
        == "Proponuję wspólny przegląd opisu konkursu."
    )


def test_temperature_rewrite_anchors_location_and_change():
    initial = (
        "Uprość zdanie „Po zamknięciu okna w korytarzu zrobiło się cieplej”. "
        "Podaj jeden tekst."
    )
    first = studio_revision(initial, [])
    assert first == "W korytarzu zrobiło się cieplej po zamknięciu okna."
    compact = studio_revision(
        "Zachowaj korytarz i podaj jeszcze krótszą wersję, wyłącznie zdanie.",
        _history((initial, first)),
    )
    assert compact == "Po zamknięciu okna w korytarzu ociepliło się."
    assert len(compact) < len(first)


@pytest.mark.parametrize(
    "source, action, causal_effect, still_going",
    [
        (
            "Po odłączeniu radia jego szum w pracowni ustał, a zegar nadal tykał",
            "Odłączono radio",
            "jego szum w pracowni ustał",
            "zegar nadal tykał",
        ),
        (
            "Po wyłączeniu pompy jej buczenie w świetlicy ustało, a metronom wciąż stukał",
            "Wyłączono pompę",
            "jej buczenie w świetlicy ustało",
            "metronom wciąż stukał",
        ),
    ],
)
def test_sound_rewrite_keeps_the_action_and_both_independent_effects(
    source, action, causal_effect, still_going
):
    initial = f"Skróć „{source}”. Zachowaj oba dźwięki i miejsce, podaj jedno zdanie."
    draft = studio_revision(initial, [])
    assert draft == f"{action}, {causal_effect}, a {still_going}."
    action_phrase = " ".join(source.split()[1:3]).replace("czeniu", "czenie")
    followup = f"Napisz jeszcze krócej, zachowując {action_phrase} i oba dźwięki."
    history = _history((initial, "W pomieszczeniu zrobiło się cicho."))
    short = studio_revision(followup, history)
    assert short == f"{action}, {causal_effect}, {still_going}."
    assert len(short) < len(draft) < len(source) + 1
    assert (
        studio_revision(followup.replace(action_phrase, "włączenie radia"), history)
        is None
    )


def test_compaction_keeps_the_location_of_removed_material_and_the_effect():
    source = "Po zabraniu kartki z lewej ławki reszta materiałów się zmieściła"
    request = f"Skróć „{source}”. Jedna wersja."
    draft = studio_revision(request, [])
    assert draft == "Zabrano kartkę z lewej ławki, a reszta materiałów się zmieściła."
    history = _history((request, "Zabrano kartkę, reszta się zmieściła."))
    short = studio_revision(
        "Zachowaj lewą ławkę, lecz skróć zdanie jeszcze bardziej.", history
    )
    assert short == "Zabrano kartkę z lewej ławki, reszta materiałów się zmieściła."
    assert len(short) < len(draft) < len(source) + 1
    assert (
        studio_revision(
            "Zachowaj prawą ławkę, lecz skróć zdanie jeszcze bardziej.", history
        )
        is None
    )


@pytest.mark.parametrize(
    "outcome",
    [
        "drzwi dały się domknąć",
        "drzwi nie dały się domknąć",
        "drzwi się domknęły",
        "nie można było zamknąć drzwi",
    ],
)
def test_removal_location_revision_does_not_change_outcome_modality(outcome):
    source = f"Po zabraniu pudełka spod stołu {outcome}"
    request = f"Skróć „{source}”. Podaj jedno zdanie."
    draft = studio_revision(request, [])
    assert draft == f"Zabrano pudełko spod stołu, a {outcome}."
    assert len(draft) < len(source) + 1
    history = _history((request, "Po zabraniu pudełka drzwi się domknęły."))
    assert (
        studio_revision(
            "Korekta: pudełko było pod ławką. Zmień tylko to i podaj jedno zdanie.",
            history,
        )
        == f"Zabrano pudełko spod ławki, a {outcome}."
    )
    assert (
        studio_revision(
            "Korekta: pudełko było na prawej ławce. Zmień tylko to i podaj jedno zdanie.",
            history,
        )
        == f"Zabrano pudełko z prawej ławki, a {outcome}."
    )
    assert (
        studio_revision(
            "Korekta: teczka była pod ławką. Zmień tylko to i podaj jedno zdanie.",
            history,
        )
        is None
    )


def test_removal_rule_does_not_convert_a_future_instruction_into_a_fact():
    assert (
        studio_revision(
            "Skróć „Po zabraniu pudełka spod stołu domknij drzwi”. Podaj jedno zdanie.",
            [],
        )
        is None
    )


def test_removal_accepts_an_independent_surface_and_material():
    source = "Po zabraniu teczki z prawej ławki część dokumentów się zmieściła"
    request = f"Skróć „{source}”. Jedna wersja."
    draft = studio_revision(request, [])
    assert draft == "Zabrano teczkę z prawej ławki, a część dokumentów się zmieściła."
    history = _history((request, draft))
    assert (
        studio_revision("Zachowaj prawą ławkę i napisz jeszcze krócej.", history)
        == "Zabrano teczkę z prawej ławki, część dokumentów się zmieściła."
    )


@pytest.mark.parametrize(
    "effect",
    [
        "skrzynia dała się otworzyć",
        "skrzynia nie dała się otworzyć",
        "skrzynia otworzyła się",
        "skrzynia nie otworzyła się",
        "nie dało się otworzyć skrzyni",
    ],
)
def test_removal_of_stool_preserves_opening_modality(effect):
    original = f"Po zabraniu stołka spod okna {effect}"
    initial = f"Skróć „{original}”. Podaj jedno zdanie."
    draft = studio_revision(initial, [])
    assert draft == f"Zabrano stołek spod okna, a {effect}."
    history = _history((initial, "Po zabraniu stołka skrzynia się otworzyła."))
    assert (
        studio_revision(
            "Korekta: stołek był pod stołem. Zmień tylko to i podaj jedno zdanie.",
            history,
        )
        == f"Zabrano stołek spod stołu, a {effect}."
    )


@pytest.mark.parametrize(
    "relation, effect",
    [
        ("z", "szafka nie dała się domknąć"),
        ("spod", "szafka dała się domknąć"),
        ("spod", "szafka domknęła się"),
    ],
)
def test_relative_correction_changes_only_direction_of_same_place(relation, effect):
    initial = (
        f"Skróć „Po zabraniu torby {relation} dolnej ławki {effect}”. Jedna wersja."
    )
    draft = studio_revision(initial, [])
    assert draft == f"Zabrano torbę {relation} dolnej ławki, a {effect}."
    history = _history((initial, "Po zabraniu torby szafka nie domknęła się."))
    assert (
        studio_revision("Korekta: była to górna ławka. Zmień tylko położenie.", history)
        == f"Zabrano torbę {relation} górnej ławki, a {effect}."
    )
    assert (
        studio_revision("Korekta: była to górna półka. Zmień tylko położenie.", history)
        is None
    )


def test_removal_preserves_explicit_preposition_when_there_is_no_correction():
    request = "Skróć „Po zabraniu pudełka ze stołu wieko się zamknęło”. Jedna wersja."
    assert (
        studio_revision(request, [])
        == "Zabrano pudełko ze stołu, a wieko się zamknęło."
    )
