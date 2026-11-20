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
_REVISION = re.compile(
    r"\b(?:sformułuj|sformułowani\w*|gotowe zdanie|przeredaguj)\b",
    re.I,
)
_SINGLE_CHOICE = re.compile(
    r"\b(?:wybierz (?:coś|jedną opcję|jedną propozycję)|"
    r"(?:tę|tą) (?:propozycję|opcję))\b",
    re.I,
)
_COMPARISON = re.compile(
    r"^\s*(?:co (?:będzie|jest) (?:łagodniejsz\w*|uprzejmiejsz\w*|lepsz\w*)|"
    r"porównaj|która wersja)\b",
    re.I,
)
_ORDINARY_BUDGET_HINT = (
    "Zacznij od odpowiedzi na ostatnie pytanie. "
    "Jeśli podajesz wartość, wynik z jednostką ma poprzedzać objaśnienie. "
    "Gdy potrzebujesz informacji do odpowiedzi, zadaj jedno krótkie pytanie. "
    "Zakończ po spełnieniu prośby, bez dodatkowych wariantów i pytań. "
    "Zastosuj aktualne warunki użytkownika i żądaną liczbę elementów. "
    "W gotowym tekście zachowaj liczbę adresatów i właściwą formę zwrotu."
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
        "Zachowaj pojedynczego adresata, jeśli podano jedną osobę. "
        "Jeśli piszesz podziękowanie, "
        "wyraź ciepły ton przez wdzięczność. "
        "Zmiana tonu zachowuje temat i podane fakty. "
        "Nie dopisuj niepodanych ilości, przebiegu ani wyników zdarzenia. "
        "Nie przypisuj czynności wykonawcy ani odbiorcy, których użytkownik "
        "nie podał. Zachowaj bezosobową formę faktu, jeśli była podana. "
        "Wcześniejszy szkic asystenta nie jest źródłem nowych faktów. "
        "Jeśli się urwał, napisz kompletną wersję."
    )


def ordinary_reply_hint(text: str) -> str:
    """Keep short Studio turns complete and responsive to the latest request."""
    visible = without_quotes(text)
    hints = [_ORDINARY_BUDGET_HINT]
    if _SINGLE_CHOICE.search(visible):
        hints.append(
            "Wybierz lub dopracuj jedną czynność zgodną z wykluczeniami. "
            "Pomiń wcześniejszą listę propozycji."
        )
    if _REVISION.search(visible) and not _MULTIPLE_DRAFTS.search(visible):
        hints.append(
            "Podaj sam gotowy tekst, w jednej wersji. "
            "W zachowanej treści przenieś dokładne liczby i warunki "
            "użytkownika. Usuń części, z których użytkownik zrezygnował."
        )
    if visible != text and _COMPARISON.search(visible):
        hints.append(
            "Wyjaśnij znaczenie obu przytoczonych wersji, a potem uzasadnij "
            "ocenę różnicy tonu."
        )
    return " ".join(hints)
