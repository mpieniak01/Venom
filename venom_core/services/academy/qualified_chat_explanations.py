"""Keep short, plain Studio explanations on the topic the user selected."""

from __future__ import annotations

import re
from collections.abc import Sequence

from venom_core.api.schemas.llm_simple import HistoryMessage
from venom_core.services.academy.qualified_chat_quote import (
    is_text_transformation,
    without_quotes,
)

_EXPLAIN = re.compile(
    r"\b(?:wyjaśnij|wytłumacz|opisz prosto|skąd się bierze|na czym polega|jak działa|dlaczego)\b",
    re.I,
)
_EXAMPLE_CHANGE = re.compile(
    r"\b(?:(?:zamiast[^.!?\n]*\b(?:użyj|podaj|weź|wybierz|pokaż)"
    r"|(?:zmień|zamień|zastąp|pokaż na innym|użyj innego))\s+"
    r"(?:innego\s+|inny\s+|nowego\s+|nowy\s+)?przykład\w*)\b",
    re.I,
)
_USER_FORMAT = re.compile(
    r"\b(?:szczegółowo|wyczerpująco|obszernie|krok po kroku|"
    r"minimum|co najmniej|w (?:\d+|jednym|dwóch|trzech|czterech|pięciu|kilku)"
    r" (?:\w+ )?(?:zdaniach|punktach|akapitach))\b",
    re.I,
)
_COMPACT = (
    "W prostym wyjaśnieniu podaj mechanizm od razu, a potem jeden przykład. "
    "Zmieść całość w najwyżej trzech krótkich zdaniach. "
    "Bez wstępu, listy i osobnego podsumowania."
)
_CHANGE_ONLY = (
    "Zachowaj zjawisko z poprzedniej prośby użytkownika. Zmień tylko przykład. "
    "Wyjaśnij to samo zjawisko od początku na nowym przykładzie. "
    "Poprzedni szkic asystenta mógł być przerwany."
)


def changes_example(text: str) -> bool:
    return not is_text_transformation(text) and bool(
        _EXAMPLE_CHANGE.search(without_quotes(text))
    )


def explanation_hint(text: str, history: Sequence[HistoryMessage]) -> str:
    visible = without_quotes(text)
    if is_text_transformation(text) or _USER_FORMAT.search(visible):
        return ""
    if changes_example(text):
        last_user = next(
            (turn.content for turn in reversed(history) if turn.role == "user"), ""
        )
        if _EXPLAIN.search(without_quotes(last_user)):
            return f"{_CHANGE_ONLY} {_COMPACT}"
    return _COMPACT if _EXPLAIN.search(visible) else ""
