"""Choose the first irrigation check from scoped, current observations."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from venom_core.services.academy.qualified_chat_sources import card_link, read_card

ZONE = re.compile(r"\b(?:lini[iaeęą]|stref[ayęie])\s+([a-d])\b")
DOMAIN = re.compile(r"\bnawadnian\w*|\bkroplown\w*|\blini\w+\s+kroplując\w*")
REQUEST = re.compile(
    r"\b(?:co|gdzie|od czego|który)\b.*\b(?:sprawdzić|zacząć|skontrolować)\b"
)
LOCAL = re.compile(
    r"\b(?:jeden|jednym|jednego|pojedyncz\w*|tylko jeden)\s+(?:kroplown|emiter|punkt)\w*"
)
NEARBY = re.compile(
    r"\b(?:pozostałe|sąsiednie|inne)\b.*\b(?:dział|podaj|kapi|mają przepływ|płynie|prawidłowo|normalnie)"
)
_GROUP_PATTERNS = (
    re.compile(r"\bcał\w* (?:lini|stref|sekcj)\w*"),
    re.compile(r"\bkilk\w* (?:kroplown|emiter|punkt)\w*"),
    re.compile(r"\bwszystk\w* (?:kroplown|emiter)\w*"),
)


def _group_assertion(text: str) -> bool:
    return any(pattern.search(text) for pattern in _GROUP_PATTERNS)


WEAK = re.compile(
    r"\b(?:słab|such|ledwie|ucier|brak przepływu|nie podaj|nie dział|nie kapi|mało wody|kapie zbyt wolno)\w*"
)
FILTER = re.compile(r"\bfiltr\w*\b")
DIRTY = re.compile(r"\b(?:zabrudz|brudn|zatkan|zapycha|osad)\w*")
CLEAN = re.compile(r"\b(?:czyst|wyczyszcz|bez osadu)\w*")
RETRACT = re.compile(r"\b(?:cofam|nie wiem|nie potwierdz|nie wiadomo|wycofuj)\w*")
HYPOTHETICAL = re.compile(r"\b(?:jeśli|jeżeli|gdyby|możliwe|prawdopodobnie)\b")


@dataclass
class Observation:
    spread: str | None = None
    filter_state: str | None = None


def _observations(turns: Sequence[str]) -> tuple[str, dict[str, Observation]]:
    by_zone: dict[str, Observation] = {}
    current = ""
    for message in turns:
        for assertion in re.split(r"(?<=[.!?;])\s+", message):
            zones = ZONE.findall(assertion)
            if (
                len(set(zones)) > 1
                or assertion.endswith("?")
                or HYPOTHETICAL.search(assertion)
            ):
                continue
            if zones:
                current = zones[-1]
            state = by_zone.setdefault(current, Observation())
            if RETRACT.search(assertion):
                if FILTER.search(assertion):
                    state.filter_state = None
                else:
                    state.spread = None
                continue
            if WEAK.search(assertion):
                if _group_assertion(assertion):
                    state.spread = "group"
                elif LOCAL.search(assertion) and NEARBY.search(assertion):
                    state.spread = "local"
            elif _group_assertion(assertion) and re.search(
                r"\bdziałają (?:już )?(?:prawidłowo|normalnie)", assertion
            ):
                state.spread = None
            if FILTER.search(assertion):
                if re.search(r"\bnie (?:jest )?(?:zabrudzon|czyst)", assertion):
                    state.filter_state = None
                elif DIRTY.search(assertion):
                    state.filter_state = "dirty"
                elif CLEAN.search(assertion):
                    state.filter_state = "clean"
    return current, by_zone


def irrigation_reply(prompt: str, users: Sequence[str]) -> str | None:
    if not (REQUEST.search(prompt) and DOMAIN.search(prompt)):
        return None
    current, by_zone = _observations(users)
    zones = set(ZONE.findall(prompt))
    selected = by_zone.get(next(iter(zones), current)) if len(zones) <= 1 else None
    if selected is None or selected.spread is None:
        return "Czy słaby przepływ dotyczy jednego kroplownika czy kilku na tej samej linii?"
    card = read_card("irrigation")
    guidance = card.get("guidance") if card else None
    action = selected.spread
    if action == "group":
        action = selected.filter_state or "upstream"
    step = guidance.get(action) if isinstance(guidance, dict) else None
    if card is None or not isinstance(step, str):
        return "Czy możesz podać wiarygodną kartę konserwacji tej instalacji?"
    return f"{step} {card_link(card, 'Poradnik OSU Extension')}"
