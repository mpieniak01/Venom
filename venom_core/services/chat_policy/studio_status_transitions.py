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

_FIELDS_DRAFT = re.compile(
    r"do wysłania zatwierdzono (?:już )?tylko (?P<field>salę|miejsce|adres|lokalizację) "
    rf"(?P<place>[^.!?,]{{2,60}}), a godzina (?P<time>{_TIME}) (?:była szkicem|pozostała robocza)[.!] "
    r"jak (?:wpisać|zapisać|opisać) stan\?",
    re.I,
)
_FIELDS_APPROVAL = re.compile(
    rf"(?:teraz )?godzina (?P<time>{_TIME}) (?:też|również) jest (?:zaakceptowana|zatwierdzona)[.!] "
    r"(?:zespół jeszcze niczego nie rozesłał|komunikatu jeszcze nie wysłano"
    r"|niczego jeszcze nie wysłano)[.!]",
    re.I,
)
_FIELDS_RECEIPT = re.compile(
    r"(?:wysłany wpis widzę jako|w wysłanej wiadomości widzę) [„\"](?P<place>[^”\"]{2,60})[”\"], "
    r"(?:pola z godziną w nim nie ma|bez godziny)[.!] "
    r"(?:podsumuj jedno zdanie|podaj stan w jednym zdaniu)[.!]?",
    re.I,
)
_VERSION_PREFERENCE = re.compile(
    r"mam dwie propozycje [^.!?]{2,60}[.!] "
    r"(?P<choice>pierwszą|drugą) (?:odbiorca|zespół|organizator) ocenił lepiej, "
    r"(?:lecz|ale) formalnie decyzję podejmie (?:jutro|później)[.!] "
    r"w jakim stanie jest (?P<asked>pierwsza|druga)\?",
    re.I,
)
_VERSION_APPROVAL = re.compile(
    r"(?:dzisiaj|teraz) (?:odbiorca|zespół|organizator) odpisał "
    r"[„\"]zatwierdzam (?P<choice>pierwszą|drugą) wersję[”\"][.!] "
    r"plik (?:jeszcze )?nie poszedł do druku[.!] podaj status[.!]?",
    re.I,
)
_HOUR = r"(?:[01]?[0-9]|2[0-3])(?::[0-5][0-9])?"
_HOURS_CONDITION = re.compile(
    rf"(?:notatka z poranka|notatka) (?:ma|podaje) stare otwarcie o (?P<old>{_HOUR}) "
    rf"i nową godzinę (?P<new>{_HOUR}) po (?P<operation>wymianie|aktualizacji) "
    r"(?P<condition>[^.!?,]{2,45})[.!] (?:wymiany|aktualizacji) jeszcze nie potwierdzono[.!] "
    r"którą godzinę traktować jako obowiązującą\?",
    re.I,
)
_HOURS_CONFIRMED = re.compile(
    r"teraz (?:obsługa|organizator|zespół) potwierdza (?P<operation>wymianę|aktualizację) "
    r"(?P<condition>[^.!?,]{2,45}), ale na (?P<source>[^.!?,]{2,45}) "
    rf"nadal jest (?P<shown>{_HOUR})[.!] jak opisać status\?",
    re.I,
)
_EVENT_NOUNS = {"wymianie": "wymianę", "aktualizacji": "aktualizację"}
_NUMERALS = r"[1-9][0-9]{0,3}"
_NUMBERING = re.compile(
    rf"cała seria (?P<total>{_NUMERALS}) (?P<item>[^\W\d_]+) miała otrzymać numery przed przekazaniem[.!] "
    rf"mamy numery dla (?P<done>{_NUMERALS}) i (?:wyraźny )?brak ich dla (?P<missing>{_NUMERALS})[.!] "
    r"czy skończono rejestr\?",
    re.I,
)
_WITHDRAWN_DISPATCH = re.compile(
    r"(?:organizator|koordynator|zespół) (?:cofnął|wycofał) zgodę na przekazanie, "
    r"a niczego jeszcze nie wydano[.!] zapisz stan po zmianie[.!]?",
    re.I,
)

_VERSION = {"pierwszą": "Pierwsza", "drugą": "Druga"}


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


def _dispatch_fields(text: str, earlier: Sequence[str]) -> str | None:
    if draft := _FIELDS_DRAFT.fullmatch(text):
        return (
            f"Zatwierdzono {draft['field']} {draft['place']}. Godzina {draft['time']} jest robocza. "
            "Brak potwierdzenia wysłania."
        )
    if not earlier:
        return None
    if approval := _FIELDS_APPROVAL.fullmatch(text):
        if draft := _FIELDS_DRAFT.fullmatch(earlier[-1]):
            return (
                f"Zatwierdzono {draft['field']} {draft['place']} oraz godzinę {approval['time']}. "
                "Komunikatu jeszcze nie wysłano."
            )
        return None
    if (
        len(earlier) == 2
        and (draft := _FIELDS_DRAFT.fullmatch(earlier[0]))
        and (approval := _FIELDS_APPROVAL.fullmatch(earlier[1]))
        and (receipt := _FIELDS_RECEIPT.fullmatch(text))
        and draft["place"].casefold() == receipt["place"].casefold()
    ):
        return (
            f"Wysłano informację „{receipt['place']}”, "
            f"a zatwierdzonej godziny {approval['time']} w wysłanym wpisie nie było."
        )
    return None


def _version_status(text: str, earlier: Sequence[str]) -> str | None:
    if preference := _VERSION_PREFERENCE.fullmatch(text):
        version = _VERSION[preference["choice"].casefold()]
        if preference["asked"].casefold() == version.casefold():
            return f"{version} wersja jest roboczo preferowana. Decyzja nie została jeszcze podjęta."
        return None
    if (
        earlier
        and _VERSION_PREFERENCE.fullmatch(earlier[-1])
        and (approval := _VERSION_APPROVAL.fullmatch(text))
    ):
        version = _VERSION[approval["choice"].casefold()]
        return (
            f"{version} wersja jest zatwierdzona. Pliku jeszcze nie wysłano do druku."
        )
    return None


def _conditional_hours(text: str, earlier: Sequence[str]) -> str | None:
    if initial := _HOURS_CONDITION.fullmatch(text):
        return (
            f"Obowiązuje godzina {initial['old']}. Godzina {initial['new']} zacznie obowiązywać "
            f"po tym, jak potwierdzą {_EVENT_NOUNS[initial['operation'].casefold()]} {initial['condition']}."
        )
    if not earlier or not (initial := _HOURS_CONDITION.fullmatch(earlier[-1])):
        return None
    confirmed = _HOURS_CONFIRMED.fullmatch(text)
    if (
        confirmed is None
        or confirmed["operation"].casefold()
        != _EVENT_NOUNS[initial["operation"].casefold()]
        or confirmed["condition"].casefold() != initial["condition"].casefold()
    ):
        return None
    return (
        f"Potwierdzono {confirmed['operation']} {confirmed['condition']}, "
        f"więc obowiązuje godzina {initial['new']}. "
        f"Na {confirmed['source']} nadal widnieje godzina {confirmed['shown']}."
    )


def _numbering_status(text: str, earlier: Sequence[str]) -> str | None:
    record = _NUMBERING.fullmatch(text)
    withdrawn = (
        record is None and bool(earlier) and bool(_WITHDRAWN_DISPATCH.fullmatch(text))
    )
    if withdrawn:
        record = _NUMBERING.fullmatch(earlier[-1])
    if record is None or int(record["total"]) != int(record["done"]) + int(
        record["missing"]
    ):
        return None
    status = f"Numery ma {record['done']} z {record['total']} pozycji, a {record['missing']} nadal ich nie ma."
    if withdrawn:
        return f"Cofnięto zgodę na przekazanie i niczego nie wydano. {status}"
    return f"Rejestr nadal jest niekompletny. {status}"


def status_transition_reply(text: str, earlier: Sequence[str]) -> str | None:
    """Summarize linked status updates using only adjacent user messages."""
    return (
        _duty_status(text, earlier)
        or _message_status(text, earlier)
        or _dispatch_fields(text, earlier)
        or _version_status(text, earlier)
        or _conditional_hours(text, earlier)
        or _numbering_status(text, earlier)
    )
