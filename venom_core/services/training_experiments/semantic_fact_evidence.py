"""Resolve narrowly scoped facts from exact candidate and user evidence."""

from __future__ import annotations

import re
from collections.abc import Callable
from decimal import Decimal
from typing import Literal, NotRequired, TypedDict

from .semantic_judge_v5 import MAX_EVIDENCE_TEXT_CHARS, Relation


class UserSource(TypedDict):
    message_index: int
    quote: str
    continuity_index: NotRequired[int]
    continuity_quote: NotRequired[str]


ProofKind = Literal["pickup_role", "signed_current", "setting_rejected"]
Proof = tuple[Relation, str, UserSource, str]
UserMessages = list[tuple[int, str]]


class ResponseScope(TypedDict):
    kind: Literal["withdrawn_role", "withdrawn_setting_advice", "setting_advice"]
    quote: str
    withdrawn_role: NotRequired[str]
    withdrawn_role_reference: NotRequired[str]
    source: UserSource
    withdrawn_quotes: NotRequired[list[str]]
    setting_criterion: NotRequired[str]
    setting_quote: NotRequired[str]


class PickupPointEvidence(TypedDict):
    source: UserSource
    source_name: str
    quote: str
    answer_name: str
    relation: Literal["supported", "contradicted"]
    criterion: NotRequired[str]


class Comparison(TypedDict):
    criterion: str
    kind: ProofKind
    observed: str
    effective_observed: str
    raw_relation: Relation
    effective_relation: Relation
    source: UserSource


_NAME = r"[^\W\d_]{2,32}"
_NUMBER = r"[+−-]?(?a:\d){1,12}(?:[.,](?a:\d){1,12})?"
_AMPERE = r"(?:mA|µA|μA|A)"
_CLAUSE = re.compile(r"(?<=[.!?])(?=\s)|[;\r\n]+")
_EMPHASIS = re.compile(r"\*\*([^*\r\n]+)\*\*")
_OMITTED = "brak w odpowiedzi"
_UNSAFE_CONTEXT = re.compile(
    r"\b(?:hipotetyczn\w*|przykład\w*|przykładow\w*|przyjmijmy|"
    r"nie dotyczy|wycof\w*|odwołuj\w*|cof(?:am|amy|nięt\w*|nął\w*|nęł\w*)|"
    r"anul(?:uj\w*|owan\w*)|unieważn(?:ia\w*|ion\w*)|nieaktualn\w*|"
    r"nie obowiązuj(?:e|ą)|(?:inna|innym|innej) (?:próba|próbie|komor\w*|pomiar\w*))\b",
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
_PICKUP_LOCATION_PATTERNS = (
    re.compile(r"\b(?:punkt(?:em|u)?|punkcie)\b", re.I),
    re.compile(r"\b(?:szyld|adres|miejsc|placów)\w*\b", re.I),
    re.compile(r"[«„]\s*U\s+", re.I),
)

_PICKUP_AT = re.compile(rf"\b(?:odbiór|odbierzesz)\s+u\s+(?P<name>{_NAME})\b", re.I)
_PICKUP_CLAIM = re.compile(
    rf"(?P<leading>U\s+(?P<before>{_NAME}))\s+odbierzesz"
    rf"(?:\s+(?:(?a:\d){{1,6}}\s+)?{_NAME})?\.?"
    rf"|(?:{_NAME}\s+)?odbierzesz\s+(?P<trailing>u\s+(?P<after>{_NAME}))\.?",
    re.I,
)

_PICKUP_QUANTITY = r"(?P<count>(?a:\d){1,6}) (?P<unit>pudeł(?:ek|ka|o)?|karton(?:y|ów)?|pacz(?:ek|ki|ka))"
_PICKUP_SOURCE_COUNT = re.compile(
    rf"Do odbioru (?:jest|są|zostało|pozostało|pozostaje) {_PICKUP_QUANTITY}\.?", re.I
)
_POINT_LABEL = r"[^\W_]{1,32}(?:[ -][^\W_]{1,32}){0,4}"
_PICKUP_POINT_NAME = re.compile(
    r"(?:Korekta:\s*)?(?:Punkt(?: odbioru)? (?:ma nazwę|nazywa się)|"
    r"Szyld to|Nazwa punktu:|Odbiór (?:jest )?w punkcie) "
    rf"(?:„(?P<polish>{_POINT_LABEL})”|«(?P<angle>{_POINT_LABEL})»|"
    rf'"(?P<ascii>{_POINT_LABEL})")\.?',
    re.I,
)
_PICKUP_FIELD = (
    r"(?:osobę(?: wydającą| obsługującą odbiór)?|rolę|"
    r"liczbę(?: paczek| kartonów| pudeł| sztuk)?|"
    r"(?:aktualną )?nazwę punktu(?: odbioru)?|(?:aktualny )?szyld)"
)
_PICKUP_QUESTION = re.compile(
    rf"(?:Podaj|Wypisz|Podsumuj) {_PICKUP_FIELD}(?:(?:, | i | oraz ){_PICKUP_FIELD})*[.!?]?",
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
    r"(?a:\d){1,12}\s+(?i:sekund\w*|s|minut\w*|min))?\.?"
)
_CURRENT_MENTION = re.compile(r"\b(?:pomiar|prąd(?:u|em)?|natężenie)\b", re.I)
# Whitespace belongs entirely to the prefix: consuming it possessively keeps
# the accepted language while avoiding overlap with the question body.
_CURRENT_QUESTION = re.compile(
    r"^(?:Podaj|Wypisz|Podsumuj)\s++(?a:[^\d.!?]*)[.?!]?\Z", re.I
)
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
_SPOKEN_SIGN = r"(?:minusem|minus|plusem|plus)"
_TEMP_MAGNITUDE = rf"(?:{_NUMBER}|{_CARDINAL})"
# Only a numeric temperature can attach its unit without a space.
_TEMP_UNIT = (
    r"(?:(?<=(?a:\d))\s*°\s*C|\s+(?:°\s*C|stop(?:ień|nia|nie|ni)(?:\s+Celsjusza)?))"
)
_TEMP_TOKEN = rf"(?:{_SPOKEN_SIGN}\s+)?{_TEMP_MAGNITUDE}{_TEMP_UNIT}"
_TEMPERATURE = re.compile(_TEMP_TOKEN, re.I)
_TEMP_PARTS = re.compile(
    rf"(?:(?P<sign>{_SPOKEN_SIGN})\s+)?(?P<magnitude>{_TEMP_MAGNITUDE}){_TEMP_UNIT}",
    re.I,
)
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
_SETTING_QUESTION = re.compile(r"^(?:Podaj|Wypisz|Podsumuj)\s++[^.!?]*[.?!]?\Z", re.I)


def _pickup_location(text: str) -> bool:
    return any(
        pattern.search(text) is not None for pattern in _PICKUP_LOCATION_PATTERNS
    )


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
    if _pickup_location(clause) or _UNSAFE_CONTEXT.search(clause):
        return False
    if not _ROLE_MENTION.search(clause):
        return True
    match = _PICKUP_AT.search(clause)
    return bool(
        match and match["name"].casefold() in forms and not _ROLE_UNSAFE.search(clause)
    )


def _point_name(clause: str) -> str | None:
    point = _PICKUP_POINT_NAME.fullmatch(clause)
    if point is None:
        return None
    return point["polish"] or point["angle"] or point["ascii"]


def _independent_pickup_clause(clause: str, role_forms: set[str]) -> bool:
    if _PICKUP_SOURCE_COUNT.fullmatch(clause) or _PICKUP_QUESTION.fullmatch(clause):
        return True
    point = _point_name(clause)
    return point is not None and not role_forms.intersection(
        point.casefold().removeprefix("u ").replace("-", " ").split()
    )


def _role_statement(
    text: str, forms: set[str], *, separate_fields: bool
) -> tuple[str, str | None] | None:
    anchors: list[tuple[str, str | None]] = []
    for clause in _clauses(text):
        if found := _ROLE_ASSIGN.fullmatch(clause):
            anchors.append((clause, found["name"]))
        elif _ROLE_SAME.fullmatch(clause):
            anchors.append((clause, None))
        elif separate_fields and _independent_pickup_clause(clause, forms):
            continue
        elif not _role_source_clause(clause, forms):
            return None
    return anchors[0] if len(anchors) == 1 else None


def _role_reference(
    users: UserMessages, person: str, *, separate_fields: bool = False
) -> UserSource | None:
    forms = _role_forms(person)
    if not forms:
        return None
    continuity: tuple[int, str] | None = None
    for index, text in reversed(users):
        anchor = _role_statement(text, forms, separate_fields=separate_fields)
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
    if not criterion or _pickup_location(candidate):
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
    match = _TEMP_PARTS.fullmatch(token.casefold())
    if match is None:
        return None
    spoken_sign = match["sign"]
    magnitude = match["magnitude"]
    if spoken_sign and magnitude.startswith(("+", "-", "−")):
        return None
    count = _COUNTS.get(magnitude)
    if count is not None:
        value = Decimal(count)
    else:
        value = _normalize_decimal(magnitude)
    return -value if spoken_sign and spoken_sign.startswith("minus") else value


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
            doc.get("current", True) and _pickup_location(doc["text"])
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


_ROLE_WITHDRAWAL = re.compile(
    r"(?:Cofam|Wycofuję|Odwołuję) (?:informację|stwierdzenie) o osobie"
    r"(?: obsługującej odbiór)?\.?",
    re.I,
)
_ADVICE_WITHDRAWAL = re.compile(
    r"(?:Cofam|Wycofuję|Odwołuję) (?:tę instrukcję|to odradzanie|tę poradę)\.?",
    re.I,
)
_PICKUP_COUNT = re.compile(rf"(?:Do odbioru zostało )?{_PICKUP_QUANTITY}\.?", re.I)
_PICKUP_TIME = r"(?:odbiór|odbiór jest) o (?:[01]?(?a:\d)|2[0-3]):[0-5](?a:\d)"
_SETTING_REPORT = re.compile(
    rf"(?:Aktualna|Bieżąca) nastawa (?:to|wynosi) (?P<value>{_TEMP_TOKEN})"
    rf", a {_PICKUP_TIME}\.?",
    re.I,
)
_PICKUP_TIME_REPORT = re.compile(rf"{_PICKUP_TIME}\.?", re.I)


def _explicit_pickup_point(text: str, *, source: bool) -> tuple[str, str] | None:
    points = []
    for clause in _clauses(text):
        if name := _point_name(clause):
            points.append((name, clause))
        elif not source and _ROLE_WITHDRAWAL.fullmatch(clause):
            continue
        elif _UNSAFE_CONTEXT.search(clause) or (
            _pickup_location(clause)
            and not (source and _PICKUP_QUESTION.fullmatch(clause))
        ):
            return None
    return points[0] if len(points) == 1 else None


def pickup_point_evidence(material: dict, candidate: str) -> PickupPointEvidence | None:
    """Compare explicit point names without interpreting a bare reference to a person."""
    if (
        material.get("candidate") != candidate
        or len(candidate) > MAX_EVIDENCE_TEXT_CHARS
        or material.get("evidence")
    ):
        return None
    users = _users(material)
    if not users:
        return None
    index, text = users[-1]
    source = _explicit_pickup_point(text, source=True)
    answer = _explicit_pickup_point(candidate, source=False)
    if source is None or answer is None:
        return None
    source_name, source_quote = source
    answer_name, quote = answer
    result: PickupPointEvidence = {
        "source": {"message_index": index, "quote": source_quote},
        "source_name": source_name,
        "quote": quote,
        "answer_name": answer_name,
        "relation": (
            "supported"
            if answer_name.casefold() == source_name.casefold()
            else "contradicted"
        ),
    }
    criteria = [
        item["id"]
        for item in material["criteria"]
        if (name := _point_name(item["description"]))
        and name.casefold() == source_name.casefold()
    ]
    if len(criteria) == 1:
        result["criterion"] = criteria[0]
    return result


def _withdrawn_role_scope(
    material: dict, users: UserMessages, clauses: list[str], candidate: str
) -> ResponseScope | None:
    if len(clauses) != 3 or not _ROLE_WITHDRAWAL.fullmatch(clauses[1]):
        return None
    pickup = _PICKUP_CLAIM.fullmatch(clauses[0])
    count = _PICKUP_COUNT.fullmatch(clauses[2])
    if not pickup or not count or _ROLE_UNSAFE.search(clauses[0]):
        return None
    unit = count["unit"].casefold()
    amount = int(count["count"])
    if amount == 1:
        units = {"pudełko", "karton", "paczka"}
    elif 2 <= amount % 10 <= 4 and not 12 <= amount % 100 <= 14:
        units = {"pudełka", "kartony", "paczki"}
    else:
        units = {"pudeł", "kartonów", "paczek"}
    if unit not in units or not clauses[0].casefold().removesuffix(".").endswith(
        f" {count['count']} {unit}"
    ):
        return None
    name = pickup["before"] or pickup["after"]
    roles = [
        (item["id"], matched["name"])
        for item in material["criteria"]
        if (matched := _ROLE.fullmatch(item["description"]))
    ]
    if len(roles) != 1:
        return None
    field, person = roles[0]
    source = _role_reference(users, person, separate_fields=True)
    if source is None or name.casefold() not in _role_forms(person):
        return None
    return {
        "kind": "withdrawn_role",
        "quote": candidate,
        "source": source,
        "withdrawn_role": field,
        "withdrawn_role_reference": pickup["leading"] or pickup["trailing"],
        "withdrawn_quotes": clauses[:2],
    }


def _setting_criterion_id(material: dict, value: Decimal) -> str | None:
    criteria = [
        (item["id"], match["value"])
        for item in material["criteria"]
        if (match := _SETTING.fullmatch(item["description"]))
    ]
    if len(criteria) != 1:
        return None
    criterion_id, token = criteria[0]
    if _EXPLICIT_C.search(token) is None or _temperature(token) != value:
        return None
    return criterion_id


def _setting_scope(
    material: dict, users: UserMessages, clauses: list[str], candidate: str
) -> ResponseScope | None:
    index, text = users[-1]
    if len(clauses) not in (2, 3) or _UNSAFE_CONTEXT.search(text):
        return None
    rejection = _SETTING_REJECT.fullmatch(clauses[0])
    source = _explicit_setting(text)
    if rejection is None or source is None:
        return None
    source_value, source_quote = source
    if not _EXPLICIT_C.search(source_value):
        return None
    value = _temperature(source_value)
    if value is None or _temperature(rejection["pre"] or rejection["post"]) != value:
        return None
    criterion_id = _setting_criterion_id(material, value)
    if criterion_id is None:
        return None
    if not any(
        _SETTING_QUESTION.fullmatch(clause) and _SETTING_MENTION.search(clause)
        for clause in _clauses(text)
    ):
        return None
    evidence: ResponseScope = {
        "kind": "setting_advice",
        "quote": candidate,
        "source": {"message_index": index, "quote": source_quote},
    }
    if len(clauses) == 2:
        return evidence if _PICKUP_TIME_REPORT.fullmatch(clauses[1]) else None
    report = _SETTING_REPORT.fullmatch(clauses[2])
    if (
        not _ADVICE_WITHDRAWAL.fullmatch(clauses[1])
        or report is None
        or not _EXPLICIT_C.search(report["value"])
        or _temperature(report["value"]) != value
    ):
        return None
    evidence["setting_criterion"] = criterion_id
    evidence["setting_quote"] = clauses[2]
    evidence["kind"] = "withdrawn_setting_advice"
    evidence["withdrawn_quotes"] = clauses[:2]
    return evidence


def response_scope(
    material: dict, candidate: str, *, point: PickupPointEvidence | None = None
) -> ResponseScope | None:
    """Prove the entire answer is confined to a narrowly recognized task response."""
    if (
        material.get("candidate") != candidate
        or len(candidate) > MAX_EVIDENCE_TEXT_CHARS
        or material.get("evidence")
    ):
        return None
    users = _users(material)
    if not users:
        return None
    clauses = _clauses(candidate)
    role_clauses = clauses
    if (
        point is not None
        and point["relation"] == "supported"
        and len(clauses) == 4
        and point["quote"] in clauses[2:]
    ):
        role_clauses = [clause for clause in clauses if clause != point["quote"]]
    return _withdrawn_role_scope(
        material, users, role_clauses, candidate
    ) or _setting_scope(material, users, clauses, candidate)
