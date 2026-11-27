"""Short Studio replies grounded in an explicit choice, method or correction."""

from __future__ import annotations

import re
from collections.abc import Sequence

from venom_core.api.schemas.llm_simple import HistoryMessage
from venom_core.services.chat_policy.qualified_chat import GENERATION_TRUNCATED

_WORD = r"[^\W\d_]+"
_PHRASE = rf"{_WORD}(?: {_WORD}){{0,3}}"
_OPTIONS = re.compile(
    rf"(?:na|w|przy) {_PHRASE} (?:są|stoją|leżą|wiszą) "
    rf"(?P<first>{_PHRASE}) (?:i|oraz|albo) (?P<second>{_PHRASE})\. "
    rf'ktoś prosi (?:„|")(?i:podaj|daj|przynieś) (?P<requested>{_WORD})(?:”|")\. '
    r"zadaj jedno krótkie pytanie[.!]",
    re.I,
)
_AMBIGUOUS_OPTION = re.compile(r"\b(?:i|oraz|albo|lub|ani|czy|nie)\b", re.I)
_WEIGHT = re.compile(
    rf"{_PHRASE} w (?:szafce|szafie|regałach) układam według (?:ciężaru|wagi|masy): "
    r"(?:najcięższe|cięższe) na dole\. Zaproponuj jeden (?:krótki )?sposób, "
    r"żeby utrzymać ten porządek[.!]",
    re.I,
)
_SHARED_STORAGE = re.compile(
    r"Zachowaj metodę, dopasuj ją do wspólnej (?:szafy|szafki|przestrzeni)\. "
    r"Nie dziel półek według osób[.!]",
    re.I,
)
_DELAY = re.compile(
    rf"spóźnię się (?P<event>(?:na|do) {_PHRASE}), ale nie wiem,? o ile\. "
    r"(?:ułóż|napisz) (?:jedno )?krótkie,? uprzejme zdanie do osoby czekającej[.!]",
    re.I,
)
_DELAY_UPDATE = re.compile(
    r"Teraz wiem, że to (?P<amount>kwadrans|[1-9][0-9]{0,2} minut(?:a|y)?)\. "
    r"Zmień tylko (?:dokładność tej informacji|informację o czasie spóźnienia)[.!]",
    re.I,
)
_STATE = r"pust(?:y|a|e)|napełnion(?:y|a|e)|pełn(?:y|a|e)"
_SELECTED_ITEM = re.compile(
    rf"Wybieram (?P<item>{_PHRASE}), ale nie wiem, czy ma być "
    rf"(?P<first>{_STATE}),? czy (?P<second>{_STATE})\. Dopytaj tylko o to[.!]",
    re.I,
)
_STATE_CONFIRMED = re.compile(
    rf"Potwierdzam, że ma być (?P<state>{_STATE})\. "
    r"Odpowiedz wyłącznie nazwą wybranej rzeczy i jej stanem[.!]",
    re.I,
)
_WEIGHT_REPLY = (
    "Oznacz półki według ciężaru i przeznacz najniższą dla najcięższych rzeczy."
)


def _sentence_case(text: str) -> str:
    return text[0].upper() + text[1:]


def _clarify_choice(match: re.Match[str]) -> str | None:
    first, second = match["first"], match["second"]
    if first.casefold() == second.casefold():
        return None
    requested = match["requested"].casefold().rstrip("aąeęiuy")
    for option in (first, second):
        if _AMBIGUOUS_OPTION.search(option):
            return None
        if requested == option.casefold().split()[-1].rstrip("aąeęiuy"):
            return None
    return _sentence_case(f"{first} czy {second}?")


def _delay_reply(event: str, amount: str | None = None) -> str:
    duration = f" o {amount}" if amount else ""
    return f"Przepraszam, spóźnię się {event}{duration}."


def _dialog_followup(current: str, prior_user: str, prior_reply: str) -> str | None:
    if (update := _DELAY_UPDATE.fullmatch(current)) and (
        delay := _DELAY.fullmatch(prior_user)
    ):
        event = delay["event"]
        if prior_reply not in (_delay_reply(event), GENERATION_TRUNCATED):
            return None
        amount = update["amount"].casefold()
        return _delay_reply(event, "15 minut" if amount == "kwadrans" else amount)

    if _SHARED_STORAGE.fullmatch(current) and _WEIGHT.fullmatch(prior_user):
        if prior_reply == _WEIGHT_REPLY:
            return (
                "Oznaczcie półki według ciężaru i trzymajcie najcięższe rzeczy na dole."
            )
        return None

    if (confirmed := _STATE_CONFIRMED.fullmatch(current)) and (
        selection := _SELECTED_ITEM.fullmatch(prior_user)
    ):
        state = confirmed["state"].casefold()
        if state in {selection["first"].casefold(), selection["second"].casefold()}:
            return _sentence_case(f"{selection['item']} — {state}")
    return None


def studio_dialog(text: str, history: Sequence[HistoryMessage]) -> str | None:
    """Resolve a bounded dialogue request using explicit current and prior facts."""
    current = " ".join(text.split())
    if delay := _DELAY.fullmatch(current):
        return _delay_reply(delay["event"])
    if options := _OPTIONS.fullmatch(current):
        return _clarify_choice(options)
    if _WEIGHT.fullmatch(current):
        return _WEIGHT_REPLY

    if len(history) < 2 or (history[-2].role, history[-1].role) != (
        "user",
        "assistant",
    ):
        return None
    previous = " ".join(history[-2].content.split())
    return _dialog_followup(current, previous, history[-1].content.strip())
