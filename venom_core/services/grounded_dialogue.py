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
from typing import Protocol

from venom_core.services.grounded_calculator import CalculationError, calculate

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
    )
)


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
    return Requirements(
        sources=source_words
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


@dataclass(frozen=True)
class SourceQuote:
    source_id: str
    version: str
    quote: str


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
        self, query: str
    ) -> tuple[tuple[SourceDocument, ...], tuple[str, ...]]:
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

    def prepare(self, plan: TurnPlan, *, infer_requirements: bool = True) -> Evidence:
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
        sources: tuple[SourceDocument, ...] = ()
        unavailable: tuple[str, ...] = ()
        if required.sources:
            try:
                sources, unavailable = self.read_sources(
                    plan.source_query or plan.message
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
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        self._evidence = Evidence(
            identity, sources, tuple(calculations), required, unavailable
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
                if not claim.quote.strip() or claim.quote not in document.text:
                    raise EvidenceError("answer_quote_unsupported")
                used_sources.add(claim.source_id)
                lines.append(f"„{claim.quote}” [{claim.source_id}@{claim.version}]")
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
