"""Bind an explicit pair of cable segments and a separate sourced threshold."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from venom_core.services.grounded_dialogue import (
    CalculationEvidence,
    Evidence,
    EvidenceError,
    PublishedAnswer,
    SourceDocument,
    SourceQuote,
    requested_card_ids,
    verify_result_prose,
)

SEGMENT_LENGTH_ID = "segment_length_total"
_AMOUNT = r"(?P<value>[0-9]{1,7}(?:[.,][0-9]{1,4})?) (?P<unit>cm|m)"
_CABLE = r"(?:przewodu|kabla)"
_CARD = r"(?:kartę [\w.-]{1,64} i kartę [\w.-]{1,64})"
_INTRO = re.compile(
    rf"mamy {_AMOUNT} {_CABLE}, a dostawca gwarantuje osobny odcinek zapasu (?:w metrach|w centymetrach)",
    re.IGNORECASE,
)
_TOTAL = re.compile(
    rf"przeczytaj {_CARD}\. kalkulatorem policz długość obu odcinków łącznie w metrach",
    re.IGNORECASE,
)
_UPDATE = re.compile(
    rf"odcinek główny (?P<shortened>skrócono do|zmieniono na) {_AMOUNT}, zapas ten sam\. "
    rf"sprawdź {_CARD}, przelicz kalkulatorem w metrach i wskaż, czy spełnimy normę",
    re.IGNORECASE,
)
_RESERVE = re.compile(
    rf"(?:dostawca gwarantuje oddzielny zapas {_CABLE} o długości|"
    rf"osobny odcinek zapasowy {_CABLE} ma długość) {_AMOUNT}\."
    r"(?: jest on dostępny również po skróceniu głównego odcinka\.)?",
    re.IGNORECASE,
)
_MINIMUM = re.compile(
    rf"minimalna łączna długość dwóch odcinków to {_AMOUNT}\."
    r"(?: wartość minimalna jest warunkiem odbioru\.)?",
    re.IGNORECASE,
)
_RECAP = re.compile(
    r"podaj tylko aktualną łączną długość i czy wystarczy", re.IGNORECASE
)


def _normalized(message: str) -> str:
    return " ".join(message.split())


def _turn(message: str) -> str:
    return _normalized(message).rstrip(".?!")


def _number(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _metres(value: Decimal) -> str:
    return f"{_number(value).replace('.', ',')} m"


@dataclass(frozen=True)
class _Measure:
    value: Decimal
    unit: str

    @classmethod
    def from_match(cls, match: re.Match[str]) -> _Measure:
        return cls(Decimal(match["value"].replace(",", ".")), match["unit"].lower())

    @property
    def metres(self) -> Decimal:
        return self.value.scaleb(-2) if self.unit == "cm" else self.value

    @property
    def expression(self) -> str:
        value = _number(self.value)
        return f"{value}/100" if self.unit == "cm" else value


@dataclass(frozen=True)
class _LengthFact:
    measure: _Measure
    source: SourceDocument

    @property
    def quote(self) -> SourceQuote:
        ref = self.source.ref
        return SourceQuote(ref.source_id, ref.version, self.source.text.strip())


@dataclass(frozen=True)
class SegmentLengthState:
    main: _Measure
    reserve: _LengthFact | None
    minimum: _LengthFact | None
    compare: bool

    @property
    def missing(self) -> list[str]:
        labels = []
        if self.reserve is None:
            labels.append("długość osobnego odcinka zapasu")
        if self.minimum is None:
            labels.append("minimalna łączna długość wymagana do odbioru")
        return labels

    @property
    def question(self) -> str:
        if self.reserve is None and self.minimum is None:
            return (
                "Jaka jest długość osobnego odcinka zapasu i jaka łączna długość "
                "jest wymagana do odbioru?"
            )
        if self.reserve is None:
            return "Jaka jest długość osobnego odcinka zapasu?"
        return "Jaka łączna długość jest wymagana do odbioru?"

    @property
    def expression(self) -> str | None:
        if self.reserve is None or self.minimum is None:
            return None
        return f"{self.main.expression}+{self.reserve.measure.expression}"


def segment_length_intro(message: str) -> str | None:
    match = _INTRO.fullmatch(_turn(message))
    if match is None:
        return None
    main = _Measure.from_match(match)
    value = _number(main.value).replace(".", ",")
    return (
        f"Odcinek główny ma {value} {main.unit}. "
        "Dostawca gwarantuje osobny zapas, ale jego długość pozostaje nieznana."
    )


def _source_fact(
    documents: tuple[SourceDocument, ...], pattern: re.Pattern[str]
) -> _LengthFact | None:
    facts = [
        _LengthFact(_Measure.from_match(match), document)
        for document in documents
        if (match := pattern.fullmatch(_normalized(document.text))) is not None
    ]
    return facts[0] if len(facts) == 1 else None


def _requested_main_length(
    users: tuple[str, ...],
    current: str,
    named: tuple[str, ...],
    update: re.Match[str] | None,
) -> _Measure | None:
    if update is not None:
        if (
            len(users) < 3
            or not _TOTAL.fullmatch(_turn(users[-2]))
            or set(requested_card_ids(users[-2])) != set(named)
        ):
            return None
        intro = _INTRO.fullmatch(_turn(users[-3]))
        if intro is None:
            return None
        main = _Measure.from_match(update)
        if (
            update["shortened"].casefold() == "skrócono do"
            and main.metres >= _Measure.from_match(intro).metres
        ):
            return None
    elif _TOTAL.fullmatch(current):
        intro = _INTRO.fullmatch(_turn(users[-2]))
        if intro is None:
            return None
        main = _Measure.from_match(intro)
    else:
        return None
    return main


def bind_segment_length(
    users: tuple[str, ...], documents: tuple[SourceDocument, ...]
) -> SegmentLengthState | None:
    """Recognize the explicit two-card request and bind each quantity by role."""
    if len(users) < 2 or any(len(turn) > 1000 for turn in users[-3:]):
        return None
    current = _turn(users[-1])
    named = requested_card_ids(users[-1])
    if len(named) != 2 or not {document.ref.source_id for document in documents} <= set(
        named
    ):
        return None
    update = _UPDATE.fullmatch(current)
    main = _requested_main_length(users, current, named, update)
    if main is None:
        return None
    return SegmentLengthState(
        main,
        _source_fact(documents, _RESERVE),
        _source_fact(documents, _MINIMUM),
        compare=update is not None,
    )


@dataclass(frozen=True)
class SegmentLengthReceipt:
    users: tuple[str, ...]
    state: SegmentLengthState
    calculation: CalculationEvidence
    reserve: _LengthFact
    minimum: _LengthFact

    @classmethod
    def from_evidence(
        cls, users: tuple[str, ...], state: SegmentLengthState, evidence: Evidence
    ) -> SegmentLengthReceipt:
        expression = state.expression
        reserve, minimum = state.reserve, state.minimum
        if (
            expression is None
            or reserve is None
            or minimum is None
            or reserve.source not in evidence.sources
            or minimum.source not in evidence.sources
        ):
            raise EvidenceError("pilot_segment_sources_mismatch")
        if len(evidence.calculations) != 1:
            raise EvidenceError("pilot_segment_calculation_mismatch")
        calculation = evidence.calculations[0]
        if (
            calculation.calculation_id != SEGMENT_LENGTH_ID
            or calculation.expression != expression
            or calculation.unit != "m"
            or Decimal(calculation.value) != state.main.metres + reserve.measure.metres
        ):
            raise EvidenceError("pilot_segment_calculation_mismatch")
        return cls(users, state, calculation, reserve, minimum)

    @property
    def _total(self) -> str:
        return _metres(Decimal(self.calculation.value))

    @property
    def _meets_minimum(self) -> bool:
        return Decimal(self.calculation.value) >= self.minimum.measure.metres

    @property
    def quotes(self) -> tuple[SourceQuote, SourceQuote]:
        return self.reserve.quote, self.minimum.quote

    def summary(self) -> str:
        main = self.state.main
        if main.unit == "cm":
            main_clause = f"Odcinek główny ma {_number(main.value).replace('.', ',')} cm, czyli {_metres(main.metres)}."
        else:
            main_clause = f"Odcinek główny ma {_metres(main.metres)}."
        reserve = f"Oddzielny zapas ma {_metres(self.reserve.measure.metres)} [{self.reserve.quote.source_id}]."
        minimum = (
            f"Norma odbioru wynosi {_metres(self.minimum.measure.metres)} "
            f"[{self.minimum.quote.source_id}] i jest progiem dla sumy."
        )
        summary = f"{main_clause} {reserve} Łącznie {self._total}. {minimum}"
        if not self.state.compare:
            return summary
        verdict = "spełnia normę" if self._meets_minimum else "jest za mała"
        return f"{summary} Łączna długość {verdict}."

    def verify_prose(self, prose: str, evidence: Evidence) -> None:
        # Verify the exact renderer, including source operands in metres.
        # The generic result verifier still binds the displayed computed claim.
        if prose != self.summary():
            raise EvidenceError("pilot_segment_prose_mismatch")
        verify_result_prose(f"Łącznie {self._total}.", evidence, "m")

    def recap(self, message: str, users: tuple[str, ...]) -> str | None:
        if _RECAP.fullmatch(_turn(message)) is None:
            return None
        if users[: len(self.users)] != self.users or any(
            _RECAP.fullmatch(_turn(turn)) is None for turn in users[len(self.users) :]
        ):
            return "Potrzebuję aktualnego potwierdzonego wyniku i normy odbioru."
        minimum = _metres(self.minimum.measure.metres)
        verdict = "wystarczy" if self._meets_minimum else "za mało"
        return f"{self._total}, {verdict} wobec normy {minimum}."


@dataclass(frozen=True)
class PilotSegmentLengthAnswer(PublishedAnswer):
    segment_length_receipt: SegmentLengthReceipt
