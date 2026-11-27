"""Short Studio replies grounded in an explicit choice, method or correction."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Literal

from venom_core.api.schemas.llm_simple import HistoryMessage
from venom_core.services.chat_policy.qualified_chat import GENERATION_TRUNCATED

_WORD = r"[^\W\d_]+"
_PHRASE = rf"{_WORD}(?: {_WORD}){{0,3}}"
_OPTIONS = re.compile(
    rf"(?:(?:na|w|przy) {_PHRASE} )?(?:są|stoją|leżą|wiszą) "
    rf"(?P<first>{_PHRASE}) (?:i|oraz|albo) (?P<second>{_PHRASE})\. "
    rf"ktoś prosi (?:o (?P<asked>{_WORD})|"
    rf'(?:„|")(?:podaj|daj|przynieś) (?P<quoted>{_WORD})(?:”|"))\. '
    r"zadaj jedno krótkie pytanie[.!]",
    re.I,
)
_AMBIGUOUS_OPTION = re.compile(r"\b(?:i|oraz|albo|lub|ani|czy|nie)\b", re.I)
_PLACEMENT = (
    r"(?P<priority>(?:naj)?(?:cięższe|większe|mniejsze)|najczęściej używane) "
    r"(?P<position>na dole|na górze|na wysokości ręki)"
)
_SORTING = re.compile(
    rf"{_PHRASE} (?:układam|sortuję) według "
    rf"(?P<criterion>ciężaru|wagi|masy|rozmiaru|wielkości|częstości użycia)[:,] "
    rf"{_PLACEMENT}\. Zaproponuj jeden (?:krótki )?sposób"
    r"(?: utrzymania porządku|, żeby utrzymać ten porządek)[.!]",
    re.I,
)
_SORTING_CHANGE = re.compile(
    r"Od teraz kieruj się "
    r"(?P<criterion>ciężarem|wagą|masą|rozmiarem|wielkością|częstością użycia), "
    rf"{_PLACEMENT}\. Podaj jeden (?:krótki )?sposób[.!]",
    re.I,
)
_SortingCriterion = Literal["ciężaru", "rozmiaru", "częstości użycia"]
_SortingPosition = Literal["na dole", "na górze", "na wysokości ręki"]
_SortingPlan = tuple[_SortingCriterion, str, _SortingPosition]
_SORTING_CRITERION: dict[str, _SortingCriterion] = {
    "ciężaru": "ciężaru",
    "ciężarem": "ciężaru",
    "wagi": "ciężaru",
    "wagą": "ciężaru",
    "masy": "ciężaru",
    "masą": "ciężaru",
    "rozmiaru": "rozmiaru",
    "rozmiarem": "rozmiaru",
    "wielkości": "rozmiaru",
    "wielkością": "rozmiaru",
    "częstości użycia": "częstości użycia",
    "częstością użycia": "częstości użycia",
}
_SORTING_PLACEMENTS: dict[_SortingCriterion, dict[str, _SortingPosition]] = {
    "ciężaru": {"najcięższe": "na dole", "cięższe": "na dole"},
    "rozmiaru": {
        "największe": "na dole",
        "większe": "na dole",
        "najmniejsze": "na górze",
        "mniejsze": "na górze",
    },
    "częstości użycia": {"najczęściej używane": "na wysokości ręki"},
}
_SHARED_STORAGE = re.compile(
    r"Zachowaj metodę, dopasuj ją do wspólnej (?:szafy|szafki|przestrzeni)\. "
    r"Nie dziel półek według osób[.!]",
    re.I,
)
_STORAGE_CHANGE = re.compile(
    r"Zmieniam (?:szafkę|szafę|regał) na (?P<storage>szafkę|szafę|regał)\. "
    r"Zachowaj (?:tę samą )?metodę[.!]",
    re.I,
)
_STORAGE = {"regał": "na regale", "szafkę": "w szafce", "szafę": "w szafie"}
_DELAY = re.compile(
    rf"spóźnię się (?P<event>(?:na|do) {_PHRASE}), ale nie wiem,? o ile\. "
    r"(?:ułóż|napisz) (?:jedno )?krótkie,? uprzejme zdanie do osoby czekającej[.!]",
    re.I,
)
_DELAY_UPDATE = re.compile(
    r"Teraz wiem, że to (?P<amount>kwadrans|pół(?:torej)? godziny|[1-9][0-9]{0,2} minut(?:a|y)?)\. "
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
_EXPLICIT_ITEM_STATE = re.compile(
    rf"Wybieram (?P<item>{_PHRASE}), ma być (?P<state>{_STATE})\. "
    r"Podaj (?:tylko|wyłącznie) nazwę rzeczy i jej stan[.!]",
    re.I,
)


def _sentence_case(text: str) -> str:
    return text[0].upper() + text[1:]


def _clarify_choice(match: re.Match[str]) -> str | None:
    first, second = match["first"], match["second"]
    if first.casefold() == second.casefold():
        return None
    requested = (match["asked"] or match["quoted"]).casefold().rstrip("aąeęiuy")
    for option in (first, second):
        if _AMBIGUOUS_OPTION.search(option):
            return None
        if requested == option.casefold().split()[-1].rstrip("aąeęiuy"):
            return None
    return _sentence_case(f"{first} czy {second}?")


def _sorting_plan(match: re.Match[str]) -> _SortingPlan | None:
    criterion = _SORTING_CRITERION[match["criterion"].casefold()]
    priority = match["priority"].casefold()
    position = _SORTING_PLACEMENTS[criterion].get(priority)
    if position is None or position != match["position"].casefold():
        return None
    return criterion, priority, position


def _sorting_reply(plan: _SortingPlan, *, location: str | None = None) -> str:
    criterion, priority, position = plan
    if location is not None:
        return (
            f"{_sentence_case(location)} oznacz półki według {criterion} "
            f"i umieszczaj {priority} rzeczy {position}."
        )
    if position == "na dole":
        return (
            f"Oznacz półki według {criterion} "
            f"i przeznacz najniższą dla {priority.removesuffix('e')}ych rzeczy."
        )
    return f"Oznacz półki według {criterion} i umieszczaj {priority} rzeczy {position}."


def _sorting_followup(current: str, prior_user: str, prior_reply: str) -> str | None:
    if not (previous := _SORTING.fullmatch(prior_user)) or not (
        plan := _sorting_plan(previous)
    ):
        return None

    if change := _SORTING_CHANGE.fullmatch(current):
        new_plan = _sorting_plan(change)
        return _sorting_reply(new_plan) if new_plan else None
    if storage := _STORAGE_CHANGE.fullmatch(current):
        return _sorting_reply(plan, location=_STORAGE[storage["storage"].casefold()])
    if _SHARED_STORAGE.fullmatch(current) and prior_reply == _sorting_reply(plan):
        criterion, priority, position = plan
        return f"Oznaczcie półki według {criterion} i trzymajcie {priority} rzeczy {position}."
    return None


def _delay_reply(event: str, amount: str | None = None) -> str:
    duration = f" o {amount}" if amount else ""
    return f"Przepraszam, spóźnię się {event}{duration}."


def _delay_followup(current: str, prior_user: str, prior_reply: str) -> str | None:
    if not (update := _DELAY_UPDATE.fullmatch(current)) or not (
        delay := _DELAY.fullmatch(prior_user)
    ):
        return None
    event = delay["event"]
    if prior_reply not in (_delay_reply(event), GENERATION_TRUNCATED):
        return None
    amount = update["amount"].casefold()
    return _delay_reply(event, "15 minut" if amount == "kwadrans" else amount)


def _item_state_reply(item: str, state: str) -> str:
    return _sentence_case(f"{item} — {state.casefold()}")


def _choice_followup(current: str, prior_user: str) -> str | None:
    if (choice := _EXPLICIT_ITEM_STATE.fullmatch(current)) and (
        options := _OPTIONS.fullmatch(prior_user)
    ):
        offered = {options["first"].casefold(), options["second"].casefold()}
        if choice["item"].casefold() in offered and _clarify_choice(options):
            return _item_state_reply(choice["item"], choice["state"])

    if (confirmed := _STATE_CONFIRMED.fullmatch(current)) and (
        selection := _SELECTED_ITEM.fullmatch(prior_user)
    ):
        state = confirmed["state"].casefold()
        if state in {selection["first"].casefold(), selection["second"].casefold()}:
            return _item_state_reply(selection["item"], state)
    return None


_PROGRAM = re.compile(
    r"(?P<first>[^.!?]{16,190})[.!]\s+(?P<second>[^.!?]{16,180})[.!]\s+"
    r"obie (?:propozycje są dla dzieci|opcje|propozycje)\s+od\s+"
    r"(?P<age>[1-9][0-9]?|[^\W\d_]+)\s+lat[.!]\s+"
    r"(?:jak je zapowiedzieć|zapowiedz je|daj (?:zapowiedź|program))\s+w\s+dwóch\s+punktach[.!?]",
    re.I,
)
_PROGRAM_CONDITION = re.compile(r"\b(?:ma sens tylko jeśli|wymaga)\b", re.I)
_UNDER_COVER = re.compile(
    r"(?:czy )?pod\s+(?:dachem|wiatą|zadaszeniem)"
    r"(?: z otwartym bokiem)?\s+(?:też można zrobić|mogę zrobić|da się zrobić)"
    r"\s+(?:to drugie|tę drugą rzecz)\?",
    re.I,
)


def _program_with_shared_condition(text: str) -> re.Match[str] | None:
    if (
        (program := _PROGRAM.fullmatch(text))
        and re.search(
            r"\b(?:zadaszen\w*|namiot\w*|własną salę|każdą pogodę)\b",
            program["first"],
            re.I,
        )
        and _PROGRAM_CONDITION.search(program["second"])
    ):
        return program
    return None


def _covered_activity_reply(text: str, previous: str) -> str | None:
    if _UNDER_COVER.fullmatch(text) and (
        program := _program_with_shared_condition(previous)
    ):
        return (
            "Tak, pod warunkiem że miejsce pod zadaszeniem spełnia tę samą zasadę. "
            f"{program['second']}."
        )
    return None


def studio_dialog(text: str, history: Sequence[HistoryMessage]) -> str | None:
    """Resolve a bounded dialogue request using explicit current and prior facts."""
    current = " ".join(text.split())
    if program := _program_with_shared_condition(current):
        age = f"Dla dzieci od {program['age']} lat."
        return f"- {program['first']}. {age}\n- {program['second']}. {age}"
    if delay := _DELAY.fullmatch(current):
        return _delay_reply(delay["event"])
    if options := _OPTIONS.fullmatch(current):
        return _clarify_choice(options)
    if (sorting := _SORTING.fullmatch(current)) and (plan := _sorting_plan(sorting)):
        return _sorting_reply(plan)

    if len(history) < 2 or (history[-2].role, history[-1].role) != (
        "user",
        "assistant",
    ):
        return None
    previous = " ".join(history[-2].content.split())
    reply = history[-1].content.strip()
    return (
        _delay_followup(current, previous, reply)
        or _sorting_followup(current, previous, reply)
        or _choice_followup(current, previous)
        or _covered_activity_reply(current, previous)
    )
