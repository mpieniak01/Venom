"""Keep an explicitly requested short draft in the user's requested form."""

from __future__ import annotations

import re

from venom_core.services.chat_policy.qualified_chat_quote import (
    single_quoted_operand,
    without_quotes,
)

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
_SINGLE_SELECTION = re.compile(
    r"(?<!nie )\bwybierz (?:coś|jedną opcję|jedną propozycję)\b", re.I
)
_SINGLE_ADAPTATION = re.compile(
    r"(?<!nie )\b(?:jak (?:zastosować|wykonać|wdrożyć)|doprecyzuj|dostosuj|rozwiń) "
    r"(?:tę|tą) (?:propozycję|opcję)\b",
    re.I,
)
_COMPARISON = re.compile(
    r"^\s*(?:co (?:będzie|jest) (?:łagodniejsz\w*|uprzejmiejsz\w*|lepsz\w*)|"
    r"porównaj|która wersja)\b",
    re.I,
)
_COMPOUND_REQUEST = re.compile(r"\b(?:przy okazji|dodatkowo|oprócz tego)\b", re.I)
_SAME_REQUEST = re.compile(r"\b(?:tę samą|tę samą uprzejmą) prośbę\b", re.I)
_NARROW_REVISION = re.compile(r"\b(?:już tylko|wyłącznie|tylko i wyłącznie)\b", re.I)
_OPENING_ONLY = re.compile(
    r"^\s*(?:zmień|popraw|zastąp|przeredaguj)\s+(?:wyłącznie|tylko)\s+"
    r"(?:zdanie\s+otwarcia\b|pierwsze\s+zdanie\b|otwarcie(?=[.!?,:]|$))",
    re.I,
)
_SUBJECT_AND_OPENING = re.compile(
    r"^\s*(?:podaj|napisz|zaproponuj|ułóż|przygotuj)\s+(?:krótki\s+)?temat\b"
    r"[^.!?\n]{0,96}\b(?:zdanie\s+otwarcia|pierwsze\s+zdanie)\b",
    re.I,
)
_SUBJECT_LINE = re.compile(r"(?im)^[ \t*]*temat[ *]*:[^\r\n]*(?:\r?\n|$)")
_SENTENCE_END = re.compile(r"[.!?](?=\s|$)")
_ABBREVIATION = re.compile(r"\b(?:godz|ul|nr|np|tj|tzn|dr|prof|m\.in)\.$", re.I)
_OPENING_CONTENT = re.compile(
    r"^\s*(?:[.:]\s*|,?\s*(?:tak,\s*)?(?:żeby|aby|by)\s+"
    r"(?:(?:informowało|wskazywało|mówiło|wynikało z niego),\s+że|"
    r"(?:poinformować|wskazać|powiedzieć),\s+że)\s+)",
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


def revises_opening_only(text: str) -> bool:
    return bool(_OPENING_ONLY.match(without_quotes(text)))


def opening_sentence(draft: str) -> str:
    text = _SUBJECT_LINE.sub("", draft).strip()
    for end in _SENTENCE_END.finditer(text):
        if not _ABBREVIATION.search(text[max(0, end.end() - 12) : end.end()]):
            return text[: end.end()]
    return text


def opening_target(text: str) -> str | None:
    command = _OPENING_ONLY.match(text)
    if command is None:
        return None
    tail = text[command.end() :]
    intro = _OPENING_CONTENT.match(tail)
    if intro is None:
        return None
    content = tail[intro.end() :].strip()
    if content.startswith(("„", "«", '"')):
        content = single_quoted_operand(content) or ""
    return opening_sentence(content) or None


def _opening_key(text: str) -> str:
    sentence = " ".join(text.split()).removesuffix(".")
    return sentence[:1].upper() + sentence[1:]


def opening_matches(sentence: str, target: str | None) -> bool:
    """Verify an explicit proposition without guessing semantic equivalence."""
    return bool(sentence and target and _opening_key(sentence) == _opening_key(target))


def writing_hint(text: str) -> str:
    visible = without_quotes(text)
    if _SUBJECT_AND_OPENING.search(visible):
        return (
            "Podaj temat oraz jedno gotowe zdanie otwarcia. Jeśli polecenie "
            "zawiera zdarzenie, czas lub miejsce, użyj tych faktów od razu. "
            "W takim poleceniu «z tego zdania» odsyła do treści bieżącej prośby. "
            "Gdy fakty podano, przejdź do szkicu bez dopytywania o tekst."
        )
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


def selects_one_proposal(text: str) -> bool:
    """Identify a request to select one option from an earlier list."""
    return bool(_SINGLE_SELECTION.search(without_quotes(text)))


def ordinary_reply_hint(text: str) -> str:
    """Keep short Studio turns complete and responsive to the latest request."""
    visible = without_quotes(text)
    hints = [_ORDINARY_BUDGET_HINT]
    if _SINGLE_ADAPTATION.search(visible):
        hints.append(
            "Podaj jeden konkretny sposób wykonania wcześniej wybranej czynności "
            "w jednym krótkim zdaniu. Wskaż, co użytkownik ma zrobić i na czym "
            "ma się skupić. Uwzględnij ostatnie ograniczenie. "
            "Pomiń samą nazwę czynności i pozostałe propozycje."
        )
    if _COMPOUND_REQUEST.search(visible):
        hints.append(
            "Spełnij każdą część polecenia. Przy zmianie jednego pola "
            "podaj też pozostałe ustalenia, których zmiana nie dotyczy."
        )
    if _SAME_REQUEST.search(visible):
        hints.append(
            "Zachowaj tryb uprzejmej prośby skierowanej do odbiorcy. "
            "Treść ma pozostać prośbą po zmianie języka."
        )
    if _REVISION.search(visible) and not _MULTIPLE_DRAFTS.search(visible):
        hints.append(
            "Podaj sam gotowy tekst, w jednej wersji. "
            "W zachowanej treści przenieś dokładne liczby i warunki "
            "użytkownika. Usuń części, z których użytkownik zrezygnował."
        )
        if _NARROW_REVISION.search(visible):
            hints.append(
                "Zostaw tylko wskazany składnik. Opuść resztę wcześniejszych "
                "ustaleń, w tym wcześniejsze obowiązki spoza nowego zakresu."
            )
    if visible != text and _COMPARISON.search(visible):
        hints.append(
            "Wyjaśnij znaczenie obu przytoczonych wersji, a potem uzasadnij "
            "ocenę różnicy tonu."
        )
    return " ".join(hints)
