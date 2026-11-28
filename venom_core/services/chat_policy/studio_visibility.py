"""Keep private contents and audience-specific fields out of public labels."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from venom_core.api.schemas.llm_simple import HistoryMessage

_WORD = r"[^\W\d_]+(?:-[^\W\d_]+)?"
_PHRASE = rf"{_WORD}(?: {_WORD}){{0,5}}?"
_LABEL_PAIR = re.compile(
    rf"(?:^|[.!?]\s+)(?P<first>{_WORD})\s+(?:ma|zawiera)\s+{_PHRASE}\s+dla\s+"
    rf"(?P<recipient1>{_PHRASE}),\s*(?P<second>{_WORD})\s+(?:(?:ma|zawiera)\s+)?"
    rf"{_PHRASE}\s+dla\s+(?P<recipient2>{_PHRASE})[.!]",
    re.I,
)
_LABEL_PRIVACY = re.compile(
    r"(?:potrzebuję (?:do każdej|dla obu)|podaj (?:do każdej|dla obu))\s+"
    r"(?:podpis\w*|etykiet\w*)\s+bez\s+(?:danych|informacji|wzmianek)\s+"
    r"o\s+(?:zawartości|treści)(?: na froncie| z przodu)?[.!]?"
    r"(?:\s+co (?:wpisać|napisać)\?)?",
    re.I,
)
_LABEL_REFERENCE = re.compile(
    rf"(?:w\s+tej|na\s+tej)\s+dla\s+(?P<name>{_PHRASE})\s+"
    r"(?:podaj|dopisz|dodaj)\s+(?:jeszcze\s+)?numer\s+sprawy\s+"
    r"(?P<reference>[A-Z0-9][A-Z0-9/-]{1,29}),?\s+(?:resztę|pozostałe)\s+zostaw[.!]?",
    re.I,
)

_FORM = r"(?:wersja|formularz|karta|bilet|arkusz)"
_FIELD_PAIR = re.compile(
    rf"\b{_FORM}\s+(?:dla\s+)?(?P<group1>{_WORD})\s+(?:ma zawierać|zawiera|ma)\s+"
    rf"(?P<field1>{_PHRASE}),\s*(?:a\s+)?{_FORM}\s+(?:dla\s+)?(?P<group2>{_WORD})"
    rf"\s+(?:(?:ma zawierać|zawiera|ma)\s+)?(?P<field2>{_PHRASE})[.!]\s*"
    rf"(?:w obu ma być|obie mają|oba mają)\s+(?P<shared>{_PHRASE})[.!]\s*"
    r"(?:jakich pól potrzebuję|rozpisz dwie listy pól)[.!?]?$",
    re.I,
)
_FIELDS_FOR = re.compile(
    rf"(?:chodzi mi o (?P<clarification>{_PHRASE})[.!]\s*)?"
    r"(?:pokaż|wypisz)\s+(?:tylko|jedynie|wyłącznie)\s+pola"
    rf"(?:\s+na\s+{_WORD})?\s+dla\s+(?P<group>{_WORD})"
    r"(?:,\s*bez omawiania tego, co jest dla\s+[^\W\d_]+)?[.!?]?",
    re.I,
)
_HIDE_FIELD = re.compile(
    rf"(?:a\s+jeśli\s+)?chcę\s+(?:schować|ukryć)\s+{_PHRASE}\s+"
    rf"przed\s+(?P<group>{_WORD})\?",
    re.I,
)


@dataclass(frozen=True)
class _Label:
    label: str
    recipient: str

    def render(self, reference: str = "") -> str:
        suffix = f", sprawa {reference}" if reference else ""
        name = self.label[:1].upper() + self.label[1:]
        return f"{name} — „Dla {self.recipient}{suffix}”."


def _labels(text: str) -> tuple[_Label, _Label] | None:
    match = _LABEL_PAIR.search(text)
    if (
        not match
        or not _LABEL_PRIVACY.fullmatch(text[match.end() :].strip())
        or match["recipient1"].casefold() == match["recipient2"].casefold()
        or match["first"].casefold() == match["second"].casefold()
    ):
        return None
    return (
        _Label(match["first"], match["recipient1"]),
        _Label(match["second"], match["recipient2"]),
    )


def _scope_key(word: str) -> str:
    return word.casefold().removesuffix("ami").removesuffix("ów")


def _fields(text: str, users: Sequence[str]) -> str | None:
    if fields := _FIELD_PAIR.search(text):
        first, second = fields["group1"], fields["group2"]
        if _scope_key(first) == _scope_key(second):
            return None
        return (
            f"- Dla {first}: {fields['field1']}, {fields['shared']}.\n"
            f"- Dla {second}: {fields['field2']}, {fields['shared']}."
        )
    selection = _FIELDS_FOR.fullmatch(text)
    hide = _HIDE_FIELD.fullmatch(text)
    if not users or not (selection or hide):
        return None
    source = _FIELD_PAIR.search(users[-1])
    if (
        source is None
        and selection
        and len(users) >= 2
        and _HIDE_FIELD.fullmatch(users[-1])
    ):
        source = _FIELD_PAIR.search(users[-2])
    if source is None:
        return None
    groups = {
        _scope_key(source["group1"]): source["field1"],
        _scope_key(source["group2"]): source["field2"],
    }
    if hide:
        if _scope_key(hide["group"]) in groups:
            return "Które oznaczenie masz na myśli?"
        return None
    if selection is None or (key := _scope_key(selection["group"])) not in groups:
        return None
    own = groups[key]
    if clarification := selection["clarification"]:
        other = next((value for name, value in groups.items() if name != key), "")
        prefix = clarification.casefold() + " "
        if not (other.casefold() + " ").startswith(prefix) or (
            own.casefold() + " "
        ).startswith(prefix):
            return None
    return f"- {own}\n- {source['shared']}"


def studio_visibility(text: str, history: Sequence[HistoryMessage]) -> str | None:
    """Render only explicitly allowed fields or neutral recipient labels."""
    text = " ".join(text.split())
    if labels := _labels(text):
        return "\n".join(label.render() for label in labels)
    users = [" ".join(turn.content.split()) for turn in history if turn.role == "user"]
    if (
        users
        and (change := _LABEL_REFERENCE.fullmatch(text))
        and (labels := _labels(users[-1]))
    ):
        person = change["name"].casefold()
        if any(label.recipient.casefold() == person for label in labels):
            return "\n".join(
                label.render(
                    change["reference"] if label.recipient.casefold() == person else ""
                )
                for label in labels
            )
    return _fields(text, users)
