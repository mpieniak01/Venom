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
_PENDING_VISIT_IN_CARD = re.compile(
    r"polecenie [„\"](?P<task>sprawdzić [^”\"]{2,60})[”\"] jest w karcie "
    r"(?:obchodu|kontroli), (?:ale|lecz) wpisu z (?:obchodu|kontroli) brak[.!] "
    r"co wiemy o wykonaniu\?",
    re.I,
)
_NOTED_VISIT = re.compile(
    rf"(?P<person>{_PERSON}) (?P<reported>zameldował[ao]?|zgłosił[ao]?|podał[ao]?), "
    rf"że (?P<visit>był[ao]? (?:w|we|na) [^.!?,]{{2,60}}? o {_TIME}), "
    r"(?:ale|lecz) (?P<unchecked>nie sprawdził[ao]? [^.!?,]{2,55})[.!] "
    r"(?:jaki jest stan|co można odnotować)\?",
    re.I,
)
_VISIT_BY_REPORTER = re.compile(
    rf"według (?P<person>{_PERSON}) o (?P<time>{_TIME}) "
    r"(?P<visit>był[ao]? (?:przy|w|we|na) [^.!?,]{2,60})[.!] "
    r"(?P<unchecked>nie sprawdził[ao]? [^.!?,]{2,55})[.!] (?:podaj|zapisz) stan[.!]?",
    re.I,
)
_ACCEPTED_TASK = re.compile(
    r"(?:prosił[ae]m|poprosił[ae]m) o (?P<task>[^.!?]{4,90})[.!] "
    r"w (?:wykazie|rejestrze) zadanie jest przyjęte[,;] "
    r"(?:lecz )?brak (?:adnotacji|wpisu) o wykonaniu[.!] "
    r"(?:napisz|zapisz|podaj) (?:status|stan)[.!]?",
    re.I,
)
_ACCEPTED_TASK_IN_REGISTER = re.compile(
    r"wpisu o wykonaniu nie ma[.!] (?:rejestr|wykaz) przyjął zadanie:\s*"
    r"(?P<task>[^.!?]{4,90})[.!] (?:podsumuj|podaj|zapisz) stan[.!]?",
    re.I,
)
_TWO_OBSERVED = re.compile(
    rf"(?P<person>{_PERSON}) (?P<observed>widział[ao]?) dwie rozłożone, trzeciej "
    r"(?P<unchecked>nie sprawdził[ao]?)[.!] "
    r"(?:podaj|zapisz) aktualny (?:stan|status) z rozróżnieniem źródła[.!]?",
    re.I,
)
_TWO_OBSERVED_ITEM_FIRST = re.compile(
    rf"trzeciej (?:sztuki|pozycji) (?P<person>{_PERSON}) (?P<unchecked>nie sprawdził[ao]?)[.!] "
    r"(?P<observed>widział[ao]?) dwie (?:już )?rozłożone[.!] "
    r"(?:zapisz|podaj), co potwierdził[ao]?[.!]?",
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
_REQUEST_PAIR_UNSENT_FIRST = re.compile(
    r"(?P<object>katalog|folder|pakiet|komplet|zestaw)ów (?P<first>[A-Z0-9]) i (?P<second>[A-Z0-9]) "
    r"jeszcze nie (?:nadano|wysłano)[.!] "
    r"wniosek o (?P<pending>[A-Z0-9]) tylko złożono, (?:a|zaś) (?P<accepted>[A-Z0-9]) "
    r"(?:zaakceptowano|zatwierdzono)[.!] co zapisać dla każdego\?",
    re.I,
)
_REQUEST_DISPATCH = re.compile(
    r"(?:także|również) wniosek (?P<approved>[A-Z0-9]) (?:zaakceptowano|zatwierdzono)[.!] "
    r"do nadania trafił (?:jednak )?tylko (?P<sent>[A-Z0-9]), co potwierdza "
    r"(?P<source>wpis w (?:rejestrze|ewidencji|księdze wysyłek))[.!] "
    r"(?:podaj|zapisz) stan obu[.!]?",
    re.I,
)

_REQUEST_DISPATCH_FIRST = re.compile(
    r"(?:nadano|wysłano) tylko (?P<sent>[A-Z0-9]), jak podaje "
    r"(?P<source>ewidencja|rejestr|księga wysyłek)[.!] "
    r"wniosek o (?P<approved>[A-Z0-9]) (?:też|także|również) ma już akceptację[.!] "
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
_ACCESS_TEST_FIRST = re.compile(
    r"brak zapisu testu (?P<device>czytnika|zamka|terminala), (?:choć|mimo że) "
    r"(?P<installed>czytnik|zamek|terminal) (?:zamontowano|zainstalowano)[.!] "
    rf"dopiero po teście wolno włączyć dostęp do (?P<location>[^.!?,]{{2,55}}) po (?P<time>{_TIME})[.!] "
    r"(?:jaki jest stan|jak zapisać stan)\?",
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

_TEST_TIME_FIRST = re.compile(
    rf"o (?P<time>{_TIME}) (?P<test>próba|test) (?P<device>czytnika|zamka|terminala) "
    r"(?P<result>nie powiodła się|nie powiódł się|powiodła się|powiódł się) według "
    r"(?P<actor>technika|techniczki|serwisanta|serwisantki|administratora|administratorki)[.!] "
    r"włączenia dostępu nie potwierdzono[.!] (?:podaj|zapisz) oba stany[.!]?",
    re.I,
)

_PUBLICATION_DATE = (
    r"(?:[1-9]|[12][0-9]|3[01]) (?:stycznia|lutego|marca|kwietnia|maja|czerwca|"
    r"lipca|sierpnia|września|października|listopada|grudnia)"
)
_PUBLISHED_DRAFT = re.compile(
    r"do ogłoszenia (?:zaakceptowano|zatwierdzono) miejsce (?P<place>[^.!?,]{2,60}?) i datę "
    rf"(?P<date>{_PUBLICATION_DATE})[.!] "
    r"(?:na razie )?szkic (?:wspomina|podaje|zawiera) (?:adres|miejsce), (?:ale )?bez daty[.!] "
    r"co wiemy o akceptacji i publikacji\?",
    re.I,
)
_DRAFT_BEFORE_APPROVAL = re.compile(
    rf"roboczy szkic zawiera tylko nazwę (?P<place>[^.!?,]{{2,60}})[.!] "
    rf"w decyzji mamy zatwierdzoną (?:tę salę|tę lokalizację) i datę (?P<date>{_PUBLICATION_DATE})[.!] "
    r"oddziel zatwierdzenie od publikacji[.!]?",
    re.I,
)
_PUBLISHED_PLACE_ONLY = re.compile(
    r"w opublikowanym tekście (?:widzę|podano) (?:wyłącznie|tylko) (?P<place>[^.!?,]{2,60})[.!] "
    r"jak w jednym zdaniu (?:podać|opisać) stan zaakceptowanej daty\?",
    re.I,
)


_PUBLICATION_WITHOUT_DATE = re.compile(
    r"z publikacji odczytuję:\s*(?P<place>[^.!?,]{2,60})[.!] "
    r"daty tam nie podano[.!] (?:zapisz|podaj) w jednym zdaniu stan daty[.!]?",
    re.I,
)


def _accepted_task(text: str) -> re.Match[str] | None:
    return _ACCEPTED_TASK.fullmatch(text) or _ACCEPTED_TASK_IN_REGISTER.fullmatch(text)


def _approved_draft(text: str) -> re.Match[str] | None:
    return _PUBLISHED_DRAFT.fullmatch(text) or _DRAFT_BEFORE_APPROVAL.fullmatch(text)


def _reported_observation(text: str, previous: str) -> str | None:
    if pending := _PENDING_VISIT.fullmatch(text) or _PENDING_VISIT_IN_CARD.fullmatch(
        text
    ):
        return f"W karcie zapisano zadanie „{pending['task']}”. Brak wpisu potwierdzającego jego wykonanie."
    if visit := _NOTED_VISIT.fullmatch(text):
        return (
            f"{visit['person']} {visit['reported']}, że {visit['visit']}. "
            f"{visit['person']} {visit['unchecked']}."
        )
    if reported := _VISIT_BY_REPORTER.fullmatch(text):
        return (
            f"Według {reported['person']} o {reported['time']} {reported['visit']}. "
            f"{reported['unchecked'].capitalize()}."
        )
    if accepted := _accepted_task(text):
        return f"Przyjęto zadanie obejmujące {accepted['task']}. Wykonania nie potwierdzono."
    if (
        (
            observed := _TWO_OBSERVED.fullmatch(text)
            or _TWO_OBSERVED_ITEM_FIRST.fullmatch(text)
        )
        and (accepted := _accepted_task(previous))
        and (scope := _THREE_PARTS.fullmatch(accepted["task"]))
    ):
        return (
            f"{observed['person']} {observed['observed'].lower()} rozłożone 2 z 3 {scope['items']}. "
            f"Trzeciej pozycji {observed['unchecked']}."
        )
    return None


def _paired_dispatch(text: str, previous: str) -> str | None:
    update = _REQUEST_DISPATCH.fullmatch(text) or _REQUEST_DISPATCH_FIRST.fullmatch(
        text
    )
    source = previous if update else text
    initial = _REQUEST_PAIR.fullmatch(source) or _REQUEST_PAIR_UNSENT_FIRST.fullmatch(
        source
    )
    if initial is None:
        return None
    approved, pending = (initial[key].upper() for key in ("accepted", "pending"))
    if approved == pending:
        return None
    details = initial.groupdict()
    unsent_scope = details.get("unsent_scope")
    if unsent_scope and unsent_scope.casefold() != f"{initial['object'].casefold()}u":
        return None
    if "first" in details and {initial["first"].upper(), initial["second"].upper()} != {
        approved,
        pending,
    }:
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
    confirmed = f"{object} {sent} nadano, co potwierdza {update['source']}."
    if update.re is _REQUEST_DISPATCH_FIRST:
        confirmed += " Jego wniosek jest zaakceptowany."
    return (
        f"{confirmed} {object} {awaiting}: wniosek zaakceptowany, przesyłki nie nadano."
    )


def _access_status(text: str, previous: str) -> str | None:
    report = _TEST_REPORT.fullmatch(text) or _TEST_TIME_FIRST.fullmatch(text)
    source = previous if report else text
    initial = _ACCESS_GATE.fullmatch(source) or _ACCESS_TEST_FIRST.fullmatch(source)
    if (
        not initial
        or _DEVICES[initial["device"].casefold()] != initial["installed"].casefold()
    ):
        return None
    access = f"Dostęp do {initial['location']} po {initial['time']}"
    if report and report.re is _TEST_TIME_FIRST:
        if report["device"].casefold() != initial["device"].casefold():
            return None
        return (
            f"Według {report['actor']} o {report['time']} "
            f"{report['test']} {report['device']} {report['result']}. "
            f"{access}: włączenie nadal niepotwierdzone."
        )
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
    if draft := _approved_draft(text):
        return (
            f"Do ogłoszenia zaakceptowano miejsce {draft['place']} i datę {draft['date']}. "
            "Szkic zawiera tylko miejsce i nie potwierdza publikacji."
        )
    if (
        (
            receipt := _PUBLISHED_PLACE_ONLY.fullmatch(text)
            or _PUBLICATION_WITHOUT_DATE.fullmatch(text)
        )
        and (draft := _approved_draft(previous))
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
_DEFERRED_MEASURE_OBSERVATIONS_FIRST = re.compile(
    r"(?P<done>dwa|trzy|cztery|[2-4]) z (?P<total>trzech|czterech|pięciu|[3-5]) "
    r"(?P<unit>pudełek|opakowań|worków|kartonów) (?:są już|zostały) zważone[.!] "
    r"dodatkowe ważenie (?:na razie )?(?:odłożono|wstrzymano)[.!] "
    r"co jest otwarte, a co potwierdzone\?",
    re.I,
)
_REISSUED_MEASURE = re.compile(
    r"(?:ponownie|na nowo) zlecono zważenie (?P<item>trzeciego|czwartego|piątego) "
    r"(?P<unit>pudełka|opakowania|worka|kartonu)[.!] "
    r"(?:nikt go jeszcze nie wykonał|ważenia jeszcze nie wykonano)[.!] "
    r"(?:popraw|zaktualizuj) status bez kasowania (?P<retained>dwóch|trzech|czterech|[2-4]) pomiarów[.!]?",
    re.I,
)
_REQUEUED_MEASURE = re.compile(
    r"(?P<item>trzecie|trzeci|czwarte|czwarty|piąte|piąty) "
    r"(?P<unit>pudełko|opakowanie|worek|karton) wrócił[oa]? do kolejki ważenia[.!] "
    r"(?:nikt go jeszcze nie zważył|ważenia jeszcze nie wykonano)[.!] "
    r"zachowaj (?P<retained>dwa|trzy|cztery|[2-4]) udokumentowane pomiary w opisie[.!]?",
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
_MEASURE_ORDER_FORMS = {
    "trzecie": "trzeciego",
    "trzeci": "trzeciego",
    "czwarte": "czwartego",
    "czwarty": "czwartego",
    "piąte": "piątego",
    "piąty": "piątego",
}
_MEASURE_OBJECT_FORMS = {
    "pudełko": "pudełka",
    "opakowanie": "opakowania",
    "worek": "worka",
    "karton": "kartonu",
}
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
_REVIEW_CONDITION_FIRST = re.compile(
    r"bez uwag można podpisać dopiero po (?:powtórnym|ponownym) sprawdzeniu[.!] "
    r"z powodu błędnego opisu (?P<field>[^\W\d_]+(?: [^\W\d_]+)?) "
    r"(?P<inspector>kontroler(?:ka)?|inspektor(?:ka)?) "
    r"(?P<decision>odrzucił[ao]?|cofnął|cofnęła) (?P<object>[^.!?,]{3,65})[.!] "
    r"(?:podaj|zapisz) stan[.!]?",
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


_REVIEW_PROTOCOL_FIRST = re.compile(
    r"w (?P<source>karcie|rejestrze|protokole) widnieje korekta opisu "
    r"(?P<field>[^\W\d_]+(?: [^\W\d_]+)?)[.!] "
    r"(?P<inspector>kontroler(?:ka)?|inspektor(?:ka)?) "
    r"(?P<missed>nadal nie przeprowadził[ao]?) (?:ponownej|powtórnej) kontroli[.!] "
    r"czy można (?:już )?(?:zapisać|wpisać) [„\"]bez uwag[”\"]\?",
    re.I,
)


def _number(token: str) -> int:
    return int(token) if token.isdecimal() else _MEASURE_COUNTS[token.casefold()]


def _measurement_status(text: str, previous: str) -> str | None:
    reissue = _REISSUED_MEASURE.fullmatch(text) or _REQUEUED_MEASURE.fullmatch(text)
    source = previous if reissue else text
    batch = _DEFERRED_MEASURE.fullmatch(
        source
    ) or _DEFERRED_MEASURE_OBSERVATIONS_FIRST.fullmatch(source)
    if batch is None:
        return None
    done, total = (_number(batch[key]) for key in ("done", "total"))
    if done >= total:
        return None
    retained = f"Udokumentowane pozostaje zważenie {done} z {total} {batch['unit']}."
    if not reissue:
        return f"Dalsze ważenie wstrzymano. {retained}"
    ordinal = _MEASURE_ORDER_FORMS.get(reissue["item"].casefold(), reissue["item"])
    object_form = _MEASURE_OBJECT_FORMS.get(reissue["unit"].casefold(), reissue["unit"])
    if (
        done != total - 1
        or done != _number(reissue["retained"])
        or total != _MEASURE_ORDINALS[ordinal.casefold()]
        or _MEASURE_UNITS[batch["unit"].casefold()] != object_form.casefold()
    ):
        return None
    return (
        f"Ponownie zlecono zważenie {ordinal} {object_form}, "
        f"ale ważenia jeszcze nie wykonano. {retained}"
    )


def _review_evidence(text: str, previous: str) -> str | None:
    if rejection := _REJECTED_REVIEW.fullmatch(
        text
    ) or _REVIEW_CONDITION_FIRST.fullmatch(text):
        return (
            f"{rejection['object'][0].upper() + rejection['object'][1:]} "
            f"{rejection['inspector']} {rejection['decision']} z powodu błędnego opisu "
            f"{rejection['field']}. Czekają korekta i ponowna kontrola. "
            "Status „bez uwag” będzie możliwy dopiero po ponownej kontroli."
        )
    if (
        (
            change := _CORRECTED_REVIEW.fullmatch(text)
            or _REVIEW_PROTOCOL_FIRST.fullmatch(text)
        )
        and (
            rejection := _REJECTED_REVIEW.fullmatch(previous)
            or _REVIEW_CONDITION_FIRST.fullmatch(previous)
        )
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
