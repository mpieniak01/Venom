"""Resolve questions about evidence from the user's own records and their revisions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

_TIME = r"(?:[01]?\d|2[0-3]):[0-5]\d"
_WORD = r"[^\W\d_]+"
_STATUS_REQUEST = re.compile(
    r"(?:co (?:jest udokumentowane|wiadomo|wiemy|teraz wiemy|opisać|wpisać|ze słowem)\b.*"
    r"|(?:podaj|zapisz|zaktualizuj|rozróżnij|wypisz|podsumuj|przedstaw) "
    r"(?:.*\b(?:stan\w*|status\w*|etap\w*|ustalenia|wiemy|zdanie)\b.*)"
    r"|(?:jaki|jakie) (?:jest |są )?(?:stan|czas|etapy)\b.*"
    r"|czy .*(?:zamknięt|zostaje|obowiązuje).*|kiedy (?:zacząć|rozpocząć|otworzyć)"
    r"|stan w jednym zdaniu|co pozostało udokumentowane|jak to zapisać|jak opisać stan)",
    re.I,
)
# Complete declarative sentences preserve who made a claim, conditional clauses
# and explicit negation. Avoid extracting bare verbs from quotations or commands.
_SENTENCE = re.compile(r"[.!?](?:\s+|$)")


@dataclass(frozen=True)
class Record:
    facts: tuple[str, ...]
    request: str

    @classmethod
    def parse(cls, text: str) -> Record:
        parts = tuple(s.strip() for s in _SENTENCE.split(text) if s.strip())
        if (
            not 2 <= len(parts) <= 5
            or len(text) > 650
            or _REQUIRES_OTHER_TASK.search(text)
        ):
            return cls((), "")
        if not (
            _STATUS_REQUEST.fullmatch(parts[-1])
            or (_OPEN_STATE_REQUEST.match(parts[-1]) and _EVIDENCE_CUE.search(text))
        ):
            return cls((), "")
        for part in parts:
            if part.count("„") != part.count("”") or part.count('"') % 2:
                return cls((), "")
        return cls(parts[:-1], parts[-1])

    @property
    def statement(self) -> str:
        return ". ".join(_impersonal(fact) for fact in self.facts) + "."

    def fact(self, pattern: str) -> re.Match[str] | None:
        matches = [m for fact in self.facts if (m := re.fullmatch(pattern, fact, re.I))]
        return matches[0] if len(matches) == 1 else None


def _impersonal(fact: str) -> str:
    if fact.startswith(("Chcieliśmy ", "Planowaliśmy ")):
        return "Plan zakładał, żeby " + fact.split(" ", 1)[1]
    return fact.replace(
        "jeszcze nie mamy decyzji", "decyzja jeszcze nie nadeszła"
    ).replace("nie mamy decyzji", "brak decyzji")


def _noun_stem(word: str) -> str:
    for ending, stem in (
        ("nikach", "nik"),
        ("ników", "nik"),
        ("niach", "ni"),
        ("ków", "k"),
        ("kach", "k"),
        ("ek", "k"),
        ("ach", ""),
        ("ów", ""),
    ):
        if word.endswith(ending) and len(word) - len(ending) >= 3:
            return word.removesuffix(ending) + stem
    return word


def _batch(current: Record, previous: Record) -> str | None:
    pattern = rf"(?:wstawiono|ustawiono|przywieziono|dostarczono) (?P<total>\d{{1,5}}) (?P<items>{_WORD}), z których (?P<action>otwarto|sprawdzono|obejrzano|zważono) (?P<done>\d{{1,5}})"
    scope = current
    if not current.fact(pattern):
        if not current.fact(
            r"dalsze (?:oglądanie|sprawdzanie|ważenie|oględziny) (?:przełożono|odłożono|wstrzymano)"
        ):
            return None
        scope = previous
    counted = scope.fact(pattern)
    if (
        not counted
        or len(scope.facts) != 2
        or not scope.fact(
            r"pozostałych nikt (?:jeszcze )?nie (?:obejrzał|sprawdził|zważył)"
        )
    ):
        return None
    total, done = int(counted["total"]), int(counted["done"])
    if done > total:
        return None
    before = f"{counted[0]}. Liczba pozostałych pozycji bez sprawdzenia wynosi {total - done}."
    if scope is current:
        return before
    claim = re.fullmatch(
        rf"czy (?:wcześniejszy )?(?:zapis|wpis) o (?P<count>\d{{1,5}}) "
        rf"(?P<state>otwart|zamknięt|sprawdzon|obejrzan|zważon)(?:ych|e|y|ą) "
        rf"(?P<item>{_WORD}) (?:zostaje|pozostaje|nadal obowiązuje)",
        current.request,
        re.I,
    )
    if (
        len(current.facts) != 1
        or not claim
        or _noun_stem(claim["item"].casefold())
        != _noun_stem(counted["items"].casefold())
    ):
        return None
    completed = {
        "otwarto": "otwart",
        "sprawdzono": "sprawdzon",
        "obejrzano": "obejrzan",
        "zważono": "zważon",
    }[counted["action"].casefold()]
    if int(claim["count"]) != done or claim["state"].casefold() != completed:
        return f"Brak potwierdzenia takiego wpisu. {before} {current.statement}"
    return f"Tak. {before} {current.statement}"


def _schedule(current: Record, previous: Record) -> str | None:
    usual = rf"(?:zwykle|standardowo) .{{1,64}} o (?P<time>{_TIME})"
    conditional = rf"w planie na (?P<time>{_TIME}) [^,]{{1,65}}, (?:gdy|jeśli|kiedy) (?P<action>przełożony|ustawiony|wymieniony) zostanie (?P<item>{_WORD})"
    source = current if current.fact(usual) else previous
    old, plan = source.fact(usual), source.fact(conditional)
    if (
        len(source.facts) != 3
        or not old
        or not plan
        or not source.fact(r"nikt (?:jeszcze )?tego nie potwierdził")
    ):
        return None
    if source is current:
        return f"Obowiązuje {old['time']}. {plan[0]}. Brak potwierdzenia tej zmiany."
    verbs = {
        "przełożony": "przełożyć",
        "ustawiony": "ustawić",
        "wymieniony": "wymienić",
    }
    verb = verbs[plan["action"].lower()]
    # Keep optional agent words outside the polarity marker ("nie udało się").
    agent = rf"(?!(?:nie|prawie|podobno|rzekomo|gdyby)\b){_WORD}"
    event = rf"(?:(?:{agent} ){{1,2}})?(?P<negative>nie )?(?:udało się|powiodło się) {verb} {re.escape(plan['item'])}, co potwierdził[ao]? {_WORD}"
    observation = current.fact(event)
    if (
        len(current.facts) != 2
        or not observation
        or not current.fact(
            rf"(?:ulotka|tablica|witryna|rozkład) nadal (?:pokazuje|podaje) {_TIME}"
        )
    ):
        return None
    if observation["negative"]:
        return f"Obowiązuje {old['time']}. {current.statement} Warunek zmiany na {plan['time']} pozostaje niespełniony."
    return f"Obowiązuje {plan['time']}. {current.statement}"


def _approved_fields(current: Record, previous: Record) -> str | None:
    header = r"w zatwierdzon\w+ (?:komunikacie|ogłoszeniu|tekście|wiadomości) (?:są|podano|wymieniono) (?P<fields>[^.!?]{2,100})"
    source = current if current.fact(header) else previous
    record = source.fact(header)
    if (
        len(source.facts) != 2
        or not record
        or not source.fact(
            r"w (?:projekcie|szkicu) [^.!?]{2,100} (?:tylko|jedynie) [^.!?]{2,80}"
        )
    ):
        return None
    if source is current:
        return f"{current.statement} Szkic nie potwierdza wysłania."
    field = re.fullmatch(r'co ze słowem [„"]([^„”"]{1,50})[”"]', current.request, re.I)
    receipt = current.fact(
        r"w potwierdzeniu (?:wysłania|nadania|wysyłki) (?:widzę|podano) (?P<fields>[^.!?]{2,100})"
    )
    if not field or not receipt or len(current.facts) != 1:
        return None
    asked = field[1]

    def fields(s: str) -> set[str]:
        return {item.strip().casefold() for item in re.split(r",| i | oraz ", s)}

    if asked.casefold() not in fields(record["fields"]):
        return None
    present = asked.casefold() in fields(receipt["fields"])
    visibility = (
        "wymieniono je również w potwierdzeniu wysłania"
        if present
        else "w podanej treści potwierdzenia wysłania go brakuje"
    )
    return f"Słowo „{asked}” zatwierdzono. {visibility[:1].upper() + visibility[1:]}."


@dataclass(frozen=True)
class DecisionPair:
    approved: str
    pending: str
    initial: str

    @classmethod
    def parse(cls, record: Record) -> DecisionPair | None:
        approved = record.fact(
            rf"(?:zatwierdzono|zaakceptowano) tylko wniosek (?P<id>{_WORD})"
        )
        pending = record.fact(rf"wniosek (?P<id>{_WORD}) złożono")
        if (
            len(record.facts) == 3
            and approved
            and pending
            and record.fact(r"przesyłki obu (?:wciąż|nadal) czekają")
        ):
            first, second = approved["id"], pending["id"]
            statement = f"{approved[0]}. {pending[0]}, czeka na decyzję. Żadnej przesyłki jeszcze nie nadano."
        else:
            decision = record.fact(
                rf"(?:dwa zlecenia|dwa wnioski|zgłoszenia|wnioski): (?P<ok>{_WORD}) (?:zatwierdzony|zaakceptowany), (?P<pending>{_WORD}) (?:dopiero|tylko) (?:zgłoszony|złożony)"
            )
            waiting = record.fact(
                r"(?:obydwa|oba) (?:transporty|przewozy|zlecenia) (?:jeszcze |nadal )?czekają"
            )
            if len(record.facts) != 2 or not decision or not waiting:
                return None
            first, second = decision["ok"], decision["pending"]
            statement = (
                f"{first} ma zatwierdzenie. {second} dopiero zgłoszono. {waiting[0]}."
            )
        if first.casefold() == second.casefold():
            return None
        return cls(first, second, statement)

    def label(self, form: str) -> str | None:
        labels = [
            label
            for label in (self.approved, self.pending)
            if _name_related(form, label)
        ]
        return labels[0] if len(labels) == 1 else None


def _applications(current: Record, previous: Record) -> str | None:
    if original := DecisionPair.parse(current):
        return original.initial
    pair = DecisionPair.parse(previous)
    if not pair:
        return None
    granted = current.fact(
        rf"(?P<id>{_WORD}) (?:też |także )?(?:zaakceptowany|zatwierdzony|zatwierdzono|zaakceptowano)"
    )
    if not granted or granted["id"].casefold() != pair.pending.casefold():
        return None
    # An explicit source must cover the same shipment as the one being reported.
    exclusive = current.fact(
        rf"{_WORD} (?:zgłosił[ao]?|potwierdził[ao]?) nadanie (?:tylko|wyłącznie) (?P<id>{_WORD})"
    )
    if exclusive and len(current.facts) == 2 and (sent := pair.label(exclusive["id"])):
        waiting = pair.pending if sent == pair.approved else pair.approved
        return f"Oba wnioski zaakceptowano. {exclusive[0]}. Przesyłka dla wniosku {waiting} nadal czeka na nadanie."
    report = current.fact(
        rf"(?P<source>{_WORD}) (?:opisał[ao]?|zgłosił[ao]?|zrelacjonował[ao]?) (?P<event>wyjazd|transport|wysłanie|odbiór) (?P<id>{_WORD})"
    )
    gap = current.fact(
        rf"dla (?P<id>{_WORD}) (?:nadal |wciąż )?brak (?:wpisu|potwierdzenia) (?:o |dotyczącego )?(?P<event>wyjeździe|transporcie|wysłaniu|odbiorze)"
    )
    if len(current.facts) != 3 or not report or not gap:
        return None
    sent, waiting = pair.label(report["id"]), pair.label(gap["id"])
    if sent is None or waiting is None or sent == waiting:
        return None
    return f"Obie decyzje są zatwierdzone. {report[0]}. {gap[0]}."


def _signoff(current: Record, previous: Record) -> str | None:
    template = rf"do (?P<action>wydania|przekazania|przyjęcia|odbioru) [^.!?,]{{1,70}} (?:są konieczne|potrzebne są|wymagane są) (?P<check>{_WORD}) i podpis (?P<signer>{_WORD})"
    source = current if current.fact(template) else previous
    requirements = source.fact(template)
    if not requirements or len(source.facts) != 2:
        return None
    check = re.escape(requirements["check"])
    if not source.fact(
        rf"{check} (?:już jest|wykonano|potwierdzono), (?:ale )?podpisu (?:wciąż |nadal )?brak"
    ):
        return None
    if current is source:
        return f"Nie. {requirements['check'].capitalize()} już jest, ale do {requirements['action']} potrzeba jeszcze podpisu {requirements['signer']}."
    update = current.fact(
        rf"(?P<actor>{_WORD}) (?P<signed>podpisał[ao]?), (?:ale|lecz) (?:nie ma (?:jeszcze )?|brak )(?P<receipt>kwitu|potwierdzenia|pokwitowania) (?P<action>{_WORD})"
    )
    if (
        not update
        or len(current.facts) != 1
        or update["action"].casefold() != requirements["action"].casefold()
        or not _name_related(requirements["signer"], update["actor"])
    ):
        return None
    return (
        f"{requirements['check'].capitalize()} wykonano i {update['actor']} {update['signed']}."
        + f" Oba warunki są spełnione. Brak {update['receipt']} {update['action']}, więc wykonanie tej czynności jest niepotwierdzone."
    )


def _written_order(current: Record) -> str | None:
    entry = current.fact(
        r"(?:w [^,.!?]{2,50} )?(?:wpisano|zapisano|odnotowano) (?:polecenie|zlecenie) (?P<task>[^,.!?]{2,80}), (?:bez (?:zapisu|potwierdzenia) wykonania|lecz brak potwierdzenia wykonania)"
    )
    if (
        len(current.facts) == 1
        and entry
        and current.request.casefold().startswith(
            ("co wiadomo", "jaki jest stan", "podsumuj", "co jest udokumentowane")
        )
    ):
        return f"Zapisano polecenie {entry['task']}. Brak potwierdzenia jego wykonania."
    return None


def _closure(current: Record, previous: Record) -> str | None:
    req = current.request.casefold()
    initial = current.fact(r"(?:przyjęcie|odbiór|zamknięcie) wymaga .{1,120} podpisu")
    if initial and current.fact(r"brakuje obu etapów"):
        return f"{current.statement} Przyjęcie pozostaje otwarte."
    if "zamknięt" not in req:
        return None
    pending = current.fact(
        r"podpis (?P<signer>[^.!?]{1,85}) (?:przewidziano|zaplanowano) na (?P<when>[^.!?]{1,35})"
    )
    missing = current.fact(
        r"[^.!?]{1,80} wykonano, (?:ale|lecz) [^.!?]{1,55} (?:nadal |jeszcze )?(?:niczego )?nie podpisał[ao]?"
    )
    prior = previous.statement.lower()
    requested = re.search(r"^czy (\w+) ", req)
    if requested and requested[1] not in {
        "odbiór",
        "przyjęcie",
        "dokument",
        "karta",
        "formularz",
        "sprawa",
    }:
        return None
    if requested and requested[1] in {"dokument", "karta", "formularz"}:
        noun = requested[1][:4]
        if not re.search(rf"\b{noun}\w*", prior):
            return None
    if "podpis" not in prior or not re.search(
        r"przyjęcie|odbiór|warunkiem zamknięcia", prior
    ):
        return None
    if pending and len(current.facts) == 2:
        signed = current.fact(
            rf"potwierd(?:zili|zono) złożenie podpisu {re.escape(pending['signer'])} i (?P<checked>\d+ {_WORD}(?: {_WORD})?)"
        )
        if signed and signed["checked"].casefold() in prior:
            return (
                f"{signed[0]}. Jednocześnie podano plan podpisu na {pending['when']}. "
                "Czy ten plan dotyczył już złożonego podpisu, czy chodzi o dodatkowy podpis?"
            )
    confirmed = current.fact(r"potwierd(?:zili|zono) (?P<inspection>\d+ [^.!?]{1,65})")
    if (
        pending
        and len(current.facts) == 2
        and confirmed
        and "podpis" not in confirmed[0].casefold()
    ) or (missing and len(current.facts) == 1):
        return f"{current.statement} Brakuje podpisu, więc sprawa pozostaje otwarta."
    return None


class EvidenceRole(StrEnum):
    REPORT = "report"
    GAP = "gap"
    DIRECTIVE = "directive"
    CONDITION = "condition"
    DECISION = "decision"
    REGISTER = "register"
    OBSERVED = "observed"
    PREFERENCE = "preference"
    DRAFT = "draft"
    RETURNED = "returned"


@dataclass(frozen=True)
class EvidenceClause:
    role: EvidenceRole
    text: str

    @classmethod
    def from_text(cls, text: str) -> EvidenceClause | None:
        if re.match(
            r"^(?:zamkn|otworzy|przekaza|zwróci|wysła|ukończy|potwierdzi|sprawdzi|złoży|wykona|odebra)\w*(?:łam|łem)\b",
            text,
            re.I,
        ):
            return cls(EvidenceRole.REPORT, f"Zgłaszasz wykonanie w słowach „{text}”")
        if match := _SPEECH.fullmatch(text):
            return cls(
                EvidenceRole.REPORT,
                f"{match['actor']} relacjonuje, że {match['event']}",
            )
        if m := _REPORT_BY.fullmatch(text):
            return cls(EvidenceRole.REPORT, f"Według {m['source']} {m['event']}")
        if (m := _DIRECTIVE.fullmatch(text)) and not re.search(
            r"\b(?:dopiero po|nastąpić po)\b", text, re.I
        ):
            return cls(
                EvidenceRole.DIRECTIVE, f"{m['actor']} ma za zadanie {m['event']}"
            )
        if (
            re.search(r"\b(?:nikt |jeszcze |nadal )?nie potwierdz\w*", text, re.I)
            and "," not in text
        ):
            return cls(EvidenceRole.GAP, text)
        for role, pattern in _EVIDENCE:
            if pattern.search(text):
                return cls(role, _impersonal(text))
        return None


_SPEECH = re.compile(
    rf"(?P<actor>{_WORD}(?: z {_WORD})?) (?:napisał[ao]?|poinformował[ao]?|powiedział[ao]?|"
    r"oznajmił[ao]?|zgłosił[ao]?|zrelacjonował[ao]?|relacjonuje|twierdzi|mówi)(?:,? że) (?P<event>.+)",
    re.I,
)
_REPORT_BY = re.compile(r"według (?P<source>\S+(?: z \S+)?) (?P<event>.+)", re.I)
_DIRECTIVE = re.compile(
    rf"(?P<actor>{_WORD}) (?:ma|powinien|powinna) (?P<event>[^\W\d_]+ć\b.*)", re.I
)
_GAP_CUE = r"\b(?:braku?j\w*|nikt nie (?:odnotował|sprawdził|poświadczył)|brak|pust[eya]|nieznan\w*|bez (?:dowodu|pokwitowania|potwierdzenia)|nie (?:ma potwierdzenia|potwierdz\w*|ustalono|wykonano|przyjechał[ao]?|podpisał[ao]?))\b"
_EVIDENCE = tuple(
    (role, re.compile(pattern, re.I))
    for role, pattern in (
        (
            EvidenceRole.PREFERENCE,
            r"\b(?:woli|preferuj\w*|liście chętnych|zgłosił[ao]? chęć)\b",
        ),
        (EvidenceRole.RETURNED, r"\b(?:zwrócił[ao]?|odesłano)\b"),
        (
            EvidenceRole.CONDITION,
            r"\b(?:dopiero po|ma nastąpić po|warunkiem zamknięcia|po kontroli|po weryfikacji)\b",
        ),
        (EvidenceRole.DRAFT, r"\b(?:szkic|wersja robocza|wersję roboczą)\b"),
        (
            EvidenceRole.DIRECTIVE,
            r"\b(?:tylko|jedynie|wyłącznie) (?:polecenie|zlecenie|zadanie)\b|\bo kontakt\b",
        ),
        (
            EvidenceRole.REGISTER,
            r"\b(?:na (?:tablicy|stronie|afiszu)|w (?:portalu|gablocie))\b.*\b(?:wciąż|nadal)\b|\bwpisał[ao]? \S+ (?:do grafiku|na .{1,32} o \d)",
        ),
        (EvidenceRole.DECISION, r"\b(?:wybrał[ao]?|zdecydował[ao]? się na)\b"),
        (
            EvidenceRole.OBSERVED,
            r"\b(?:potwierdził[ao]?|zweryfikował[ao]?|oddzwonił[ao]?|zadzwonił[ao]?|cofnięto bez podania|wykonan[aoey]|sprawdzon[aoey])\b",
        ),
        (EvidenceRole.GAP, _GAP_CUE),
    )
)
_EVIDENCE_CUE = re.compile(
    r"\b(?:potwierdz|protok|pokwit|odnot|odwoł|zlecen|polecen|dowód|dowod|przydz|udokument|szkic|rejestr|raport|relacj|wykon|decyzj|zatwierdz|weryfik|podpis|przewidz|zaplan|przełoż|przesyłk|nada[łn]|zgłosił|doniósł|wpisał|rozkład|zwróc|kontrol|niesprawdz|sprawdz|otwart|ustawiono|wstawiono|przywieziono|dostarczono)\w*",
    re.I,
)
_OPEN_STATE_REQUEST = re.compile(
    r"(?:co |jak |jaki\w* |czy |kiedy |któr\w* |podsumuj|przedstaw|wymień|opisz|wskaż|rozróżnij|ustal|zapisz|podaj|zaktualizuj|oddziel)",
    re.I,
)
_REQUIRES_OTHER_TASK = re.compile(
    r"\b(?:przeczytaj|przetłumacz|tłumacz|wiersz|zrymuj|zredaguj|zacytuj|przepisz|wyślij|wykonaj|krok po kroku|ile kosztuje|dlaczego|dlaczegóż)\b",
    re.I,
)


def evidence_hint(text: str) -> str | None:
    """Ground uncertain status requests reaching generation in the actual speaker and event."""
    current = Record.parse(text)
    if (
        not current.facts
        or not _EVIDENCE_CUE.search(current.statement)
        or not re.search(
            r"\b(?:stan|status|wykon|wiadom|dow[oó]d|potwierdz|udokument|etap|zamknię|zapisać|aktualn|ustalen|zrobion)\w*",
            current.request,
            re.I,
        )
    ):
        return None
    return (
        "Odpowiedz wprost na pytanie o bieżący stan. Dla każdego faktu zachowaj osobę, obiekt, "
        "czas i źródło. Przy relacji świadka napisz, kto co zgłosił. Sam wpis planu, zamiaru "
        "lub przydziału nie potwierdza wykonania ani zgody. Zastosuj najnowszą zmianę tylko "
        "do jej obiektu. Przy częściowym potwierdzeniu wskaż dokładnie potwierdzone pola i brakujące dane."
    )


def _self_contained(current: Record) -> str | None:
    facts = [EvidenceClause.from_text(text) for text in current.facts]
    if not all(facts):
        return None
    known = [f for f in facts if f is not None]
    if re.search(r", (?:on|ona|oni|one) (?:jeszcze |nadal )?", current.statement, re.I):
        return None
    roles = {f.role for f in known}
    low = current.statement.casefold()
    request = current.request.casefold()
    # Questions requiring a lookup, an amount or a specific decision need an
    # interpreter. A list of sourced events answers only a state-summary request.
    if re.match(r"(?:czy|kiedy|co ze słowem|jaki czas|co wiadomo o)\b", request):
        return None
    if (
        request not in {"podsumuj", "opisz stan", "wypisz fakty"}
        and not _STATUS_REQUEST.fullmatch(request)
        and not re.search(
            r"\b(?:udokumentowano|zapisano|wiadomo|pewne|dowody|status|stan|etapy|potwierdzone)\b",
            request,
        )
    ):
        return None
    statements = [f.text for f in known]
    if any(_DIRECTIVE.fullmatch(f) for f in current.facts) and re.search(
        r"\b(?:tylko|jedynie|wyłącznie) (?:polecenie|zadanie|zlecenie)\b", low
    ):
        statements = [
            f.text
            for f in known
            if not re.search(
                r"\b(?:tylko|jedynie|wyłącznie) (?:polecenie|zadanie|zlecenie)\b",
                f.text,
                re.I,
            )
        ]
        statements.append(
            "Brak potwierdzenia wykonania"
            + (" i jego godziny" if "godzin" in low else "")
        )
    elif (
        EvidenceRole.DRAFT in roles
        and EvidenceRole.CONDITION in roles
        and EvidenceRole.GAP in roles
    ):
        statements.append("Publikacja nadal czeka na weryfikację")
    elif EvidenceRole.PREFERENCE in roles and re.search(
        r"(?:nie ma|brak) decyzji|decyzja jeszcze nie nadeszła", low
    ):
        statements.append("Wskazano preferencję, wybór pozostaje otwarty")
    elif roles == {EvidenceRole.DECISION, EvidenceRole.CONDITION} and re.search(
        _GAP_CUE, low
    ):
        statements.append("Realizacja nadal zależy od spełnienia warunku")
    elif {EvidenceRole.REGISTER, EvidenceRole.OBSERVED} == roles and re.search(
        r"\b(?:poprzedni|star)\w*", low
    ):
        statements.append("Brak potwierdzenia aktualizacji opublikowanych danych")
    elif EvidenceRole.RETURNED in roles and EvidenceRole.CONDITION in roles:
        statements.append("Sprawa pozostaje otwarta")
    elif EvidenceRole.GAP in roles and roles & {
        EvidenceRole.REPORT,
        EvidenceRole.DIRECTIVE,
        EvidenceRole.PREFERENCE,
        EvidenceRole.REGISTER,
    }:
        pass  # Joining the qualified events directly answers the status request.
    elif (
        roles == {EvidenceRole.OBSERVED}
        and re.search(
            r"\b(?:oddzwonił[ao]?|zadzwonił[ao]?|skontaktował[ao]? się)\b", low
        )
        and re.search(_GAP_CUE, low)
    ):
        pass  # A completed action and a different unknown within the same sentence.
    elif "jedn" not in request or not re.search(
        r"(?:cofnięto|odłożono|odwołano) bez podania|po kontroli", low
    ):
        return None
    if "jedn" in request:
        return (
            statements[0]
            + "".join(", a " + t[:1].lower() + t[1:] for t in statements[1:])
            + "."
        )
    return ". ".join(statements) + "."


def _name_related(name: str, word: str) -> bool:
    # Accept exact case or regular singular inflection. Other spellings are delegated.
    base = word.casefold()
    spelling = name.casefold()
    if base == spelling:
        return True
    if base.endswith("a"):
        return spelling in {base[:-1] + ending for ending in ("y", "i", "ę", "ą", "ie")}
    return spelling in {base + ending for ending in ("a", "u", "owi", "em")}


def record_status(text: str, previous: str) -> str | None:
    """Summarize sourced facts. Join turns only for explicitly matched entities."""
    current = Record.parse(text)
    if not current.facts:
        return None
    prior = Record.parse(previous)
    names = re.findall(r"\b[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]{2,}\b", current.request)
    # Named targets in the question must have an antecedent in the user's facts.
    words = re.findall(_WORD, current.statement + " " + prior.statement)
    if any(
        not any(_name_related(name, word) for word in words)
        for name in names
        if name != current.request.split()[0]
    ):
        return None
    return (
        _batch(current, prior)
        or _schedule(current, prior)
        or _approved_fields(current, prior)
        or _applications(current, prior)
        or _signoff(current, prior)
        or _written_order(current)
        or _closure(current, prior)
        or _self_contained(current)
    )
