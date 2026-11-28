"""Preserve explicit uncertainty and limits in ready-to-publish Studio drafts."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from venom_core.api.schemas.llm_simple import HistoryMessage
from venom_core.services.chat_policy.qualified_chat_quote import (
    single_quoted_operand,
    without_quotes,
)

_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_BULLETIN = re.compile(
    r"skróć (?:mój tekst )?do dwóch zdań"
    r"(?: (?:mój tekst )?(?:do (?:biuletynu|ogłoszenia)|na (?:tablicę|plakat)))?:\s*"
    r"(?:[.!]\s*)?(?:nie zmieniaj przybliżenia w dokładną liczbę[.!]?|"
    r"(?:nie używaj|bez) pierwszej osoby[.!]?)?",
    re.I,
)
_SOURCE_TEASER = re.compile(
    r"źródło do zajawki\s*[.!:]?\s*napisz dwa zdania w bezosobowym stylu[.!]?",
    re.I,
)
_COMMUNICATION_NOTE = re.compile(
    r"(?:notatka do komunikatu|materiał do ogłoszenia)\s*:\s*[.!]?\s*"
    r"(?:oddaj|podaj) to w dwóch zdaniach bezosobowych[.!]?",
    re.I,
)
_DAYS = {
    "poniedziałek": "w poniedziałek",
    "wtorek": "we wtorek",
    "środa": "w środę",
    "czwartek": "w czwartek",
    "piątek": "w piątek",
    "sobota": "w sobotę",
    "niedziela": "w niedzielę",
}
_DAY_ACCUSATIVE = {"środę": "środa", "sobotę": "sobota", "niedzielę": "niedziela"}
_PLAN_DATE_EDIT = re.compile(
    r"nie zmieniaj liczb ani liczby zdań[.!] (?P<new>[^\W\d_]+) zastąpi "
    r"(?P<old>[^\W\d_]+) w planie (?:ogłoszenia|publikacji)[.!]?",
    re.I,
)
_COMMUNICATION_DATE_EDIT = re.compile(
    r"(?P<subject>[^.!?]{3,44}?) planujemy (?:w|we) (?P<new>[^\W\d_]+) "
    r"zamiast (?:w|we) (?P<old>[^\W\d_]+)[.!]\s*"
    r"(?:liczb i dwóch zdań nie zmieniaj|zachowaj liczby i dwa zdania)[.!]?",
    re.I,
)
_IMPERSONAL = re.compile(r"napisz od strony czytelnika,\s*bez\s+i\s*[.!]?", re.I)
_PENDING = re.compile(
    r"(?P<detail>[^.!?]{4,120}?\bbez\s+[^.!?]{2,65}?)\s+"
    r"(?:jeszcze|nadal|wciąż)\s+(?:weryfikujemy|sprawdzamy)[.!]?",
    re.I,
)
_PENDING_PASSIVE = re.compile(
    r"(?P<detail>[^.!?]{4,120}?\bbez\s+[^.!?]{2,65}?)\s+"
    r"(?:jest|są)\s+(?:jeszcze|nadal|wciąż)\s+(?:sprawdzan(?:e|y|ych)|weryfikowan(?:e|y|ych))[.!]?",
    re.I,
)
_PENDING_QUEUE = re.compile(
    r"(?P<detail>[^.!?]{4,120}?\bbez\s+[^.!?]{2,65}?)\s+"
    r"(?:jeszcze|nadal|wciąż)\s+(?:czeka(?:ją)?|oczekuje|oczekują) na "
    r"(?:kontrolę|sprawdzenie|weryfikację)[.!]?",
    re.I,
)
_PLAN = re.compile(
    r"(?P<subject>[^.!?]{3,44}?)\s+(?:chcemy|planujemy|zamierzamy)\s+"
    r"(?P<action>ogłosić|podać|udostępnić|opublikować)\s+(?P<time>[^.!?]{2,48})[.!]?",
    re.I,
)
_PROVISIONAL = re.compile(r"\b(?:wstępni\w*|około|mniej więcej)\b", re.I)
_PLANNING_WORD = re.compile(
    r"\b(?:planuje się|planowane|planowana|planowany|w planie)\b", re.I
)
_FIRST_PERSON = re.compile(
    r"\b(?:nami|nam|nasz\w*|chcemy|planujemy|zamierzamy|sprawdzamy|weryfikujemy)\b",
    re.I,
)
_NUMERIC_LITERAL = re.compile(r"(?<!\w)\d+(?::\d{2})?(?!\w)")
_FIRST_PERSON_COUNTS = {
    "naliczyliśmy": "naliczono",
    "policzyliśmy": "policzono",
    "zebraliśmy": "zebrano",
    "mamy": "jest",
}
_FIRST_COUNT = re.compile(rf"\b(?:{'|'.join(_FIRST_PERSON_COUNTS)})\b", re.I)
_CAP_COMMAND = re.compile(
    r"zrób z tego zapowiedź do [^.!?]{3,60},\s*podkreśl ograniczenia bez tonu zakazu[.!]?",
    re.I,
)
_CAP = re.compile(
    r"pula (?:to|obejmuje|wynosi)\s+(?P<bound>do|maksymalnie|najwyżej|nie więcej niż)\s+"
    r"(?P<number>[1-9][0-9]{0,4})\s+(?P<unit>[^\W\d_]+)[.!]?",
    re.I,
)
_PERSON_CAP = re.compile(
    r"jedna osoba może (?P<verb>wziąć|odebrać|dostać)\s+"
    r"(?:maksymalnie |do )?(?P<amount>dwie|dwa|trzy|cztery|pięć|[1-9])"
    r"(?: (?P<units>sztuki|sztukę|sztuk))?[.!]?",
    re.I,
)
_REMOVE_CAP_WORD = re.compile(r"usuń słowo\s*,?\s*(?:bo [^.!?]{4,80})?[.!]?", re.I)
_TEASER = re.compile(
    r"daj krótką zajawkę do ogłoszenia:\s*[.!]?\s*"
    r"nie rób z planu nowego grafiku[.!]?",
    re.I,
)
_OPTIONAL = re.compile(r"\bmogą się pojawić\b", re.I)
_HEADLINE = re.compile(
    r"daj nagłówek trzy słowa,\s*wyłącznie o (?P<topic>[^\W\d_]+),\s*"
    r"pod nim dotychczasowy tekst[.!]?",
    re.I,
)


def _sentences(source: str) -> list[str]:
    return [part.rstrip(".") for part in _SENTENCE.split(source.strip())]


def _sentence(text: str) -> str:
    return f"{text[0].upper()}{text[1:].rstrip('.')}."


@dataclass(frozen=True)
class PublicationCheck:
    """Verify literal anchors in the draft or use a source-derived safe version."""

    fallback: str
    required: tuple[str, ...]
    sentences: int | None = None
    modality: re.Pattern[str] | None = None
    forbidden: re.Pattern[str] | None = None
    expected_numbers: tuple[str, ...] | None = None

    def publish(self, draft: str) -> str:
        candidate = " ".join(draft.split())
        folded = candidate.casefold()
        if (
            any(anchor.casefold() not in folded for anchor in self.required)
            or (
                self.sentences is not None
                and len(_sentences(candidate)) != self.sentences
            )
            or (self.modality is not None and not self.modality.search(candidate))
            or (self.forbidden is not None and self.forbidden.search(candidate))
            or (
                self.expected_numbers is not None
                and tuple(sorted(_NUMERIC_LITERAL.findall(candidate)))
                != self.expected_numbers
            )
        ):
            return self.fallback
        return draft


def _bulletin(
    source: str, *, date_edit: re.Match[str] | None = None
) -> PublicationCheck | None:
    lines = _sentences(source)
    if len(lines) != 3 or not _PROVISIONAL.search(lines[0]):
        return None
    passive = _PENDING_PASSIVE.fullmatch(lines[1])
    queue = _PENDING_QUEUE.fullmatch(lines[1])
    pending = _PENDING.fullmatch(lines[1]) or passive or queue
    plan = _PLAN.fullmatch(lines[2])
    if not pending or not plan:
        return None
    opening = _FIRST_COUNT.sub(
        lambda match: _FIRST_PERSON_COUNTS[match[0].casefold()], lines[0]
    )
    if opening.casefold().startswith("przed nami wstępnie "):
        opening = "Wstępna liczba to " + opening[len("przed nami wstępnie ") :]
    if _FIRST_PERSON.search(opening):
        return None
    timing = plan["time"]
    if date_edit:
        old = date_edit["old"].casefold()
        old = _DAY_ACCUSATIVE.get(old, old)
        new = date_edit["new"].casefold()
        new = _DAY_ACCUSATIVE.get(new, new)
        subject = date_edit.groupdict().get("subject")
        if (
            timing.casefold() != _DAYS.get(old)
            or new not in _DAYS
            or (
                subject is not None and subject.casefold() != plan["subject"].casefold()
            )
        ):
            return None
        timing = _DAYS[new]
    detail = pending["detail"][:1].lower() + pending["detail"][1:]
    pending_fact = (
        lines[1][:1].lower() + lines[1][1:] if queue else f"nadal sprawdza się {detail}"
    )
    fallback = (
        f"{opening}, a {pending_fact}. "
        f"{plan['subject']} planuje się {plan['action']} {timing}."
    )
    # Keep the plan, its action and the date in one sentence.
    plan_pattern = (
        rf"\b{re.escape(plan['subject'])}\b[^.!?]{{0,35}}{_PLANNING_WORD.pattern}"
        rf"[^.!?]{{0,32}}\b{re.escape(plan['action'])}\b[^.!?]{{0,20}}"
        rf"\b{re.escape(timing)}\b"
    )
    if passive:
        # The detail and its unresolved verification must remain in one sentence.
        anchor = re.escape(pending["detail"])
        pending_pattern = (
            rf"(?:\b{anchor}\b[^.!?]{{0,38}}\b"
            r"(?:jest|są) (?:jeszcze|nadal|wciąż) (?:sprawdzan(?:e|y|ych)|weryfikowan(?:e|y|ych))"
            rf"|\b(?:jeszcze|nadal|wciąż) sprawdza się {anchor}\b)"
        )
        plan_pattern = rf"(?=.*{pending_pattern})(?=.*{plan_pattern})"
    forbidden = _FIRST_PERSON
    if date_edit and timing.casefold() != plan["time"].casefold():
        forbidden = re.compile(
            rf"(?:{_FIRST_PERSON.pattern}|\b{re.escape(plan['time'])}\b)", re.I
        )
    planning = re.compile(plan_pattern, re.I)
    return PublicationCheck(
        fallback,
        (opening, pending_fact if queue else pending["detail"]),
        sentences=2,
        modality=planning,
        forbidden=forbidden,
        expected_numbers=tuple(sorted(_NUMERIC_LITERAL.findall(source))),
    )


def _capped(source: str, *, remove_word: bool) -> PublicationCheck | None:
    lines = _sentences(source)
    if len(lines) != 3 or not _NUMERIC_LITERAL.search(lines[0]):
        return None
    cap, per_person = _CAP.fullmatch(lines[1]), _PERSON_CAP.fullmatch(lines[2])
    if not cap or not per_person:
        return None
    bound = f"{cap['number']} {cap['unit']}"
    amount = per_person["amount"]
    units = f" {per_person['units']}" if per_person["units"] else ""
    ceiling = "do" if cap["bound"].casefold() == "do" else "najwyżej"
    fallback = (
        f"{_sentence(lines[0])} Pula obejmuje {ceiling} {bound}, "
        f"a jedna osoba może {per_person['verb']} {amount}{units}."
    )
    quantified = re.compile(
        rf"(?=.*\b(?:do|najwyżej|maksymalnie|nie więcej niż)\s+{re.escape(bound)}\b)"
        rf"(?=.*\b(?:jedna|każda) osoba może {re.escape(per_person['verb'])}"
        rf"\s+(?:do |maksymalnie )?{re.escape(amount)}\b)",
        re.I,
    )
    forbidden = re.compile(r"\bmaksymalnie\b", re.I) if remove_word else None
    return PublicationCheck(
        fallback,
        (lines[0],),
        modality=quantified,
        forbidden=forbidden,
        expected_numbers=tuple(sorted(_NUMERIC_LITERAL.findall(source))),
    )


def _teaser(source: str) -> PublicationCheck | None:
    lines = _sentences(source)
    if (
        len(lines) != 2
        or not _OPTIONAL.search(lines[0])
        or not _NUMERIC_LITERAL.search(lines[1])
    ):
        return None
    fallback = " ".join(_sentence(line) for line in lines)
    return PublicationCheck(fallback, tuple(lines), sentences=2)


def _source(text: str, command: re.Pattern[str]) -> str | None:
    visible = " ".join(without_quotes(text).split())
    source = single_quoted_operand(text)
    return (
        source if source and len(source) <= 750 and command.fullmatch(visible) else None
    )


def communication_note(text: str, prior: str) -> str | None:
    """Compose a bounded two-sentence note from the user's three source facts."""
    if source := _source(text, _COMMUNICATION_NOTE):
        check = _bulletin(source)
        return check.fallback if check else None
    if edit := _COMMUNICATION_DATE_EDIT.fullmatch(text):
        if source := _source(prior, _COMMUNICATION_NOTE):
            check = _bulletin(source, date_edit=edit)
            return check.fallback if check else None
    return None


def publication_check(
    text: str, history: Sequence[HistoryMessage]
) -> PublicationCheck | None:
    """Bind a constrained editorial request to the active source text."""
    if source := _source(text, _BULLETIN) or _source(text, _SOURCE_TEASER):
        return _bulletin(source)
    if source := _source(text, _CAP_COMMAND):
        return _capped(source, remove_word=False)
    if source := _source(text, _TEASER):
        return _teaser(source)
    if len(history) < 2 or (history[-2].role, history[-1].role) != (
        "user",
        "assistant",
    ):
        return None
    previous = history[-2].content
    visible = " ".join(without_quotes(text).split())
    if date_edit := _PLAN_DATE_EDIT.fullmatch(visible):
        source = _source(previous, _BULLETIN) or _source(previous, _SOURCE_TEASER)
        return _bulletin(source, date_edit=date_edit) if source else None
    if _IMPERSONAL.fullmatch(visible) and (source := _source(previous, _BULLETIN)):
        return _bulletin(source)
    if (
        _REMOVE_CAP_WORD.fullmatch(visible)
        and single_quoted_operand(text) == "maksymalnie"
    ):
        if source := _source(previous, _CAP_COMMAND):
            return _capped(source, remove_word=True)
    return None


def publication_heading(text: str, history: Sequence[HistoryMessage]) -> str | None:
    """Add the requested heading without sending the existing text to a rewrite."""
    match = _HEADLINE.fullmatch(" ".join(text.split()))
    if not match or len(history) < 2:
        return None
    previous, answer = history[-2:]
    if (previous.role, answer.role) != ("user", "assistant"):
        return None
    source = _source(previous.content, _TEASER)
    if not source or not (check := _teaser(source)):
        return None
    topic = match["topic"].casefold()
    if not re.search(rf"\bw\s+{re.escape(topic)}\b", source, re.I):
        return None
    if check.publish(answer.content) != answer.content:
        return None
    return f"Terminy w {topic}\n\n{answer.content}"
