"""Keep Studio requests, observed execution and delegated roles distinct."""

from __future__ import annotations

import re
from collections.abc import Sequence

from venom_core.api.schemas.llm_simple import HistoryMessage

_REQUEST = re.compile(
    r"poprosi(?:łem|łam) o (?P<action>[\w ]{2,75})[,.;] "
    r"(?:lecz |ale )?(?:jeszcze )?nikt nie potwierdził wykonania\. "
    r"(?:podsumuj stan|zapisz (?:krótki )?status|podaj aktualny stan)\.",
    re.I,
)
_REQUEST_UPDATE = re.compile(
    r"prośba nadal obowiązuje\. (?:wiem (?:tylko|jedynie)|potwierdzam), że "
    r"(?P<phase>rozpoczęto|zakończono|nie wykonano|nadal trwa) "
    r"(?P<action>[\w ]{2,75})\. (?:zaktualizuj stan|podsumuj stan|podaj aktualny stan)\.",
    re.I,
)
_REQUEST_WITHDRAWN = re.compile(
    r"(?:prośbę wycofuję|wycofuję prośbę)\. "
    r"nie potwierdzam, czy rozpoczęt[oyąe] (?P<action>[\w ]{2,75}) dokończono\. "
    r"(?:zapisz (?:krótki )?status|podsumuj stan|podaj aktualny stan)\.",
    re.I,
)
_NAME = r"[^\W\d_]+(?:-[^\W\d_]+)?"
_PICKUP = re.compile(
    rf"(?P<item>[\w ]{{2,65}}) należy do (?P<owner>{_NAME}), "
    rf"(?P<delegate>{_NAME}) ma (?P<pronoun>ją|go) tylko odebrać "
    r"w (?P<possessive>jej|jego) imieniu\. (?:wymień|podaj) obie role\.",
    re.I,
)
_PICKUP_WITHDRAWN = re.compile(
    rf"(?P<delegate>{_NAME}) (?P<withdrawal>zrezygnował(?:a)?) z odbioru, "
    r"a (?:nikt jeszcze nie potwierdził zastępcy|nie ma potwierdzonego zastępcy)\. "
    r"powiedz, kto jest właściciel(?:ką|em) i jaki jest stan odbioru\.",
    re.I,
)
_PICKUP_REPLACED = re.compile(
    rf"{_NAME} potwierdza, że (?P<item>[\w ]{{2,65}}) odbierze (?P<delegate>{_NAME})\. "
    r"własność się nie zmienia\. podaj oba (?:nazwiska lub imiona|imiona) w rolach\.",
    re.I,
)


def _last_users(history: Sequence[HistoryMessage], count: int) -> list[str]:
    turns = history[-2 * count :]
    if [turn.role for turn in turns] != ["user", "assistant"] * count:
        return []
    return [" ".join(turn.content.split()) for turn in turns[::2]]


def _same_action(source: str, update: str) -> bool:
    # A bare action noun may refer to the immediately preceding request.
    return update.casefold() in {source.casefold(), source.split()[0].casefold()}


def _request_status(text: str, history: Sequence[HistoryMessage]) -> str | None:
    if request := _REQUEST.fullmatch(text):
        return f"Zgłoszono prośbę o {request['action']}, a wykonania nie potwierdzono."

    if (update := _REQUEST_UPDATE.fullmatch(text)) and (
        users := _last_users(history, 1)
    ):
        if (request := _REQUEST.fullmatch(users[0])) and _same_action(
            request["action"], update["action"]
        ):
            return (
                f"Prośba o {request['action']} nadal obowiązuje, "
                f"a {update['phase'].lower()} {update['action']}."
            )

    if (withdrawal := _REQUEST_WITHDRAWN.fullmatch(text)) and (
        users := _last_users(history, 2)
    ):
        request = _REQUEST.fullmatch(users[0])
        update = _REQUEST_UPDATE.fullmatch(users[1])
        if (
            request
            and update
            and update["phase"].casefold() in {"rozpoczęto", "nadal trwa"}
            and _same_action(request["action"], update["action"])
            and _same_action(request["action"], withdrawal["action"])
        ):
            return (
                f"Prośbę o {request['action']} wycofano. "
                f"Rozpoczęto {update['action']}, ale nie potwierdzono dokończenia."
            )
    return None


def _same_pickup_item(source: str, update: str) -> bool:
    source = source.casefold()
    forms = {source}
    if source.endswith("a") and " " not in source:
        forms.add(source[:-1] + "ę")
    return update.casefold() in forms


def _pickup_withdrawal(source: str, correction: re.Match[str]) -> re.Match[str] | None:
    pickup = _PICKUP.fullmatch(source)
    if pickup and pickup["delegate"].casefold() == correction["delegate"].casefold():
        return pickup
    return None


def _pickup_status(text: str, history: Sequence[HistoryMessage]) -> str | None:
    if pickup := _PICKUP.fullmatch(text):
        return (
            f"{pickup['item']} należy do {pickup['owner']}, a {pickup['delegate']} "
            f"ma {pickup['pronoun']} odebrać w {pickup['possessive']} imieniu."
        )

    if (withdrawal := _PICKUP_WITHDRAWN.fullmatch(text)) and (
        users := _last_users(history, 1)
    ):
        if pickup := _pickup_withdrawal(users[0], withdrawal):
            return (
                f"{pickup['item']} należy do {pickup['owner']}. {pickup['delegate']} "
                f"{withdrawal['withdrawal'].lower()} z odbioru, "
                "a zastępcy jeszcze nie potwierdzono."
            )

    if (replacement := _PICKUP_REPLACED.fullmatch(text)) and (
        users := _last_users(history, 2)
    ):
        if (withdrawal := _PICKUP_WITHDRAWN.fullmatch(users[1])) and (
            pickup := _pickup_withdrawal(users[0], withdrawal)
        ):
            if _same_pickup_item(pickup["item"], replacement["item"]):
                return (
                    f"{pickup['item']} nadal należy do {pickup['owner']}, "
                    f"a {replacement['delegate']} ma {pickup['pronoun']} odebrać."
                )
    return None


def studio_status(text: str, history: Sequence[HistoryMessage]) -> str | None:
    """Report explicit user evidence without inferring execution from intent."""
    return _request_status(text, history) or _pickup_status(text, history)
