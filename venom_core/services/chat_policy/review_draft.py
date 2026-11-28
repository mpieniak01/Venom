"""Validate short review invitations against the current request."""

from __future__ import annotations

import re
from dataclasses import dataclass

from venom_core.services.chat_policy.qualified_chat_quote import (
    single_quoted_operand,
    without_quotes,
)

_INVITATION = r"(?:przygotuj|napisz|ułóż) krótką wiadomość (?:dla|do) "
_AUDIENCE = r"(?P<audience>zespołu|grupy|współpracowników|koleżanki|kolegi)"
_TOPIC = r"(?P<topic>[a-ząćęłńóśźż]+(?: [a-ząćęłńóśźż]+){1,5})"
_REQUEST = re.compile(
    rf"{_INVITATION}{_AUDIENCE}"
    rf"(?:\. chodzi o wspólny przegląd| o wspólnym przeglądzie) {_TOPIC}"
    r"(?:, ale (?:jeszcze nie chcę ustalać kiedy|na razie bez ustalania terminu)"
    r"|\. (?:na razie )?bez ustalania terminu)\.",
    re.I,
)
_TOPIC_HEAD = {
    "szkicu": "szkic",
    "projektu": "projekt",
    "planu": "plan",
    "tekstu": "tekst",
    "notatki": None,
    "wersji": None,
    "konspektu": "konspekt",
    "opisu": "opis",
    "harmonogramu": "harmonogram",
}
_TOPIC_MODIFIERS = re.compile(
    r"\b(?:jeśli|chyba|i|oraz|albo|lub|który|która|które|żeby|aby|dziś|jutro|później|"
    r"wkrótce|wysłać|prześlij|sprawdź|dopisz)\b",
    re.I,
)
_FEEDBACK_REQUEST = re.compile(
    r"(?<=\. )poproś wprost o (?P<feedback>(?:krótkie )?uwagi do (?P<head>\w+))\.",
    re.I,
)
_PENDING_PDF = re.compile(
    r"pdf z kartą (?P<label>[a-ząćęłńóśźż]+(?: [a-ząćęłńóśźż]+){0,3}) mam gotowy, "
    r"ale jeszcze nie jest dołączony ani wysłany\. "
    r"napisz do zespołu krótką wiadomość z zaproszeniem do wspólnego przeglądu karty\. "
    r"powiedz, że plik mogę dołączyć po ich zgodzie\. bez ustalania terminu\.",
    re.I,
)
_GREETING = re.compile(r"^(cześć wszystkim|cześć|hej|dzień dobry)[,!]\s+")
_NO_DATE_SENTENCE = " na razie bez ustalania terminu."
_UNSUPPORTED_ADDITION = re.compile(
    r"\b(?:przygotowa(?:łem|łam|liśmy|łyśmy)|opracowa(?:łem|łam|liśmy|łyśmy)|"
    r"mój|moja|moje|naszego|naszej|zespołowy|ustalimy|ustalę|umówimy|umówię|"
    r"niedługo|wkrótce|jutro|pojutrze|dzisiaj|w (?:poniedziałek|piątek|sobotę|"
    r"przyszłym tygodniu)|za (?:tydzień|miesiąc)|o \d{1,2}(?::\d{2})?|"
    r"dajcie znać|daj znać|odezwę się|powiadomię|wyślę|przyślę|przesyłam|"
    r"wrócimy do tematu|potwierdźcie|bo|ponieważ|gdyż|z powodu|ze względu na)\b"
)
_SENDING = (
    r"(?:przesyłam|wysyłam|dołączam|załączam|udostępniam|przesłałem|przesłałam|"
    r"wysłałem|wysłałam|dołączyłem|dołączyłam|załączyłem|załączyłam|w załączniku znajdziecie)"
)
_FEEDBACK = (
    r"(?:zgłoś(?:cie)? (?:uwagi|komentarze)|"
    r"proszę o (?:(?:wasze|twoje) )?(?:(?:krótkie|zwięzłe) )?"
    r"(?:uwagi|opinie|komentarze|feedback|(?:zgłoszenie|przesłanie) uwag)|"
    r"daj(?:cie)? znać,? (?:czy (?:macie|masz|widzicie|widzisz) "
    r"(?:\w+ ){0,5}(?:uwagi|opinie|komentarze|zastrzeżenia)|"
    r"co (?:(?:\w+ ){0,3}myśl(?:isz|icie)|poprawić|zmienić))|"
    r"zgłaszanie (?:ewentualnych )?(?:uwag|komentarzy))"
)
_FEEDBACK_TARGET = re.compile(
    r"^ do (?P<target>[a-ząćęłńóśźż]+(?: [a-ząćęłńóśźż]+){0,5})"
)
_AVAILABILITY = r"daj(?:cie)? znać,? (?:kiedy|w jakim terminie)"
_SET_DATE = r"(?:ustalimy|ustalę|uzgodnimy|uzgodnię|umówimy|umówię)"
_FOLLOW_UP = (
    r"(?:dam(?:y)? znać|będ(?:ę|ziemy) (?:dawać|dawali|dawały) znać|"
    r"odezw(?:ę|iemy) się|powiadomi(?:ę|my) (?:was|cię|zespół)|"
    r"wróc(?:ę|imy) (?:do was |do ciebie )?z propozycj(?:ą|ami))"
)
_AUTHOR = r"(?:przygotowa(?:łem|łam|liśmy|łyśmy)|opracowa(?:łem|łam|liśmy|łyśmy))"
_TRANSFER_PROMISE = r"(?:dołącz(?:ę|ymy)|prześl(?:ę|emy)|wyśl(?:ę|emy)|załącz(?:ę|ymy))"
_INITIAL_ADDITION = re.compile(
    rf"\b(?:(?P<feedback>{_FEEDBACK})|(?P<transfer>{_SENDING}|{_TRANSFER_PROMISE})"
    rf"|(?P<author>{_AUTHOR})|(?P<follow_up>{_FOLLOW_UP})|"
    rf"(?P<schedule>{_AVAILABILITY}|termin(?:u)? (?:\w+ ){{0,3}}{_SET_DATE}|"
    rf"{_SET_DATE} (?:\w+ ){{0,3}}termin(?:u)?))\b"
)
_REVIEW_INTENT = re.compile(
    r"\b(?:wspóln\w+ przegląd\w*|wspólnie przejrz\w+|przejrz\w+ wspólnie)\b"
)
_PDF_PERMISSION = re.compile(
    r"\b(?:mogę dołączyć(?: (?:plik|pdf|dokument))? po (?:waszej |uzyskaniu waszej )?zgodzie|"
    r"po (?:waszej |uzyskaniu waszej )?zgodzie mogę dołączyć (?:plik|pdf|dokument))\b"
)
_CLAUSE_BOUNDARY = re.compile(
    r"[.!?;\n–—]+|,\s*(?:ale|lecz|jednak)\s+"
    rf"|(?:,\s*|\s+(?:a|i|oraz)\s+)(?=(?:(?:a|i|oraz)\s+)?(?:{_SENDING}|{_FEEDBACK}|{_AVAILABILITY}|{_FOLLOW_UP})\b)"
)
_NEGATION = re.compile(r"\b(?:nie|bez|ani)\b")
_DRAFT_PREFACE = re.compile(
    r"(?:oto wiadomość|oto propozycja wiadomości|propozycja wiadomości):"
)
REVIEW_RETRY_INSTRUCTION = (
    "Podaj wyłącznie jedno krótkie zdanie zapraszające do wspólnego przeglądu "
    "dokładnie wskazanego przedmiotu. Nie dopisuj autorstwa, terminu, prośby "
    "o opinię, powodu ani zobowiązania. Zaczynaj od «Proponuję wspólny przegląd»."
)


@dataclass(frozen=True)
class ReviewDraft:
    audience: str
    topic: str
    object_topic: str | None
    check_initial: bool = True
    requested_feedback: str | None = None
    pending_pdf: bool = False

    def invitation(self) -> str:
        return f"Proponuję wspólny przegląd {self.topic}."

    def _minimum(self) -> str:
        invitation = self.invitation()
        if self.requested_feedback:
            return f"{invitation} Proszę o {self.requested_feedback}."
        if self.pending_pdf:
            return f"{invitation} Plik PDF mogę dołączyć po Waszej zgodzie."
        return invitation

    def _checks_explicit_state(self) -> bool:
        return self.requested_feedback is not None or self.pending_pdf

    def publish_initial(self, draft: str) -> str:
        """Repair an explicit addition and preserve other first drafts as received."""
        if not self.check_initial or self._matches(draft):
            return draft
        text = draft.casefold().strip()
        visible = without_quotes(text)
        surrounding = " ".join(visible.split())
        if not surrounding or _DRAFT_PREFACE.fullmatch(surrounding):
            visible = single_quoted_operand(text) or visible
        feedback_present = False
        for raw in _CLAUSE_BOUNDARY.split(visible):
            clause = " ".join(raw.split())
            for match in _INITIAL_ADDITION.finditer(clause):
                if _NEGATION.search(clause, 0, match.end()):
                    continue
                if match.lastgroup == "feedback" and self.requested_feedback:
                    target = _FEEDBACK_TARGET.match(clause[match.end() :])
                    expected = self.requested_feedback.partition(" do ")[2]
                    if target and target["target"] not in {
                        expected,
                        self.topic.casefold(),
                    }:
                        return self._minimum()
                    brief = self.requested_feedback.startswith("krótkie ")
                    feedback_present |= not brief or bool(
                        re.search(r"\b(?:krótkie|zwięzłe)\b", match[0])
                    )
                else:
                    return self._minimum()
        if self._checks_explicit_state():
            names = (
                self.topic.casefold(),
                (self.object_topic or self.topic).casefold(),
            )
            if not _REVIEW_INTENT.search(visible) or not any(
                name in visible for name in names
            ):
                return self._minimum()
        if self.requested_feedback and not feedback_present:
            return self._minimum()
        if self.pending_pdf and not _PDF_PERMISSION.search(" ".join(visible.split())):
            return self._minimum()
        return draft

    def publish_retry(self, draft: str) -> str | None:
        """Return the original or a grounded minimum after a recognized addition."""
        if self._checks_explicit_state():
            return self.publish_initial(draft)
        if self._matches(draft):
            return draft
        if _UNSUPPORTED_ADDITION.search(draft.casefold()):
            return self._minimum()
        return None

    def _matches(self, draft: str) -> bool:
        text = " ".join(draft.casefold().split()).strip('„”"')
        greeting = _GREETING.match(text)
        if greeting:
            if greeting[1] == "cześć wszystkim" and self.audience in {
                "koleżanki",
                "kolegi",
            }:
                return False
            text = text[greeting.end() :]
        text = text.removesuffix(_NO_DATE_SENTENCE)
        topic = self.topic.casefold()
        if self._checks_explicit_state():
            return False
        if text in {
            f"proponuję wspólny przegląd {topic}.",
            f"chciałbym zaproponować wspólny przegląd {topic}.",
            f"chciałabym zaproponować wspólny przegląd {topic}.",
        }:
            return True
        if self.object_topic is None:
            return False
        obj = self.object_topic.casefold()
        return text in {
            f"proponuję, żebyśmy wspólnie przejrzeli {obj}.",
            f"proponuję, abyśmy wspólnie przejrzeli {obj}.",
            f"przejrzyjmy wspólnie {obj}.",
            f"czy możemy wspólnie przejrzeć {obj}?",
        }


def parse_review_draft(
    request: str, *, check_initial: bool = True
) -> ReviewDraft | None:
    if len(request) > 340:
        return None
    text = " ".join(request.split())
    if check_initial and (pending := _PENDING_PDF.fullmatch(text)) is not None:
        label = pending["label"]
        if not _TOPIC_MODIFIERS.search(label):
            return ReviewDraft(
                "zespołu", f"karty {label}", f"kartę {label}", pending_pdf=True
            )
        return None
    feedback = list(_FEEDBACK_REQUEST.finditer(text)) if check_initial else []
    if len(feedback) > 1:
        return None
    if feedback:
        text = " ".join(_FEEDBACK_REQUEST.sub("", text).split())
    if len(text) > 260:
        return None
    match = _REQUEST.fullmatch(text)
    if match is None:
        return None
    topic = match["topic"]
    head, tail = topic.split(" ", 1)
    head = head.casefold()
    if head not in _TOPIC_HEAD or _TOPIC_MODIFIERS.search(topic):
        return None
    if feedback and feedback[0]["head"].casefold() != head:
        return None
    object_head = _TOPIC_HEAD[head]
    object_topic = f"{object_head} {tail}" if object_head else None
    return ReviewDraft(
        match["audience"].casefold(),
        topic,
        object_topic,
        check_initial,
        feedback[0]["feedback"].casefold() if feedback else None,
    )
