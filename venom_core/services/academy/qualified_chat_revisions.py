"""Prefer the current user-supplied source when a plain turn updates one field."""

from __future__ import annotations

import re

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
    r"\b(?:w internecie|w sieci|online|na stronie|w publiczn\w* źród)\b",
    re.I,
)
_SOURCE_REVISION_HINT = (
    "Najnowsza wiadomość użytkownika zawiera aktualizację źródła. "
    "Przepisz z niej aktualną wartość podanego pola. "
    "Z wcześniejszego materiału zachowaj pozostałe pola, których aktualizacja nie zmienia. "
    "Wcześniejsza odpowiedź asystenta nie rozstrzyga konfliktu wartości."
)


def source_revision_hint(text: str) -> str:
    if _UPDATED_SOURCE.search(text) and not _PUBLIC_CHECK.search(text):
        return _SOURCE_REVISION_HINT
    return ""
