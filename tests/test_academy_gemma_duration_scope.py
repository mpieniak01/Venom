import pytest

from venom_core.api.schemas.llm_simple import HistoryMessage
from venom_core.services.chat_policy.studio_followup import studio_followup

_START = (
    "Pierwsze dwa opisy poprawiano przez 12 minut. "
    "Trzecia korekta trwała 5 minut. Jaka jest suma?"
)
_QUESTION = "Czy 12 min dotyczy obu korekt łącznie, czy każdej z osobna?"
_PENDING = (
    "Trzecia korekta trwała jednak 8 minut. Zakresu 12 minut nadal nie podałam. "
    "Czy da się podać jedną sumę?"
)


def _history(*messages):
    return [
        entry
        for text in messages
        for entry in (
            HistoryMessage(role="user", content=text),
            HistoryMessage(role="assistant", content="Niezweryfikowana suma 17 min."),
        )
    ]


@pytest.mark.parametrize(
    ("correction", "expected"),
    [
        (_PENDING, _QUESTION),
        (
            "Nadal nie wiadomo, czy 12 minut dotyczy obu łącznie, czy każdej z osobna. "
            "Korekta trzeciej trwała 4 min. Czy można podać sumę?",
            _QUESTION,
        ),
        (
            "12 minut to łączny czas obu korekt, a trzecia jednak trwała 7 minut. Podaj sumę.",
            "19 min",
        ),
        (
            "Poprawiam: trzecia trwała 6 minut. Te 12 minut było na każdą z dwóch pierwszych. "
            "Podaj wynik z jednostką.",
            "30 min",
        ),
        (
            "Trzecia korekta trwała 0 minut. 12 minut to łączny czas obu. Podaj sumę.",
            "12 min",
        ),
        (
            "Trzecia korekta trwała jednak 8 minut. Zakresu 11 minut nadal nie podałam. "
            "Czy da się podać jedną sumę?",
            None,
        ),
        (
            "Spotkanie trwało 8 minut. Zakresu 12 minut nadal nie podałam. "
            "Czy da się podać jedną sumę?",
            None,
        ),
        (
            "Trzecia korekta trwała 8 minut. 12 minut to czas późniejszego odczytu. Podaj sumę.",
            None,
        ),
        (
            "Trzecia trwała 8 minut. 12 minut to łączny czas obu. Odpowiedz na inny temat.",
            None,
        ),
    ],
)
def test_duration_scope_tracks_independent_component_and_scope(correction, expected):
    assert studio_followup(correction, _history(_START)) == expected


def test_later_confirmation_uses_component_revision_with_missing_scope():
    confirm = "Potwierdzam: 12 minut to łączny czas dwóch pierwszych. Zsumuj z poprawionym czasem trzeciej."
    assert studio_followup(confirm, _history(_START, _PENDING)) == "20 min"


def test_component_revision_does_not_infer_unknown_group_or_override_explicit_scope():
    assert studio_followup(_PENDING, _history("Sporządzono opis w pracowni.")) is None
    first = _START.replace("przez 12", "przez łącznie 12")
    assert studio_followup(_PENDING, _history(first)) is None
