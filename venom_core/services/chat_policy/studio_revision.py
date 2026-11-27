"""Bounded Studio revisions grounded in the user's original text."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from venom_core.api.schemas.llm_simple import HistoryMessage
from venom_core.services.chat_policy.qualified_chat_quote import (
    single_quoted_operand,
    without_quotes,
)
from venom_core.services.chat_policy.review_draft import parse_review_draft

_WORD = r"[^\W\d_]+"
_INITIAL_REWRITE = re.compile(
    r"(?P<command>uprość (?:to )?zdanie|skróć(?: (?:to )?zdanie)?)\s*:?\s*"
    r"(?:, bez zmiany przyczyny)?[.!]?"
    r"(?: (?:podaj (?:tylko )?(?:jeden tekst|jedną wersję|jedno zdanie)|tylko jedno zdanie|"
    r"nie dodawaj wyjaśnienia|jedna wersja|bez komentarza)[.!]?){0,2}",
    re.I,
)
_SHORTER = r"(?:napisz (?:jeszcze )?krócej|skróć jeszcze bardziej|podaj jeszcze krótszą wersję)"
_SHORTEN = re.compile(
    rf"(?:zachowaj (?P<before>{_WORD}(?: {_WORD})?) i {_SHORTER}"
    rf"|zachowaj (?P<separate>{_WORD}(?: {_WORD})?)[.] {_SHORTER}"
    rf"|{_SHORTER}(?: i zachowaj (?P<after>{_WORD}(?: {_WORD})?)(?: w zdaniu)?)?)"
    r"(?:, wyłącznie zdanie)?[.!]?(?: tylko jedna wersja bez komentarza[.!]?)?",
    re.I,
)
_KEEP_WORD = re.compile(
    r"zachowaj słowo w odpowiedniej odmianie[.] napisz krócej, tylko jedno zdanie[.]?",
    re.I,
)
_CHANGE = re.compile(
    rf"po (?P<event>(?:odsunięciu|otwarciu|zamknięciu) {_WORD}(?: {_WORD})?) "
    rf"(?P<place>w {_WORD}) zrobiło się (?P<result>jaśniej|ciemniej|cieplej|chłodniej)",
    re.I,
)
_FALL = re.compile(
    rf"po otwarciu (?P<opened>{_WORD}) z (?P<from>{_WORD}) "
    rf"(?P<result>spadł[ao]? {_WORD})",
    re.I,
)
_STOP_NOISE = re.compile(
    rf"po wyłączeniu (?P<device>{_WORD}) (?P<sound>szum|buczenie|brzęczenie) "
    rf"(?P<place>w {_WORD}) (?P<stopped>ustał|ustało)",
    re.I,
)
_SHELF = r"górn|doln|środkow"
_SHELF_REMOVAL = re.compile(
    rf"po zabraniu (?P<object>{_WORD}) z (?P<shelf>{_SHELF})ej półki "
    rf"(?P<subject>{_WORD}) przestał skrzypieć",
    re.I,
)
_SHELF_CORRECTION = re.compile(
    rf"(?:korekta|poprawka): (?P<object>{_WORD}) był[ao] na (?P<shelf>{_SHELF})ej półce[.] "
    r"zmień tylko to i podaj jedną gotową wersję[.]?",
    re.I,
)
_CHANGE_VERB = {
    "jaśniej": "pojaśniało",
    "ciemniej": "pociemniało",
    "cieplej": "ociepliło się",
    "chłodniej": "ochłodziło się",
}
_OPENED_ITEMS = {"drzwi": "drzwi", "okna": "okno"}
_FROM_OBJECTS = {"ławki": "ławka", "półki": "półka", "stołu": "stół"}
_DEVICES = {
    "projektora": "projektor",
    "silnika": "silnik",
    "wentylatora": "wentylator",
}
_LOCATIVE_OBJECTS = {
    "czytelni": "czytelnię",
    "korytarzu": "korytarz",
    "przejściu": "przejście",
    "sali": "salę",
    "świetlicy": "świetlicę",
}
_SHELF_OBJECTS = {
    "książki": ("książka", "książkę"),
    "płyty": ("płyta", "płytę"),
    "pudełka": ("pudełko", "pudełko"),
    "teczki": ("teczka", "teczkę"),
}
_WITHDRAW_FEEDBACK = re.compile(
    r"(?:(?:zrezygnuj|wycofuję) z prośby|wycofaj prośbę) o uwagi[.] "
    r"(?:(?:podaj|napisz) (?:tylko )?jedno zaproszenie bez dodatkowych poleceń"
    r"|zostaw samo zaproszenie do wspólnego przeglądu)[.]?",
    re.I,
)
_PLAN_INVITATION = re.compile(
    rf"{_WORD} (?:opracował[ao]?|sporządził[ao]?|przygotował[ao]?) "
    rf"(?P<topic>plan {_WORD}(?: {_WORD}){{0,4}})[.] "
    r"(?:na razie )?(?:możesz zaprosić|zaproś) (?:grupę|zespół) "
    r"do wspólnego przeglądu, bez zbierania opinii[.] "
    r"napisz (?:krótkie )?zaproszenie[.]?",
    re.I,
)
_PLAN_QUESTION = re.compile(
    r"(?:zamieniam zasadę: )?poproś (?:teraz )?(?:wprost )?o jedno krótkie pytanie do planu"
    r", nadal bez zbierania ogólnych opinii[.]?",
    re.I,
)
_RESTORE_INVITATION = re.compile(
    r"wycofuję prośbę o pytanie[.] "
    r"wracamy do samego zaproszenia w jednym zdaniu[.]?",
    re.I,
)
_TOPIC_CONNECTOR = re.compile(r"\b(?:i|lub|albo|oraz|bez|nie|tylko)\b", re.I)


@dataclass(frozen=True)
class _ShelfRemoval:
    original_name: str
    object: str
    shelf: str
    subject: str

    def render(self, *, compact: bool) -> str:
        result = "nie skrzypi" if compact else "przestał skrzypieć"
        return f"Zabrano {self.object} z {self.shelf}ej półki, {self.subject} {result}."


@dataclass(frozen=True)
class _Revision:
    initial: str
    compact: str
    anchor: str
    shelf: _ShelfRemoval | None = None


def _prior_user(history: Sequence[HistoryMessage], turns_back: int = 1) -> str:
    start = -2 * turns_back
    if len(history) < -start:
        return ""
    before, after = history[start], history[start + 1]
    if (before.role, after.role) != ("user", "assistant"):
        return ""
    return " ".join(before.content.split())


def _locative_anchor(place: str) -> str:
    noun = place.casefold().split()[1]
    return _LOCATIVE_OBJECTS.get(noun, noun)


def _source_revision(source: str) -> _Revision | None:
    if change := _CHANGE.fullmatch(source):
        event = change["event"]
        place_name = change["place"].split()[1]
        result = change["result"].casefold()
        return _Revision(
            f"W {place_name} zrobiło się {result} po {event}.",
            f"Po {event} w {place_name} {_CHANGE_VERB[result]}.",
            _locative_anchor(change["place"]),
        )
    if (fall := _FALL.fullmatch(source)) and (
        opened := _OPENED_ITEMS.get(fall["opened"].casefold())
    ):
        location = fall["from"]
        return _Revision(
            f"Z {location} {fall['result']} po otwarciu {fall['opened']}.",
            f"Otwarto {opened}, z {location} {fall['result']}.",
            _FROM_OBJECTS.get(location.casefold(), location.casefold()),
        )
    if noise := _STOP_NOISE.fullmatch(source):
        device = _DEVICES.get(noise["device"].casefold())
        if device is None:
            return None
        stopped = "ustał" if noise["sound"].casefold() == "szum" else "ustało"
        result = f"{noise['sound']} {noise['place']} {stopped}."
        return _Revision(
            f"Wyłączono {device}, a {result}",
            f"Wyłączono {device}, {result}",
            _locative_anchor(noise["place"]),
        )
    if removal := _SHELF_REMOVAL.fullmatch(source):
        names = _SHELF_OBJECTS.get(removal["object"].casefold())
        if names is None:
            return None
        name, object_name = names
        shelf = removal["shelf"].casefold()
        event = _ShelfRemoval(name, object_name, shelf, removal["subject"])
        return _Revision(
            event.render(compact=False),
            event.render(compact=True),
            f"{shelf}ą półkę",
            event,
        )
    return None


def _revision_for_request(request: str) -> _Revision | None:
    source = single_quoted_operand(request)
    if not source or len(source) > 200:
        return None
    command = _INITIAL_REWRITE.fullmatch(" ".join(without_quotes(request).split()))
    if command is None:
        return None
    source = " ".join(source.split()).rstrip(".")
    revision = _source_revision(source)
    if revision and command["command"].casefold().startswith("skróć"):
        if len(revision.initial.rstrip(".")) >= len(source):
            return None
    return revision


def _compatible_shortening(text: str, revision: _Revision) -> bool:
    if instruction := _SHORTEN.fullmatch(text):
        protected = (
            instruction["before"] or instruction["separate"] or instruction["after"]
        )
        return protected is None or protected.casefold() == revision.anchor
    if _KEEP_WORD.fullmatch(" ".join(without_quotes(text).split())):
        operand = single_quoted_operand(text)
        return operand is not None and operand.casefold() == revision.anchor
    return False


def _rewrite(text: str, prior: str, origin: str) -> str | None:
    if revision := _revision_for_request(text):
        return revision.initial
    if (revision := _revision_for_request(prior)) and _compatible_shortening(
        text, revision
    ):
        return revision.compact
    if correction := _SHELF_CORRECTION.fullmatch(text):
        revision = _revision_for_request(origin)
        if (
            revision is not None
            and (shelf := revision.shelf) is not None
            and shelf.original_name == correction["object"].casefold()
            and _compatible_shortening(prior, revision)
        ):
            return _ShelfRemoval(
                shelf.original_name,
                shelf.object,
                correction["shelf"].casefold(),
                shelf.subject,
            ).render(compact=True)
    return None


def _plan_topic(request: str) -> str | None:
    match = _PLAN_INVITATION.fullmatch(request)
    if match is None or _TOPIC_CONNECTOR.search(match["topic"]):
        return None
    return match["topic"]


def _review_revision(text: str, prior: str, origin: str) -> str | None:
    if _WITHDRAW_FEEDBACK.fullmatch(text):
        review = parse_review_draft(prior)
        if review is not None and review.requested_feedback:
            return review.invitation()
    if _PLAN_QUESTION.fullmatch(text) and _plan_topic(prior):
        return "Proszę o jedno krótkie pytanie do planu."
    if _RESTORE_INVITATION.fullmatch(text) and _PLAN_QUESTION.fullmatch(prior):
        if topic := _plan_topic(origin):
            return f"Proponuję wspólny przegląd planu{topic[4:]}."
    return None


def studio_revision(text: str, history: Sequence[HistoryMessage]) -> str | None:
    """Resolve only recognized edits, using adjacent user turns as evidence."""
    current = " ".join(text.split())
    prior = _prior_user(history)
    origin = _prior_user(history, 2) if prior else ""
    return _rewrite(current, prior, origin) or _review_revision(current, prior, origin)
