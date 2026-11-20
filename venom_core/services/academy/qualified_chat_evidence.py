"""Qualified advice from current, user-provided observations and verified cards."""

from __future__ import annotations

import re
from collections.abc import Sequence

from venom_core.api.schemas.llm_simple import HistoryMessage
from venom_core.services.academy.qualified_chat_irrigation import irrigation_reply
from venom_core.services.academy.qualified_chat_quote import (
    wants_rewrite,
    without_quotes,
)
from venom_core.services.academy.qualified_chat_sources import card_link, read_card

NOUNS = {"butelk": "butelki", "słoik": "słoika", "szklan": "szklanki"}
_SENTENCE = re.compile(r"(?<=[.!?;])\s+")
_PHYSICAL = re.compile(r"\b(?:wyjaśnij|opisz|dlaczego|czemu|skąd|czego)\b", re.I)
_FORM = re.compile(r"\b(?:dwa|dwóch|2)\s+(?:krótkie\s+)?zdani", re.I)
_BEGIN = re.compile(r"\b(?:powst|pojaw|skąd zebr)\w*", re.I)
_END = re.compile(r"\b(?:znik|parowan|odpar|wypar)\w*", re.I)
_WARM = re.compile(r"ogrz|nagrz|ogrzew", re.I)
_PAST_WARM = re.compile(r"ogrz(?:ał|ano|ana|ana)|nagrz(?:ał|ano|ana)", re.I)
_HYP = re.compile(
    r"\b(?:jeśli|jeżeli|gdyby|co by|gdy się)\b|\b(?:może|mogą)\s+wypar", re.I
)
_RETRACT = re.compile(
    r"nie (?:wiadomo|wiem|ma potwierdzenia|potwierdz|ustal|odnotow)|brak (?:pomiaru|potwierdzenia|danych)|cofam",
    re.I,
)
_COLD = re.compile(r"chłod|zimn|(?:z|po wyjęciu z) lodówk", re.I)
_SURFACE = re.compile(r"ścianc|ściank|powierzchni|zewnętrzn", re.I)
_DROP = re.compile(r"\bkropl\w*|\bros[ayę]\b", re.I)
_NEG_DROP = re.compile(
    r"nie (?:było|ma|widzia\w*)\s+(?:żadnych\s+)?(?:kropel|kropli)", re.I
)
_NEW_INSTANCE = re.compile(
    r"\b(?:drug|inn|now|kolejn)\w*\s+(?:słoik|butelk|szklan)\w*", re.I
)
_CORE = re.compile(r"kropl|ros[ayę]", re.I)
_NEG_COLD = re.compile(
    r"(?:nie był\w*|nie było|niepotwierdzon\w*)\s+(?:zimn|chłod)", re.I
)
_LEAK = re.compile(r"\b(?:przecieka|wyciek)\w*", re.I)
_NO_LEAK = re.compile(r"nie (?:przecieka|ma wyciek)|bez wyciek", re.I)
_PREVENT = re.compile(r"zapobie|ogranicz|zmniejsz|unik", re.I)
_ANAPHORA = re.compile(r"\bto\s+(?:tuż\s+)?przed|\btego\s+(?:tuż\s+)?przed", re.I)
_TOPIC_CHANGE = re.compile(
    r"\b(?:zmieniam temat|inny temat|przejdźmy do|teraz mowa o)\b", re.I
)
_BATH = re.compile(
    r"\bprzed\s+(?:(?:wejściem|rozpoczęciem)\s+(?:pod\s+)?)?prysznic", re.I
)
_FAN = re.compile(r"wyciąg|wentylator|odciąg|wentylac", re.I)
_NEG_FAN = re.compile(
    r"\b(?:nie\s+(?:dział|mam|ma|mogę|sprawn)|nieczynn|niesprawn|uszkodz|wyłączon|niedostępn|brak (?:sprawnego )?(?:wyciąg|wentylator|odciąg|wentylac))\w*",
    re.I,
)
_POS_FAN = re.compile(r"działa|sprawny|sprawna|dostępny|dostępna", re.I)


def _normalized(text: str) -> str:
    return " ".join(without_quotes(text).casefold().split())


def _objects(text: str) -> set[str]:
    return {noun for key, noun in NOUNS.items() if key in text}


def _water_facts(
    users: Sequence[str], text: str
) -> tuple[str | None, tuple[str, str] | None]:
    cold = None
    heat = None
    current_objects: set[str] = set()
    for message in users:
        for clause in _SENTENCE.split(message):
            if clause.endswith("?"):
                continue
            names = _objects(clause)
            if names:
                current_objects = names
            leak = bool(
                _LEAK.search(clause)
                and not _NO_LEAK.search(clause)
                and not _HYP.search(clause)
            )
            new_instance = bool(_NEW_INSTANCE.search(clause))
            revoked = bool(
                _NEG_COLD.search(clause)
                or _NEG_DROP.search(clause)
                or (
                    _RETRACT.search(clause)
                    and _COLD.search(clause)
                    and _SURFACE.search(clause)
                )
            )
            if revoked or (leak and current_objects) or new_instance:
                cold = heat = None
            elif (
                len(current_objects) == 1
                and _COLD.search(clause)
                and _SURFACE.search(clause)
                and _DROP.search(clause)
                and not leak
                and not _HYP.search(clause)
            ):
                cold = next(iter(current_objects))
            if not _WARM.search(clause):
                continue
            if _RETRACT.search(clause) or re.search(r"\bnie (?:ogrza|nagrza)", clause):
                heat = None
            elif len(current_objects) == 1 and _HYP.search(clause):
                heat = next(iter(current_objects)), "conditional"
            elif (
                len(current_objects) == 1
                and _PAST_WARM.search(clause)
                and _DROP.search(clause)
                and _END.search(clause)
            ):
                heat = next(iter(current_objects)), "actual"
    target = _objects(text) or current_objects
    return (
        (cold, heat) if cold and target == current_objects == {cold} else (None, None)
    )


def _fan_state(users: Sequence[str]) -> str:
    state = "unknown"
    last_explicit_fan = False
    for row in users:
        for sentence in _SENTENCE.split(row):
            mentions_fan = bool(_FAN.search(sentence))
            related_uncertainty = (
                last_explicit_fan
                and _RETRACT.search(sentence)
                and re.search(
                    r"\bczy (?:został[ao]? naprawion|jest sprawn|działa)", sentence
                )
            )
            last_explicit_fan = mentions_fan
            if _HYP.search(sentence) or (
                sentence.endswith("?") and not _RETRACT.search(sentence)
            ):
                continue
            if not mentions_fan and not related_uncertainty:
                continue
            clauses = re.split(r",\s*(?:ale|lecz)\s+(?=(?:teraz|obecnie)\b)", sentence)
            for clause in clauses:
                if _RETRACT.search(clause):
                    state = "unknown"
                elif _NEG_FAN.search(clause):
                    state = "unavailable"
                elif _POS_FAN.search(clause):
                    state = "available"
    return state


def _active_topic(users: Sequence[str]) -> list[str]:
    recent = []
    for message in users:
        fragments = _TOPIC_CHANGE.split(message)
        if len(fragments) > 1:
            recent = []
        recent.append(fragments[-1])
    return recent


def _bathroom_evidence(text: str, users: Sequence[str]) -> bool:
    def mirror_fog(value: str) -> bool:
        for sentence in _SENTENCE.split(value):
            if re.search(r"\blustr\w*(?: \w+){0,6} (?:paruj|zapar|zachodz)", sentence):
                return True
            if re.search(
                r"\b(?:parowanie|zaparowani\w*|parowaniu) (?:łazienkowego )?lustr",
                sentence,
            ):
                return True
        return False

    return mirror_fog(text) or (
        bool(_ANAPHORA.search(text)) and any(mirror_fog(message) for message in users)
    )


def _condensation_reply(text: str, users: Sequence[str]) -> str | None:
    first, last = _BEGIN.search(text), _END.search(text)
    if not (
        first
        and last
        and _PHYSICAL.search(text)
        and _FORM.search(text)
        and _CORE.search(text)
    ):
        return None
    cold, heat = _water_facts(users, text)
    if not cold:
        return "Na jakiej powierzchni pojawiły się krople i czy była chłodna?"
    if not heat or heat[0] != cold:
        return "Czy naczynie ogrzało się, zanim krople zniknęły?"
    condensation = f"Para wodna z powietrza skrapla się na chłodnej ściance {cold}."
    verb = "mogą wyparować" if heat[1] == "conditional" else "wyparowały"
    evaporation = f"Po ogrzaniu {cold} istniejące krople {verb}."
    if last.start() < first.start():
        return f"{evaporation} {condensation}"
    return f"{condensation} {evaporation}"


def _ventilation_reply(text: str, users: Sequence[str]) -> str | None:
    if not (
        _PREVENT.search(text) and _BATH.search(text) and _bathroom_evidence(text, users)
    ):
        return None
    card = read_card("ventilation")
    if card is None:
        return "Czy możesz podać wiarygodne źródło dotyczące ograniczania parowania lustra?"
    state = _fan_state([*users, text])
    if state == "unavailable":
        answer = "Do ograniczenia wilgoci potrzebujesz dostępnej wentylacji. Ściereczka usuwa już powstałe krople."
    else:
        action = "włącz wyciąg tuż przed prysznicem i zostaw go włączony w trakcie, żeby ograniczyć wilgoć przy lustrze."
        answer = (
            f"Jeśli wyciąg działa, {action}"
            if state == "unknown"
            else action.capitalize()
        )
    return f"{answer} {card_link(card, 'Poradnik EPA')}"


def evidence_reply(question: str, history: Sequence[HistoryMessage]) -> str | None:
    if wants_rewrite(question):
        return None
    text = _normalized(question)
    users = _active_topic(
        [_normalized(turn.content) for turn in history if turn.role == "user"]
    )
    if _TOPIC_CHANGE.search(text):
        users = []
    return (
        _condensation_reply(text, users)
        or _ventilation_reply(text, users)
        or irrigation_reply(text, users)
    )
