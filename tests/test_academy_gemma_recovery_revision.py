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
