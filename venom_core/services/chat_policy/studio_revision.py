"""Bounded Studio revisions grounded in the user's original text."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace

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
    r"nie dodawaj wyjaśnienia|jedna wersja|bez komentarza)[.!]?){0,2}"
    r"(?: (?P<keep_sounds>zachowaj oba dźwięki i miejsce), podaj jedno zdanie[.!]?)?",
    re.I,
)
_SHORTER = r"(?:napisz (?:jeszcze )?krócej|skróć (?:zdanie )?jeszcze bardziej|podaj jeszcze krótszą wersję)"
_SHORTEN = re.compile(
    rf"(?:zachowaj (?P<before>{_WORD}(?: {_WORD})?)(?: i|, (?:ale|lecz)) {_SHORTER}"
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
_SOUND_SWITCHES = {
    "odłączeniu": ("Odłączono", "odłączenie"),
    "wyłączeniu": ("Wyłączono", "wyłączenie"),
}
_STOP_NOISE = re.compile(
    rf"po (?P<switch>{'|'.join(_SOUND_SWITCHES)}) (?P<device>{_WORD}) "
    r"(?P<sound>(?:(?:jego|jej) )?(?:szum|buczenie|brzęczenie)) "
    rf"(?P<place>w {_WORD}) (?P<stopped>ustał|ustało)"
    rf"(?:, a (?P<continuing>{_WORD} (?:nadal|wciąż) (?:tykał|brzęczał|stukał|buczał)[ao]?))?",
    re.I,
)
_SHORTEN_SOUNDS = re.compile(
    rf"{_SHORTER}, zachowując (?P<action>(?:odłączenie|wyłączenie) {_WORD}) i oba dźwięki[.!]?",
    re.I,
)
_PLACE_DIRECTION = r"górn|doln|środkow|lew|praw"
_OPEN_CLOSE_INFINITIVE = r"(?:domknąć|zamknąć|otworzyć)"
_OPEN_CLOSE_MODAL = r"(?:dał[ayo]?|dawał[ayo]?)"
_OPEN_CLOSE_EVENT = r"(?:domknął|domknęł[ayo]|zamknął|zamknęł[ayo]|otworzył[ayo]?)"
_REMOVAL_EFFECT = (
    rf"{_WORD} przestał skrzypieć"
    rf"|(?:reszta|część) {_WORD} się zmieściła"
    rf"|{_WORD} (?:nie )?{_OPEN_CLOSE_MODAL} się {_OPEN_CLOSE_INFINITIVE}"
    rf"|(?:nie )?(?:można było|dało się) {_OPEN_CLOSE_INFINITIVE} {_WORD}"
    rf"|{_WORD} (?:nie )?(?:się {_OPEN_CLOSE_EVENT}|{_OPEN_CLOSE_EVENT} się)"
)
_REMOVAL = re.compile(
    rf"po zabraniu (?P<object>{_WORD}) (?P<relation>z|ze|spod) "
    rf"(?:(?P<direction>{_PLACE_DIRECTION})ej )?(?P<place>{_WORD}) (?P<effect>{_REMOVAL_EFFECT})",
    re.I,
)
_LOCATION_CORRECTION = re.compile(
    rf"(?:korekta|poprawka): (?:(?P<object>{_WORD}) był[ao]? (?P<relation>na|pod) "
    rf"(?:(?P<direction>{_PLACE_DIRECTION})(?P<ending>ej|ą) )?(?P<place>{_WORD})[.] "
    r"zmień tylko to i podaj (?:jedną gotową wersję|jedno zdanie)"
    rf"|była to (?P<relative_direction>{_PLACE_DIRECTION})a (?P<relative_place>ławka|półka)[.] "
    r"zmień tylko położenie)[.]?",
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
    "pompy": "pompę",
    "projektora": "projektor",
    "radia": "radio",
    "silnika": "silnik",
    "wentylatora": "wentylator",
}
_LOCATIVE_OBJECTS = {
    "czytelni": "czytelnię",
    "korytarzu": "korytarz",
    "przejściu": "przejście",
    "pracowni": "pracownię",
    "sali": "salę",
    "świetlicy": "świetlicę",
}
_REMOVED_ITEMS = {
    "kartki": ("kartka", "kartkę"),
    "książki": ("książka", "książkę"),
    "płyty": ("płyta", "płytę"),
    "pudełka": ("pudełko", "pudełko"),
    "stołka": ("stołek", "stołek"),
    "teczki": ("teczka", "teczkę"),
    "torby": ("torba", "torbę"),
}
_REMOVAL_PLACE_ANCHORS = {
    "blatu": "blat",
    "ławki": "ławkę",
    "okna": "okno",
    "półki": "półkę",
    "regału": "regał",
    "stołu": "stół",
}
_LOCATION_UPDATES = {
    ("na", "blacie"): ("z", "blatu"),
    ("na", "ławce"): ("z", "ławki"),
    ("na", "półce"): ("z", "półki"),
    ("na", "stole"): ("ze", "stołu"),
    ("pod", "ławką"): ("spod", "ławki"),
    ("pod", "oknem"): ("spod", "okna"),
    ("pod", "półką"): ("spod", "półki"),
    ("pod", "regałem"): ("spod", "regału"),
    ("pod", "stołem"): ("spod", "stołu"),
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
class _Removal:
    name: str
    object: str
    relation: str
    place: str
    direction: str
    effect: str

    @property
    def anchor(self) -> str:
        modifier = f"{self.direction}ą " if self.direction else ""
        return modifier + _REMOVAL_PLACE_ANCHORS[self.place]

    def render(self, *, compact: bool) -> str:
        modifier = f"{self.direction}ej " if self.direction else ""
        location = f"{self.relation} {modifier}{self.place}"
        subject, creaks, _ = self.effect.partition(" przestał skrzypieć")
        if creaks:
            effect = f"{subject} nie skrzypi" if compact else self.effect
            return f"Zabrano {self.object} {location}, {effect}."
        connector = "" if compact else "a "
        return f"Zabrano {self.object} {location}, {connector}{self.effect}."


@dataclass(frozen=True)
class _Revision:
    initial: str
    compact: str
    anchor: str
    removal: _Removal | None = None
    sound_action: str = ""


def _sound_revision(noise: re.Match[str]) -> _Revision | None:
    device_source = noise["device"].casefold()
    device = _DEVICES.get(device_source)
    if device is None:
        return None
    verb, action = _SOUND_SWITCHES[noise["switch"].casefold()]
    first_effect = f"{noise['sound']} {noise['place']} {noise['stopped']}"
    anchor = _locative_anchor(noise["place"])
    if continuing := noise["continuing"]:
        return _Revision(
            f"{verb} {device}, {first_effect}, a {continuing}.",
            f"{verb} {device}, {first_effect}, {continuing}.",
            anchor,
            sound_action=f"{action} {device_source}",
        )
    return _Revision(
        f"{verb} {device}, a {first_effect}.",
        f"{verb} {device}, {first_effect}.",
        anchor,
    )


def _removal_revision(match: re.Match[str]) -> _Revision | None:
    names = _REMOVED_ITEMS.get(match["object"].casefold())
    place = match["place"].casefold()
    if names is None or place not in _REMOVAL_PLACE_ANCHORS:
        return None
    name, object_name = names
    removal = _Removal(
        name,
        object_name,
        match["relation"].casefold(),
        place,
        (match["direction"] or "").casefold(),
        match["effect"],
    )
    return _Revision(
        removal.render(compact=False),
        removal.render(compact=True),
        removal.anchor,
        removal=removal,
    )


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
        return _sound_revision(noise)
    if removal := _REMOVAL.fullmatch(source):
        return _removal_revision(removal)
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
    if revision is None or (command["keep_sounds"] and not revision.sound_action):
        return None
    if command["command"].casefold().startswith("skróć"):
        if len(revision.initial.rstrip(".")) >= len(source):
            return None
    return revision


def _compatible_shortening(text: str, revision: _Revision) -> bool:
    if sounds := _SHORTEN_SOUNDS.fullmatch(text):
        return sounds["action"].casefold() == revision.sound_action
    if instruction := _SHORTEN.fullmatch(text):
        protected = (
            instruction["before"] or instruction["separate"] or instruction["after"]
        )
        return protected is None or protected.casefold() == revision.anchor
    if _KEEP_WORD.fullmatch(" ".join(without_quotes(text).split())):
        operand = single_quoted_operand(text)
        return operand is not None and operand.casefold() == revision.anchor
    return False


def _correct_removal(correction: re.Match[str], prior: str, origin: str) -> str | None:
    revision = _revision_for_request(prior)
    compact = revision is None
    if compact:
        revision = _revision_for_request(origin)
        if revision is None or not _compatible_shortening(prior, revision):
            return None
    if revision is None or revision.removal is None:
        return None
    removal = revision.removal
    if relative_place := correction["relative_place"]:
        if {"ławka": "ławki", "półka": "półki"}[
            relative_place.casefold()
        ] != removal.place:
            return None
        return replace(
            removal, direction=correction["relative_direction"].casefold()
        ).render(compact=compact)
    if removal.name != correction["object"].casefold():
        return None
    relation = correction["relation"].casefold()
    location = _LOCATION_UPDATES.get((relation, correction["place"].casefold()))
    if location is None or correction["ending"] not in {
        None,
        "ej" if relation == "na" else "ą",
    }:
        return None
    source_relation, place = location
    return replace(
        removal,
        relation=source_relation,
        place=place,
        direction=(correction["direction"] or "").casefold(),
    ).render(compact=compact)


def _rewrite(text: str, prior: str, origin: str) -> str | None:
    if revision := _revision_for_request(text):
        return revision.initial
    if (revision := _revision_for_request(prior)) and _compatible_shortening(
        text, revision
    ):
        return revision.compact
    if correction := _LOCATION_CORRECTION.fullmatch(text):
        return _correct_removal(correction, prior, origin)
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
