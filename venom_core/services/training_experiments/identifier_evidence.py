"""Compare explicitly attributed Polish digit sequences against current user evidence."""

from __future__ import annotations

import re
from typing import TypedDict

from .semantic_judge_v5 import Relation

_DIGITS = {
    name: str(index)
    for index, name in enumerate(
        (
            "zero",
            "jeden",
            "dwa",
            "trzy",
            "cztery",
            "pięć",
            "sześć",
            "siedem",
            "osiem",
            "dziewięć",
        )
    )
}
_ENTITY = r"[^\W\d_]{1,32}"
_DIGIT = rf"(?:{'|'.join(_DIGITS)})"
_WORDS = rf"{_DIGIT}(?:[- ]{_DIGIT}){{1,31}}"
_SEQUENCE = re.compile(rf"(?<![\w-]){_WORDS}(?![\w-])", re.IGNORECASE)
_CRITERION = re.compile(
    rf"Bieżący kod (?P<entity>{_ENTITY}) to (?P<value>[0-9]{{1,32}})"
    r"(?:, wraz z zerem wiodącym)?\.?",
    re.IGNORECASE,
)
_REFERENCE = re.compile(
    rf"(?:Korekta: )?(?:dla (?P<parcel>{_ENTITY}) obowiązuje kod"
    rf"|(?:dziś )?kod (?P<asset>{_ENTITY}) to) (?P<value>[0-9]{{1,32}})",
    re.IGNORECASE,
)
_ASSERTION = re.compile(
    rf"(?:^|(?<=[.!?\n]))\s*(?:"
    rf"(?P<parcel>{_ENTITY}), pod (?:poprawionym )?kodem (?P<attached>{_WORDS}),"
    rf"|(?:bieżący )?kod (?P<asset>{_ENTITY}) to (?P<declared>{_WORDS})(?=\s*(?:[.!]|\Z)))",
    re.IGNORECASE,
)
_CODE_MENTION = re.compile(r"\bkod(?:em|u)?\b", re.IGNORECASE)


class Source(TypedDict):
    message_index: int
    entity: str
    quote: str
    value: str


class Comparison(TypedDict):
    criterion: str
    observed: str
    raw_relation: Relation
    effective_relation: Relation
    candidate_digits: str | None
    source: Source | None


def _unresolved_assignment(quote: str, entity: str) -> bool:
    return (
        _CODE_MENTION.search(quote) is not None
        and re.search(r"\d", quote, re.ASCII) is not None
        and entity in {word.casefold() for word in re.findall(r"[^\W\d_]+", quote)}
    )


def _latest_reference(messages: list[dict], entity: str) -> Source | None:
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if message["role"] == "user":
            break
    else:
        return None

    matches: list[Source] = []
    for sentence in re.split(r"[.!?\n]+", message["content"]):
        quote = sentence.strip()
        found = _REFERENCE.fullmatch(quote)
        if found is None:
            if _unresolved_assignment(quote, entity):
                return None
            continue
        named = found["parcel"] or found["asset"]
        if named.casefold() == entity:
            matches.append(
                {
                    "message_index": index,
                    "entity": named,
                    "quote": quote,
                    "value": found["value"],
                }
            )
    return matches[0] if len(matches) == 1 else None


def _asserted_digits(candidate: str, observed: str, entity: str) -> str | None:
    if len(_CODE_MENTION.findall(candidate)) != 1:
        return None
    assertions = list(_ASSERTION.finditer(candidate))
    if len(assertions) != 1:
        return None
    assertion = assertions[0]
    named = assertion["parcel"] or assertion["asset"]
    written = assertion["attached"] or assertion["declared"]
    if named.casefold() != entity or _SEQUENCE.findall(candidate) != [written]:
        return None
    if _SEQUENCE.findall(observed) != [written]:
        return None
    return "".join(_DIGITS[part] for part in re.split(r"[- ]", written.casefold()))


def compare(
    material: dict, candidate: str, observed: str, raw_relation: Relation
) -> Comparison | None:
    if _SEQUENCE.search(candidate) is None:
        return None
    description = next(
        (
            criterion["description"]
            for criterion in material["criteria"]
            if criterion["id"] == "code"
        ),
        "",
    )
    criterion = _CRITERION.fullmatch(description)
    if criterion is None:
        return None
    entity = criterion["entity"].casefold()
    source = _latest_reference(material["messages"], entity)
    if source is not None and source["value"] != criterion["value"]:
        source = None
    asserted = _asserted_digits(candidate, observed, entity)
    effective: Relation = "unclear"
    if source is not None and asserted is not None:
        effective = "supported" if asserted == source["value"] else "contradicted"
    return {
        "criterion": "code",
        "observed": observed,
        "raw_relation": raw_relation,
        "effective_relation": effective,
        "candidate_digits": asserted,
        "source": source,
    }
