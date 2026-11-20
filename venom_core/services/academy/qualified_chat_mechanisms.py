"""Resolve required facts before publishing a supported Studio explanation."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from venom_core.api.schemas.llm_simple import HistoryMessage
from venom_core.services.academy.qualified_chat_explanations import (
    active_explanation_topic,
    changes_example,
    explanation_hint,
)
from venom_core.services.academy.qualified_chat_quote import without_quotes

_OTHER_TASK = re.compile(
    r"\b(?:zacytuj|przetłumacz|streść|sprawdź|zweryfikuj|oblicz|"
    r"źródł\w*|cytat\w*|internet\w*|szczegółow\w*|a potem|"
    r"dołącz|dopisz|dodatkowo|podaj (?:także|również)|wprost z karty|w języku|po (?:angielsku|niemiecku|francusku))\b"
)
_EXAMPLE_REQUEST = re.compile(
    r"\b(?:użyj (?:innego )?przykład\w*|podaj przykład\w*|weź przykład\w*|"
    r"pokaż (?:to )?na (?:innym )?przykładzie|"
    r"(?:zmień|zamień|zastąp) przykład\w*)\b"
)
_EXAMPLE_TAIL = re.compile(r"[^.!?]*")
_REPLACEMENT = re.compile(r"\b(?:na|przykładem)\b")
_NO_TOPIC_CHANGE = re.compile(r"\bbez zmiany (?:wyjaśnienia|mechanizmu|tematu)\b")
_NEGATION = re.compile(r"\b(?:bez|nie|zamiast)\b")
_THERMAL_TOPIC = re.compile(r"\b(?:chłodniejsz|zimniejsz)\w*")
_HOT_OR_OTHER = re.compile(
    r"\b(?:gorąc|rozgrzan|podgrzan|z piekarnik|mr[oó][zź]|w rękawic|"
    r"na zewnątrz|nie mają tej samej|różną temperatur)\w*"
)
_MATERIALS = {
    "drewno": (re.compile(r"\bdrewn\w*"), "drewnian"),
    "plastik": (re.compile(r"\bplastik\w*"), "plastikow"),
}
_THERMAL_EXAMPLES = (
    (re.compile(r"\bklam[ck]\w*"), "klamka", "a"),
    (re.compile(r"\bkrzes[łl]\w*"), "krzesło", "e"),
    (re.compile(r"\błyż[kc]\w*"), "łyżka", "a"),
    (re.compile(r"\bporęcz\w*"), "poręcz", "a"),
    (re.compile(r"\bblat\w*"), "blat", "y"),
)
_BELT = re.compile(r"\bpas(?:y|a|ów|em|ami)? bezpieczeństw\w*")
_BRAKING = re.compile(r"\b(?:hamuj|hamowa|zwalni|zatrzym)\w*")
_VEHICLES = (
    (re.compile(r"\b(?:samoch[oó]d\w*|aucie|auto|auta|autem|autu)\b"), "samochodu"),
    (re.compile(r"\bautobus\w*"), "autobusu"),
    (re.compile(r"\bautokar\w*"), "autokaru"),
    (re.compile(r"\bmikrobus\w*"), "mikrobusu"),
    (re.compile(r"\bbus\w*"), "busa"),
)
_CAR_VARIANT = re.compile(r"\b(?:dostawcz|ciężarow|terenow|wyścigow)\w*")
_APPEARANCE = re.compile(r"\b(?:wydaje|wygląda|pozorn)\w*")
_BENDING = re.compile(r"\b(?:zgięt|złaman|zakrzyw|przesunięt)\w*")
_WATER = re.compile(r"\bwod(?:a|y|ę|ą|zie)\b")
_OTHER_MEDIUM = re.compile(
    r"\b(?:olej|mlek|ciecz inna|na sucho|bez wody|pust\w+ "
    r"(?:słoik|szklan|misk)|gorąc\w+ wod)\w*"
)
_OPTICAL_OBJECTS = (
    (re.compile(r"\błyżecz[kc]\w*"), "łyżeczka", "zgięta"),
    (re.compile(r"\bsłom[ck]\w*"), "słomka", "zgięta"),
    (re.compile(r"\boł[oó]w(?:e?k|c)\w*"), "ołówek", "zgięty"),
    (re.compile(r"\b(?:patycz[kc]|patyk)\w*"), "patyczek", "zgięty"),
)
_VESSELS = (
    (re.compile(r"\bsłoik\w*"), "w słoiku"),
    (re.compile(r"\bszklan[ck]\w*"), "w szklance"),
    (re.compile(r"\bmis[ck]\w*"), "w misce"),
    (re.compile(r"\bkub[kc]\w*"), "w kubku"),
)


@dataclass(frozen=True)
class CheckedExplanation:
    mechanism: str
    example: str

    def text(self) -> str:
        return f"{self.mechanism} {self.example}"


def _visible(text: str) -> str:
    return " ".join(without_quotes(text).casefold().split())


def _requested_example(text: str) -> str:
    matches = list(_EXAMPLE_REQUEST.finditer(text))
    if not matches:
        return text
    request = matches[-1]
    tail = _EXAMPLE_TAIL.match(text, request.end())
    if tail is None:
        return ""
    example = _NO_TOPIC_CHANGE.sub("", tail[0])
    if request[0].startswith(("zmień", "zamień", "zastąp")):
        if replace := _REPLACEMENT.search(example):
            example = example[replace.end() :]
    return example.strip()


def _thermal(topic: str, example: str) -> CheckedExplanation | None:
    if (
        not _THERMAL_TOPIC.search(topic)
        or not re.search(r"\bmetal\w*", topic)
        or _HOT_OR_OTHER.search(f"{topic} {example}")
    ):
        return None
    objects = [
        (name, gender)
        for pattern, name, gender in _THERMAL_EXAMPLES
        if pattern.search(example)
    ]
    materials = [
        adjective
        for pattern, adjective in _MATERIALS.values()
        if pattern.search(example)
    ]
    if not materials:
        materials = [
            adjective
            for pattern, adjective in _MATERIALS.values()
            if pattern.search(topic)
        ]
    if len(objects) != 1 or len(materials) != 1:
        return None
    noun, gender = objects[0]
    return CheckedExplanation(
        "Gdy oba przedmioty mają tę samą temperaturę niższą od temperatury dłoni, metal szybciej odbiera jej ciepło.",
        f"Dlatego metalow{gender} {noun} wydaje się wtedy chłodniejsz{gender} niż {materials[0]}{gender}.",
    )


def _braking(topic: str, example: str) -> CheckedExplanation | None:
    if not (_BELT.search(topic) and _BRAKING.search(topic)):
        return None
    vehicles = [name for pattern, name in _VEHICLES if pattern.search(example)]
    if len(vehicles) != 1 or _CAR_VARIANT.search(example):
        return None
    vehicle = vehicles[0]
    if vehicle == "samochodu" and re.search(r"\bosobow\w*", example):
        vehicle = "samochodu osobowego"
    return CheckedExplanation(
        f"Podczas hamowania {vehicle} ciało pasażera z powodu bezwładności nadal porusza się do przodu.",
        "Pas bezpieczeństwa ogranicza ten ruch, przytrzymując pasażera na siedzeniu.",
    )


def _refraction(topic: str, example: str) -> CheckedExplanation | None:
    if not (
        _WATER.search(topic) and _APPEARANCE.search(topic) and _BENDING.search(topic)
    ) or _OTHER_MEDIUM.search(f"{topic} {example}"):
        return None
    objects = [
        (name, adjective)
        for pattern, name, adjective in _OPTICAL_OBJECTS
        if pattern.search(example)
    ]
    places = [name for pattern, name in _VESSELS if pattern.search(example)]
    if len(objects) != 1 or len(places) != 1:
        return None
    noun, adjective = objects[0]
    return CheckedExplanation(
        "Światło zmienia kierunek na granicy wody i powietrza, więc zanurzona część przedmiotu wygląda na przesuniętą.",
        f"Dlatego {noun} {places[0]} z wodą wydaje się {adjective} przy powierzchni wody.",
    )


def checked_explanation(
    question: str,
    history: Sequence[HistoryMessage],
    *,
    token_budget: int | None = None,
) -> CheckedExplanation | None:
    if token_budget is not None and token_budget < 96:
        return None
    if not explanation_hint(question, history, token_budget=token_budget):
        return None

    visible = _visible(question)
    if _OTHER_TASK.search(visible):
        return None
    topic = visible
    example = _requested_example(visible)
    if changes_example(question):
        topic = _visible(active_explanation_topic(history))
        if _OTHER_TASK.search(topic) or (
            example == visible and _NEGATION.search(visible)
        ):
            return None
    if (
        not example
        or _NEGATION.search(example)
        or re.match(r"\bzamiast metal", visible)
    ):
        return None

    return (
        _thermal(topic, example)
        or _braking(topic, example)
        or _refraction(topic, example)
    )
