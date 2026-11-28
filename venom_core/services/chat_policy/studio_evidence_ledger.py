"""Bind complete, reorderable clauses to explicit Studio evidence slots."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

_NAME = r"[^\W\d_]+(?:-[^\W\d_]+)?"
_TIME = r"(?:[01]?[0-9]|2[0-3]):[0-5][0-9]"
_DAY = r"(?:w poniedziałek|we wtorek|w środę|w czwartek|w piątek|w sobotę|w niedzielę)"
_COUNTS = {
    "jeden": 1,
    "jedną": 1,
    "jednego": 1,
    "dwa": 2,
    "dwie": 2,
    "dwóch": 2,
    "trzy": 3,
    "trzech": 3,
    "cztery": 4,
    "czterech": 4,
    "pięć": 5,
    "pięciu": 5,
    "sześć": 6,
    "sześciu": 6,
    "siedem": 7,
    "siedmiu": 7,
    "osiem": 8,
    "ośmiu": 8,
    "dziewięć": 9,
    "dziewięciu": 9,
    "dziesięć": 10,
    "dziesięciu": 10,
}
_NUMBER = rf"(?:{'|'.join(_COUNTS)}|[0-9]{{1,4}})"
_TOPIC = r"[^.!?,;„”\"]{2,75}"
_ROLES = r"(?:kierowniczka|kierownik|koordynatorka|koordynator|redaktorka|redaktor)"
_END = re.compile(
    r"[.!?](?:\s+|$)|;\s*|,\s+(?:(?:a|ale|lecz|natomiast|zaś)\s+|"
    r"(?=(?:(?:pierwsz[ąya]|drug[ąiya]|odpowiedzi|protokołu weryfikacji|w grafiku)\b|"
    rf"{_NUMBER} (?:nikt nie sprawdził|jeszcze nie przejrzano)\b)))",
    re.I,
)
_QUESTION = re.compile(
    r"(?:co|czy|jak|jaki(?:e|a)?|któr[aeąy]|podaj|zapisz|oddziel|"
    r"zaktualizuj|podsumuj|stan proszę)\b[^.!?]{2,120}",
    re.I,
)


@dataclass(frozen=True)
class _Turn:
    clauses: tuple[str, ...]
    request: str

    @classmethod
    def parse(cls, text: str) -> _Turn:
        if not text or len(text) > 650:
            return cls((), "")
        parts = tuple(part for part in _END.split(text) if part)
        if len(parts) < 2 or not _QUESTION.fullmatch(parts[-1]):
            return cls((), "")
        return cls(parts[:-1], parts[-1])

    def bind(self, **roles: str) -> dict[str, re.Match[str]] | None:
        """Fill every slot exactly once. A clause outside the slots invalidates the binding."""
        if len(self.clauses) != len(roles):
            return None
        result = {}
        available = set(range(len(self.clauses)))
        for slot, pattern in roles.items():
            matches = [
                (i, m)
                for i in available
                if (m := re.fullmatch(pattern, self.clauses[i], re.I))
            ]
            if len(matches) != 1:
                return None
            i, result[slot] = matches[0]
            available.remove(i)
        return result


def _number(word: str) -> int:
    return int(word) if word.isdecimal() else _COUNTS[word.casefold()]


def _same_groups(a: re.Match[str], b: re.Match[str], *keys: str) -> bool:
    return all(a[k].casefold() == b[k].casefold() for k in keys)


def _sentence(text: str) -> str:
    return text[0].upper() + text[1:] + "."


_TASK = rf"w (?:harmonogramie jest|wykazie zapisano) polecenie [„\"](?P<task>przejrzeć {_TOPIC})[”\"]"
_EMPTY_DATE = (
    r"(?:rubryka daty wykonania jest pusta|pole daty wykonania pozostaje puste)"
)
_OBSERVATION = rf"(?P<actor>{_NAME}) podał[ao]?, że (?P<event>przejrzał[ao]? {_TOPIC}) o (?P<time>{_TIME})"
_OBSERVATION_BY = (
    rf"według (?P<actor>{_NAME}) (?P<event>przejrzano {_TOPIC}) o (?P<time>{_TIME})"
)
_UNCHECKED = rf"(?:nie widział[ao]?(?: natomiast)?, czy {_TOPIC}|czy {_TOPIC}, (?P<observer>{_NAME}) nie sprawdził[ao]?)"


def _task_report(text: _Turn, previous: _Turn) -> str | None:
    if initial := text.bind(task=_TASK, date=_EMPTY_DATE):
        return (
            f"Zapisano zadanie „{initial['task']['task']}”. "
            "Brak potwierdzenia wykonania i daty."
        )
    anchor = previous.bind(task=_TASK, date=_EMPTY_DATE)
    report = text.bind(report=_OBSERVATION, gap=_UNCHECKED)
    by_source = text.bind(report=_OBSERVATION_BY, gap=_UNCHECKED)
    if anchor is None or not (report or by_source):
        return None
    parts = report or by_source
    assert parts is not None
    event = parts["report"]
    source_target = anchor["task"]["task"].split(maxsplit=1)[1].casefold()
    reported_target = event["event"].split(maxsplit=1)[1].casefold()
    if reported_target != source_target and not source_target.startswith(
        reported_target + " "
    ):
        return None
    gap = parts["gap"][0]
    observer = parts["gap"]["observer"]
    if observer and event["actor"].casefold() not in _case_forms(observer):
        return None
    return f"{_sentence(event[0])} {_sentence(gap)}"


_PAIR_NO_DISPATCH = r"żadn(?:ego z nich|ej oferty) nie wysłano"
_PAIR_ACCEPTED = rf"pierwsz(?:y|ą)(?: (?P<topic>kosztorys|ofertę))? (?P<decision>zaakceptował[ao]?|zatwierdził[ao]?) (?P<actor>{_ROLES})"
_PAIR_PENDING = r"drug(?:i nadal do niego czeka|ą ofertę dopiero złożono)"
_PAIR_NEXT_ACCEPTANCE = r"drug(?:i został tymczasem zaakceptowany|ą też zaakceptowano)"
_PAIR_REPORT = (
    rf"(?P<actor>{_NAME}) podał[ao]?, że przesłano jedynie (?P<sent>pierwszy|drugi)"
)
_PAIR_REPORT_BY = (
    rf"zgodnie z raportem (?P<actor>{_NAME}) wysłano wyłącznie (?P<sent>pierwszą|drugą)"
)


def _dispatch(text: _Turn, previous: _Turn) -> str | None:
    slots = dict(approval=_PAIR_ACCEPTED, pending=_PAIR_PENDING, sent=_PAIR_NO_DISPATCH)
    initial = text.bind(**slots)
    first = initial or previous.bind(**slots)
    if first is None:
        return None
    approval = first["approval"]
    topic = approval["topic"]
    offer = "ofertę" in first["pending"][0].casefold()
    if (
        (topic is None and not offer)
        or (topic is not None and offer != (topic.casefold() == "ofertę"))
        or offer != ("oferty" in first["sent"][0].casefold())
    ):
        return None
    approved = "Pierwszą ofertę" if offer else "Pierwszy kosztorys"
    pending = "Drugą ofertę" if offer else "Drugi kosztorys"
    if initial:
        waiting = "złożono i nadal czeka" if offer else "nadal czeka"
        return (
            f"{approved} {approval['decision']} {approval['actor']}. "
            f"{pending} {waiting} na zatwierdzenie. Żadnego dokumentu nie wysłano."
        )
    updated = text.bind(
        approved=_PAIR_NEXT_ACCEPTANCE,
        report=_PAIR_REPORT_BY if offer else _PAIR_REPORT,
    )
    if not updated:
        return None
    report = updated["report"]
    if offer != updated["approved"][0].casefold().startswith("drugą"):
        return None
    sent_first = report["sent"].casefold().startswith("pierwsz")
    unsent = pending if sent_first else approved
    noun = "ofertę" if offer else "kosztorys"
    return (
        f"{_sentence(report[0] + ' ' + noun)} {unsent} zaakceptowano, ale nie wysłano."
    )


_MEASURE_DECLARATION = (
    r"(?:w protokole wpisano|na karcie zapisano) (?P<measure>masę|wysokość) "
    r"(?P<value>[0-9]{1,5}) (?P<unit>g|cm)"
)
_MEASURE_REQUIRED = (
    r"(?:wymagany jest|do zamknięcia odbioru potrzeba) (?:ponowny pomiar|ponownego pomiaru) "
    r"i (?:podpis|podpisu) (?P<authority>inspektora|inspektorki|kontrolera|kontrolerki)"
)
_MEASURE_MISSING = r"(?:tych kroków|pomiaru ponownego i podpisu (?:inspektora|inspektorki|kontrolera|kontrolerki)) jeszcze nie było"
_MEASURE_OBSERVED = (
    r"(?:ponowny pomiar potwierdził|w powtórnym pomiarze wyszło) "
    r"(?P<value>[0-9]{1,5}) (?P<unit>g|cm)"
)
_SIGNERS = {
    "inspektor": "inspektora",
    "inspektorka": "inspektorki",
    "kontroler": "kontrolera",
    "kontrolerka": "kontrolerki",
}
_MEASURE_SIGN = (
    rf"(?P<actor>{'|'.join(_SIGNERS)}) przyjdzie podpisać (?P<when>jutro|{_DAY})"
    rf"|podpis (?P<role>{'|'.join(_SIGNERS.values())}) dopiero (?P<date>jutro|{_DAY})"
)


def _acceptance(text: _Turn, previous: _Turn) -> str | None:
    required = dict(
        declared=_MEASURE_DECLARATION, steps=_MEASURE_REQUIRED, pending=_MEASURE_MISSING
    )
    initial = text.bind(**required)
    source = initial or previous.bind(**required)
    if source is None:
        return None
    recorded = source["declared"]
    signer = source["steps"]["authority"].casefold()
    pending_text = source["pending"][0].casefold()
    if pending_text.startswith("pomiaru") and f"podpisu {signer} " not in pending_text:
        return None
    if initial:
        return (
            f"{_sentence(recorded[0])} To wpis z dokumentu. "
            f"Odbiór pozostaje otwarty, bo brakuje ponownego pomiaru i podpisu {signer}."
        )
    update = text.bind(measure=_MEASURE_OBSERVED, signature=_MEASURE_SIGN)
    if not update or not _same_groups(recorded, update["measure"], "unit"):
        return None
    signed = update["signature"]
    actor = signed["role"] or _SIGNERS[signed["actor"].casefold()]
    if actor.casefold() != signer:
        return None
    when = signed["when"] or signed["date"]
    measurement = update["measure"]
    note = f"Pomiar potwierdził {measurement['value']} {measurement['unit']}."
    if measurement["value"] != recorded["value"]:
        note += f" Wcześniejsza wartość {recorded['value']} {recorded['unit']} pochodziła z dokumentu."
    return f"{note} Podpis {signer} zaplanowano {when}. Odbiór pozostaje otwarty."


_PREFERENCE = r"(?P<actor>fotograf|technik|techniczka) (?:lubi|woli) (?P<choice>pierwsz|drug)ą(?: etykietę| okładkę)?"
_PREFERENCE_AUTHORITY = r"decyzja należy do (?P<role>redaktorki|kierowniczki|koordynatorki) i jeszcze jej nie podjęła"
_PREFERENCE_WAIT = rf"(?P<role>{_ROLES}) jeszcze nie zatwierdził[ao]? żadnej"
_PREFERENCE_DECISION = (
    rf"o zatwierdzeniu dwóch (?:etykiet|okładek) decyduje (?P<role>{_ROLES})"
)
_APPROVAL = rf"(?P<role>{_ROLES}) (?:zatwierdził[ao]?|zaakceptował[ao]?) (?P<choice>pierwsz|drug)ą(?: etykietę| okładkę)?"
_DELAYED_PRINT = r"druk odło(?:żono|żyliśmy) bez (?:nowego )?terminu"
_GOVERNING_ROLE = {
    "redaktorki": "redaktorka",
    "kierowniczki": "kierowniczka",
    "koordynatorki": "koordynatorka",
}


def _version_decision(text: _Turn, previous: _Turn) -> str | None:
    def bind(turn: _Turn) -> tuple[str, re.Match[str]] | None:
        if parts := turn.bind(
            preference=_PREFERENCE, authority=_PREFERENCE_AUTHORITY
        ) or turn.bind(
            preference=_PREFERENCE,
            authority=_PREFERENCE_AUTHORITY,
            document=r"do decyzji są dwie okładki",
        ):
            return _GOVERNING_ROLE[parts["authority"]["role"].casefold()], parts[
                "preference"
            ]
        if (
            parts := turn.bind(
                preference=_PREFERENCE,
                authority=_PREFERENCE_DECISION,
                pending=_PREFERENCE_WAIT,
            )
        ) and _same_groups(parts["authority"], parts["pending"], "role"):
            return parts["authority"]["role"].casefold(), parts["preference"]
        return None

    if initial := bind(text):
        authority, preference = initial
        return (
            f"{preference['actor'].capitalize()} woli {preference['choice']}ą wersję. "
            f"Brak decyzji osoby uprawnionej do zatwierdzenia ({authority})."
        )
    prior = bind(previous)
    update = text.bind(approval=_APPROVAL, printing=_DELAYED_PRINT)
    if (
        prior is None
        or update is None
        or update["approval"]["role"].casefold() != prior[0]
    ):
        return None
    approval = update["approval"]
    return f"{_sentence(approval[0])} Druk odłożono bez terminu."


_CATALOG_GATE = r"(?P<object>nowy cennik|informator) można opublikować dopiero po (?P<check>weryfikacji podatku|sprawdzeniu daty)"
_CATALOG_SUBMITTED = (
    r"(?:złożono go w systemie|plik (?P<file>informatora|cennika) przyjęto w systemie)"
)
_CATALOG_MISSING = (
    r"(?:protokołu weryfikacji jeszcze brak|nadal brak zapisu kontroli daty)"
)
_REPORT_VERIFICATION = (
    rf"(?P<actor>{_NAME} z {_TOPIC}?) potwierdził[ao]? weryfikację o (?P<time>{_TIME})"
    rf"|o (?P<first_time>{_TIME}) sprawdzenie daty potwierdził[ao]? (?P<from_actor>{_NAME} z {_TOPIC})"
)
_CATALOG_OLD = r"(?:na portalu nadal wersja stara|w portalu wciąż widać poprzedni (?P<object>informator|cennik))"


def _catalog_publication(text: _Turn, previous: _Turn) -> str | None:
    slots = dict(
        gate=_CATALOG_GATE, submitted=_CATALOG_SUBMITTED, missing=_CATALOG_MISSING
    )

    def bind(turn: _Turn) -> tuple[str, str] | None:
        if parts := turn.bind(**slots):
            obj = parts["gate"]["object"].casefold()
            tax = parts["gate"]["check"].casefold() == "weryfikacji podatku"
            if tax == ("protokołu" in parts["missing"][0].casefold()) and (
                parts["submitted"]["file"] is None
                or parts["submitted"]["file"].casefold()
                in {"cennika" if tax else "informatora"}
            ):
                return obj, "weryfikacji podatku" if tax else "sprawdzenia daty"
        # Permit an elliptical gate only when the submitted document is named.
        if parts := turn.bind(
            gate=r"publikacja dopiero po (?P<check>sprawdzeniu daty)",
            submitted=r"plik (?P<file>informatora) przyjęto w systemie",
            missing=r"nadal brak zapisu kontroli daty",
        ):
            return "informator", "sprawdzenia daty"
        return None

    if initial := bind(text):
        obj, check = initial
        return (
            f"{obj.capitalize()} złożono w systemie. Brak potwierdzenia {check}. "
            f"Publikacja jest możliwa po zakończeniu {check} i jeszcze jej nie potwierdzono."
        )
    prior = bind(previous)
    update = text.bind(report=_REPORT_VERIFICATION, publication=_CATALOG_OLD)
    if prior is None or update is None:
        return None
    obj, check = prior
    report = update["report"]
    publication = update["publication"]["object"]
    if bool(report["first_time"]) != ("daty" in check) or (
        publication is not None and publication.casefold() != obj
    ):
        return None
    return (
        f"{_sentence(report[0])} W portalu nadal widnieje poprzednia wersja. "
        f"Nie potwierdzono opublikowania nowej."
    )


_DATE = r"(?:[1-9]|[12][0-9]|3[01]) (?:stycznia|lutego|marca|kwietnia|maja|czerwca|lipca|sierpnia|września|października|listopada|grudnia)"
_APPROVED_FIELDS = (
    r"(?:zaakceptowany komunikat ma|zatwierdzono trzy pola komunikatu:) "
    rf"nazwę (?P<name>{_TOPIC}?), datę (?P<date>{_DATE})(?: i| oraz) godzinę (?P<time>{_TIME})"
)
_FIELD_NAMES = {
    "nazwę": "nazwę",
    "nazwa": "nazwę",
    "nazwie": "nazwę",
    "datę": "datę",
    "data": "datę",
    "dacie": "datę",
    "godzinę": "godzinę",
    "godzina": "godzinę",
    "godzinie": "godzinę",
}
_FIELDS_LIST = rf"(?:{'|'.join(_FIELD_NAMES)})(?:(?: i | oraz |, )(?:{'|'.join(_FIELD_NAMES)})){{0,2}}"
_DRAFT_FIELDS = rf"(?:roboczy SMS zawiera|wersja robocza wiadomości obejmuje) tylko (?P<fields>{_FIELDS_LIST})"
_SENT_FIELDS = rf"(?:w wysłanym SMS-ie widzę|nadana wiadomość zawiera tylko) (?P<fields>{_FIELDS_LIST})"
_FOCUS_FIELD = r"pytam o (?:nazwę|datę|godzinę)"


def _field_set(value: str) -> set[str]:
    return {
        _FIELD_NAMES[f.casefold()]
        for f in re.split(r" i | oraz |, ", value, flags=re.I)
    }


def _field_status(text: _Turn, previous: _Turn) -> str | None:
    slots = dict(approved=_APPROVED_FIELDS, draft=_DRAFT_FIELDS)
    if parts := text.bind(**slots):
        approved = parts["approved"]
        return (
            f"Zatwierdzono nazwę {approved['name']}, datę {approved['date']} i godzinę {approved['time']}. "
            f"{_sentence(parts['draft'][0])}"
        )
    prior = previous.bind(**slots)
    update = text.bind(sent=_SENT_FIELDS) or text.bind(
        sent=_SENT_FIELDS, focus=_FOCUS_FIELD
    )
    ask = re.fullmatch(
        r"co (?:można powiedzieć|zapisać) o (?P<key>nazwie|dacie|godzinie)",
        text.request,
        re.I,
    )
    if prior is None or update is None or ask is None:
        return None
    field = _FIELD_NAMES[ask["key"].casefold()]
    focus = update.get("focus")
    if focus is not None and focus[0].split()[-1].casefold() != field:
        return None
    key = {"nazwę": "name", "datę": "date", "godzinę": "time"}[field]
    value = prior["approved"][key]
    if field not in _field_set(update["sent"]["fields"]):
        return f"Zatwierdzono {field} {value}, ale nie ma jej w nadanej wiadomości."
    return f"Zatwierdzono {field} {value} i to pole znajduje się w nadanej wiadomości."


_BATCH_TOTAL = r"(?:dostarczono|przyjęto) (?P<count>[0-9]{1,4}) (?P<items>kompletów|paczek|pudełek)"
_BATCH_OPEN = rf"(?:otworzono (?P<open_count>{_NUMBER})(?: (?P<open_items>paczek|kompletów|pudełek))?|(?P<first_count>{_NUMBER}) otwarto)"
_BATCH_PENDING = rf"(?P<count>{_NUMBER}) (?:nikt nie sprawdził|jeszcze nie przejrzano)"
_BATCH_DELAY = r"(?:przełożono dalsze sprawdzanie|dalszy przegląd odłożony)"


def _batch_status(text: _Turn, previous: _Turn) -> str | None:
    slots = dict(total=_BATCH_TOTAL, opened=_BATCH_OPEN, pending=_BATCH_PENDING)
    initial = text.bind(**slots)
    source = initial or previous.bind(**slots)
    if source is None or not (initial or text.bind(delay=_BATCH_DELAY)):
        return None
    total = source["total"]
    opened = source["opened"]
    explicit_items = opened["open_items"]
    opened_count = _number(opened["open_count"] or opened["first_count"])
    pending_count = _number(source["pending"]["count"])
    if opened_count + pending_count != int(total["count"]) or (
        explicit_items is not None
        and total["items"].casefold() != explicit_items.casefold()
    ):
        return None
    scope = f"Otworzono {opened_count} z {total['count']} {total['items']}, a {pending_count} nadal nie sprawdzono."
    if initial:
        return f"{_sentence(total[0])} {scope}"
    return (
        f"Dalsze sprawdzanie odłożono. Wcześniejsze otwarcie pozostaje faktem. {scope}"
    )


_HOURS_OLD = (
    rf"(?:w notatce sklep otwiera się o |dotychczasowe otwarcie to )(?P<hour>{_TIME})"
)
_HOURS_NEW = (
    rf"od (?P<hour>{_TIME}) tylko po (?P<event>wymianie) (?P<object>{_TOPIC})"
    rf"|po potwierdzeniu (?P<change>ustawienia) (?P<thing>{_TOPIC}) przejdziemy na otwarcie o (?P<new_hour>{_TIME})"
)
_HOURS_UNCONFIRMED = r"wymiana nadal bez potwierdzenia|potwierdzenia ustawienia (?P<object>bramy) jeszcze nie ma"
_HOURS_REPORTED = rf"(?P<actor>osoba dyżurna|kierownik|kierowniczka) potwierdził[ao]? (?P<event>wymianę|ustawienie) (?P<object>{_TOPIC})"
_HOURS_PRINTED = rf"(?P<location>w papierowej ulotce|w rozkładzie papierowym) (?:nadal podano|wciąż widnieje) (?P<hour>{_TIME})"


def _opening_status(text: _Turn, previous: _Turn) -> str | None:
    slots = dict(old=_HOURS_OLD, new=_HOURS_NEW, pending=_HOURS_UNCONFIRMED)
    initial = text.bind(**slots)
    base = initial or previous.bind(**slots)
    if base is None:
        return None
    new = base["new"]
    pending_obj = base["pending"]["object"]
    event = "ustawienie" if new["change"] else "wymianę"
    obj = new["thing"] or new["object"]
    hour = new["new_hour"] or new["hour"]
    old_hour = base["old"]["hour"]
    if bool(pending_obj) != bool(new["change"]) or (
        pending_obj and obj.casefold() != pending_obj.casefold()
    ):
        return None
    if initial:
        return (
            f"Obowiązuje godzina {old_hour}. Godzina {hour} zacznie obowiązywać "
            f"po potwierdzeniu, że wykonano {event} {obj}."
        )
    facts = text.bind(report=_HOURS_REPORTED, printed=_HOURS_PRINTED)
    if not facts:
        return None
    report, printed = facts["report"], facts["printed"]
    observed = report["object"].casefold()
    if report["event"].casefold() != event or (
        observed != obj.casefold() and not obj.casefold().startswith(observed + " ")
    ):
        return None
    return (
        f"{_sentence(report[0])} Obowiązuje godzina {hour}. "
        f"{printed['location'].capitalize()} nadal podano {printed['hour']}."
    )


_CALLBACK_REQUEST = (
    rf"zgłoszono pytanie do (?P<department>działu {_TOPIC}?) (?P<day>{_DAY})"
    rf"|(?P<first_day>{_DAY}) wysłano prośbę o kontakt z (?P<unit>działem {_TOPIC})"
)
_CALLBACK_UNASSIGNED = r"nie ma chętnego do oddzwonienia|nie podpisano osoby do oddzwonienia i nie ma dowodu rozmowy"
_CALLBACK_REPORT = rf"{_DAY} {_NAME} (?:zadzwonił[ao]? i zostawił[ao]? wiadomość|zostawił[ao]? wiadomość po próbie połączenia)"
_CALLBACK_NO_ANSWER = r"(?:odpowiedzi jeszcze brak|bez odpowiedzi odbiorcy)"


def _callback_status(text: _Turn, previous: _Turn) -> str | None:
    slots = dict(request=_CALLBACK_REQUEST, waiting=_CALLBACK_UNASSIGNED)
    if current := text.bind(**slots):
        return f"{_sentence(current['request'][0])} Brak osoby do oddzwonienia i potwierdzenia połączenia."
    if previous.bind(**slots) and (
        event := text.bind(report=_CALLBACK_REPORT, answer=_CALLBACK_NO_ANSWER)
    ):
        return f"{_sentence(event['report'][0])} Odpowiedzi jeszcze nie ma."
    return None


_DUTY_ATTR = r"(?:(?:poniedziałkow|wtorkow|środow|czwartkow|piątkow|niedzieln)[eąy]|sobotni(?:e|ą)?)"
_DUTY_INTEREST = (
    rf"(?P<actor>{_NAME}) (?:zapisał[ao]? się jako chętn[ya]|zgłosił[ao]? chęć) na "
    rf"{_DUTY_ATTR} (?:pakowanie|dyżur|zmianę)"
)
_DUTY_EMPTY = rf"(?:w grafiku nic przy (?P<pronoun>nim|niej) nie ma|grafik nie zawiera wpisu dla (?P<person>{_NAME}))"
_DUTY_ASSIGNMENT = (
    rf"(?P<source>brygadzistka|brygadzista|koordynator|koordynatorka) (?P<entered>wpisał[ao]?) "
    rf"(?P<actor>{_NAME})(?: do grafiku)? (?P<day>{_DAY}) (?:o|na) (?P<hour>{_TIME})"
)
_DUTY_OPEN = (
    rf"(?P<actor>{_NAME}) nie (?:potwierdził[ao]?|zaakceptował[ao]? przydziału)"
)
_DUTY_ACCEPTED = rf"(?P<actor>{_NAME}) (?:potwierdził[ao]?|zaakceptował[ao]?) przydział"


def _case_forms(name: str) -> set[str]:
    source = name.casefold()
    if source.endswith("a"):
        stem = source[:-1]
        return {
            source,
            stem + "ę",
            stem + ("i" if stem.endswith(("k", "g", "l", "j")) else "y"),
        }
    return {source, source + "a"}


def _shift_status(text: _Turn, previous: _Turn) -> str | None:
    slots = dict(interest=_DUTY_INTEREST, register=_DUTY_EMPTY)
    initial = text.bind(**slots)
    details = initial or previous.bind(**slots)
    if details is None:
        return None
    name = details["interest"]["actor"]
    mentioned = details["register"]["person"]
    if mentioned and mentioned.casefold() not in _case_forms(name):
        return None
    if initial:
        return f"{_sentence(details['interest'][0])} W grafiku brak przydziału."
    update = text.bind(assigned=_DUTY_ASSIGNMENT, pending=_DUTY_OPEN)
    accepted = text.bind(assigned=_DUTY_ASSIGNMENT, pending=_DUTY_ACCEPTED)
    parts = update or accepted
    if (
        parts is None
        or parts["assigned"]["actor"].casefold() not in _case_forms(name)
        or parts["pending"]["actor"].casefold() != name.casefold()
    ):
        return None
    status = (
        "Przydział potwierdzono."
        if accepted
        else "Przydział nadal czeka na potwierdzenie tej osoby."
    )
    assigned = parts["assigned"]
    return (
        f"{assigned['source'].capitalize()} {assigned['entered']} "
        f"{assigned['actor']} do grafiku {assigned['day']} o {assigned['hour']}. {status}"
    )


_RETURNED_FORM = (
    rf"(?P<actor>inspektorka|inspektor|kontrolerka|kontroler) zwrócił[ao]? "
    rf"(?P<doc>deklarację|formularz) z powodu błędnego (?P<field>{_TOPIC})"
)
_CORRECTIVE_GATE = r"(?:wymaga się skorygowania i ponownego podpisu|do odbioru upoważnia dopiero poprawka i powtórny podpis)"
_CORRECTED_FIELD = (
    rf"(?:zmieniono (?P<short>numer|kod) w (?P<doc>deklaracji|formularzu)|"
    rf"w (?P<first_doc>deklaracji|formularzu) poprawiono (?P<full>{_TOPIC}))"
)
_SIGNATURE_PENDING = (
    r"(?:ponownego podpisu jeszcze nie ma|powtórnego podpisu wciąż brak)"
)
_FORM_DOCS = {"deklarację": "deklaracji", "formularz": "formularzu"}


def _correction_status(text: _Turn, previous: _Turn) -> str | None:
    first_slots = dict(reported=_RETURNED_FORM, gate=_CORRECTIVE_GATE)
    if initial := text.bind(**first_slots):
        return f"{_sentence(initial['reported'][0])} Do odbioru potrzebna jest korekta i ponowny podpis."
    original = previous.bind(**first_slots)
    changed = text.bind(correction=_CORRECTED_FIELD, pending=_SIGNATURE_PENDING)
    if original is None or changed is None:
        return None
    previous_form, correction = original["reported"], changed["correction"]
    doc = correction["doc"] or correction["first_doc"]
    field = correction["short"] or correction["full"]
    if doc.casefold() != _FORM_DOCS[previous_form["doc"].casefold()]:
        return None
    initial_head, _, initial_tail = previous_form["field"].casefold().partition(" ")
    update_head, _, update_tail = field.casefold().partition(" ")
    normalized_head = {"numeru": "numer", "kodu": "kod"}.get(initial_head, initial_head)
    if update_head != normalized_head or (
        not correction["short"] and update_tail != initial_tail
    ):
        return None
    return f"{_sentence(correction[0])} Wciąż brakuje ponownego podpisu, więc odbiór pozostaje otwarty."


_PLAN_GATE = (
    rf"(?:plan zakładał (?P<planned>{_TOPIC}?) (?P<day>{_DAY}) po sprawdzeniu (?P<condition>kluczy|licznika)"
    rf"|(?P<subject>udostępnienie {_TOPIC}?) planowane na (?P<when>poniedziałek|wtorek|środę|czwartek|piątek|sobotę|niedzielę) po sprawdzeniu (?P<check>kluczy|licznika))"
)
_PLAN_MISSING = r"(?:kluczy nie sprawdzono|sprawdzenie licznika jeszcze się nie odbyło)"
_CHECKED = r"(?:klucze sprawdzono|licznik jest już sprawdzony)"
_POSTPONED = (
    rf"(?:(?P<actor>{_ROLES}) przełożył[ao]? (?P<subject>udostępnienie(?: {_TOPIC}?)?) na później bez daty"
    rf"|bez nowej daty (?P<source>{_ROLES}) odłożył[ao]? (?P<action>udostępnienie(?: {_TOPIC})?))"
)


def _planned_access(text: _Turn, previous: _Turn) -> str | None:
    slots = dict(plan=_PLAN_GATE, check=_PLAN_MISSING)
    initial = text.bind(**slots)
    base = initial or previous.bind(**slots)
    if base is None:
        return None
    plan = base["plan"]
    action = plan["planned"] or plan["subject"]
    needed = plan["condition"] or plan["check"]
    if needed.casefold() not in base["check"][0].casefold():
        return None
    if initial:
        return f"{plan[0][0].upper() + plan[0][1:]}, a {base['check'][0].lower()}."
    update = text.bind(confirmed=_CHECKED, postponed=_POSTPONED)
    if update is None:
        return None
    moved = update["postponed"]["subject"] or update["postponed"]["action"]
    required_check = "klucze" if needed.casefold() == "kluczy" else "licznik"
    if required_check not in update["confirmed"][0].casefold() or (
        moved.casefold() != action.casefold() and moved.casefold() != "udostępnienie"
    ):
        return None
    return f"{update['confirmed'][0].capitalize()}, ale {update['postponed'][0][0].lower() + update['postponed'][0][1:]}."


def clause_evidence_status(text: str, earlier: Sequence[str]) -> str | None:
    """Answer complete evidence slices, binding follow-ups only to prior user facts."""
    current = _Turn.parse(text)
    if not current.clauses:
        return None
    previous = _Turn.parse(earlier[-1]) if earlier else _Turn((), "")
    for interpret in (
        _task_report,
        _dispatch,
        _acceptance,
        _version_decision,
        _catalog_publication,
        _field_status,
        _batch_status,
        _opening_status,
        _callback_status,
        _shift_status,
        _correction_status,
        _planned_access,
    ):
        if answer := interpret(current, previous):
            return answer
    return None
