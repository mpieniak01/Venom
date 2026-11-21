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
_MELTING_PAIR = re.compile(
    r"\b(?:kostk\w+ lodu|lód) topi się szybciej na (?P<fast>\w+)(?: płytce| podłożu)? "
    r"niż na (?P<slow>\w+)\b"
)
_MELTING_COMPARE = re.compile(
    r"\b(?:lód|kostk\w+ lodu)\b[^.!?]*\b(?:topi się|stopi się)\b"
    r"[^.!?]*\bszybciej\b[^.!?]*\b(?:czy|niż)\b"
)
_EQUAL_CONDITIONS = re.compile(
    r"\b(?:w identycznych warunkach|w takich samych warunkach|"
    r"przy (?:tej samej|jednakowej) temperaturze (?:obu )?podłoży)\b"
)
_UNEQUAL_CONDITIONS = re.compile(
    r"\b(?:różn\w* temperatur\w*|nie znam\w* temperatur\w*|"
    r"nie wiadomo[^.!?]*temperatur\w*|niekoniecznie|nie identyczn\w*)\b"
)
_MELTING_SHORTEN = re.compile(
    r"^skróć (?:to|wyjaśnienie|odpowiedź) do jednego zdania"
    r"(?: i zachowaj (?:kierunek przepływu ciepła|przyczynę))?[.!?]*$"
)
_MELTING_FORMAT = re.compile(r"\bw dwóch zdaniach\b")
_CONDUCTIVE_SURFACES = {
    "aluminium": "aluminium",
    "aluminiowej": "aluminium",
    "miedzi": "miedzi",
    "miedzianej": "miedzi",
    "stali": "stali",
    "stalowej": "stali",
}
_INSULATING_SURFACES = {
    "korku": "korku",
    "drewnie": "drewna",
    "filcu": "filcu",
}
_HOT_BASE_TO_ICE = (
    "Jeśli oba podłoża są cieplejsze od lodu, ciepło płynie z podłoża do lodu"
)
_UNKNOWN_MELTING = (
    "Podaj temperatury obu podłoży i warunki kontaktu. Ciepło płynie od "
    "cieplejszego ciała do chłodniejszego, a sam materiał nie rozstrzyga tempa topnienia."
)
_HEAT_TOPIC = re.compile(
    r"\b(?:kierun\w* przepływu ciepła|(?:oddaj|przekazuj)\w* ciepł\w*|"
    r"(?:przepływ|płynie)\w* ciepł\w*|ciepło (?:przepływa|płynie))\b"
)
_HEAT_DATA_REQUEST = (
    r"(?:brakującą temperaturę|brakującą daną|brakujące dane|"
    r"(?:czego|jakiej danej|jakich danych) brakuje|"
    r"jaka dana jest potrzebna|jakie dane są potrzebne|(?:jaką daną|jakie dane) trzeba znać)"
    r"(?: do (?:ustalenia|określenia|wyznaczenia) kierunku(?: przepływu(?: ciepła)?)?)?"
    r"(?: (?:i|oraz) (?:ogólną )?regułę przepływu ciepła)?"
)
_HEAT_RESUME = re.compile(
    r"(?:skróć(?: wyjaśnienie| odpowiedź| to)? do jednego zdania"
    rf"(?:(?: i |[.!?] )(?:(?:powiedz|napisz|wskaż|podaj),? {_HEAT_DATA_REQUEST}|"
    r"zachowaj (?:regułę|kierunek) przepływu ciepła))?"
    r"|w jednym (?:krótkim )?zdaniu (?:wyjaśnij|wskaż|podaj) "
    rf"(?:kierunek przepływu ciepła|{_HEAT_DATA_REQUEST}))"
    r"(?:[.!?] (?:bez wyszukiwania|nie wyszukuj))?"
)
_HEAT_SETUP = re.compile(
    r"^(?:(?:przyjmij|załóż(?:my)?)(?: teraz)?,? że|"
    r"(?:korekta|zmiana(?: warunku)?|zmień warunek):|teraz|"
    r"(?:przed|po) (?:bezpośrednim )?(?:zetknięciem|kontaktem))\s+"
)
_HEAT_OBJECT = r"[^\W\d_][\w-]*(?: [^\W\d_][\w-]*){0,4}"
_HEAT_CELSIUS = r"[+-]?\d{1,3}(?:[.,]\d{1,2})?\s*°\s*c"
_MELTING_TEMPERATURE = re.compile(
    r"\d\s*(?:°(?:\s*[cf]\b)?|[kc]\b|stopni\w*|kelwin\w*)|"
    r"\b(?:poniżej|powyżej) zera\b"
)
_ADJECTIVE_ENDING = re.compile(r"(?:ego|emu|ymi|imi|ych|ich|ej|ym|im|[aąeęiy])$")
_HEAT_PAIR = re.compile(
    rf"(?P<first>{_HEAT_OBJECT}) ma (?:jednak )?(?P<first_c>{_HEAT_CELSIUS})"
    rf",? (?:a|i|natomiast) (?P<second>{_HEAT_OBJECT}) (?:ma )?(?:jednak )?"
    rf"(?P<second_c>{_HEAT_CELSIUS})"
)
_HEAT_CONTACT_PAIR = re.compile(
    rf"(?:połóż(?:my)?|umieść(?:my)?) (?P<first>{_HEAT_OBJECT}) "
    rf"w temperaturze {_HEAT_CELSIUS} na (?:kawałku|fragmencie|powierzchni) "
    rf"(?P<second>{_HEAT_OBJECT}) (?:o|w) temperaturze {_HEAT_CELSIUS}"
)
_HEAT_ONE_KNOWN = re.compile(
    rf"(?:znam(?:y)?|mam(?:y)?|podano) (?:tylko|jedynie) temperaturę (?P<known>{_HEAT_OBJECT})"
)
_HEAT_ONE_UNKNOWN = re.compile(
    rf"(?:nie znam(?:y)?(?: już)?|nie podano|brakuje) temperatury (?P<unknown>{_HEAT_OBJECT})"
)
_HEAT_RULE = "ciepło płynie od ciała cieplejszego do chłodniejszego"
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
_OTHER_MEDIUM = re.compile(r"\b(?:olej|mlek|ciecz inna|gorąc\w+ wod)\w*")
_NO_WATER = re.compile(
    r"\b(?:na sucho|bez wody|pust\w+ (?:słoik|szklan|mis[ck]|kubk|kubec)\w*)\b"
)
_BENT_MASCULINE = "zgięty"
_OPTICAL_OBJECTS = (
    (re.compile(r"\błyżecz[kc]\w*"), "łyżeczka", "zgięta"),
    (re.compile(r"\bsłom[ck]\w*"), "słomka", "zgięta"),
    (re.compile(r"\boł[oó]w(?:e?k|c)\w*"), "ołówek", _BENT_MASCULINE),
    (re.compile(r"\bpatycz(?:e?k|c)\w*"), "patyczek", _BENT_MASCULINE),
    (re.compile(r"\bpatyk\w*"), "patyk", _BENT_MASCULINE),
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


def ice_melting_reply(
    text: str,
    history: Sequence[HistoryMessage],
    *,
    token_budget: int | None = None,
) -> str | None:
    """Resolve a short ice-melting comparison from the user's thermal premise."""
    if token_budget is not None and token_budget < 96:
        return None

    visible = _visible(text)
    shorten = bool(_MELTING_SHORTEN.fullmatch(visible))
    topic = _visible(active_explanation_topic(history)) if shorten else visible
    if not topic or _OTHER_TASK.search(topic) or _MELTING_TEMPERATURE.search(topic):
        return None
    pair = _MELTING_PAIR.search(topic)
    if _UNEQUAL_CONDITIONS.search(topic) and (pair or _MELTING_COMPARE.search(topic)):
        return None if shorten else _UNKNOWN_MELTING
    if (
        not pair
        or not _EQUAL_CONDITIONS.search(topic)
        or not _MELTING_FORMAT.search(topic)
    ):
        return None
    metal = _CONDUCTIVE_SURFACES.get(pair["fast"])
    insulation = _INSULATING_SURFACES.get(pair["slow"])
    if not metal or not insulation:
        return None
    if shorten:
        return f"{_HOT_BASE_TO_ICE}, a większa przewodność {metal} przyspiesza ten przepływ."
    return (
        f"{_HOT_BASE_TO_ICE}. Większa przewodność {metal} względem "
        f"{insulation} przyspiesza ten przepływ i topnienie lodu."
    )


def _heat_premise(text: str) -> str:
    first_statement = re.split(r"[.!?](?=\s|$)", text, maxsplit=1)[0]
    return _HEAT_SETUP.sub("", first_statement)


def _same_heat_object(label: str, reference: str) -> bool:
    *label_modifiers, label_noun = label.split()
    *reference_modifiers, reference_noun = reference.split()
    label_stems = {_ADJECTIVE_ENDING.sub("", word) for word in label_modifiers}
    reference_stems = {_ADJECTIVE_ENDING.sub("", word) for word in reference_modifiers}
    if not reference_stems <= label_stems:
        return False
    noun = label_noun.replace("ó", "o")
    mentioned = reference_noun.replace("ó", "o")
    return (
        noun == mentioned
        or mentioned in {noun + "a", noun + "u"}
        or (noun.endswith("ek") and mentioned in {noun[:-2] + "ka", noun[:-2] + "ku"})
        or (
            len(noun) > 3
            and noun[-1] in "aoe"
            and mentioned in {noun[:-1] + "i", noun[:-1] + "y", noun[:-1] + "a"}
        )
    )


def _heat_followup_inputs(
    text: str, history: Sequence[HistoryMessage]
) -> tuple[str, str, re.Match[str], re.Match[str] | None] | None:
    visible = _visible(text)
    statements = re.split(r"[.!?](?=\s|$)", visible, maxsplit=1)
    if len(statements) != 2 or not _HEAT_RESUME.fullmatch(
        statements[1].strip().rstrip(".!?")
    ):
        return None
    previous = next(
        (_visible(turn.content) for turn in reversed(history) if turn.role == "user"),
        "",
    )
    if not _HEAT_TOPIC.search(previous):
        return None
    previous_premise = _heat_premise(previous)
    contact_pair = _HEAT_CONTACT_PAIR.fullmatch(previous_premise)
    earlier = contact_pair or _HEAT_PAIR.fullmatch(previous_premise)
    if not earlier:
        return None
    return visible, _heat_premise(visible), earlier, contact_pair


def _changed_heat_pair(changed: re.Match[str], earlier: re.Match[str]) -> str | None:
    labels = {earlier["first"], earlier["second"]}
    if len(labels) != 2 or labels != {changed["first"], changed["second"]}:
        return None
    first = float(changed["first_c"].split("°", 1)[0].replace(",", "."))
    second = float(changed["second_c"].split("°", 1)[0].replace(",", "."))
    if first == second:
        return (
            "Przy jednakowych temperaturach nie ma przepływu ciepła netto, "
            f"a przy ich różnicy {_HEAT_RULE}."
        )
    warmer, cooler = changed["first"], changed["second"]
    if first < second:
        warmer, cooler = cooler, warmer
    return f"{_HEAT_RULE.capitalize()}, więc oddaje je {warmer}, a przyjmuje {cooler}."


def _known_heat_followup(
    premise: str, earlier: re.Match[str], contact_pair: re.Match[str] | None
) -> str | None:
    known = _HEAT_ONE_KNOWN.fullmatch(premise)
    if not known:
        return None
    remaining = [
        key
        for key in ("first", "second")
        if not _same_heat_object(earlier[key], known["known"])
    ]
    if len(remaining) != 1:
        return None
    missing_key = remaining[0]
    label = earlier[missing_key]
    if contact_pair:
        if missing_key == "first":
            label = f"ciała położonego na podłożu ({label})"
        return f"Brakuje temperatury {label}, ponieważ {_HEAT_RULE}."
    return f"Brakuje informacji, jaką temperaturę ma {label}, ponieważ {_HEAT_RULE}."


def _unknown_heat_followup(premise: str, earlier: re.Match[str]) -> str | None:
    missing = _HEAT_ONE_UNKNOWN.fullmatch(premise)
    if not missing:
        return None
    matches = sum(
        _same_heat_object(earlier[key], missing["unknown"])
        for key in ("first", "second")
    )
    return (
        f"Brakuje temperatury {missing['unknown']}, ponieważ {_HEAT_RULE}."
        if matches == 1
        else None
    )


def thermal_followup_reply(
    text: str,
    history: Sequence[HistoryMessage],
    *,
    token_budget: int | None = None,
) -> str | None:
    """Retain the heat flow rule when the latest user revises a two-body premise."""
    if token_budget is not None and token_budget < 96:
        return None
    inputs = _heat_followup_inputs(text, history)
    if inputs is None:
        return None
    _visible_text, premise, earlier, contact_pair = inputs
    changed = _HEAT_PAIR.fullmatch(premise)
    if changed:
        return _changed_heat_pair(changed, earlier)
    if reply := _known_heat_followup(premise, earlier, contact_pair):
        return reply
    if reply := _unknown_heat_followup(premise, earlier):
        return reply
    return None


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
        _WATER.search(_NO_WATER.sub(" ", topic))
        and _APPEARANCE.search(topic)
        and _BENDING.search(topic)
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
    remainder = _NO_WATER.sub(" ", example)
    if remainder != example:
        if _WATER.search(remainder):
            return None
        return CheckedExplanation(
            "Bez wody w naczyniu nie ma granicy wody i powietrza, która powodowała pozorne zgięcie.",
            f"Dlatego {noun} {places[0]} bez wody nie wydaje się {adjective} z tego powodu.",
        )
    return CheckedExplanation(
        "Światło zmienia kierunek na granicy wody i powietrza, więc zanurzona część przedmiotu wygląda na przesuniętą.",
        f"Dlatego {noun} {places[0]} z wodą wydaje się {adjective} przy powierzchni wody.",
    )


def _explanation_topic(
    question: str, history: Sequence[HistoryMessage], visible: str, example: str
) -> str | None:
    if not changes_example(question):
        return visible
    topic = _visible(active_explanation_topic(history))
    if _OTHER_TASK.search(topic) or (example == visible and _NEGATION.search(visible)):
        return None
    return topic


def _explanation_for_example(topic: str, example: str) -> CheckedExplanation | None:
    if _NO_WATER.search(example) or _NEGATION.search(example):
        if not _NO_WATER.search(example) or _NEGATION.search(
            _NO_WATER.sub(" ", example)
        ):
            return None
        return _refraction(topic, example)
    return (
        _thermal(topic, example)
        or _braking(topic, example)
        or _refraction(topic, example)
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
    example = _requested_example(visible)
    topic = _explanation_topic(question, history, visible, example)
    if topic is None:
        return None
    if not example or re.match(r"\bzamiast metal", visible):
        return None
    return _explanation_for_example(topic, example)
