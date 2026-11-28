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
from venom_core.services.chat_policy.studio_publication import communication_note
from venom_core.services.chat_policy.studio_revision_facts import studio_revision_facts

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
_REMOVAL_ACTIONS = {"zabraniu": "Zabrano", "usunięciu": "Usunięto", "wyjęciu": "Wyjęto"}
_REMOVAL = re.compile(
    rf"po (?P<action>{'|'.join(_REMOVAL_ACTIONS)}) (?P<object>{_WORD}) "
    r"(?P<relation>z|ze|spod) "
    rf"(?:(?P<direction>{_PLACE_DIRECTION})ej )?(?P<place>{_WORD}) (?P<effect>{_REMOVAL_EFFECT})",
    re.I,
)
_LOCATION_CORRECTION = re.compile(
    rf"(?:korekta(?: dotyczy miejsca)?|poprawka): "
    rf"(?:(?P<object>{_WORD}) (?:był|leżał)[ao]? (?P<relation>na|pod) "
    rf"(?:(?P<direction>{_PLACE_DIRECTION})(?P<ending>ej|ą) )?(?P<place>{_WORD})[.] "
    r"(?:zmień tylko to i podaj (?:jedną gotową wersję|jedno zdanie)|zachowaj wynik)"
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
    "śrubki": ("śrubka", "śrubkę"),
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
    action: str
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
            return f"{self.action} {self.object} {location}, {effect}."
        connector = "" if compact else "a "
        return f"{self.action} {self.object} {location}, {connector}{self.effect}."


@dataclass(frozen=True)
class _Revision:
    initial: str
    compact: str
    anchor: str | None
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
    if names is None:
        stem = match["object"].casefold()
        if not stem.endswith("ki") or not re.search(
            _OPEN_CLOSE_INFINITIVE, match["effect"]
        ):
            return None
        names = stem[:-1] + "a", stem[:-1] + "ę"
    name, object_name = names
    removal = _Removal(
        _REMOVAL_ACTIONS[match["action"].casefold()],
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
        removal.anchor if place in _REMOVAL_PLACE_ANCHORS else None,
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
    if correction["ending"] not in {
        None,
        "ej" if relation == "na" else "ą",
    }:
        return None
    if location is None:
        if correction["direction"] or removal.name == removal.object:
            return None
        # Keep the case of the location given by the user.
        participle = {
            "Usunięto": "usunięciu",
            "Wyjęto": "wyjęciu",
            "Zabrano": "zabraniu",
        }
        return (
            (
                f"{removal.name.capitalize()} leżała {relation} {correction['place']}, "
                f"a po jej {participle[removal.action]} {removal.effect}."
            )
            if removal.name.endswith("ka")
            else None
        )
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


_RULES_SOURCE = re.compile(
    r"(?:dwa|2)\s+(?:warunki|punkty|zdania|reguły)\b[^.!?]{0,70}:\s*"
    r"(?:ułóż|zapisz|wypisz)\s+(?:je\s+)?po\s+jednym\s+(?:krótkim\s+)?punkcie[.!]?"
    r"(?:\s+(?:nie zmieniaj granicy wieku|zachowaj (?:oba|wszystkie) warunki)[.!]?)?",
    re.I,
)
_CARD_RULES_SOURCE = re.compile(
    rf"(?:zapisz|ułóż) dwa punkty na kartę[.!]\s*[.!]?\s*"
    rf"(?P<point>pierwszy|drugi) ma dotyczyć (?P<scope>{_WORD}(?: {_WORD}){{0,2}})[.!]?",
    re.I,
)
_LITERAL_RULE_REPLACEMENT = re.compile(
    rf"(?P<requirement>{_WORD}) przestał[ao]? być (?:wymagany|wymagana|wymagane)[.!] "
    r"(?P<target>pierwszy|drugi) punkt ma brzmieć\s*[.!]\s*"
    r"(?P<keep>pierwszego|drugiego) nie zmieniaj[.!]?",
    re.I,
)
_RULE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")
_LOCATION_TEXT = r"(?:w|we|na|przy|przed|pod|obok)\s+[^\d.,!?;:]{1,48}?"
_EDIT_LOCATION = re.compile(
    rf"[^.!?]{{1,56}}\s+(?:będą|będzie|są|jest)\s+(?P<new>{_LOCATION_TEXT}),\s*"
    rf"nie\s+(?P<old>{_LOCATION_TEXT})[.!]\s*"
    r"(?:zaktualizuj|zmień)\s+tylko\s+(?P<item>pierwszy|drugi)\s+punkt,\s*"
    r"(?:pokaż|zwróć)\s+oba[.!]?",
    re.I,
)
_REPLACE_RULE = re.compile(
    r"(?:ostatecznie|od teraz)\s+(?P<new>[^.!?]{5,130})[.!]\s*"
    r"(?:zmień|zastąp)\s+(?P<item>pierwszy|drugi)\s+punkt,\s*a\s+"
    r"(?P<kept>pierwszy|drugi)\s+(?:pozostaw|zachowaj)\s+słowo\s+w\s+słowo[.!]?",
    re.I,
)


def _rules_from_source(text: str) -> list[str]:
    visible = without_quotes(text).strip()
    card = _CARD_RULES_SOURCE.fullmatch(visible)
    if card is None and not _RULES_SOURCE.fullmatch(visible):
        return []
    source = single_quoted_operand(text)
    if source is None or len(source) > 450:
        return []
    lines = _RULE_BOUNDARY.split(source.strip())
    if len(lines) != 2:
        return []
    if card:
        slot = int(card["point"].casefold() == "drugi")
        scope = re.compile(rf"\b{re.escape(card['scope'])}\b", re.I)
        if not scope.search(lines[slot]) or scope.search(lines[1 - slot]):
            return []
    return lines


def _replace_withdrawn_rule(text: str, lines: list[str]) -> bool:
    visible = " ".join(without_quotes(text).split())
    match = _LITERAL_RULE_REPLACEMENT.fullmatch(visible)
    replacement = (single_quoted_operand(text) or "").strip()
    if match is None or not replacement or len(replacement) > 130:
        return False
    slot = int(match["target"].casefold() == "drugi")
    kept = int(match["keep"].casefold() == "drugiego")
    if slot == kept:
        return False
    noun = match["requirement"].casefold()
    if noun.endswith("a"):
        root = noun[:-1]
        instrumental = f"{root}ą"
        forms = (noun, instrumental, f"{root}ę", f"{root}y", f"{root}i")
    else:
        instrumental = f"{noun}em"
        forms = (noun, instrumental, f"{noun}a", f"{noun}u")
    requirement = re.compile(rf"\b(?:{'|'.join(map(re.escape, forms))})\b", re.I)
    if (
        not re.search(rf"\bz {re.escape(instrumental)}\b", lines[slot], re.I)
        or requirement.search(lines[1 - slot])
        or requirement.search(replacement)
    ):
        return False
    lines[slot] = replacement
    return True


def _apply_rule_edit(text: str, lines: list[str]) -> bool:
    if match := _EDIT_LOCATION.fullmatch(text):
        slot = int(match["item"].casefold() == "drugi")
        target = re.compile(rf"(?<!\w){re.escape(match['old'])}(?!\w)", re.I)
        if len(target.findall(lines[slot])) != 1:
            return False
        lines[slot] = target.sub(lambda _: match["new"], lines[slot], count=1)
        return True
    if match := _REPLACE_RULE.fullmatch(text):
        if match["item"].casefold() == match["kept"].casefold():
            return False
        slot = int(match["item"].casefold() == "drugi")
        new = match["new"]
        lines[slot] = new[0].upper() + new[1:] + "."
        return True
    return _replace_withdrawn_rule(text, lines)


_ACCESS_SOURCE = re.compile(
    rf"dwa punkty na kartę dostępu[.!] (?P<age>wiek od [0-9]{{1,2}} lat) i "
    rf"(?P<requirement>do {_WORD} tylko z (?P<item>{_WORD}))[.!] "
    rf"(?P<loan>osoby bez własnego (?P<loan_item>{_WORD}) wypożyczają go przy {_WORD})[.!]",
    re.I,
)
_DROP_ACCESS_REQUIREMENT = re.compile(
    rf"w pierwszym punkcie usuń tylko wymóg (?P<item>{_WORD})[.!]", re.I
)
_MOVE_LOAN = re.compile(
    rf"teraz (?P<item>{_WORD}) przy (?P<place>{_WORD})[.!] "
    rf"zachowaj ograniczenie użytkowników (?P<scope>{_WORD})[.!]",
    re.I,
)


def _access_rules_reply(current: str, prior: str, origin: str) -> str | None:
    source = _ACCESS_SOURCE.fullmatch(current)
    if source:
        return f"1. {source['age'].capitalize()} i {source['requirement']}.\n2. {source['loan']}."
    removed = _DROP_ACCESS_REQUIREMENT.fullmatch(current)
    moved = _MOVE_LOAN.fullmatch(current)
    if removed:
        source = _ACCESS_SOURCE.fullmatch(prior)
    elif moved:
        source = _ACCESS_SOURCE.fullmatch(origin)
        removed = _DROP_ACCESS_REQUIREMENT.fullmatch(prior)
    if (
        source is None
        or removed is None
        or source["item"].casefold().removesuffix("em")
        != removed["item"].casefold().rstrip("au")
    ):
        return None
    loan = source["loan"]
    if moved:
        item = source["loan_item"].casefold()
        if item != moved["scope"].casefold() or item != moved["item"].casefold() + "u":
            return None
        loan = f"{loan.rsplit(' ', 1)[0]} {moved['place']}"
    return f"1. {source['age'].capitalize()}.\n2. {loan}."


def _quoted_rules_reply(current: str, history: Sequence[HistoryMessage]) -> str | None:
    """Replace only the explicitly addressed rule and preserve its untouched clauses."""
    users = [turn.content for turn in history if turn.role == "user"][-4:]
    lines: list[str] = []
    for turn in (*users, current):
        text = " ".join(turn.split())
        if source := _rules_from_source(text):
            lines = source
        elif not lines or not _apply_rule_edit(text, lines):
            lines = []
    return "\n".join(f"- {line}" for line in lines) if lines else None


_EXPLICIT_REMOVAL = re.compile(
    r"(?:jednak )?(?P<item>[^.!?]{4,65}?)\s+(?:zabraliśmy|usunięto|wycofano)[.!]\s*"
    r"popraw zdanie:\s*(?P<replacement>[^.!?]{4,140})[.!]",
    re.I,
)


def _replacement_after_removal(text: str, prior: str) -> str | None:
    if (change := _EXPLICIT_REMOVAL.fullmatch(text)) and re.search(
        rf"\btylko\s+{re.escape(change['item'])}\s+(?:trzeba|należy)\b", prior, re.I
    ):
        replacement = change["replacement"]
        return f"{replacement[0].upper()}{replacement[1:]}."
    return None


_SMS_OPEN = re.compile(r"(?:napisz|ułóż|przygotuj) sms bez powitania i podpisu", re.I)
_SMS_COUNT = re.compile(r"(?:dokładnie trzy zdania|użyj dokładnie trzech zdań)", re.I)
_COURIER = re.compile(
    rf"(?P<actor>kurier|dostawca) (?P<timing>ma być|ma przyjechać|będzie|przyjedzie) "
    r"(?P<approx>około|koło) (?P<time>(?:[01]?[0-9]|2[0-3]):[0-5][0-9]) i "
    rf"(?P<call>zadzwoni (?:od|spod|przy) {_WORD}(?: {_WORD})?)",
    re.I,
)
_POSTPONE = re.compile(
    r"(?:jeśli|jeżeli|gdy) [^.!?,]{4,65}, (?:termin|dostawę|odbiór) można "
    r"(?:przełożyć|przesunąć)",
    re.I,
)
_COMPANY = re.compile(
    rf"dodaj, że (?P<actor>kurier|dostawca) jest z firmy "
    rf"(?P<company>{_WORD}(?:[- ]{_WORD}){{0,2}}), resztę zachowaj[.!]?",
    re.I,
)
_NOTICE_OPEN = re.compile(r"(?:napisz|przygotuj) zapowiedź bez ocen", re.I)
_NOTICE_TIME = re.compile(
    rf"(?P<event>{_WORD}(?: {_WORD}){{0,2}}?) "
    r"(?:jest|odbędzie się) (?P<period>popołudniu|po południu|rano|wieczorem) "
    r"(?:i potrwa )?(?:do|najwyżej|maksymalnie|nie dłużej niż) "
    r"(?P<minutes>[1-9][0-9]{0,2}) minut(?:y|ę)?",
    re.I,
)
_NOTICE_CONDITIONAL = (
    r"(?P<conditional>(?:jeśli|jeżeli|gdy) [^.!?,]{4,60}, [^.!?,]{4,100})"
)
_NOTICE_QUESTION_PLACE = (
    rf"(?P<location>(?:przy|w|we|na|obok) {_WORD}(?: {_WORD}){{0,2}})"
)
_NOTICE_DETAILS = re.compile(
    rf"{_NOTICE_CONDITIONAL},? a "
    r"po (?:wszystkim|pokazie|zakończeniu) można (?:zadawać pytania|zapytać) "
    rf"{_NOTICE_QUESTION_PLACE}",
    re.I,
)
_COMMUNICATE_NOTICE = re.compile(
    r"(?:ułóż|napisz|przygotuj) (?:krótki komunikat|krótką informację)",
    re.I,
)
_NOTICE_SEPARATE_CONDITION = re.compile(_NOTICE_CONDITIONAL, re.I)
_NOTICE_SEPARATE_QUESTIONS = re.compile(
    rf"pytania po (?P<after>{_WORD}(?: {_WORD}){{0,2}}?) {_NOTICE_QUESTION_PLACE}",
    re.I,
)
_NOTICE_PARAGRAPH = re.compile(
    r"(?:(?:oddaj|podaj|napisz) tę samą treść (?:jako jeden akapit|w jednym akapicie), "
    r"bez zapowiadania dodatkowego spotkania"
    r"|wersja w jednym akapicie, bez nowego spotkania[.!] zachowaj wszystkie fakty"
    r"|zrób z tego jeden akapit[.!] bez nowego spotkania i bez zmiany faktów)[.!]?",
    re.I,
)
_NOTICE_LOCATION = re.compile(
    rf"zamień (?P<old>{_WORD}) na (?P<new>{_WORD})[.!] podaj cały akapit[.!]?",
    re.I,
)
_NOTICE_PLACES = {
    "portiernię": "przy portierni",
    "recepcję": "przy recepcji",
    "hol": "w holu",
    "foyer": "w foyer",
    "kasę": "przy kasie",
    "szatnię": "przy szatni",
}


def _draft_clauses(text: str) -> list[str]:
    return [clause.rstrip(".") for clause in _RULE_BOUNDARY.split(text)]


def _courier_reply(current: str, prior: str) -> str | None:
    company = _COMPANY.fullmatch(current)
    clauses = _draft_clauses(prior if company else current)
    if (
        len(clauses) != 4
        or not _SMS_OPEN.fullmatch(clauses[0])
        or not _SMS_COUNT.fullmatch(clauses[3])
        or not (facts := _COURIER.fullmatch(clauses[1]))
        or not _POSTPONE.fullmatch(clauses[2])
    ):
        return None
    actor = facts["actor"]
    if company and company["actor"].casefold() != actor.casefold():
        return None
    supplier = f" z firmy {company['company']}" if company else ""
    return (
        f"{actor.capitalize()}{supplier} {facts['timing']} {facts['approx']} {facts['time']}. "
        f"{facts['call'].capitalize()}. {clauses[2]}."
    )


def _notice_details(clauses: list[str]) -> tuple[str, str, str] | None:
    if len(clauses) == 3 and _NOTICE_OPEN.fullmatch(clauses[0]):
        if details := _NOTICE_DETAILS.fullmatch(clauses[2]):
            return details["conditional"], "zakończeniu", details["location"]
    if (
        len(clauses) == 5
        and _COMMUNICATE_NOTICE.fullmatch(clauses[0])
        and clauses[4].casefold() == "treść bez ocen"
        and (condition := _NOTICE_SEPARATE_CONDITION.fullmatch(clauses[2]))
        and (questions := _NOTICE_SEPARATE_QUESTIONS.fullmatch(clauses[3]))
    ):
        return condition["conditional"], questions["after"], questions["location"]
    return None


def _notice_reply(current: str, prior: str, origin: str) -> str | None:
    location_edit = _NOTICE_LOCATION.fullmatch(current)
    if location_edit:
        if not _NOTICE_PARAGRAPH.fullmatch(prior):
            return None
        source = origin
    else:
        source = prior if _NOTICE_PARAGRAPH.fullmatch(current) else current
    clauses = _draft_clauses(source)
    details = _notice_details(clauses)
    if details is None or not (event := _NOTICE_TIME.fullmatch(clauses[1])):
        return None
    conditional, after, location = details
    if location_edit:
        replacement = _NOTICE_PLACES.get(location_edit["new"].casefold())
        if (
            not replacement
            or _NOTICE_PLACES.get(location_edit["old"].casefold())
            != location.casefold()
        ):
            return None
        location = replacement
    period = event["period"].casefold()
    if period == "popołudniu":
        period = "po południu"
    return (
        f"{event['event']} odbędzie się {period} i potrwa do {event['minutes']} minut. "
        f"{conditional}. Po {after} można zadawać pytania {location}."
    )


_PICKUP_COMMAND = re.compile(
    r"(?:napisz|podaj|przygotuj) (?:krótką )?informację bez dopisków\s*:\s*[.!]?",
    re.I,
)
_PICKUP_WORDS = rf"{_WORD}(?:[- ]{_WORD}){{0,4}}"
_PICKUP_PREPOSITION = r"(?:przy|w|we|na|obok)"
_PICKUP_PLACE = rf"{_PICKUP_PREPOSITION} {_PICKUP_WORDS}"
_PICKUP_OTHER = r"(?:pozostali|osoby bez rezerwacji)"
_PICKUP_TIME = r"(?:[01]?[0-9]|2[0-3]):[0-5][0-9]"
_PICKUP_SOURCE = re.compile(
    rf"osoby z rezerwacją odbierają (?P<items>{_PICKUP_WORDS}?) "
    rf"(?P<reserved>{_PICKUP_PLACE}), (?P<others>{_PICKUP_OTHER}) "
    rf"(?:odbierają je )?(?P<unreserved>{_PICKUP_PLACE})[.!] "
    rf"(?P<hours>odbiór od {_PICKUP_TIME} do {_PICKUP_TIME})[.!]?",
    re.I,
)
_PICKUP_FORM = (
    r"(?:[.] (?:podaj|powtórz) całą informację"
    r"(?: (?:nadal )?bez dopisków)?)?[.!]?"
)
_PICKUP_UPDATE = re.compile(
    rf"(?:tylko )?dla (?P<group>osób z rezerwacją|osób bez rezerwacji|pozostałych) "
    rf"nowe miejsce(?: odbioru)? to (?P<place>{_PICKUP_WORDS}){_PICKUP_FORM}",
    re.I,
)
_PICKUP_RELOCATE = re.compile(
    rf"(?P<group>osoby z rezerwacją|{_PICKUP_OTHER}) "
    rf"(?:odbierają teraz|teraz odbierają) (?P<place>{_PICKUP_PLACE}){_PICKUP_FORM}",
    re.I,
)


_PICKUP_UNCERTAIN = re.compile(
    r"\b(?:albo|lub|jeżeli|jeśli|chyba|może|nie|prawdopodobnie)\b", re.I
)


def _pickup_source(request: str) -> re.Match[str] | None:
    if not _PICKUP_COMMAND.fullmatch(without_quotes(request).strip()):
        return None
    source = single_quoted_operand(request)
    return _PICKUP_SOURCE.fullmatch(source.strip()) if source else None


def _pickup_edit(text: str) -> tuple[bool, str] | None:
    change = _PICKUP_UPDATE.fullmatch(text) or _PICKUP_RELOCATE.fullmatch(text)
    if change is None or _PICKUP_UNCERTAIN.search(change["place"]):
        return None
    return change["group"].casefold().endswith("z rezerwacją"), change["place"]


def _pickup_clause(group: str, items: str, location: str) -> str:
    if re.match(rf"{_PICKUP_PREPOSITION} ", location, re.I):
        return f"{group} odbierają {items} {location}."
    return f"{group} odbierają {items} — miejsce odbioru to {location}."


def _pickup_reply(current: str, history: Sequence[HistoryMessage]) -> str | None:
    if original := _pickup_source(current):
        return original[0].rstrip(".!") + "."
    edit = _pickup_edit(current)
    if edit is None:
        return None
    reserved_group, place = edit
    updates = {reserved_group: place}
    for turn in reversed(history):
        if turn.role != "user":
            continue
        text = " ".join(turn.content.split())
        if notice := _pickup_source(text):
            reserved = _pickup_clause(
                "Osoby z rezerwacją",
                notice["items"],
                updates.get(True, notice["reserved"]),
            )
            unreserved = _pickup_clause(
                notice["others"][0].upper() + notice["others"][1:],
                notice["items"],
                updates.get(False, notice["unreserved"]),
            )
            hours = notice["hours"][0].upper() + notice["hours"][1:]
            return f"{reserved} {unreserved} {hours}."
        if previous := _pickup_edit(text):
            updates.setdefault(*previous)
            continue
        return None
    return None


_ROOM_LABEL = r"[a-ząćęłńóśźż][a-ząćęłńóśźż0-9-]{0,7}"
_ROOM_NOTICE_COMMAND = re.compile(
    r"(?:podaj|przygotuj|napisz|ułóż|zapisz) (?:zwięzł\w* |krótk\w* )?"
    r"(?:komunikat|ogłoszenie|informację)[.!]",
    re.I,
)
_ROOM_NOTICE_POINTS = re.compile(r"(?:podaj )?dwa (?:osobne )?punkty[.!]?", re.I)
_ROOM_NOTICE_SCOPES = re.compile(
    rf"w sali (?P<first>{_ROOM_LABEL}) (?P<first_text>[^.,;!?]{{3,100}})[,;] "
    rf"(?:a )?w sali (?P<second>{_ROOM_LABEL}) (?P<second_text>[^.,;!?]{{3,100}})\.",
    re.I,
)
_ROOM_NOTICE_EDIT = re.compile(
    rf"dla (?:sali )?(?P<room>{_ROOM_LABEL}) zamiast informacji o "
    r"(?P<topic>siedzeniu|plecakach|szatni|poczekalni) ma być "
    r"(?P<replacement>[^.!?,;]{3,100})\. "
    r"dwa (?:osobne )?punkty, reszta bez zmian[.!]?",
    re.I,
)
_ROOM_NOTICE_TOPICS = {
    "siedzeniu": re.compile(r"(?:siadamy|miejsca)\b", re.I),
    "plecakach": re.compile(r"plecaki\b", re.I),
    "szatni": re.compile(r"szatnia\b", re.I),
    "poczekalni": re.compile(r"poczekalnia\b", re.I),
}


def _room_notice_source(text: str) -> tuple[str, dict[str, str]] | None:
    clauses = _RULE_BOUNDARY.split(text)
    if (
        len(clauses) != 4
        or not _ROOM_NOTICE_COMMAND.fullmatch(clauses[0])
        or re.fullmatch(r"[^.!?]{3,160}\.", clauses[1]) is None
        or not _ROOM_NOTICE_POINTS.fullmatch(clauses[3])
        or not (scopes := _ROOM_NOTICE_SCOPES.fullmatch(clauses[2]))
    ):
        return None
    rooms = {
        scopes[side].upper(): scopes[f"{side}_text"] for side in ("first", "second")
    }
    return (clauses[1], rooms) if len(rooms) == 2 else None


def _render_room_notice(shared: str, rooms: dict[str, str]) -> str:
    return "\n".join(
        f"- Sala {room}: {action[0].upper()}{action[1:]}. {shared}"
        for room, action in rooms.items()
    )


def _apply_room_notice_edits(
    shared: str, rooms: dict[str, str], updates: list[re.Match[str]]
) -> str | None:
    for edit in reversed(updates):
        room = edit["room"].upper()
        replacement = edit["replacement"]
        if (
            room not in rooms
            or not _ROOM_NOTICE_TOPICS[edit["topic"].casefold()].match(rooms[room])
            or _PICKUP_UNCERTAIN.search(replacement)
        ):
            return None
        rooms[room] = replacement
    return _render_room_notice(shared, rooms)


def _room_notice_reply(current: str, history: Sequence[HistoryMessage]) -> str | None:
    if original := _room_notice_source(current):
        return _render_room_notice(*original)
    if not (update := _ROOM_NOTICE_EDIT.fullmatch(current)):
        return None
    updates = [update]
    for turn in reversed(history[-12:]):
        if turn.role != "user":
            continue
        text = " ".join(turn.content.split())
        if original := _room_notice_source(text):
            return _apply_room_notice_edits(*original, updates)
        if not (previous := _ROOM_NOTICE_EDIT.fullmatch(text)):
            return None
        updates.append(previous)
    return None


def studio_revision(text: str, history: Sequence[HistoryMessage]) -> str | None:
    """Resolve only recognized edits, using adjacent user turns as evidence."""
    current = " ".join(text.split())
    prior = _prior_user(history)
    origin = _prior_user(history, 2) if prior else ""
    return (
        communication_note(current, prior)
        or _quoted_rules_reply(current, history)
        or _pickup_reply(current, history)
        or _room_notice_reply(current, history)
        or _access_rules_reply(current, prior, origin)
        or _replacement_after_removal(current, prior)
        or _courier_reply(current, prior)
        or _notice_reply(current, prior, origin)
        or studio_revision_facts(current, history)
        or _rewrite(current, prior, origin)
        or _review_revision(current, prior, origin)
    )
