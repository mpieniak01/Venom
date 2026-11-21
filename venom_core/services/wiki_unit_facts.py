"""Recognize and reuse bounded conversion facts from the selected wiki article."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from urllib.parse import unquote, urlsplit

_NUMBER = r"\d{1,9}(?:[,.]\d{1,6})?"
_DIGIT_GROUP_DELIMITER = " \u00a0\u2009\u202f"
_GROUPED_NUMBER = (
    rf"\d{{1,3}}(?:[{_DIGIT_GROUP_DELIMITER}]\d{{3}}){{1,2}}(?:[,.]\d{{1,6}})?"
)
_ARTICLE_NUMBER = rf"(?:{_GROUPED_NUMBER}|{_NUMBER})"
_QUANTITY_START = r"(?<![\w.,+−-])"
_TONNE_UNIT = r"ton\w*(?:\s+metryczn\w*)?"
_ALLOWED_AFTER_TONNE = re.compile(
    r"\s*(?:$|[.!?,;:=()—–]|\b(?:to|na|w|z|wynosi|równa|odpowiada|według|ile)\b)",
    re.I,
)
_HALF_BASES = {
    "jeden": 1,
    "jedna": 1,
    "jedną": 1,
    "dwa": 2,
    "dwie": 2,
    "trzy": 3,
    "cztery": 4,
}
_SPOKEN_NUMBER = (
    r"(?:(?:" + "|".join(_HALF_BASES) + r")\s+i\s+pół|półtorej|pół|jedna|jedną)"
)
_BINARY_QUESTION = re.compile(r"czy\b", re.I)
_BINARY_AFTER_COMMA = re.compile(r",\s*czy\b", re.I)

_EXACT = re.compile(r"\b(?:około|średnio|w przybliżeniu|potocznie|niemal)\b", re.I)
_CLAUSES = re.compile(r"(?<=[.!?])\s+|\n")
_PREVIOUS = re.compile(
    r"\bz tego wynika\b|\b(?:z|na podstawie)\s+"
    r"(?:tego(?:\s+konkretnego)?|wcześniejszego|poprzedniego)\s+odczytu\b",
    re.I,
)


_DAY_REQUEST = re.compile(r"\bdob\w*\s+cywiln\w*\b", re.I)
_TONNE_REQUEST = re.compile(r"\bton\w*\s+metryczn\w*\b", re.I)
_DAY_NEED = re.compile(r"\b(?:godzin\w*|h)\b", re.I)
_MASS_NEED = re.compile(r"\b(?:kilogram\w*|kg)\b", re.I)


_REGISTERED_TONNE = re.compile(r"\bton\w*\s+rejestrow\w*\b", re.I)
_DIMENSION = re.compile(r"\b(?:mas\w*|pojemnoś\w*|objętoś\w*)\b", re.I)
_REGISTERED_TONNE_VOLUME = re.compile(
    r"^\s*tona rejestrowa\b[^.!?;]{0,100}?\b(?:jednostka|jednostką)"
    r"\s+(?:objętości|pojemności)\b",
    re.I,
)


def verified_wiki_dimension_reply(
    question: str, title: str, extract: str, url: str
) -> str | None:
    if (
        _REGISTERED_TONNE.search(question)
        and _DIMENSION.search(question)
        and title.casefold() == "tona rejestrowa"
        and _REGISTERED_TONNE_VOLUME.search(extract)
    ):
        return f"Tona rejestrowa jest jednostką objętości ({url})."
    return None


@dataclass(frozen=True)
class UnitSpec:
    topic: str
    titles: tuple[str, ...]
    sections: tuple[str, ...]
    fact: re.Pattern[str]
    quantity: re.Pattern[str]
    output_unit: str
    label: str


_DAY = UnitSpec(
    "doba cywilna",
    ("doba", "doba cywilna"),
    ("Doba cywilna", "Doba urzędowa"),
    re.compile(
        r"\b(?:dob\w*\s+cywiln\w*\s+(?:trwa|wynosi|liczy|ma|obejmuje|to|"
        r"jest\s+(?:równa|okresem|jednostką\s+czasu\s+trwającą))|"
        r"urzędow\w*\s+jednostk\w+\s+czasu\s+zdefiniowana\s+jest\s+jako\s+czas\s+trwania)"
        rf"\s+(?P<factor>{_ARTICLE_NUMBER})\s+(?:godzin\w*|h)\b",
        re.I,
    ),
    re.compile(
        rf"{_QUANTITY_START}(?P<number>{_ARTICLE_NUMBER}|{_SPOKEN_NUMBER})"
        r"\s*(?P<unit>godzin\w*|h|dob\w*)\b",
        re.I,
    ),
    "godziny",
    "Doba cywilna",
)
_TONNE = UnitSpec(
    "tona metryczna",
    ("tona", "tona metryczna"),
    ("Tona metryczna",),
    re.compile(
        r"(?:\btona metryczna(?:\s*\(t\))?(?:\s*[–—-]\s*jednostka masy)?|"
        r"(?<![\w.,])1\s*(?:tona|t)\b)\s*"
        r"(?:równa(?:jąca)?\s+(?:się\s+)?|równe\s+|wynosi\s+|odpowiada\s+|to\s+|ma\s+|=)"
        rf"\s*(?P<factor>{_ARTICLE_NUMBER})\s*(?:kilogram\w*|kg)\b",
        re.I,
    ),
    re.compile(
        rf"{_QUANTITY_START}(?P<number>{_ARTICLE_NUMBER}|{_SPOKEN_NUMBER})"
        rf"\s*(?P<unit>kilogram\w*|kg|{_TONNE_UNIT}|t)\b",
        re.I,
    ),
    "kg",
    "Tona metryczna",
)
_SPECS = {"day": _DAY, "metric_tonne": _TONNE}


def requested_unit_fact(question: str) -> str | None:
    if _DAY_REQUEST.search(question) and _DAY_NEED.search(question):
        return "day"
    if _TONNE_REQUEST.search(question) and _MASS_NEED.search(question):
        return "metric_tonne"
    return None


def unit_spec(kind: str) -> UnitSpec:
    return _SPECS[kind]


def verified_unit_factor(kind: str, extract: str) -> Decimal | None:
    spec = unit_spec(kind)
    values = {
        _decimal_digits(match["factor"])
        for clause in _CLAUSES.split(extract)
        if not _EXACT.search(clause)
        for match in spec.fact.finditer(clause)
    }
    if len(values) == 1:
        value = next(iter(values))
        if Decimal("0") < value <= Decimal("1000000"):
            return value
    return None


def _format_value(value: Decimal) -> str:
    return format(value.normalize(), "f").replace(".", ",")


def _number(value: str) -> Decimal:
    words = value.split()
    if len(words) == 3 and words[0] in _HALF_BASES and words[1:] == ["i", "pół"]:
        return Decimal(_HALF_BASES[words[0]]) + Decimal("0.5")
    if value == "półtorej":
        return Decimal("1.5")
    if value in {"jedna", "jedną"}:
        return Decimal(1)
    if value == "pół":
        return Decimal("0.5")
    return _decimal_digits(value)


def _decimal_digits(digits: str) -> Decimal:
    return Decimal("".join(digits.split()).replace(",", "."))


def _has_detached_digit_prefix(question: str, quantity: re.Match[str]) -> bool:
    return question[: quantity.start()].rstrip().endswith(tuple("0123456789"))


def _has_other_tonne_qualifier(question: str, quantity: re.Match[str]) -> bool:
    unit = quantity["unit"].casefold()
    return (
        unit.startswith("ton")
        and len(unit.split()) == 1
        and _ALLOWED_AFTER_TONNE.match(question, quantity.end()) is None
    )


def _hour_label(value: Decimal) -> str:
    if value == 1:
        return "godzina"
    if value % 1:
        return "godziny"
    return (
        "godziny"
        if value % 10 in (2, 3, 4) and value % 100 not in (12, 13, 14)
        else "godzin"
    )


@dataclass(frozen=True)
class WikiUnitEvidence:
    unit: str
    factor: Decimal | None = None
    url: str | None = None

    def to_record(self) -> dict[str, str]:
        result = {"wiki_unit": self.unit}
        if self.factor is not None and self.url is not None:
            result.update(wiki_factor=str(self.factor), wiki_unit_url=self.url)
        return result

    @classmethod
    def from_record(cls, record: dict) -> WikiUnitEvidence | None:
        unit = record.get("wiki_unit")
        if not isinstance(unit, str) or unit not in _SPECS:
            return None
        factor, url = record.get("wiki_factor"), record.get("wiki_unit_url")
        if (
            not isinstance(factor, str)
            or not re.fullmatch(_NUMBER, factor)
            or not isinstance(url, str)
        ):
            return cls(unit)
        try:
            parsed = urlsplit(url)
        except ValueError:
            return cls(unit)
        name = unquote(parsed.path.removeprefix("/wiki/")).replace("_", " ").casefold()
        if (
            parsed.scheme != "https"
            or parsed.netloc != "pl.wikipedia.org"
            or not parsed.path.startswith("/wiki/")
            or name not in unit_spec(unit).titles
        ):
            return cls(unit)
        value = _number(factor)
        return cls(unit, value, url) if 0 < value <= 1000000 else cls(unit)

    def first_reply(self) -> str:
        if self.factor is None or self.url is None:
            return (
                "Nie udało się potwierdzić przelicznika w odczytanym haśle Wikipedii."
            )
        spec = unit_spec(self.unit)
        unit = _hour_label(self.factor) if self.unit == "day" else spec.output_unit
        return f"{spec.label} to {_format_value(self.factor)} {unit} ({self.url})."

    def follow_up_reply(self, question: str) -> str | None:
        if not _PREVIOUS.search(question):
            return None
        spec = unit_spec(self.unit)
        quantities = list(spec.quantity.finditer(question))
        needed = _DAY_NEED if self.unit == "day" else _MASS_NEED
        if not quantities or not needed.search(question) or len(quantities) > 2:
            return None
        if any(_has_detached_digit_prefix(question, q) for q in quantities):
            return None
        if self.unit == "metric_tonne" and any(
            _has_other_tonne_qualifier(question, q) for q in quantities
        ):
            return "Poprzedni odczyt potwierdzał wyłącznie przelicznik tony metrycznej."
        fields = [
            (_number(q["number"].casefold()), bool(needed.fullmatch(q["unit"])))
            for q in quantities
        ]
        binary = bool(
            _BINARY_QUESTION.match(question.lstrip())
            or _BINARY_AFTER_COMMA.search(question)
        )
        if binary and (len(fields) != 2 or fields[0][1] == fields[1][1]):
            return None
        if not binary and (len(fields) != 1 or fields[0][1]):
            return None
        if self.factor is None:
            return "Poprzedni odczyt nie potwierdził potrzebnego przelicznika."
        original = next((number for number, small in fields if not small), fields[0][0])
        result = original * self.factor
        unit = _hour_label(result) if self.unit == "day" else spec.output_unit
        if binary:
            converted = next(number for number, small in fields if small)
            return self._binary_reply(original, converted, result, unit, self.factor)
        return f"{_format_value(result)} {unit}"

    def _binary_reply(
        self,
        original: Decimal,
        converted: Decimal,
        result: Decimal,
        unit: str,
        factor: Decimal,
    ) -> str:
        prefix = "Tak" if result == converted else "Nie"
        if self.unit != "day":
            return f"{prefix}, {_format_value(original)} t to {_format_value(result)} {unit}."
        days = converted / factor
        if days == 1:
            civil_day = "1 dobie cywilnej"
        elif days % 1 == 0:
            civil_day = f"{_format_value(days)} dobom cywilnym"
        else:
            civil_day = f"{_format_value(days)} doby"
        if days * factor == converted:
            hours = _hour_label(converted)
            return (
                f"{prefix}, {_format_value(converted)} {hours} odpowiada {civil_day}."
            )
        return f"{prefix}, {_format_value(original)} doby odpowiada {_format_value(result)} {unit}."
