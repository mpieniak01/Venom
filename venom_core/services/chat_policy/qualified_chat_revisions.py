"""Prefer the current user-supplied source when a plain turn updates one field."""

from __future__ import annotations

import re
from collections.abc import Sequence

from venom_core.services.chat_policy.qualified_chat_quote import without_quotes

_DOCUMENT = (
    r"(?:kart[kc]|ulot[kc]|ogłosz|notat[kc]|komunikat|tablic|dokumen|instrukcj)\w*"
)
_NEW = r"(?:aktualn|nowsz|zaktualizowan|poprawion)\w*"
_UPDATED_SOURCE = re.compile(
    rf"^\s*(?:na|w|mam)\s+{_NEW}\s+{_DOCUMENT}\b",
    re.I,
)
_PUBLIC_CHECK = re.compile(
    r"\b(?:sprawdź|zweryfikuj|potwierdź|poszukaj)\b[^.!?]{0,90}"
    r"\b(?:w internecie|w sieci|online|na stronie|w (?:publiczn|oficjaln)\w* źród\w*)\b",
    re.I,
)
_NO_LOOKUP = re.compile(
    r"\b(?:bez (?:\w+ )?(?:wyszukiwania|szukania|sprawdzania|korzystania z internetu)|"
    r"nie (?:szukaj|wyszukuj)(?: ponownie)?\b|"
    r"nie (?:sprawdzaj|weryfikuj) (?:ponownie )?"
    r"(?:internetu|w internecie|w sieci|online|na stronie)|nie korzystaj z internetu)\b",
    re.I,
)
_LOCAL_REVISION = re.compile(
    r"(?:^|[.!?]\s+)(?:skróć|doprecyzuj|przeredaguj|przeformułuj)\s+"
    r"(?:to\b|(?:(?:poprzedni[ąe]|powyższ[ąe])\s+)?"
    r"(?:odpowiedź|wyjaśnienie|opis|szkic|podsumowanie))"
    r"(?=\s*(?:[.!?]|$|do\b|i\b|w\b|z\b))",
    re.I,
)
_QUOTED_TASK = re.compile(
    r"^\s*(?:przetłumacz|przeredaguj|przeformułuj|zacytuj|skróć|"
    r"napisz inaczej|sformułuj inaczej)\b",
    re.I,
)
_COMPOSITION_TASK = re.compile(
    r"^\s*(?:napisz|ułóż|przygotuj|zredaguj|przeredaguj|potrzebuję|poproszę|podaj|zmień|popraw|zastąp)\b",
    re.I,
)
_COMPOSITION_FORM = re.compile(
    r"\b(?:podziękowani\w*|zaproszeni\w*|życzeni\w*|"
    r"(?:tekst|treść|szkic|temat\w*) wiadomości|zdani\w* otwarcia|wiadomość (?:dla|do))\b",
    re.I,
)
_COMPOSITION_WITH_SOURCE = re.compile(
    r"\b(?:wikipedi\w*|na podstawie (?:publiczn\w* |oficjaln\w* )?źród\w*|"
    r"(?:aktualn\w*|najnowsz\w*|dzisiejsz\w*) wiadomości)\b",
    re.I,
)
_LINK = re.compile(r"\[([^\]]+)\]\(https?://[^)\s]+\)|\bhttps?://[^\s<>]+", re.I)
_EMPTY_LINK_LABEL = re.compile(r"(?im)(?:^|\s)(?:link|źródło|odnośnik):[ \t]*(?=$|\n)")
_SOURCE_REVISION_HINT = (
    "Najnowsza wiadomość użytkownika zawiera aktualizację źródła. "
    "Przepisz z niej aktualną wartość podanego pola. "
    "Z wcześniejszego materiału zachowaj pozostałe pola, których aktualizacja nie zmienia. "
    "Wcześniejsza odpowiedź asystenta nie rozstrzyga konfliktu wartości. "
    "Nie przypisuj aktualizacji wcześniejszemu odnośnikowi. "
    "Gdy użytkownik prosi o samą wartość, podaj samą wartość."
)


def source_revision_hint(text: str) -> str:
    if _UPDATED_SOURCE.search(text) and not _PUBLIC_CHECK.search(without_quotes(text)):
        return _SOURCE_REVISION_HINT
    return ""


def _lookup_instruction(visible: str) -> bool | None:
    requested = max(
        (match.start() for match in _PUBLIC_CHECK.finditer(visible)), default=-1
    )
    declined = max(
        (match.start() for match in _NO_LOOKUP.finditer(visible)), default=-1
    )
    if requested == declined:
        return None
    return requested > declined


def explicit_lookup_allowed(text: str) -> bool:
    """Recognize the newest explicit lookup permission in the current turn."""
    return _lookup_instruction(without_quotes(text)) is True


def lookup_forbidden(text: str, previous_users: Sequence[str] = ()) -> bool:
    """Keep the user's lookup decision for revisions of the same answer."""
    visible = without_quotes(text)
    choice = _lookup_instruction(visible)
    if choice is not None:
        return not choice
    if not _LOCAL_REVISION.search(visible):
        return False
    for preceding in reversed(previous_users):
        visible = without_quotes(preceding)
        choice = _lookup_instruction(visible)
        if choice is not None:
            return not choice
        if not _LOCAL_REVISION.search(visible):
            break
    return False


def public_lookup_query(text: str) -> str | None:
    """Honor the latest explicit lookup instruction and treat quoted text as data."""
    visible = without_quotes(text)
    choice = _lookup_instruction(visible)
    if choice is False:
        return None
    requested = choice is True
    if (
        not requested
        and _COMPOSITION_TASK.match(visible)
        and _COMPOSITION_FORM.search(visible)
        and not _COMPOSITION_WITH_SOURCE.search(visible)
    ):
        return None
    if not requested and visible != text and _QUOTED_TASK.match(visible):
        return visible
    return text


def without_previous_links(text: str) -> str:
    if not _LINK.search(text):
        return text
    unlinked = _LINK.sub(lambda match: match[1] or "", text)
    return _EMPTY_LINK_LABEL.sub("", unlinked).rstrip()
