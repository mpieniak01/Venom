"""Resolve narrowly scoped facts from exact candidate and user evidence."""

from __future__ import annotations

import re
from collections.abc import Callable
from decimal import Decimal
from typing import Literal, NotRequired, TypedDict

from .semantic_judge_v5 import Relation


class UserSource(TypedDict):
    message_index: int
    quote: str
    continuity_index: NotRequired[int]
    continuity_quote: NotRequired[str]


ProofKind = Literal["pickup_role", "signed_current", "setting_rejected"]
Proof = tuple[Relation, str, UserSource, str]
UserMessages = list[tuple[int, str]]


class Comparison(TypedDict):
    criterion: str
    kind: ProofKind
    observed: str
    effective_observed: str
    raw_relation: Relation
    effective_relation: Relation
    source: UserSource


_NAME = r"[^\W\d_]{2,32}"
_NUMBER = r"[+−-]?[0-9]{1,12}(?:[.,][0-9]{1,12})?"
_AMPERE = r"(?:mA|µA|μA|A)"
_CLAUSE = re.compile(r"(?<=[.!?])(?=\s)|[;\r\n]+")
_EMPHASIS = re.compile(r"\*\*([^*\r\n]+)\*\*")
_OMITTED = "brak w odpowiedzi"
_UNSAFE_CONTEXT = re.compile(
    r"\b(?:hipotetyczn\w*|przykład\w*|przykładow\w*|przyjmijmy|"
    r"nie dotyczy|wycof\w*|odwołuj\w*|(?:inna|innym|innej) (?:próba|próbie|komor\w*|pomiar\w*))\b",
    re.I,
)

_ROLE = re.compile(
    rf"Osoba obsługująca odbiór:\s*(?P<name>{_NAME})"
    r"(?:\.\s*Wystarczy jej identyfikacja w kontekście odbioru;"
    r"\s*osobny adres ani opis czynności nie są wymagane)?\.?",
    re.I,
)
_ROLE_ASSIGN = re.compile(
    rf"(?:Korekta:\s*)?(?:Osobą obsługującą odbiór jest|"
    rf"Osoba obsługująca odbiór:|Odbiór obsługuje)\s+(?P<name>{_NAME})\.?",
    re.I,
)
_ROLE_SAME = re.compile(
    r"Osoba (?:przy odbiorze|obsługująca odbiór) (?:pozostaje )?bez zmian\.?",
    re.I,
)
_ROLE_QUESTION = re.compile(
    r"Pytanie o osobę dotyczy osoby obsługującej odbiór\.?|"
    r"Nie pytam o osobny adres ani o opis czynności\.?|"
    r"Ta osoba osobiście wydaje [^\W\d_]+\.?",
    re.I,
)
_ROLE_MENTION = re.compile(
    r"\b(?:odbior\w*|odbiór|odbierz\w*|wydaj\w*|obsług\w*)\b", re.I
)
_ROLE_UNSAFE = re.compile(
    r"\b(?:nie|chyba|może|prawdopodobnie|albo|lub|zamiast|punkt\w*|sklep\w*|adres\w*)\b",
    re.I,
)
_PICKUP_LOCATION = re.compile(
    r"\b(?:punkt(?:em|u)?|punkcie|szyld\w*|adres\w*|miejsc\w*|placów\w*)\b|[«„]\s*U\s+",
    re.I,
)
_PICKUP_AT = re.compile(rf"\b(?:odbiór|odbierzesz)\s+u\s+(?P<name>{_NAME})\b", re.I)
_PICKUP_CLAIM = re.compile(
    rf"U\s+(?P<before>{_NAME})\s+odbierzesz(?:\s+(?:[0-9]{{1,6}}\s+)?{_NAME})?\.?"
    rf"|(?:{_NAME}\s+)?odbierzesz\s+u\s+(?P<after>{_NAME})\.?",
    re.I,
)

_CURRENT = re.compile(
    rf"(?i:Prąd|Natężenie prądu) (?i:wynosi) (?P<value>{_NUMBER}) (?P<unit>{_AMPERE})\.?"
)
_CURRENT_FACT = re.compile(
    rf"(?:(?i:Pomiar)\s+(?P<object>[\w-]{{1,32}})\s*[:—–-]\s*)?"
    r"(?i:prąd|natężenie prądu)(?:\s+(?:(?i:wynosi)\s+)?|\s*[:=]\s*)"
    rf"(?P<value>{_NUMBER})\s+(?P<unit>{_AMPERE})"
    r"(?:(?:\s+(?i:przez)|,\s*(?i:czas))\s+"
    r"[0-9]{1,12}\s+(?i:sekund\w*|s|minut\w*|min))?\.?"
)
_CURRENT_MENTION = re.compile(r"\b(?:pomiar|prąd(?:u|em)?|natężenie)\b", re.I)
_CURRENT_QUESTION = re.compile(r"^(?:Podaj|Wypisz|Podsumuj)\s+[^0-9.!?]*[.?!]?\Z", re.I)
_EXPLICIT_SIGN = re.compile(
    r"\b(?:plus\w*|znak\w*|biegunowoś\w*|polaryzacj\w*)\b", re.I
)

_COUNTS = {
    word: number
    for number, words in enumerate(
        (
            "zero zera",
            "jeden jednego",
            "dwa dwóch",
            "trzy trzech",
            "cztery czterech",
            "pięć pięciu",
            "sześć sześciu",
            "siedem siedmiu",
            "osiem ośmiu",
            "dziewięć dziewięciu",
            "dziesięć dziesięciu",
            "jedenaście jedenastu",
            "dwanaście dwunastu",
            "trzynaście trzynastu",
            "czternaście czternastu",
            "piętnaście piętnastu",
            "szesnaście szesnastu",
            "siedemnaście siedemnastu",
            "osiemnaście osiemnastu",
            "dziewiętnaście dziewiętnastu",
            "dwadzieścia dwudziestu",
        )
    )
    for word in words.split()
}
_CARDINAL = "|".join(sorted(_COUNTS, key=len, reverse=True))
_TEMP_TOKEN = (
    rf"(?:(?:minusem|minus|plusem|plus)\s+)?(?:{_NUMBER}|(?:{_CARDINAL}))"
    r"\s*(?:°\s*C|stop(?:ień|nia|nie|ni)(?:\s+Celsjusza)?)"
)
_TEMPERATURE = re.compile(_TEMP_TOKEN, re.I)
_EXPLICIT_C = re.compile(r"(?:°\s*C|Celsjusza)\Z", re.I)
_SETTING = re.compile(
    rf"(?:Po (?:korekcie|zmianie)\s+)?(?:nastawa|Bieżąca nastawa|Aktualna nastawa)"
    rf"(?: próbna)?\s+wynosi\s+(?P<value>{_TEMP_TOKEN})\.?",
    re.I,
)
_SETTING_SOURCE = re.compile(
    rf"(?:Zmieni(?:łam|łem|ono)\s+nastawę\s+na|(?:Aktualna |Bieżąca )?nastawa"
    rf"\s+wynosi|Ustaw\s+nastawę\s+na)\s+(?P<value>{_TEMP_TOKEN})\.?",
    re.I,
)
_SETTING_REJECT = re.compile(
    rf"(?P<pre>{_TEMP_TOKEN})\s+nie należy się kierować\.?"
    rf"|Nie (?:należy się kierować|kieruj się|ustawiaj|stosuj)\s+(?P<post>{_TEMP_TOKEN})\.?",
    re.I,
)
_SETTING_MENTION = re.compile(
    r"\b(?:nastaw\w*|stopni\w*|Celsjusza|Fahrenheita|kelwin\w*)\b|°", re.I
)
_SETTING_QUESTION = re.compile(r"^(?:Podaj|Wypisz|Podsumuj)\s+[^.!?]*[.?!]?\Z", re.I)


def _clauses(text: str) -> list[str]:
    return [clause.strip() for clause in _CLAUSE.split(text) if clause.strip()]


def _users(material: dict) -> UserMessages:
    return [
        (index, message["content"])
        for index, message in enumerate(material["messages"])
        if message["role"] == "user"
    ]


def _normalize_decimal(value: str) -> Decimal:
    return Decimal(value.replace(",", ".").replace("−", "-"))


def _role_forms(person: str) -> set[str]:
    name = person.casefold()
    if len(name) < 3 or not name.endswith("a"):
        return set()
    # Polish genitives are not regular for every given name. Use only the
    # unambiguous suffix families; uncertain inflections stay with Luna.
    if name[-2] in "kgl":
        return {name[:-1] + "i"}
    if name[-2] in "bdmnrstwz":
        return {name[:-1] + "y"}
    return set()


def _role_source_clause(clause: str, forms: set[str]) -> bool:
    if _ROLE_QUESTION.fullmatch(clause):
        return True
    if _PICKUP_LOCATION.search(clause) or _UNSAFE_CONTEXT.search(clause):
        return False
    if not _ROLE_MENTION.search(clause):
        return True
    match = _PICKUP_AT.search(clause)
    return bool(
        match and match["name"].casefold() in forms and not _ROLE_UNSAFE.search(clause)
    )


def _role_statement(text: str, forms: set[str]) -> tuple[str, str | None] | None:
    anchors: list[tuple[str, str | None]] = []
    for clause in _clauses(text):
        if found := _ROLE_ASSIGN.fullmatch(clause):
            anchors.append((clause, found["name"]))
        elif _ROLE_SAME.fullmatch(clause):
            anchors.append((clause, None))
        elif not _role_source_clause(clause, forms):
            return None
    return anchors[0] if len(anchors) == 1 else None


def _role_reference(users: UserMessages, person: str) -> UserSource | None:
    forms = _role_forms(person)
    if not forms:
        return None
    continuity: tuple[int, str] | None = None
    for index, text in reversed(users):
        anchor = _role_statement(text, forms)
        if anchor is None:
            return None
        quote, name = anchor
        if name is None:
            continuity = continuity or (index, quote)
            continue
        if name.casefold() != person.casefold():
            return None
        out: UserSource = {"message_index": index, "quote": quote}
        if continuity:
            out["continuity_index"], out["continuity_quote"] = continuity
        return out
    return None


def _role_evidence(
    description: str, users: UserMessages, candidate: str
) -> Proof | None:
    criterion = _ROLE.fullmatch(description)
    if not criterion or _PICKUP_LOCATION.search(candidate):
        return None
    person = criterion["name"]
    source = _role_reference(users, person)
    if not source:
        return None
    clauses = [clause for clause in _clauses(candidate) if _ROLE_MENTION.search(clause)]
    if len(clauses) != 1 or _ROLE_UNSAFE.search(clauses[0]):
        return None
    claim = _PICKUP_CLAIM.fullmatch(clauses[0])
    if not claim:
        return None
    name = claim["before"] or claim["after"]
    if name.casefold() not in _role_forms(person):
        return None
    return "supported", clauses[0], source, name


def _single_current(text: str, *, source: bool) -> tuple[re.Match[str], str] | None:
    matches = []
    for clause in _clauses(text):
        fact = _CURRENT_FACT.fullmatch(_EMPHASIS.sub(r"\1", clause))
        if fact:
            matches.append((fact, clause))
        elif _CURRENT_MENTION.search(clause) and not (
            source and _CURRENT_QUESTION.fullmatch(clause)
        ):
            return None
    return matches[0] if len(matches) == 1 else None


def _current_evidence(
    description: str, users: UserMessages, candidate: str
) -> Proof | None:
    criterion = _CURRENT.fullmatch(description)
    index, text = users[-1]
    if not criterion or _EXPLICIT_SIGN.search(text) or _UNSAFE_CONTEXT.search(text):
        return None
    grounded, claim = (
        _single_current(text, source=True),
        _single_current(candidate, source=False),
    )
    if grounded is None or claim is None:
        return None
    source_fact, source_quote = grounded
    candidate_fact, quote = claim
    if (source_fact["object"] or "").casefold() != (
        candidate_fact["object"] or ""
    ).casefold():
        return None
    unit = criterion["unit"]
    expected = _normalize_decimal(criterion["value"])
    if (
        source_fact["unit"] != unit
        or candidate_fact["unit"] != unit
        or _normalize_decimal(source_fact["value"]) != expected
    ):
        return None
    actual = _normalize_decimal(candidate_fact["value"])
    relation: Relation = "supported" if actual == expected else "contradicted"
    return (
        relation,
        quote,
        {"message_index": index, "quote": source_quote},
        candidate_fact["value"],
    )


def _temperature(token: str) -> Decimal | None:
    sign, words = 1, token.casefold().split()
    if words[0] in {"minus", "minusem", "plus", "plusem"}:
        sign = -1 if words[0].startswith("minus") else 1
        words.pop(0)
        if words[0].startswith(("+", "-", "−")):
            return None
    value = re.match(_NUMBER, words[0])
    if value:
        return sign * _normalize_decimal(value[0])
    return sign * Decimal(_COUNTS[words[0]])


def _explicit_setting(text: str) -> tuple[str, str] | None:
    matches = []
    for clause in _clauses(text):
        setting = _SETTING_SOURCE.fullmatch(clause)
        if setting:
            matches.append((setting["value"], clause))
        elif _TEMPERATURE.search(clause) or (
            _SETTING_MENTION.search(clause) and not _SETTING_QUESTION.fullmatch(clause)
        ):
            return None
    return matches[0] if len(matches) == 1 else None


def _setting_rejection(
    description: str, users: UserMessages, candidate: str
) -> Proof | None:
    criterion = _SETTING.fullmatch(description)
    index, text = users[-1]
    grounded = _explicit_setting(text)
    if not criterion or grounded is None or _UNSAFE_CONTEXT.search(text):
        return None
    token, source_quote = grounded
    if not (_EXPLICIT_C.search(token) and _EXPLICIT_C.search(criterion["value"])):
        return None
    clauses = [
        clause for clause in _clauses(candidate) if _SETTING_MENTION.search(clause)
    ]
    if len(clauses) != 1:
        return None
    rejection = _SETTING_REJECT.fullmatch(clauses[0])
    if not rejection:
        return None
    quoted = rejection["pre"] or rejection["post"]
    expected = _temperature(criterion["value"])
    if (
        expected is None
        or expected != _temperature(token)
        or expected != _temperature(quoted)
    ):
        return None
    return (
        "contradicted",
        clauses[0],
        {"message_index": index, "quote": source_quote},
        quoted,
    )


_PROVERS: tuple[
    tuple[ProofKind, Callable[[str, UserMessages, str], Proof | None]], ...
] = (
    ("pickup_role", _role_evidence),
    ("signed_current", _current_evidence),
    ("setting_rejected", _setting_rejection),
)


def _bound_observed(
    observed: str, raw_relation: Relation, quote: str, needle: str
) -> bool:
    if observed == _OMITTED:
        return raw_relation == "omitted"
    return needle in observed and (observed in quote or quote in observed)


def compare(
    material: dict,
    candidate: str,
    criterion_id: str,
    observed: str,
    raw_relation: Relation,
) -> Comparison | None:
    """Derive a local decision only when both source and answer have a strict binding."""
    if (
        material.get("candidate") != candidate
        or _UNSAFE_CONTEXT.search(candidate)
        or (observed != _OMITTED and observed not in candidate)
    ):
        return None
    description = next(
        (
            item["description"]
            for item in material["criteria"]
            if item["id"] == criterion_id
        ),
        "",
    )
    users = _users(material)
    if not users:
        return None
    for kind, prover in _PROVERS:
        if kind == "pickup_role" and any(
            doc.get("current", True) and _PICKUP_LOCATION.search(doc["text"])
            for doc in material.get("evidence", ())
        ):
            continue
        proof = prover(description, users, candidate)
        if proof is None:
            continue
        relation, quote, source, needle = proof
        if _bound_observed(observed, raw_relation, quote, needle):
            return {
                "criterion": criterion_id,
                "kind": kind,
                "observed": observed,
                "effective_observed": quote,
                "raw_relation": raw_relation,
                "effective_relation": relation,
                "source": source,
            }
    return None
