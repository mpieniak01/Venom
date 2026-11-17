"""Offline-capable execution boundary for source/calculator-backed dialogue.

The caller supplies a plan, never a gold answer. Required tools run before any
answer can be released. Free paraphrases need semantic review and are deliberately
not certified by this deterministic boundary. This is an opt-in service, not a
replacement for Studio Normal's existing excerpt-based chat.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Protocol

from venom_core.services.grounded_calculator import CalculationError, calculate
from venom_core.services.grounded_presentation import rounded_value

MAX_SOURCE_CHARS = 32_000
MAX_TOTAL_SOURCE_CHARS = 64_000
MAX_SOURCES = 8
MAX_CALCULATIONS = 8
UNITS = frozenset(
    (
        "",
        "m",
        "km",
        "cm",
        "g",
        "kg",
        "ml",
        "l",
        "zł",
        "s",
        "min",
        "h",
        "km/h",
        "m/s",
        "%",
        "stron",
        "porcji",
        "punktów",
        "paczek",
        "przesyłek",
        "sztuk",
        "osób",
    )
)


_UNIT_ALIASES = {
    "m": ("metr", "metry", "metrów", "metrach"),
    "cm": ("centymetr", "centymetry", "centymetrów", "centymetrach"),
    "km": ("kilometr", "kilometry", "kilometrów", "kilometrach"),
    "g": ("gram", "gramy", "gramów", "gramach"),
    "kg": ("kilogram", "kilogramy", "kilogramów", "kilogramach"),
    "ml": ("mililitr", "mililitry", "mililitrów", "mililitrach"),
    "l": ("litr", "litry", "litrów", "litrach"),
    "zł": ("złoty", "złote", "złotych"),
    "s": ("sekunda", "sekundy", "sekund", "sekundach"),
    "min": ("minuta", "minuty", "minut", "minutach"),
    "h": ("godzina", "godziny", "godzin", "godzinach"),
    "m/s": ("metrów na sekundę", "metrach na sekundę"),
    "km/h": ("kilometrów na godzinę", "kilometrach na godzinę"),
    "%": ("procent", "procenty", "procentów", "procentach"),
    "stron": ("strona", "strony", "stronach"),
    "porcji": ("porcja", "porcje", "porcjach"),
    "punktów": ("punkt", "punkty", "punktu", "punktach"),
    "paczek": ("paczka", "paczki", "paczkach"),
    "przesyłek": ("przesyłka", "przesyłki", "przesyłkach"),
    "sztuk": ("sztuka", "sztuki", "sztukach"),
    "osób": ("osoba", "osoby", "osobach"),
}
_UNIT_BY_SPELLING = {
    spelling: unit
    for unit in UNITS - {""}
    for spelling in (unit, *_UNIT_ALIASES.get(unit, ()))
}
_UNIT_TOKEN = (
    "(?:"
    + "|".join(
        re.escape(spelling)
        for spelling in sorted(_UNIT_BY_SPELLING, key=lambda item: (-len(item), item))
    )
    + r")(?![\w/])"
)
_RECONVERT = re.compile(
    rf"\b(?:przelicz|zamień|wyraź)\b[^!?;\n]{{0,180}}?\b(?:na|w)\s+({_UNIT_TOKEN})",
    re.IGNORECASE,
)
_COMPUTE_IN = re.compile(
    rf"\b(?:oblicz|policz|wyznacz|podaj)\b[^!?;\n]{{0,140}}?\bw\s+({_UNIT_TOKEN})",
    re.IGNORECASE,
)
_PERCENT_REQUEST = re.compile(
    r"\b(?:(?:podaj|oblicz|policz|wyznacz)\s+(?:(?:kalkulatorem|aktualny|obecny|nowy|dokładny)\s+){0,3}procent|jaki\s+procent)\b",
    re.IGNORECASE,
)
_RESULT_IN_PROSE = re.compile(
    rf"(?<![\w.,+−-])([+−-]?(?:[0-9]{{1,3}}(?:[ \u00a0\u202f][0-9]{{3}})+"
    rf"|[0-9]{{1,160}})(?:[.,][0-9]{{1,160}})?)\s*({_UNIT_TOKEN})",
    re.IGNORECASE,
)
_NUMERIC_SPACES = str.maketrans({"−": "-", " ": None, "\u00a0": None, "\u202f": None})
_ALTERNATE_UNIT = re.compile(
    rf"\s*(?:i|oraz|lub|albo|bądź)\s+(?:(?:na|w)\s+)?({_UNIT_TOKEN})",
    re.IGNORECASE,
)
_SENTENCE_BREAK = re.compile(r"[!?;\n]|\.(?=\s|$)")


def explicit_result_unit(message: str) -> str | None:
    """Find an unambiguous unit explicitly requested in a calculation clause."""
    units: set[str] = {"%"} if _PERCENT_REQUEST.search(message) else set()
    for sentence in _SENTENCE_BREAK.split(message):
        for regex in (_RECONVERT, _COMPUTE_IN):
            for match in regex.finditer(sentence):
                units.add(_UNIT_BY_SPELLING[match[1].casefold()])
                alternative = _ALTERNATE_UNIT.match(sentence, match.end())
                if alternative:
                    units.add(_UNIT_BY_SPELLING[alternative[1].casefold()])
    return next(iter(units)) if len(units) == 1 else None


_CARD_ID = r"(?:\[[\w.-]{1,64}\]|[^\W\d_][\w-]{1,63})"
_CARD_REFERENCE = re.compile(
    rf"\b(?:według|zgodnie z|na podstawie|zajrzyj do|sprawdź(?: w)?"
    rf"|(?:w|z)\s+karcie|karta|kartę|karty)"
    rf"\s+(?:kart[ayęcie]*\s+)?(?P<name>{_CARD_ID})(?![\w-])"
    rf"|\b(?:z|w)\s+(?P<read>{_CARD_ID})(?![\w-])\s+"
    r"(?i:odczytaj|znajdź|wyczytaj|podaj|sprawdź|policz|wynika)\b",
    re.IGNORECASE,
)


_CARD_USE = re.compile(
    r"\b(?:(?:użyj|wykorzystaj|zacytuj)\s+(?:(?:tylko|wyłącznie|jedynie)\s+)?"
    r"|(?:oblicz|policz)\s+nową\s+kwotę\s+z\s+)"
    rf"(?:karty\s+)?(?P<name>{_CARD_ID})(?![\w-])",
    re.IGNORECASE,
)
_CARD_LIST_ITEM = re.compile(rf"\s*(?:,|i\b|oraz\b)\s+(?P<name>{_CARD_ID})(?![\w-])")
_CARD_ASSIGNMENT = re.compile(r"\bprzypisz\b[^.!?\n]*", re.IGNORECASE)
_CARD_ASSIGNMENT_TARGET = re.compile(
    rf"\bdo\s+(?:karty\s+)?(?P<name>{_CARD_ID})(?![\w-])", re.IGNORECASE
)


def _card_marker(marker: str) -> bool:
    return marker.startswith("[") or marker.isupper()


def requested_card_ids(
    message: str, *, include_contextual: bool = True
) -> tuple[str, ...]:
    """Extract card references after the source context is established."""
    references = []
    patterns = (
        (_CARD_REFERENCE, _CARD_USE) if include_contextual else (_CARD_REFERENCE,)
    )
    for pattern in patterns:
        for match in pattern.finditer(message):
            marker = match["name"] or match.groupdict().get("read")
            if not marker or not _card_marker(marker):
                continue
            references.append((match.start(), marker))
            end = match.end()
            while (item := _CARD_LIST_ITEM.match(message, end)) and _card_marker(
                item["name"]
            ):
                references.append((item.start("name"), item["name"]))
                end = item.end()
    if include_contextual:
        for assignment in _CARD_ASSIGNMENT.finditer(message):
            targets = [
                item
                for item in _CARD_ASSIGNMENT_TARGET.finditer(assignment[0])
                if item["name"].startswith("[")
                or (
                    len(item["name"]) >= 3
                    and item["name"].isalpha()
                    and item["name"].isupper()
                )
            ]
            if len(targets) > 1:
                references.extend(
                    (assignment.start() + item.start(), item["name"])
                    for item in targets
                )
    return tuple(dict.fromkeys(marker.strip("[]") for _, marker in sorted(references)))


class EvidenceError(ValueError):
    """A reason code for a failed contract, without an unverified answer."""


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _normal(text: str) -> str:
    return "".join(
        c
        for c in unicodedata.normalize("NFKD", text.casefold().replace("ł", "l"))
        if not unicodedata.combining(c)
    )


@dataclass(frozen=True)
class Requirements:
    sources: bool = False
    calculation: bool = False


def detect_requirements(message: str, prior_users: Sequence[str] = ()) -> Requirements:
    """Conservative hints, not a general natural-language theorem prover.

    Explicit caller requirements can strengthen these hints, never weaken them.
    History is user-only: source text/model answers cannot switch this policy.
    Ambiguous calculations without a plan are blocked, not guessed.
    """
    current = _normal(message)
    history = _normal(" ".join(prior_users[-8:]))
    arithmetic = (
        r"\b(?:oblicz\w*|przelicz\w*|rachun\w*|ile|jak daleko|dystans\w*|"
        r"lacznie|razem|porcj\w*|obniz\w*|rabat\w*)\b"
    )
    current_math = bool(re.search(arithmetic, current))
    follow_up = bool(
        re.search(
            r"\b(?:teraz|jesli|dokladnie|przyjmij|odcinek|dojsc|pozostal\w*|"
            r"zostalo|poprawka|korekta|zmiana)\b",
            current,
        )
    )
    numbers = bool(re.search(r"\d", current + " " + history))
    symbolic = bool(re.search(r"\d\s*[+*/]\s*\d", current))
    calculation = symbolic or (
        numbers
        and (current_math or (follow_up and bool(re.search(arithmetic, history))))
    )
    source_words = bool(
        re.search(r"\b(?:zrodl\w*|regulamin\w*|pakie\w*|dokument\w*)\b", current)
    )
    source_reference = bool(re.search(r"\bwedlug\s+(?:instrukcj\w*|zasad\w*)", current))
    check = bool(re.search(r"\b(?:sprawdz|przeczytaj)\b", current))
    fact_check = bool(re.search(r"\bczy\b.{0,200}\b(?:zawsze|prawda)\b", current))
    explicit_cards = requested_card_ids(message, include_contextual=False)
    contextual_cards = requested_card_ids(message)
    previous_cards = {
        ident
        for earlier in prior_users[-8:]
        for ident in requested_card_ids(earlier, include_contextual=False)
    }
    named_source = bool(explicit_cards) or (
        bool(contextual_cards) and set(contextual_cards) <= previous_cards
    )
    return Requirements(
        sources=named_source
        or source_words
        or source_reference
        or fact_check
        or (check and not calculation),
        calculation=calculation,
    )


@dataclass(frozen=True)
class SourceRef:
    source_id: str
    version: str
    sha256: str


@dataclass(frozen=True)
class SourceDocument:
    ref: SourceRef
    text: str
    complete: bool
    available: bool = True
    superseded: bool = False


class SourceBackend(Protocol):
    """Adapters must distinguish whole documents/cards from truncated excerpts."""

    def search(self, query: str) -> Sequence[SourceRef]: ...
    def read(self, ref: SourceRef) -> SourceDocument: ...
    def current_ref(self, source_id: str) -> SourceRef: ...


@dataclass(frozen=True)
class CalculationPlan:
    calculation_id: str
    expression: str
    unit: str = ""


@dataclass(frozen=True)
class CalculationEvidence:
    calculation_id: str
    expression: str
    value: str
    unit: str


@dataclass(frozen=True)
class TurnPlan:
    message: str
    revision: str
    prior_users: tuple[str, ...] = ()
    source_query: str = ""
    calculations: tuple[CalculationPlan, ...] = ()
    required: Requirements = Requirements()


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    sources: tuple[SourceDocument, ...]
    calculations: tuple[CalculationEvidence, ...]
    requirements: Requirements
    unavailable: tuple[str, ...]
    requested_source_ids: tuple[str, ...] = ()


def verify_result_prose(
    prose: str,
    evidence: Evidence,
    result_unit: str,
    *,
    decimal_places: int | None = None,
) -> None:
    """Bind the visible result, including only explicitly requested rounding."""
    values = {
        Decimal(
            c.value
            if decimal_places is None
            else rounded_value(c.value, decimal_places)
        )
        for c in evidence.calculations
        if c.unit == result_unit
    }
    displayed = [
        match[1].translate(_NUMERIC_SPACES).replace(",", ".")
        for match in _RESULT_IN_PROSE.finditer(prose)
        if _UNIT_BY_SPELLING[match[2].casefold()] == result_unit
    ]
    if decimal_places is None:
        matched = any(Decimal(value) in values for value in displayed)
    else:
        # A correct intermediate cannot conceal a different rounded final value.
        matched = bool(displayed) and all(
            Decimal(value) in values and len(value.partition(".")[2]) == decimal_places
            for value in displayed
        )
    if not matched:
        raise EvidenceError("answer_result_unbound")


_BOOKKEEPING = re.compile(
    r"\(\s*(?:current_state|resolved_inputs|"
    r"(?:calculation|obliczenie)\s+\d+\s*,\s*(?:version|wersja)\s+[\w.-]+)\s*\)"
    r"|\(\s*(?:fakt|fact)\s*\d*\s*:[^()]*\b(?:przypisanie|attribution)\s*:[^()]*\)",
    re.IGNORECASE,
)


_BOOKKEEPING_TAIL = re.compile(
    r"(?<=[.!?])\s+fakt(?:y)?\s*:\s*(?=[^.!?\n]*[:(])"
    r"(?P<body>[^.!?\n\[\]]*\.?)(?=\s*(?:\[[^\]\n]+\]\s*)*$)",
    re.IGNORECASE,
)


def strip_public_bookkeeping(prose: str, source_versions: dict[str, str]) -> str:
    """Remove generated bookkeeping wrappers and preserve a public card citation."""

    def replace_wrapper(match: re.Match[str]) -> str:
        cited = [
            ident
            for ident in source_versions
            if re.search(rf"(?<![\w-]){re.escape(ident)}(?![\w-])", match[0])
            and not re.search(
                rf"(?<![\w-]){re.escape(ident)}(?![\w-])",
                prose[: match.start()] + prose[match.end() :],
            )
        ]
        return " ".join(f"[{ident}]" for ident in cited)

    def remove_label(match: re.Match[str]) -> str:
        body = match["body"].strip(" :")
        if not body or (
            match["body"].lstrip().startswith(":")
            and body.rstrip(".") in match.string[: match.start()]
        ):
            return ""
        return f" {body[0].upper()}{body[1:]}"

    cleaned = _BOOKKEEPING_TAIL.sub(
        remove_label, _BOOKKEEPING.sub(replace_wrapper, prose)
    )
    if cleaned == prose:
        return prose
    return re.sub(r"[ \t]{2,}", " ", re.sub(r"[ \t]+([.,!?])", r"\1", cleaned)).strip()


@dataclass(frozen=True)
class SourceQuote:
    source_id: str
    version: str
    quote: str


_DOUBLE_QUOTES = str.maketrans({mark: '"' for mark in "„“”«»"})
_PUBLIC_CARD = re.compile(r"\[(?P<name>[\w.-]{1,64})(?:@[\w.-]+)?\]")
_PUBLIC_CARD_REFERENCE = re.compile(
    r"\b(?:według|zgodnie\s+z|na\s+podstawie|karta|karty|karcie|kartą|dokument|źródło)"
    r"\s*:?\s+(?:kart(?:y|ą|ę|a)\s+)?"
    r"[*_'\"„“«\x60]*(?P<name>[^\W\d_][\w-]{1,63})(?![\w-])",
    re.IGNORECASE,
)

_MAX_RECOVERED_CARD_LENGTH = 640


def literal_source_quote(text: str, quote: str) -> str:
    """Return the exact card substring while tolerating double-quote typography."""
    if any(character.isalnum() for character in quote):
        start = text.find(quote)
        if start < 0:
            start = text.translate(_DOUBLE_QUOTES).find(quote.translate(_DOUBLE_QUOTES))
        if start >= 0:
            return text[start : start + len(quote)]
    raise EvidenceError("answer_quote_unsupported")


def _verified_document(document: SourceDocument) -> bool:
    return (
        document.complete
        and document.available
        and not document.superseded
        and bool(document.text.strip())
        and text_hash(document.text) == document.ref.sha256
    )


def bind_source_quotes(
    prose: str, evidence: Evidence, quotes: Sequence[SourceQuote]
) -> tuple[SourceQuote, ...]:
    """Bind actual public references to literal evidence before semantic review."""
    documents = {doc.ref.source_id: doc for doc in evidence.sources}
    cited = {
        match["name"]
        for pattern in (_PUBLIC_CARD, _PUBLIC_CARD_REFERENCE)
        for match in pattern.finditer(prose)
        if match["name"].isupper() or match["name"] in documents
    }
    cited.update(
        ident
        for ident in documents
        if re.search(rf"(?<![\w-]){re.escape(ident)}(?![\w-])", prose)
    )
    if not cited <= documents.keys():
        raise EvidenceError("answer_source_unknown")
    bound = []
    for quote in quotes:
        document = documents.get(quote.source_id)
        if document is None or quote.version != document.ref.version:
            raise EvidenceError("answer_source_unknown")
        if not _verified_document(document):
            raise EvidenceError("source_incomplete")
        bound.append(
            SourceQuote(
                quote.source_id,
                quote.version,
                literal_source_quote(document.text, quote.quote),
            )
        )
    used = {quote.source_id for quote in bound}
    for ident in sorted(cited - used):
        document = documents[ident]
        if (
            not _verified_document(document)
            or len(document.text) > _MAX_RECOVERED_CARD_LENGTH
            or not any(character.isalnum() for character in document.text)
            or len(bound) >= MAX_SOURCES
        ):
            raise EvidenceError("answer_public_source_required")
        # The card is pinned and already named in the answer. The complete
        # literal gives the reviewer the basis to check the associated claim.
        bound.append(SourceQuote(ident, document.ref.version, document.text))
    return tuple(bound)


_MEETING_PLACE_QUESTION = re.compile(
    r"^\s*gdzie\s+(?:(?:grupa|uczestnicy)\s+(?:zbiera(?:ją)?|spotyka(?:ją)?)\s+się|"
    r"(?:jest|będzie|odbywa\s+się)\s+zbiórka)"
    r"(?:\s+tego\s+dnia)?\s+(?:według|zgodnie\s+z|na\s+podstawie)\s+"
    rf"(?:kart[ayąęcie]*\s+)?{_CARD_ID}\s*[?.!]?\s*$",
    re.IGNORECASE,
)
_MEETING_PLACE_FACT = re.compile(
    r"(?:^|(?<=[.!?]))\s*((?:grupa|uczestnicy)\s+"
    r"(?:spotyka(?:ją)?|zbiera(?:ją)?)\s+się\s+(?:przy|pod|koło|obok|w|we|na)\s+"
    r"[^.!?;:\n]{1,100}\.)",
    re.IGNORECASE,
)


def requested_meeting_place(
    message: str, documents: Sequence[SourceDocument]
) -> SourceQuote | None:
    """Resolve one literal location only for a direct question on a named full card."""
    if not _MEETING_PLACE_QUESTION.search(message) or len(documents) != 1:
        return None
    document = documents[0]
    if requested_card_ids(message) != (
        document.ref.source_id,
    ) or not _verified_document(document):
        return None
    facts = _MEETING_PLACE_FACT.findall(document.text)
    if len(facts) != 1:
        return None
    return SourceQuote(document.ref.source_id, document.ref.version, facts[0])


_PICKUP_TITLE = r'["„“«][^"„“”«»\r\n]{1,100}["”»]'
_PICKUP_REQUEST = re.compile(
    r"\s*zestaw(?:\s+dla\s+mnie)?\s+oba\s+punkty\s*[,;:]\s*"
    rf"(?:wyraźnie\s+)?przypisz\s+(?P<first>{_PICKUP_TITLE})\s+do\s+(?:karty\s+)?(?P<first_card>{_CARD_ID})"
    rf"\s*,?\s+(?:a|oraz|i)\s+(?:przypisz\s+)?(?P<second>{_PICKUP_TITLE})\s+do\s+"
    rf"(?:karty\s+)?(?P<second_card>{_CARD_ID})\s*[.!?]?\s*",
    re.IGNORECASE,
)
_PICKUP_CARD = re.compile(
    rf"\s*(?:dokument|karta)\s+dla\s+(?P<item>{_PICKUP_TITLE})\.\s*"
    r"wydanie\s+w\s+punkcie\s+(?P<point>[\w-]+(?:[ \t]+[\w-]+){0,4})"
    r"\s+do\s+(?:godziny\s+)?(?P<until>(?:[01][0-9]|2[0-3]):[0-5][0-9])\.\s*",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PickupDetail:
    item: str
    point: str
    until: str
    quote: SourceQuote


def _pickup_title(title: str) -> str:
    return unicodedata.normalize("NFC", " ".join(title[1:-1].split()))


def requested_pickup_details(
    message: str, documents: Sequence[SourceDocument]
) -> tuple[PickupDetail, PickupDetail] | None:
    """Resolve a two-card pickup summary only for exact item-to-card assignments."""
    request = _PICKUP_REQUEST.fullmatch(message)
    if request is None or len(documents) != 2:
        return None
    cards = {document.ref.source_id: document for document in documents}
    first_id = request["first_card"].strip("[]")
    second_id = request["second_card"].strip("[]")
    if first_id == second_id or cards.keys() != {first_id, second_id}:
        return None
    first_title = _pickup_title(request["first"]).casefold()
    second_title = _pickup_title(request["second"]).casefold()
    if not first_title or not second_title or first_title == second_title:
        return None

    def detail(document: SourceDocument, title: str) -> PickupDetail | None:
        if not _verified_document(document):
            return None
        card = _PICKUP_CARD.fullmatch(document.text)
        if card is None or _pickup_title(card["item"]).casefold() != title:
            return None
        return PickupDetail(
            _pickup_title(card["item"]),
            " ".join(card["point"].split()),
            card["until"],
            SourceQuote(
                document.ref.source_id, document.ref.version, document.text.strip()
            ),
        )

    first = detail(cards[first_id], first_title)
    second = detail(cards[second_id], second_title)
    return (first, second) if first is not None and second is not None else None


@dataclass(frozen=True)
class CalculationClaim:
    calculation_id: str
    value: str
    unit: str


@dataclass(frozen=True)
class AnswerDraft:
    evidence_id: str
    claims: tuple[SourceQuote | CalculationClaim, ...]
    # Any free text in an evidence answer remains uncertified, even if fluent.
    prose: str = ""


@dataclass(frozen=True)
class PublishedAnswer:
    evidence_id: str
    text: str


class GroundedTurn:
    """Execute the plan, pin full evidence and validate before publishing once."""

    def __init__(self, backend: SourceBackend) -> None:
        self.backend = backend
        self._evidence: Evidence | None = None

    def read_sources(
        self, query: str, *, message: str = ""
    ) -> tuple[tuple[SourceDocument, ...], tuple[str, ...]]:
        named = requested_card_ids(message)
        if len(named) > MAX_SOURCES:
            raise EvidenceError("source_count_limit")
        if named:
            try:
                references = tuple(self.backend.current_ref(ident) for ident in named)
            except (KeyError, FileNotFoundError) as exc:
                raise EvidenceError("source_not_found") from exc
            except (OSError, TimeoutError) as exc:
                raise EvidenceError("source_unavailable") from exc
            if tuple(ref.source_id for ref in references) != named:
                raise EvidenceError("source_identity_mismatch")
        else:
            references = tuple(self.backend.search(query))
        if not references:
            raise EvidenceError("source_not_found")
        if len(references) > MAX_SOURCES:
            raise EvidenceError("source_count_limit")
        documents: list[SourceDocument] = []
        unavailable: list[str] = []
        total = 0
        seen: set[str] = set()
        for ref in references:
            if ref.source_id in seen:
                raise EvidenceError("source_duplicate")
            seen.add(ref.source_id)
            document = self.backend.read(ref)  # Search previews can never satisfy this.
            if document.ref != ref or self.backend.current_ref(ref.source_id) != ref:
                raise EvidenceError("source_version_changed")
            if document.superseded:
                raise EvidenceError("source_superseded")
            if not document.available:
                unavailable.append(ref.source_id)
                continue
            if not document.complete or not document.text.strip():
                raise EvidenceError("source_incomplete")
            if text_hash(document.text) != ref.sha256:
                raise EvidenceError("source_hash_mismatch")
            total += len(document.text)
            if len(document.text) > MAX_SOURCE_CHARS or total > MAX_TOTAL_SOURCE_CHARS:
                raise EvidenceError("source_context_limit")
            documents.append(document)
        return tuple(documents), tuple(unavailable)

    def prepare(
        self,
        plan: TurnPlan,
        *,
        infer_requirements: bool = True,
        required_result_unit: str | None = None,
    ) -> Evidence:
        """Recompute each turn; a user correction cannot silently reuse a cache."""
        self._evidence = None
        if not plan.message.strip() or not plan.revision.strip():
            raise EvidenceError("turn_identity_required")
        if len(plan.message) > 16_000 or sum(map(len, plan.prior_users)) > 64_000:
            raise EvidenceError("turn_context_limit")
        required = plan.required
        if infer_requirements:
            detected = detect_requirements(plan.message, plan.prior_users)
            required = Requirements(
                sources=required.sources or detected.sources or bool(plan.source_query),
                calculation=required.calculation
                or detected.calculation
                or bool(plan.calculations),
            )
        elif (plan.source_query and not required.sources) or (
            plan.calculations and not required.calculation
        ):
            raise EvidenceError("tool_not_explicitly_enabled")
        if required.calculation and not plan.calculations:
            raise EvidenceError("calculation_plan_required")
        if len(plan.calculations) > MAX_CALCULATIONS:
            raise EvidenceError("calculation_count_limit")
        calculations: list[CalculationEvidence] = []
        seen: set[str] = set()
        for item in plan.calculations:
            if (
                not item.calculation_id
                or item.calculation_id in seen
                or item.unit not in UNITS
            ):
                raise EvidenceError("calculation_identity_or_unit_invalid")
            seen.add(item.calculation_id)
            try:
                value = calculate(item.expression)
            except CalculationError as exc:
                raise EvidenceError(str(exc)) from exc
            calculations.append(
                CalculationEvidence(
                    item.calculation_id, item.expression, value, item.unit
                )
            )
        output_unit = required_result_unit
        if output_unit is None and infer_requirements and required.calculation:
            output_unit = explicit_result_unit(plan.message)
        if output_unit is not None and not any(
            c.unit == output_unit for c in calculations
        ):
            raise EvidenceError("calculation_result_unit_missing")
        sources: tuple[SourceDocument, ...] = ()
        unavailable: tuple[str, ...] = ()
        named = requested_card_ids(plan.message) if required.sources else ()
        if required.sources:
            try:
                sources, unavailable = self.read_sources(
                    plan.source_query or plan.message, message=plan.message
                )
            except (OSError, TimeoutError, KeyError) as exc:
                raise EvidenceError("source_unavailable") from exc
        identity = text_hash(
            json.dumps(
                {
                    "plan": asdict(plan),
                    "sources": [asdict(d) for d in sources],
                    "calculations": [asdict(c) for c in calculations],
                    "unavailable": unavailable,
                    **({"result_unit": output_unit} if output_unit is not None else {}),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        self._evidence = Evidence(
            identity, sources, tuple(calculations), required, unavailable, named
        )
        return self._evidence

    def publish(self, draft: AnswerDraft) -> PublishedAnswer:
        """Only exact source quotations and bound calculator values are certified."""
        evidence = self._evidence
        if evidence is None or draft.evidence_id != evidence.evidence_id:
            raise EvidenceError("answer_evidence_stale")
        if draft.prose.strip():
            raise EvidenceError("answer_semantic_review_required")
        documents = {d.ref.source_id: d for d in evidence.sources}
        calculations = {c.calculation_id: c for c in evidence.calculations}
        used_sources: set[str] = set()
        used_calculations: set[str] = set()
        lines: list[str] = []
        for claim in draft.claims:
            if isinstance(claim, SourceQuote):
                document = documents.get(claim.source_id)
                if document is None or document.ref.version != claim.version:
                    raise EvidenceError("answer_source_unknown")
                try:
                    current_ref = self.backend.current_ref(claim.source_id)
                except (OSError, TimeoutError, KeyError) as exc:
                    raise EvidenceError("answer_source_unavailable") from exc
                if current_ref != document.ref:
                    raise EvidenceError("answer_source_stale")
                quote = literal_source_quote(document.text, claim.quote)
                used_sources.add(claim.source_id)
                lines.append(f"„{quote}” [{claim.source_id}@{claim.version}]")
            elif isinstance(claim, CalculationClaim):
                calculation = calculations.get(claim.calculation_id)
                if calculation is None:
                    raise EvidenceError("answer_calculation_unknown")
                try:
                    value = calculate(claim.value)
                except CalculationError as exc:
                    raise EvidenceError("answer_calculation_mismatch") from exc
                # Claims must contain a number, not a second expression/explanation.
                if not re.fullmatch(r"[+-]?\d+(?:\.\d+)?", claim.value.strip()):
                    raise EvidenceError("answer_calculation_mismatch")
                if value != calculation.value or claim.unit != calculation.unit:
                    raise EvidenceError("answer_calculation_mismatch")
                used_calculations.add(claim.calculation_id)
                lines.append(
                    f"{calculation.expression} = {calculation.value} {calculation.unit}".rstrip()
                )
            else:
                raise EvidenceError("answer_claim_unsupported")
        if evidence.requirements.sources and not used_sources:
            raise EvidenceError("answer_source_required")
        if not set(evidence.requested_source_ids) <= used_sources:
            raise EvidenceError("answer_named_source_required")
        if set(calculations) != used_calculations:
            raise EvidenceError("answer_calculation_required")
        if not lines:
            raise EvidenceError("answer_empty")
        self._evidence = (
            None  # A finalized receipt cannot be replayed for another turn.
        )
        return PublishedAnswer(evidence.evidence_id, "\n".join(lines))


def execute_grounded_turn(
    plan: TurnPlan,
    backend: SourceBackend,
    draft_generator: Callable[[Evidence], AnswerDraft],
) -> PublishedAnswer:
    """Run mandatory evidence collection before drafting, then the release gate.

    The generator may be a model adapter or an offline double. No partial draft
    is streamed or returned if publication fails.
    """
    turn = GroundedTurn(backend)
    evidence = turn.prepare(plan)
    return turn.publish(draft_generator(evidence))
