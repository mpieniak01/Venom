"""Keep reported requests, execution evidence and delegated roles distinct."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from enum import StrEnum

from venom_core.api.schemas.llm_simple import HistoryMessage

_TOPIC = r"[\w -]{2,75}"
_CLAUSE_BREAK = re.compile(
    r"[.;] |, (?:lecz |ale )| i (?=(?:nadal )?nie (?:wiem|wiadomo),)", re.I
)
_STATUS_COMMAND = re.compile(
    r"(?:podaj|zapisz|podsumuj|zaktualizuj) (?:aktualny |krótki )?(?:stan|status)"
    r"(?: w jednym zdaniu)?|jedno zdanie",
    re.I,
)
_REPORTED = re.compile(
    rf"(?:poprosi(?:łem|łam)(?: wczoraj| dzisiaj| dziś)?|dosta(?:łem|łam) prośbę|"
    rf"zgłoszono prośbę) o (?P<topic>{_TOPIC})",
    re.I,
)
_ACTIVE = re.compile(
    rf"(?:prośba(?: o (?P<request>{_TOPIC}?))?|"
    rf"(?P<order_kind>zlecenie)(?: (?P<order>{_TOPIC}?))?)"
    r" (?:nadal |wciąż )?obowiązuje",
    re.I,
)
_WITHDRAWN = re.compile(
    r"(?:prośbę wycofuję|wycofuję (?:samą )?prośbę|anulowano tę prośbę|"
    r"zlecenie wycofuję|wycofuję (?:samo )?zlecenie|anulowano to zlecenie)",
    re.I,
)
_NO_EVIDENCE = re.compile(
    rf"(?:jeszcze )?nikt nie potwierdził wykonania|nie ma potwierdzenia wykonania|"
    rf"nie mam (?:wiadomości, czy to zrobiono|potwierdzenia, że to zrobił(?:em|am))|"
    rf"(?:nadal )?nie (?:wiem|wiadomo), czy (?P<topic>{_TOPIC}) wykonano",
    re.I,
)
_UNCONFIRMED_END = re.compile(
    rf"nie (?:wiadomo|potwierdzam), czy rozpoczęt[oyąe] (?P<topic>{_TOPIC}) "
    r"(?:dokończono|zakończono)",
    re.I,
)
_EVIDENCE_PREFIX = re.compile(
    r"(?:(?P<limited>(?:wiem|wiadomo) (?:tylko|jedynie))|"
    r"(?:przed chwilą )?(?:potwierdzam|potwierdzono|rozmówca potwierdził)), że ",
    re.I,
)
_PHASE_SUBJECT = re.compile(
    rf"(?P<verb>rozpoczęto|zakończono|nie zakończono|nie wykonano|nadal trwa) (?P<topic>{_TOPIC})",
    re.I,
)
_STILL_RUNNING = re.compile(rf"(?P<topic>{_TOPIC}) nadal trwa", re.I)
_STARTED_ACTION = re.compile(
    r"ktoś zaczął (?P<verb>skanować|odczytywać|sprawdzać)", re.I
)
_LOOKED_AT = re.compile(
    r"(?P<negated>nie )?(?:obejrzano|sprawdzono) (?P<pronoun>ją|go|je|jej|ich) do końca",
    re.I,
)
_RETAIN_DONE = re.compile(
    r"dotychczasowe (?P<topic>oględziny) są potwierdzone|"
    r"dotychczasowy (?P<action>odczyt|skan) jest potwierdzony",
    re.I,
)
_STARTED_ACTION_TOPICS = {
    "skanować": "skan",
    "odczytywać": "odczyt",
    "sprawdzać": "sprawdzenie",
}
_ACTION_FORMS = {
    "odczytu": "odczyt",
    "skanu": "skan",
    "skanować": "skan",
    "skanowanie": "skan",
    "skanowania": "skan",
    "sprawdzenia": "sprawdzenie",
    "sprawdzanie": "sprawdzenie",
    "oględzin": "oględziny",
    "przeglądu": "przegląd",
}
_INSPECTION_ACTIONS = {"sprawdzenie", "przegląd", "oględziny"}
_PLURAL_SCOPE = re.compile(
    r"\b(?:obu|obydwu|dwóch|trzech|czterech|kilku|wszystkich|[2-9]\d*|1\d+)\b",
    re.I,
)
_SINGULAR_SCOPE = re.compile(r"\b(?:jednej|jednego|1)\b", re.I)

_NAME = r"[^\W\d_]+(?:-[^\W\d_]+)?"
_PERSON = rf"{_NAME}(?: {_NAME})?"
_PICKUP = re.compile(
    rf"(?P<item>[\w -]{{2,65}}) należy do (?P<owner>{_PERSON})[,\.] "
    rf"(?P<delegate>{_PERSON}) (?P<assignment>ma (?:ją|go|je) tylko odebrać|"
    r"jest wyznaczon[ya] do odbioru) "
    r"w (?P<possessive>jej|jego|ich) imieniu\. (?:wymień|podaj) (?:obie )?role\.",
    re.I,
)
_PICKUP_CLAUSE_BREAK = re.compile(r"[.;] |, a ", re.I)
_PICKUP_WITHDRAWN = re.compile(
    rf"(?P<delegate>{_PERSON}) (?P<verb>zrezygnował(?:a)?)(?: z odbioru)?", re.I
)
_NO_REPLACEMENT = re.compile(
    r"nikt jeszcze nie potwierdził zastępcy|(?:nie ma|brak) potwierdzonego zastępcy|"
    r"nie potwierdzono zastępcy",
    re.I,
)
_PICKUP_STATUS_COMMAND = re.compile(
    r"powiedz, kto jest właściciel(?:ką|em) i jaki jest stan odbioru|"
    r"podaj właściciel(?:kę|a) i stan odbioru",
    re.I,
)
_PICKUP_OUTCOME = re.compile(
    r"potwierdzono, że (?:nie odebrano tego przedmiotu|odebrano ten przedmiot)",
    re.I,
)
_PICKUP_REPLACED = re.compile(
    rf"{_PERSON} potwierdza, że (?P<item>[\w -]{{2,65}}) odbierze (?P<delegate>{_PERSON})\. "
    r"własność się nie zmienia\. podaj oba (?:nazwiska lub imiona|imiona) w rolach\.",
    re.I,
)


class RequestStatus(StrEnum):
    REPORTED = "reported"
    ACTIVE = "active"
    WITHDRAWN = "withdrawn"


class Phase(StrEnum):
    STARTED = "started"
    ONGOING = "ongoing"
    COMPLETED = "completed"
    INCOMPLETE = "incomplete"
    NOT_PERFORMED = "not_performed"


class EvidenceKind(StrEnum):
    OBSERVED = "observed"
    START_ONLY = "start_only"
    UNCONFIRMED = "unconfirmed"
    END_UNCONFIRMED = "end_unconfirmed"
    RETAIN_COMPLETION = "retain_completion"


_PHASE_BY_VERB = {
    "rozpoczęto": Phase.STARTED,
    "nadal trwa": Phase.ONGOING,
    "zakończono": Phase.COMPLETED,
    "nie zakończono": Phase.INCOMPLETE,
    "nie wykonano": Phase.NOT_PERFORMED,
}


@dataclass(frozen=True)
class Request:
    status: RequestStatus
    topic: str = ""
    is_order: bool = False


@dataclass(frozen=True)
class Evidence:
    kind: EvidenceKind
    phase: Phase | None = None
    statement: str = ""
    topic: str = ""
    pronoun: str = ""
    inspection: bool = False


@dataclass(frozen=True)
class StatusUpdate:
    request: Request | None = None
    execution: Evidence | None = None
    one_sentence: bool = False


@dataclass(frozen=True)
class ActionState:
    request: Request
    execution: Evidence


@dataclass(frozen=True)
class PickupRoles:
    item: str
    owner: str
    delegate: str
    assignment: str
    possessive: str


def _last_users(history: Sequence[HistoryMessage], count: int) -> list[str]:
    turns = history[-2 * count :]
    if [turn.role for turn in turns] != ["user", "assistant"] * count:
        return []
    return [" ".join(turn.content.split()) for turn in turns[::2]]


def _canonical_action(action: str) -> tuple[str, ...]:
    head, *tail = action.casefold().split()
    return (_ACTION_FORMS.get(head, head), *tail)


def _same_action(source: str, mention: str) -> bool:
    # Only a bare action name can refer back to a more specific, adjacent topic.
    topic = _canonical_action(source)
    reference = _canonical_action(mention)
    return reference == topic or reference == topic[:1]


def _request_clause(clause: str) -> Request | None:
    if reported := _REPORTED.fullmatch(clause):
        return Request(RequestStatus.REPORTED, reported["topic"])
    if active := _ACTIVE.fullmatch(clause):
        return Request(
            RequestStatus.ACTIVE,
            active["request"] or active["order"] or "",
            active["order_kind"] is not None,
        )
    if _WITHDRAWN.fullmatch(clause):
        return Request(
            RequestStatus.WITHDRAWN, is_order="zlecenie" in clause.casefold()
        )
    return None


def _observed_execution(clause: str) -> Evidence | None:
    if not (prefix := _EVIDENCE_PREFIX.match(clause)):
        return None
    description = clause[prefix.end() :]
    bounded_start = (
        EvidenceKind.START_ONLY if prefix["limited"] else EvidenceKind.OBSERVED
    )
    if match := _PHASE_SUBJECT.fullmatch(description):
        phase = _PHASE_BY_VERB[match["verb"].casefold()]
        kind = bounded_start if phase == Phase.STARTED else EvidenceKind.OBSERVED
        return Evidence(kind, phase, description, match["topic"])
    if match := _STILL_RUNNING.fullmatch(description):
        return Evidence(
            EvidenceKind.OBSERVED, Phase.ONGOING, description, match["topic"]
        )
    if match := _STARTED_ACTION.fullmatch(description):
        topic = _STARTED_ACTION_TOPICS[match["verb"].casefold()]
        return Evidence(bounded_start, Phase.STARTED, f"rozpoczęto {topic}", topic)
    if match := _LOOKED_AT.fullmatch(description):
        return Evidence(
            EvidenceKind.OBSERVED,
            Phase.INCOMPLETE if match["negated"] else Phase.COMPLETED,
            f"potwierdzono, że {description}",
            pronoun=match["pronoun"].casefold(),
            inspection=True,
        )
    return None


def _execution_clause(clause: str) -> Evidence | None:
    if unknown := _NO_EVIDENCE.fullmatch(clause):
        return Evidence(EvidenceKind.UNCONFIRMED, topic=unknown["topic"] or "")
    if unfinished := _UNCONFIRMED_END.fullmatch(clause):
        return Evidence(EvidenceKind.END_UNCONFIRMED, topic=unfinished["topic"])
    if clause.casefold() == "potwierdzono początek":
        return Evidence(
            EvidenceKind.OBSERVED, Phase.STARTED, "potwierdzono rozpoczęcie"
        )
    if retained := _RETAIN_DONE.fullmatch(clause):
        return Evidence(
            EvidenceKind.RETAIN_COMPLETION,
            topic=retained["action"] or "",
            inspection=retained["topic"] is not None,
        )
    return _observed_execution(clause)


def _parse_status(text: str) -> StatusUpdate | None:
    *clauses, instruction = _CLAUSE_BREAK.split(text.removesuffix("."))
    if not clauses or not _STATUS_COMMAND.fullmatch(instruction):
        return None
    instruction = instruction.casefold()
    update = StatusUpdate(
        one_sentence=instruction == "jedno zdanie"
        or instruction.endswith("w jednym zdaniu")
    )
    for clause in clauses:
        if (request := _request_clause(clause)) and update.request is None:
            update = replace(update, request=request)
        elif (execution := _execution_clause(clause)) and update.execution is None:
            update = replace(update, execution=execution)
        else:
            return None
    return update


def _bind_execution(
    observation: Evidence, topic: str, previous: Evidence
) -> Evidence | None:
    if observation.topic and not _same_action(topic, observation.topic):
        return None
    if (
        observation.inspection
        and _canonical_action(topic)[0] not in _INSPECTION_ACTIONS
    ):
        return None
    if observation.pronoun in {"go", "ją", "jej"} and _PLURAL_SCOPE.search(topic):
        return None
    if observation.pronoun in {"je", "ich"} and _SINGULAR_SCOPE.search(topic):
        return None
    if observation.kind == EvidenceKind.END_UNCONFIRMED:
        if previous.phase in {Phase.STARTED, Phase.ONGOING}:
            return Evidence(
                EvidenceKind.END_UNCONFIRMED,
                Phase.STARTED,
                f"rozpoczęto {observation.topic}, ale nie potwierdzono dokończenia",
            )
        return None
    if observation.kind == EvidenceKind.RETAIN_COMPLETION:
        return previous if previous.phase == Phase.COMPLETED else None
    return observation


def _apply_status(
    update: StatusUpdate, previous: ActionState | None
) -> ActionState | None:
    mention = update.request
    if mention and mention.topic:
        request = mention
        prior_execution = Evidence(EvidenceKind.UNCONFIRMED)
    elif previous:
        if mention and mention.is_order != previous.request.is_order:
            return None
        request = (
            replace(previous.request, status=mention.status)
            if mention
            else previous.request
        )
        prior_execution = previous.execution
    else:
        return None

    execution = (
        _bind_execution(update.execution, request.topic, prior_execution)
        if update.execution
        else prior_execution
    )
    return ActionState(request, execution) if execution is not None else None


def _render_status(state: ActionState, *, one_sentence: bool) -> str:
    request = state.request
    report = (
        f"Zlecenie {request.topic}" if request.is_order else f"Prośba o {request.topic}"
    )
    if request.status == RequestStatus.WITHDRAWN:
        line = (
            f"{report} {'zostało wycofane' if request.is_order else 'została wycofana'}"
        )
    elif request.status == RequestStatus.ACTIVE:
        line = f"{report} nadal obowiązuje"
    else:
        line = f"Zgłoszono prośbę o {request.topic}"

    execution = state.execution
    if execution.kind == EvidenceKind.UNCONFIRMED:
        return f"{line}, a wykonania nie potwierdzono."
    if execution.kind == EvidenceKind.START_ONLY:
        return f"{line}, a {execution.statement}, lecz dalszego przebiegu nie potwierdzono."
    if (
        request.status == RequestStatus.WITHDRAWN
        and execution.kind == EvidenceKind.END_UNCONFIRMED
        and not request.is_order
        and not one_sentence
    ):
        statement = execution.statement[0].upper() + execution.statement[1:]
        return f"Prośbę o {request.topic} wycofano. {statement}."
    return f"{line}, a {execution.statement}."


def _request_history(history: Sequence[HistoryMessage]) -> ActionState | None:
    updates: list[StatusUpdate] = []
    for i in range(len(history) - 2, -1, -2):
        user, assistant = history[i], history[i + 1]
        if (user.role, assistant.role) != ("user", "assistant"):
            break
        source = _parse_status(" ".join(user.content.split()))
        if source is None:
            break
        updates.append(source)
        if source.request and source.request.topic:
            break

    state = None
    for source in reversed(updates):
        state = _apply_status(source, state)
    return state


def _request_status(text: str, history: Sequence[HistoryMessage]) -> str | None:
    if (update := _parse_status(text)) is None:
        return None
    prior = (
        None if update.request and update.request.topic else _request_history(history)
    )
    state = _apply_status(update, prior)
    return _render_status(state, one_sentence=update.one_sentence) if state else None


def _pickup_roles(text: str) -> PickupRoles | None:
    if match := _PICKUP.fullmatch(text):
        return PickupRoles(**match.groupdict())
    return None


def _same_pickup_item(source: str, update: str) -> bool:
    source = source.casefold()
    forms = {source}
    if source.endswith("a") and " " not in source:
        forms.add(source[:-1] + "ę")
    return update.casefold() in forms


def _pickup_withdrawal(text: str) -> tuple[re.Match[str], str] | None:
    *clauses, instruction = _PICKUP_CLAUSE_BREAK.split(text.removesuffix("."))
    if len(clauses) not in {2, 3} or not _PICKUP_STATUS_COMMAND.fullmatch(instruction):
        return None
    withdrawal = _PICKUP_WITHDRAWN.fullmatch(clauses[0])
    if withdrawal is None or not _NO_REPLACEMENT.fullmatch(clauses[1]):
        return None
    outcome = ""
    if len(clauses) == 3:
        if not _PICKUP_OUTCOME.fullmatch(clauses[2]):
            return None
        outcome = f" {clauses[2][0].upper()}{clauses[2][1:]}."
    return withdrawal, outcome


def _bind_pickup_delegate(source: str, delegate: str) -> PickupRoles | None:
    roles = _pickup_roles(source)
    if roles and roles.delegate.casefold() == delegate.casefold():
        return roles
    return None


def _pickup_status(text: str, history: Sequence[HistoryMessage]) -> str | None:
    if roles := _pickup_roles(text):
        assignment = roles.assignment.replace(" tylko ", " ")
        return (
            f"{roles.item} należy do {roles.owner}, a {roles.delegate} "
            f"{assignment} w {roles.possessive} imieniu."
        )

    if (change := _pickup_withdrawal(text)) and (users := _last_users(history, 1)):
        withdrawal, outcome = change
        if roles := _bind_pickup_delegate(users[0], withdrawal["delegate"]):
            return (
                f"{roles.item} należy do {roles.owner}. {roles.delegate} "
                f"{withdrawal['verb'].lower()} z odbioru, "
                f"a zastępcy jeszcze nie potwierdzono.{outcome}"
            )

    if (replacement := _PICKUP_REPLACED.fullmatch(text)) and (
        users := _last_users(history, 2)
    ):
        if (change := _pickup_withdrawal(users[1])) and (
            roles := _bind_pickup_delegate(users[0], change[0]["delegate"])
        ):
            if _same_pickup_item(roles.item, replacement["item"]):
                _, pronoun, *_ = roles.assignment.split()
                assignment = (
                    f"ma {pronoun} odebrać"
                    if pronoun in {"go", "ją", "je"}
                    else "ma odebrać ten przedmiot"
                )
                return (
                    f"{roles.item} nadal należy do {roles.owner}, "
                    f"a {replacement['delegate']} {assignment}."
                )
    return None


_PENDING_FIELD = re.compile(
    r"[„«\"](?P<queued>przyjęto do sprawdzenia|przekazano do weryfikacji|"
    r"skierowano do kontroli)[”»\"]\s*,?\s*(?:bez dalszych wpisów|bez potwierdzenia wykonania)"
    r"[^„«\"]{0,90}[„«\"](?P<field>sprawdzono|zweryfikowano|skontrolowano)[”»\"]"
    r"[.!]\s*(?:podpowiedz,\s*jak je wypełnić|co (?:tam )?wpisać)[.?]$",
    re.I,
)


def _pending_log_field(text: str) -> str | None:
    if match := _PENDING_FIELD.search(text):
        queued = match["queued"]
        return (
            f"{queued[:1].upper()}{queued[1:]}. "
            f"Pole „{match['field']}” pozostaje otwarte do potwierdzenia wyniku."
        )
    return None


_PLANNED_ENTRY = re.compile(
    r"[„«\"](?:zlecić|zamówić|sprawdzić|przekazać)\s+[^”»\"]{2,100}[”»\"]"
    r"\s+(?:i\s+żadnego numeru zamówienia|bez potwierdzenia wykonania)[.!]\s*"
    r"czy mogę (?:zaznaczyć|wpisać) wykonano\?$",
    re.I,
)
_DECLARED_COUNT = re.compile(
    r"(?:[„«\"]|na (?:karcie|etykiecie) \w+ (?:jest|widnieje) )"
    r"(?P<number>[1-9][0-9]{0,3})\s+sztuk\b",
    re.I,
)
_UNCHECKED_PACKAGE = re.compile(
    r"\b(?:przed przyjęciem\b[^.!?]{0,72}|przed przyjęciem\s+paczki[^.!?]{0,72})"
    r"trzeba sprawdzić\b[^.!?]{0,52}(?P<aspect>odcienie|kolorów)"
    r"[^.!?]{0,24}(?:podpis|podpisać)",
    re.I,
)
_UNCHECKED_EVIDENCE = re.compile(
    r"(?:nie porównaliśmy ani nie podpisaliśmy|karty nie widzę)"
    r"[.!]\s*co (?:wpisać na liście kontrolnej|wpisujemy)\?$",
    re.I,
)
_REVOKED_ISSUE = re.compile(
    r"wpisaliśmy (?P<done>[0-9]{1,4}) z (?P<total>[1-9][0-9]{0,3})[.!]\s*"
    r"(?:potem )?zgodę cofnięto,\s*nic nie wydano[.!]\s*"
    r"(?:napisz finał|podaj stan)[.!]?",
    re.I,
)


def _explicit_pending_status(text: str) -> str | None:
    if _PLANNED_ENTRY.search(text):
        return "Wpis oznacza zadanie do zrobienia. Wykonanie pozostaje niepotwierdzone."
    counts = list(_DECLARED_COUNT.finditer(text))
    if (
        len(counts) == 1
        and (check := _UNCHECKED_PACKAGE.search(text))
        and _UNCHECKED_EVIDENCE.search(text)
    ):
        aspect = "odcieni" if check["aspect"].casefold() == "odcienie" else "kolorów"
        return (
            f"Na etykiecie podano {counts[0]['number']} sztuk. "
            f"Zgodność {aspect} i podpis karty nadal wymagają potwierdzenia."
        )
    if (revoked := _REVOKED_ISSUE.fullmatch(text)) and int(revoked["done"]) <= int(
        revoked["total"]
    ):
        remaining = int(revoked["total"]) - int(revoked["done"])
        return (
            f"Zgoda została cofnięta i nic nie wydano. "
            f"Jest {revoked['done']} wpisów z {revoked['total']}. "
            f"Liczba pozycji bez wpisu to {remaining}."
        )
    return None


def studio_status(text: str, history: Sequence[HistoryMessage]) -> str | None:
    """Report explicit user evidence and keep planned and performed actions separate."""
    return (
        _pending_log_field(text)
        or _explicit_pending_status(text)
        or _request_status(text, history)
        or _pickup_status(text, history)
    )
