"""Validate explicit counts for proposal tasks without counting unrelated quantities."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

Mode = Literal["exact", "at_most"]

_SINGLE = frozenset(("jeden", "jedna", "jedną", "jednego", "jednej"))
_PAIR = frozenset(("dwa", "dwie", "dwóch"))
_COUNT = r"(?:[1-9]\d{0,2}|jeden|jedna|jedną|jednego|jednej|dwa|dwie|dwóch)"
_BOUND = r"(?:co najwyżej|najwyżej|maksymalnie|nie więcej niż)"
_QUALIFIER = rf"(?:{_BOUND}|dokładnie|tylko)"
_REQUEST = re.compile(
    rf"\b(?P<verb>daj|podaj|zaproponuj|przedstaw|wymień|wypisz|pokaż|zasugeruj|wybierz|"
    rf"potrzebuję|poproszę|proszę o|chcę)\s+(?:(?:mi|proszę|teraz)\s+){{0,2}}"
    rf"(?:(?P<modifier>{_QUALIFIER})\s+)?(?P<number>{_COUNT})\b",
    re.I,
)
_BARE_REQUEST = re.compile(
    rf"(?:\A|(?<=[.!?]))\s*(?P<modifier>{_QUALIFIER})\s+(?P<number>{_COUNT})\b",
    re.I,
)
_NUMERIC_TAIL = re.compile(
    rf"^(?:[.,]\d|\s*(?:[–—-]|do\b|lub\b|albo\b)\s*{_COUNT}\b)", re.I
)
_ALTERNATE_COUNT = re.compile(
    rf"^\s+[^\W\d_]+(?:\s+[^\W\d_]+){{0,3}}\s+(?:lub|albo)\s+{_COUNT}\b", re.I
)
_WORDS = re.compile(r"^\s*([^\W\d_]+(?:\s+[^\W\d_]+){0,4})", re.UNICODE)
_AMOUNT_UNITS = re.compile(
    r"(?:mm|cm|m|km|ml|cl|dl|l|g|kg|mg|h|s|min|zł|pln|eur|usd|"
    r"milimetr\w*|centymetr\w*|metr\w*|kilometr\w*|mililitr\w*|litr\w*|gram\w*|kilogram\w*|"
    r"złot\w*|euro|dol(ar)\w*|minut\w*|sekund\w*|godzin\w*|dzień|dni|tygod\w*|"
    r"miesiąc\w*|miesięc\w*|procent\w*|słów|słow(?:o|a|ie|om|ach|ami)|wyraz(?:u|y|em|ów|om|ach|ami)?|"
    r"znak(?:u|i|iem|ów|om|ach|ami)?|token(?:u|y|em|ów|om|ach|ami)?|cyfr(?:a|ę|y|ze|om|ach|ami)?|"
    r"liter(?:a|ę|y|ze|om|ach|ami)?|punkt(?:u|y|em|ów|om|ach|ami)?|"
    r"zdani(?:e|a|u|om|ach|ami)|zdań|akapit(?:u|y|em|ów|om|ach|ami)?|pytań|pytani(?:e|a|u|om|ach|ami))",
    re.I,
)
_PHRASE_END = frozenset(
    ("bez", "dla", "do", "i", "lub", "albo", "o", "od", "na", "w", "we", "z", "ze")
)
_BOUNDARY = re.compile(r"^(?:\s*[.!?,;:])?\s*$")
_QUOTED = re.compile(r'[„“][^”]*(?:”|$)|«[^»]*(?:»|$)|"[^"]*(?:"|$)')
_NEGATION = re.compile(r"(?:\bnie\s+|(?:po co|czy)\s+)$", re.I)

_BULLET = re.compile(r"^\s*(?:[-*•]\s+|[1-9]\d{0,2}[.)]\s+)(\S.*)$")
_ALTERNATIVE = re.compile(r"\b(?:lub|albo|bądź)\b", re.I)
_OPTION_PREFIX = (
    r"alternatywnie|inną opcją jest|inna opcja to|kolejną propozycją jest|"
    r"druga propozycja to|drugą propozycją jest|możesz też|można też"
)
_NEW_OPTION = re.compile(rf"(?:[.!?;]\s+|\n+)(?=(?:{_OPTION_PREFIX})\b)", re.I)
_SUMMARY = re.compile(
    r"(?:[.!?;]\s+|\n+)(?=(?:obie|oba|wszystkie)\s+(?:opcje|propozycje|warianty)\b)",
    re.I,
)
_EXCLUSION = re.compile(r"\b(?:bez|unikaj|wyklucz)\b", re.I)
_ACTION = re.compile(
    r"^\s*(?:prześlij|wyślij|wybierz|zrób|przygotuj|postaw|dodaj|zaproponuj|podaj)\b",
    re.I,
)
_SHORT_NUMBER = re.compile(r"\b\d+(?:[.,]\d+)?\s*$")
_FENCE = chr(96) * 3


@dataclass(frozen=True)
class CountRequirement:
    mode: Mode
    count: int

    def accepts(self, count: int) -> bool:
        return count == self.count if self.mode == "exact" else 0 <= count <= self.count


def _without_quotes(text: str) -> str:
    return _QUOTED.sub(lambda match: " " * len(match[0]), text)


def _proposal_phrase(tail: str, verb: str, number: int) -> bool:
    if _NUMERIC_TAIL.match(tail) or _ALTERNATE_COUNT.match(tail):
        return False
    if verb == "wybierz" and number == 1 and _BOUNDARY.fullmatch(tail):
        return True
    phrase = _WORDS.match(tail)
    if not phrase:
        return False
    words = phrase[1].casefold().split()
    if verb == "wybierz" and words[0] in {"z", "ze"}:
        return True
    label = []
    for word in words:
        if word in _PHRASE_END:
            break
        label.append(word)
    return bool(label) and not any(_AMOUNT_UNITS.fullmatch(word) for word in label)


def requested_count(text: str) -> CountRequirement | None:
    """Recognize a count within an explicit proposal request in the current turn."""
    text = _without_quotes(text)
    found = set()
    for pattern in (_REQUEST, _BARE_REQUEST):
        for match in pattern.finditer(text):
            verb = (match.groupdict().get("verb") or "").casefold()
            if verb and _NEGATION.search(text[: match.start()]):
                continue
            numeral = match["number"].casefold()
            if numeral in _SINGLE:
                number = 1
            elif numeral in _PAIR:
                number = 2
            else:
                number = int(numeral)
            if not _proposal_phrase(text[match.end() :], verb, number):
                continue
            modifier = (match["modifier"] or "").casefold()
            mode = "at_most" if re.fullmatch(_BOUND, modifier) else "exact"
            found.add(CountRequirement(mode, number))
    return next(iter(found)) if len(found) == 1 else None


def _components(option: str) -> list[str]:
    parts = []
    consumed = 0
    visible = _without_quotes(option)
    for split in _ALTERNATIVE.finditer(visible):
        left = visible[consumed : split.start()]
        right = visible[split.end() :]
        clause = re.split(r"[.!?;,:]", left)[-1]
        if _EXCLUSION.search(clause) and not _ACTION.match(right):
            continue
        if _SHORT_NUMBER.search(left) and re.match(r"\s*\d", right):
            continue
        element = option[consumed : split.start()].strip(" \t,;")
        if element:
            parts.append(element)
        consumed = split.end()
    tail = option[consumed:].strip(" \t,;")
    if tail:
        parts.append(tail)
    return parts


def _decode(text: str) -> list[str]:
    text = text.strip()
    if text.startswith(_FENCE):
        first, _, rest = text.partition("\n")
        if first.casefold() not in {_FENCE, _FENCE + "json"} or not rest.endswith(
            _FENCE
        ):
            return []
        text = rest[: -len(_FENCE)].strip()
    if text.startswith(("{", "[")):
        try:
            result = json.loads(text)
        except (ValueError, RecursionError):
            return []
        if isinstance(result, dict) and set(result) == {"options"}:
            result = result["options"]
        if isinstance(result, list) and all(
            isinstance(item, str) and item.strip() for item in result
        ):
            return result
        return []

    items = []
    current = []
    for line in text.splitlines():
        bullet = _BULLET.match(line)
        if bullet:
            if current:
                items.append(" ".join(current))
            current = [bullet[1]]
        elif current and line.strip():
            current.append(line.strip())
    if current:
        items.append(" ".join(current))
    if items:
        return [_SUMMARY.split(item, maxsplit=1)[0] for item in items]
    plain = _SUMMARY.split(text, maxsplit=1)[0]
    return _NEW_OPTION.split(plain) if plain else []


def option_key(text: str) -> str:
    return " ".join(text.casefold().strip(" .!?").split())


def _effective(items: Sequence[str]) -> tuple[str, ...]:
    options = {}
    for item in items:
        nested = (
            _decode(item)
            if "\n" in item and _BULLET.match(item.splitlines()[0])
            else (item,)
        )
        for line in nested:
            for piece in _components(line):
                key = option_key(piece)
                if key:
                    options.setdefault(key, piece)
    return tuple(options.values())


def split_options(text: str) -> list[str]:
    """Return effective options from a list or a short proposal draft."""
    return list(_effective(_decode(text)))
