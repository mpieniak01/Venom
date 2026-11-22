"""Keep short, plain Studio explanations on the topic the user selected."""

from __future__ import annotations

import re
from collections.abc import Sequence

from venom_core.api.schemas.llm_simple import HistoryMessage
from venom_core.services.chat_policy.qualified_chat_quote import (
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
    r" (?:\w+ )?(?:zdaniu|zdaniach|punktach|akapitach))\b",
    re.I,
)
_PROTECTION = re.compile(
    r"\b(?:pas\w* bezpieczeństw\w*|zabezpiecze\w*|osłon\w*|blokad\w*|kask\w*)\b",
    re.I,
)
_MATCHED_CONDITIONS = re.compile(
    r"\b(?:w tym samym|w tej samej|w takich samych|przy tej samej|przy tych samych)\b",
    re.I,
)
_MATCHED_CONDITIONS_HINT = (
    "Zachowaj wspólny warunek porównania w wyjaśnieniu i w nowym przykładzie."
)
_PROTECTION_HINT = (
    "Przy opisie zabezpieczenia nazwij, co stałoby się bez niego i dlaczego, "
    "a potem co zmienia samo zabezpieczenie. Nie przypisuj zabezpieczeniu "
    "zjawiska, któremu przeciwdziała."
)
_COMPACT = (
    "W prostym wyjaśnieniu podaj mechanizm od razu, a potem jeden przykład. "
    "Zmieść całość w najwyżej trzech krótkich zdaniach. "
    "Bez wstępu, listy i osobnego podsumowania."
)
_TIGHT_BUDGET = (
    "Dwa krótkie zdania, razem najwyżej 32 słowa. W pierwszym zdaniu podaj "
    "mechanizm, w drugim pokaż go na wymaganym przykładzie. "
    "Bez wstępu, listy i podsumowania."
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


def active_explanation_topic(history: Sequence[HistoryMessage]) -> str:
    for turn in reversed(history):
        if turn.role == "user" and not changes_example(turn.content):
            return turn.content if _EXPLAIN.search(without_quotes(turn.content)) else ""
    return ""


def explanation_hint(
    text: str, history: Sequence[HistoryMessage], *, token_budget: int | None = None
) -> str:
    visible = without_quotes(text)
    if is_text_transformation(text) or _USER_FORMAT.search(visible):
        return ""
    compact = (
        _TIGHT_BUDGET if token_budget is not None and token_budget <= 96 else _COMPACT
    )
    topic = visible
    revision = ""
    if changes_example(text):
        previous = without_quotes(active_explanation_topic(history))
        if _EXPLAIN.search(previous):
            topic = previous
            revision = _CHANGE_ONLY
    if not _EXPLAIN.search(topic):
        return ""
    protection = _PROTECTION_HINT if _PROTECTION.search(topic) else ""
    conditions = _MATCHED_CONDITIONS_HINT if _MATCHED_CONDITIONS.search(topic) else ""
    return " ".join(filter(None, (revision, compact, protection, conditions)))
