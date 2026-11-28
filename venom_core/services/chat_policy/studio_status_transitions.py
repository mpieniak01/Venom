"""Resolve successive, source-backed changes in duty and message status."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

_DAY = {
    "poniedziałkowego": "w poniedziałek",
    "wtorkowego": "we wtorek",
    "środowego": "w środę",
    "czwartkowego": "w czwartek",
    "piątkowego": "w piątek",
    "sobotniego": "w sobotę",
    "niedzielnego": "w niedzielę",
}
_DAY_NAMES = {
    "poniedziałek": "w poniedziałek",
    "wtorek": "we wtorek",
    "środę": "w środę",
    "czwartek": "w czwartek",
    "piątek": "w piątek",
    "sobotę": "w sobotę",
    "niedzielę": "w niedzielę",
}
_PERSON = r"[^\W\d_]+(?:-[^\W\d_]+)?"
_TIME = r"(?:[01]?[0-9]|2[0-3]):[0-5][0-9]"
_DUTY_STATUS = (
    r"jak (?:opisać|zapisać) stan w jednym zdaniu[.?]|"
    r"(?:podaj|zapisz) stan w jednym zdaniu[.!]?"
)
_SIGNUP = re.compile(
    rf"(?:w [^.!?]{{2,54}}? )?(?P<name>{_PERSON}) "
    r"(?:podpisał[ao]? się na liście|wpisał[ao]? się na listę|jest na liście) "
    rf"osób chętnych do (?P<day>{'|'.join(_DAY)}) dyżuru[.!] "
    r"(?:na|w) grafiku przy (?:jego|jej) imieniu (?:jest|widnieje) puste pole[.!] "
    r"(?:(?:w mailu|w wiadomości) do [^\W\d_]+ )?(?:czy )?mogę napisać, że "
    rf"(?P<asked>{_PERSON}) ma dyżur\?",
    re.I,
)
_ASSIGN = re.compile(
    r"(?:(?:lider(?:ka)?|koordynator(?:ka)?|opiekun(?:ka)?|"
    r"kierownik|kierowniczka|organizator(?:ka)?) wpisał[ao]?|wpisano) "
    rf"(?P<name>{_PERSON})(?: do grafiku)? "
    rf"(?:(?:na|w|we) (?P<day>{'|'.join(_DAY_NAMES)}) )?"
    rf"(?:na|o) (?P<time>{_TIME})"
    r"(?:, (?:on|ona) (?:jeszcze )?(?:tego |go )?nie potwierdził[ao]?|"
    r"\. (?:on|ona) (?:jeszcze )?(?:tego |go )?nie potwierdził[ao]?|"
    r" i (?:on|ona) (?:już )?(?:to )?(?P<confirmed>potwierdził[ao]?))"
    rf"[.!] (?:{_DUTY_STATUS})",
    re.I,
)
_PARTIAL_APPROVAL = re.compile(
    r"(?:zatwierdził[ae]m|zaakceptował[ae]m) do wysłania "
    r"(?:[^\W\d_]+ )?tylko (?:informację|wiadomość|wzmiankę) o "
    r"(?P<place>(?:miejscu|adresie|lokalizacji) [^.!?,]{2,60}), "
    r"(?:bo|ponieważ|a) godzina (?P<activity>dojazdu|przyjazdu|spotkania|odbioru|rozpoczęcia) "
    r"(?:jeszcze się waży|nie jest jeszcze ustalona|jeszcze nie jest ustalona|"
    r"nie została jeszcze ustalona|nadal jest nieustalona)[.!] "
    r"czy w tabeli mogę (?:napisać|wpisać) [„\"]pełny komunikat zatwierdzony[”\"]\?",
    re.I,
)
_DUE_TIME = {
    "dojazdu": "dojazd",
    "przyjazdu": "przyjazd",
    "spotkania": "spotkanie",
    "odbioru": "odbiór",
    "rozpoczęcia": "rozpoczęcie",
}
_COMPLETE_APPROVAL = re.compile(
    r"(?:(?:teraz|już) )?ustaliliśmy "
    rf"(?P<activity>{'|'.join(_DUE_TIME.values())}) (?:na|o) (?P<time>{_TIME}) "
    r"i (?:akceptuję|zatwierdzam) (?:oba elementy|obie informacje)[.!] "
    r"(?:nikt jeszcze nie wysłał|komunikatu jeszcze nie wysłano|"
    r"wysyłka jeszcze nie nastąpiła)[.!] (?:daj|podaj|zapisz) status do tabeli[.!]?",
    re.I,
)
_DISPATCH = re.compile(
    r"w (?:historii|rejestrze|logu) "
    r"(?:widzę (?:wysłany komunikat|wysłaną wiadomość)|"
    r"jest (?:wysłany komunikat|wysłana wiadomość)) "
    r"(?:z (?:miejscem|adresem|lokalizacją), bez godziny|"
    rf"z godziną (?P<time>{_TIME})(?:, bez (?:miejsca|adresu|lokalizacji)|"
    r"(?P<place> i z (?:miejscem|adresem|lokalizacją))))"
    r"[.!] (?:co jest faktycznie zrobione|co faktycznie wysłano)\?",
    re.I,
)


@dataclass(frozen=True)
class _MessageApproval:
    place: str
    activity: str
    time: str

    @classmethod
    def bind(
        cls, partial: re.Match[str], update: re.Match[str]
    ) -> _MessageApproval | None:
        activity = partial["activity"].casefold()
        if update["activity"].casefold() != _DUE_TIME[activity]:
            return None
        return cls(partial["place"], activity, update["time"])


def _same_person(name: str, assigned: str) -> bool:
    # Accept a small set of regular declensions, including movable e in -eł.
    # A different name by itself does not inherit the day of the earlier duty.
    source = name.casefold()
    candidate = assigned.casefold()
    if source == candidate:
        return True
    if source.endswith("a"):
        return candidate == source[:-1] + "ę"
    if source.endswith(("eł", "ek", "el")):
        return candidate == source[:-2] + source[-1] + "a"
    return source[-1] not in "eioóuy" and candidate == source + "a"


def _signup(text: str) -> re.Match[str] | None:
    if (match := _SIGNUP.fullmatch(text)) and match["name"].casefold() == match[
        "asked"
    ].casefold():
        return match
    return None


def _duty_status(text: str, earlier: Sequence[str]) -> str | None:
    if signup := _signup(text):
        return (
            f"{signup['name']} jest na liście chętnych do dyżuru "
            f"{_DAY[signup['day'].casefold()]}, ale w grafiku nie ma przydziału."
        )
    if (
        not earlier
        or not (signup := _signup(earlier[-1]))
        or not (assignment := _ASSIGN.fullmatch(text))
    ):
        return None

    same_person = _same_person(signup["name"], assignment["name"])
    if assignment["day"]:
        day = _DAY_NAMES[assignment["day"].casefold()]
    elif same_person:
        day = _DAY[signup["day"].casefold()]
    else:
        day = ""
    if assignment["confirmed"] is not None:
        confirmation = "ta osoba potwierdziła przydział"
    else:
        confirmation = "przydział nadal czeka na potwierdzenie tej osoby"

    added = f"wpisano {assignment['name']} do grafiku"
    if day:
        return f"Na dyżur {day} o {assignment['time']} {added}, a {confirmation}."
    return (
        f"Do grafiku wpisano {assignment['name']} na {assignment['time']}, "
        f"dnia nie podano, a {confirmation}."
    )


def _reported_dispatch(approval: _MessageApproval, receipt: re.Match[str]) -> str:
    if not receipt["time"]:
        return (
            f"Wysłano informację o {approval.place}. "
            f"Zatwierdzona godzina {approval.activity} to {approval.time}, "
            "ale nie było jej w wysłanym komunikacie."
        )

    sent_time = receipt["time"]
    sent_place = receipt["place"] is not None
    if sent_place:
        text = f"Wysłano informację o {approval.place} i godzinę {sent_time}."
    else:
        text = f"Wysłano godzinę {sent_time}, bez informacji o {approval.place}."
    if sent_time.zfill(5) != approval.time.zfill(5):
        text += f" Zatwierdzona godzina {approval.activity} to {approval.time}."
    if not sent_place:
        text += f" Informacja o {approval.place} pozostaje zaakceptowana."
    return text


def _message_status(text: str, earlier: Sequence[str]) -> str | None:
    if partial := _PARTIAL_APPROVAL.fullmatch(text):
        return (
            f"Zatwierdzono tylko informację o {partial['place']}, "
            f"a godzina {partial['activity']} nadal nie jest ustalona."
        )
    if earlier and (update := _COMPLETE_APPROVAL.fullmatch(text)):
        if (partial := _PARTIAL_APPROVAL.fullmatch(earlier[-1])) and (
            approval := _MessageApproval.bind(partial, update)
        ):
            return (
                f"Pełny komunikat zatwierdzony, łącznie z informacją o {approval.place} "
                f"i godziną {approval.activity} {approval.time}. Wysyłka jeszcze nie nastąpiła."
            )
        return None
    if len(earlier) == 2 and (receipt := _DISPATCH.fullmatch(text)):
        if (
            (partial := _PARTIAL_APPROVAL.fullmatch(earlier[0]))
            and (update := _COMPLETE_APPROVAL.fullmatch(earlier[1]))
            and (approval := _MessageApproval.bind(partial, update))
        ):
            return _reported_dispatch(approval, receipt)
    return None


def status_transition_reply(text: str, earlier: Sequence[str]) -> str | None:
    """Summarize linked status updates using only adjacent user messages."""
    return _duty_status(text, earlier) or _message_status(text, earlier)
