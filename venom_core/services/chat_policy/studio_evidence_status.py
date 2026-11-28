"""Keep user-reported evidence attached to its subject and stage in Studio."""

from __future__ import annotations

import re
from collections.abc import Sequence

_PERSON = r"[^\W\d_]+(?:-[^\W\d_]+)?"
_TIME = r"(?:[01]?[0-9]|2[0-3]):[0-5][0-9]"
_PENDING_VISIT = re.compile(
    r"w karcie (?:obchodu|kontroli) widzę [„\"](?P<task>sprawdzić [^”\"]{2,60})[”\"][.!] "
    r"nie ma wpisu z (?:obchodu|kontroli)[.!] co można (?:na pewno )?odnotować\?",
    re.I,
)
_NOTED_VISIT = re.compile(
    rf"(?P<person>{_PERSON}) (?P<reported>zameldował[ao]?|zgłosił[ao]?|podał[ao]?), "
    rf"że (?P<visit>był[ao]? (?:w|we|na) [^.!?,]{{2,60}}? o {_TIME}), "
    r"(?:ale|lecz) (?P<unchecked>nie sprawdził[ao]? [^.!?,]{2,55})[.!] "
    r"(?:jaki jest stan|co można odnotować)\?",
    re.I,
)
_ACCEPTED_TASK = re.compile(
    r"(?:prosił[ae]m|poprosił[ae]m) o (?P<task>[^.!?]{4,90})[.!] "
    r"w (?:wykazie|rejestrze) zadanie jest przyjęte[,;] "
    r"(?:lecz )?brak (?:adnotacji|wpisu) o wykonaniu[.!] "
    r"(?:napisz|zapisz|podaj) (?:status|stan)[.!]?",
    re.I,
)
_TWO_OBSERVED = re.compile(
    rf"(?P<person>{_PERSON}) (?P<observed>widział[ao]?) dwie rozłożone, trzeciej "
    r"(?P<unchecked>nie sprawdził[ao]?)[.!] "
    r"(?:podaj|zapisz) aktualny (?:stan|status) z rozróżnieniem źródła[.!]?",
    re.I,
)
_THREE_PARTS = re.compile(r"rozłożenie (?:trzech|3) (?P<items>[^\W\d_]+)", re.I)

_REQUEST_PAIR = re.compile(
    r"wniosek o (?P<object>katalog|folder|pakiet|komplet|zestaw) (?P<accepted>[A-Z0-9]) "
    r"jest (?:zaakceptowany|zatwierdzony), a o (?P=object) (?P<pending>[A-Z0-9]) "
    r"(?:dopiero )?złożony[.!] "
    r"(?:żadnego (?P<unsent_scope>katalogu|folderu|pakietu|kompletu|zestawu) nie wysłano|"
    r"niczego jeszcze nie wysłano)[.!] "
    r"(?:podaj|zapisz) stan obu[.!]?",
    re.I,
)
_REQUEST_DISPATCH = re.compile(
    r"(?:także|również) wniosek (?P<approved>[A-Z0-9]) (?:zaakceptowano|zatwierdzono)[.!] "
    r"do nadania trafił (?:jednak )?tylko (?P<sent>[A-Z0-9]), co potwierdza "
    r"(?P<source>wpis w (?:rejestrze|ewidencji|księdze wysyłek))[.!] "
    r"(?:podaj|zapisz) stan obu[.!]?",
    re.I,
)

_ACCESS_GATE = re.compile(
    rf"dostęp do (?P<location>[^.!?,]{{2,55}}) po (?P<time>{_TIME}) ma zostać włączony "
    r"(?:tylko|wyłącznie) po (?:przetestowaniu|teście) (?P<device>czytnika|zamka|terminala)[.!] "
    r"(?P<installed>czytnik|zamek|terminal) zainstalowano, (?:ale|lecz) testu nie "
    r"(?:zapisano|udokumentowano)[.!] jak (?:ująć|zapisać|opisać) stan\?",
    re.I,
)
_DEVICES = {"czytnika": "czytnik", "zamka": "zamek", "terminala": "terminal"}
_TEST_REPORT = re.compile(
    rf"(?P<actor>technik|techniczka|serwisant|serwisantka|administrator|administratorka) "
    rf"(?P<reported>podał[ao]?|zgłosił[ao]?), że test (?P<result>się udał|nie przeszedł|się nie udał) "
    rf"o (?P<time>{_TIME})[.!] Nadal nie (?:dostał[ae]m|mam) informacji, "
    r"czy (?:rzeczywiście )?włączono dostęp[.!] (?:podaj|zapisz) oba stany[.!]?",
    re.I,
)

_PUBLISHED_DRAFT = re.compile(
    r"do ogłoszenia (?:zaakceptowano|zatwierdzono) miejsce (?P<place>[^.!?,]{2,60}?) i datę "
    r"(?P<date>(?:[1-9]|[12][0-9]|3[01]) (?:stycznia|lutego|marca|kwietnia|maja|czerwca|"
    r"lipca|sierpnia|września|października|listopada|grudnia))[.!] "
    r"(?:na razie )?szkic (?:wspomina|podaje|zawiera) (?:adres|miejsce), (?:ale )?bez daty[.!] "
    r"co wiemy o akceptacji i publikacji\?",
    re.I,
)
_PUBLISHED_PLACE_ONLY = re.compile(
    r"w opublikowanym tekście (?:widzę|podano) (?:wyłącznie|tylko) (?P<place>[^.!?,]{2,60})[.!] "
    r"jak w jednym zdaniu (?:podać|opisać) stan zaakceptowanej daty\?",
    re.I,
)


def _reported_observation(text: str, previous: str) -> str | None:
    if pending := _PENDING_VISIT.fullmatch(text):
        return f"W karcie zapisano zadanie „{pending['task']}”. Brak wpisu potwierdzającego jego wykonanie."
    if visit := _NOTED_VISIT.fullmatch(text):
        return (
            f"{visit['person']} {visit['reported']}, że {visit['visit']}. "
            f"{visit['person']} {visit['unchecked']}."
        )
    if accepted := _ACCEPTED_TASK.fullmatch(text):
        return f"Przyjęto zadanie obejmujące {accepted['task']}. Wykonania nie potwierdzono."
    if (
        (observed := _TWO_OBSERVED.fullmatch(text))
        and (accepted := _ACCEPTED_TASK.fullmatch(previous))
        and (scope := _THREE_PARTS.fullmatch(accepted["task"]))
    ):
        return (
            f"{observed['person']} {observed['observed']} rozłożone 2 z 3 {scope['items']}. "
            f"Trzeciej pozycji {observed['unchecked']}."
        )
    return None


def _paired_dispatch(text: str, previous: str) -> str | None:
    initial = _REQUEST_PAIR.fullmatch(text)
    update = _REQUEST_DISPATCH.fullmatch(text)
    if update:
        initial = _REQUEST_PAIR.fullmatch(previous)
    if initial is None:
        return None
    approved, pending = (initial[key].upper() for key in ("accepted", "pending"))
    unsent_scope = initial["unsent_scope"]
    if approved == pending or (
        unsent_scope and unsent_scope.casefold() != f"{initial['object'].casefold()}u"
    ):
        return None
    object = initial["object"].capitalize()
    if not update:
        return (
            f"{object} {approved} jest niewysłany, a wniosek zaakceptowany. "
            f"{object} {pending} też jest niewysłany. Jego wniosek złożono, ale jeszcze go nie zaakceptowano."
        )
    if update["approved"].upper() != pending or update["sent"].upper() not in {
        approved,
        pending,
    }:
        return None
    sent = update["sent"].upper()
    awaiting = pending if sent == approved else approved
    return (
        f"{object} {sent} nadano, co potwierdza {update['source']}. "
        f"{object} {awaiting}: wniosek zaakceptowany, przesyłki nie nadano."
    )


def _access_status(text: str, previous: str) -> str | None:
    initial = _ACCESS_GATE.fullmatch(text)
    report = _TEST_REPORT.fullmatch(text)
    if report:
        initial = _ACCESS_GATE.fullmatch(previous)
    if (
        not initial
        or _DEVICES[initial["device"].casefold()] != initial["installed"].casefold()
    ):
        return None
    access = f"Dostęp do {initial['location']} po {initial['time']}"
    if report:
        return (
            f"{report['actor'].capitalize()} {report['reported']}, że test "
            f"{initial['device']} {report['result']} o {report['time']}. "
            f"{access}: włączenie nadal niepotwierdzone."
        )
    return (
        f"{initial['installed'].capitalize()} zainstalowano. "
        f"Brak potwierdzenia testu {initial['device']}. "
        f"{access} ma być włączony dopiero po teście i nie ma potwierdzenia włączenia."
    )


def _publication_status(text: str, previous: str) -> str | None:
    if draft := _PUBLISHED_DRAFT.fullmatch(text):
        return (
            f"Do ogłoszenia zaakceptowano miejsce {draft['place']} i datę {draft['date']}. "
            "Szkic zawiera tylko miejsce i nie potwierdza publikacji."
        )
    if (
        (receipt := _PUBLISHED_PLACE_ONLY.fullmatch(text))
        and (draft := _PUBLISHED_DRAFT.fullmatch(previous))
        and draft["place"].casefold() == receipt["place"].casefold()
    ):
        return f"Datę {draft['date']} zaakceptowano, ale nie ma jej w opublikowanym tekście."
    return None


_DEFERRED_MEASURE = re.compile(
    r"(?:odłożono|wstrzymano) zadanie ponownego ważenia, (?:ale|lecz) "
    r"(?P<done>dwa|trzy|cztery|[2-4]) z (?P<total>trzech|czterech|pięciu|[3-5]) "
    r"(?P<unit>pudełek|opakowań|worków|kartonów) (?:już )?zważono[.!] "
    r"co jest wstrzymane i co pozostaje udokumentowane\?",
    re.I,
)
_REISSUED_MEASURE = re.compile(
    r"(?:ponownie|na nowo) zlecono zważenie (?P<item>trzeciego|czwartego|piątego) "
    r"(?P<unit>pudełka|opakowania|worka|kartonu)[.!] "
    r"(?:nikt go jeszcze nie wykonał|ważenia jeszcze nie wykonano)[.!] "
    r"(?:popraw|zaktualizuj) status bez kasowania (?P<retained>dwóch|trzech|czterech|[2-4]) pomiarów[.!]?",
    re.I,
)
_MEASURE_COUNTS = {
    "dwa": 2,
    "dwóch": 2,
    "trzy": 3,
    "trzech": 3,
    "cztery": 4,
    "czterech": 4,
    "pięciu": 5,
}
_MEASURE_ORDINALS = {"trzeciego": 3, "czwartego": 4, "piątego": 5}
_MEASURE_UNITS = {
    "pudełek": "pudełka",
    "opakowań": "opakowania",
    "worków": "worka",
    "kartonów": "kartonu",
}

_REJECTED_REVIEW = re.compile(
    r"(?P<object>[^.!?,]{3,65}?) (?P<inspector>kontroler(?:ka)?|inspektor(?:ka)?) "
    r"(?P<decision>cofnął|cofnęła) "
    r"z powodu (?:źle opisan(?:ej|ego)|błędnego opisu) (?P<field>[^\W\d_]+(?: [^\W\d_]+)?)[.!] "
    r"dopiero po (?:ponownej|powtórnej) kontroli może otrzymać [„\"]bez uwag[”\"][.!] "
    r"czy (?:to już ten etap|można wpisać bez uwag)\?",
    re.I,
)
_CORRECTED_REVIEW = re.compile(
    r"opis (?P<field>[^\W\d_]+(?: [^\W\d_]+)?) (?:wymieniono|poprawiono) i "
    r"(?:zapisano|odnotowano) to w (?P<source>karcie|rejestrze|protokole)[.!] "
    r"(?P<inspector>kontroler(?:ka)?|inspektor(?:ka)?) (?P<missed>nie wykonał[ao]?) "
    r"(?:ponownej|powtórnej) kontroli[.!] "
    r"czy można (?:zapisać|wpisać) [„\"]bez uwag[”\"]\?",
    re.I,
)


def _number(token: str) -> int:
    return int(token) if token.isdecimal() else _MEASURE_COUNTS[token.casefold()]


def _measurement_status(text: str, previous: str) -> str | None:
    batch = _DEFERRED_MEASURE.fullmatch(text)
    reissue = _REISSUED_MEASURE.fullmatch(text)
    if reissue:
        batch = _DEFERRED_MEASURE.fullmatch(previous)
    if batch is None:
        return None
    done, total = (_number(batch[key]) for key in ("done", "total"))
    if done >= total:
        return None
    retained = f"Udokumentowane pozostaje zważenie {done} z {total} {batch['unit']}."
    if not reissue:
        return f"Dalsze ważenie wstrzymano. {retained}"
    if (
        done != total - 1
        or done != _number(reissue["retained"])
        or total != _MEASURE_ORDINALS[reissue["item"].casefold()]
        or _MEASURE_UNITS[batch["unit"].casefold()] != reissue["unit"].casefold()
    ):
        return None
    return (
        f"Ponownie zlecono zważenie {reissue['item']} {reissue['unit']}, "
        f"ale ważenia jeszcze nie wykonano. {retained}"
    )


def _review_evidence(text: str, previous: str) -> str | None:
    if rejection := _REJECTED_REVIEW.fullmatch(text):
        return (
            f"{rejection['object'][0].upper() + rejection['object'][1:]} "
            f"{rejection['inspector']} {rejection['decision']} z powodu błędnego opisu "
            f"{rejection['field']}. Czekają korekta i ponowna kontrola. "
            "Status „bez uwag” będzie możliwy dopiero po ponownej kontroli."
        )
    if (
        (change := _CORRECTED_REVIEW.fullmatch(text))
        and (rejection := _REJECTED_REVIEW.fullmatch(previous))
        and change["field"].casefold() == rejection["field"].casefold()
        and change["inspector"].casefold() == rejection["inspector"].casefold()
    ):
        return (
            f"Zmieniono opis {change['field']} i odnotowano zmianę w {change['source']}. "
            f"{change['inspector'].capitalize()} {change['missed']} ponownej kontroli. "
            "Status „bez uwag” nadal czeka na jej wynik."
        )
    return None


def evidence_status(text: str, earlier: Sequence[str]) -> str | None:
    """Render explicitly described evidence without widening its scope."""
    previous = earlier[-1] if earlier else ""
    return (
        _reported_observation(text, previous)
        or _paired_dispatch(text, previous)
        or _access_status(text, previous)
        or _publication_status(text, previous)
        or _measurement_status(text, previous)
        or _review_evidence(text, previous)
    )
