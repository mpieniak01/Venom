"""Prefer the current user-supplied source when a plain turn updates one field."""

from __future__ import annotations

import re

from venom_core.services.academy.qualified_chat_quote import without_quotes

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
    r"nie (?:szukaj|wyszukuj|sprawdzaj|weryfikuj) (?:ponownie )?"
    r"(?:w internecie|w sieci|online|na stronie)|nie korzystaj z internetu)\b",
    re.I,
)
_QUOTED_TASK = re.compile(
    r"^\s*(?:przetłumacz|przeredaguj|przeformułuj|zacytuj|"
    r"napisz inaczej|sformułuj inaczej)\b",
    re.I,
)
_COMPOSITION_TASK = re.compile(
    r"^\s*(?:napisz|ułóż|przygotuj|zredaguj|przeredaguj)\b", re.I
)
_COMPOSITION_FORM = re.compile(
    r"\b(?:podziękowani\w*|zaproszeni\w*|życzeni\w*|"
    r"(?:tekst|treść|szkic) wiadomości|wiadomość (?:dla|do))\b",
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


def public_lookup_query(text: str) -> str | None:
    """Honor the latest explicit lookup instruction and treat quoted text as data."""
    visible = without_quotes(text)
    requested = max(
        _PUBLIC_CHECK.finditer(visible), key=lambda match: match.start(), default=None
    )
    declined = max(
        _NO_LOOKUP.finditer(visible), key=lambda match: match.start(), default=None
    )
    if declined and (not requested or declined.start() > requested.start()):
        return None
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
