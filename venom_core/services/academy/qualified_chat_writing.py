"""Keep an explicitly requested short draft in the user's requested form."""

from __future__ import annotations

import re

from venom_core.services.academy.qualified_chat_quote import without_quotes

_DRAFT = re.compile(r"\b(?:napisz|ułóż|przygotuj)\b", re.I)
_SENTENCES = re.compile(
    r"\b(1|2|3|4|jedno|dwa|trzy|cztery|jednym|dwóch|trzech|czterech) "
    r"(?:(?:krótkie|krótkim|krótkich) )?zdani\w*",
    re.I,
)
_MULTIPLE_DRAFTS = re.compile(
    r"\b(?:wariant\w*|wersje|wersji|propozycje|opcje)\b", re.I
)
_COUNTS = {
    "jedno": "1",
    "jednym": "1",
    "dwa": "2",
    "dwóch": "2",
    "trzy": "3",
    "trzech": "3",
    "cztery": "4",
    "czterech": "4",
}


def writing_hint(text: str) -> str:
    visible = without_quotes(text)
    if not _DRAFT.search(visible) or _MULTIPLE_DRAFTS.search(visible):
        return ""
    count = _SENTENCES.search(visible)
    if count is None:
        return ""
    value = count[1].casefold()
    return (
        f"Podaj jeden gotowy tekst. Liczba zdań: {_COUNTS.get(value, value)}. "
        "Bez zapowiedzi i wariantów. W gotowym tekście nazwij wskazany temat "
        "lub zdarzenie, używając słów użytkownika w odpowiedniej odmianie. "
        "Zwracaj się do adresatów tekstu. Jeśli piszesz podziękowanie, "
        "wyraź ciepły ton przez wdzięczność. "
        "Zmiana tonu zachowuje temat i podane fakty. "
        "Nie dopisuj niepodanych ilości, przebiegu ani wyników zdarzenia. "
        "Nie przypisuj czynności wykonawcy ani odbiorcy, których użytkownik "
        "nie podał. Zachowaj bezosobową formę faktu, jeśli była podana. "
        "Wcześniejszy szkic asystenta nie jest źródłem nowych faktów. "
        "Jeśli się urwał, napisz kompletną wersję."
    )
