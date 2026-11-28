"""Ground layout advice in the user's explicit arrangement and constraints."""

from __future__ import annotations

import re
from collections.abc import Sequence

from venom_core.api.schemas.llm_simple import HistoryMessage
from venom_core.services.chat_policy.qualified_chat_quote import without_quotes

_NAME = r"[^\W\d_]+(?:-[^\W\d_]+)?"
_DISPLAY_OPTIONS = re.compile(
    rf"\b(?:wariant|plan) (?P<line>{_NAME}) (?:ma|przewiduje) [^.!?]{{1,85}}?"
    r"\b(?:w jednym rzędzie|wzdłuż jednej alejki)"
    rf"[,.;]\s*(?:(?:a|zaś|natomiast) )?(?:wariant|plan) (?P<rooms>{_NAME}) "
    r"(?:ma|przewiduje) [^.!?]{1,85}?\bw dwóch (?:osobnych|odrębnych) salach\b",
    re.I,
)
_ORIENTATION_GOAL = re.compile(
    r"(?:[.!]\s*|[,;] (?:a )?)(?:zależy mi na (?:prostej|łatwej) orientacji"
    r"|chcę ułatwić orientację(?: [^.!?]{1,55})?)[.!]\s*"
    r"(?:który (?:wariant|plan) (?:bardziej do tego pasuje|(?:będzie )?lepszy)"
    r"|który wybrać)\?$",
    re.I,
)
_BOTH_ENTRANCES = re.compile(
    rf"(?:W {_NAME} )?(?:da się (?:jednak )?wejść|można wejść) do rzędu z obu stron"
    r"[.!]\s*czy (?:jedna )?strzałka od wejścia (?:nadal )?jest dobrym pomysłem\?",
    re.I,
)
_UNDIRECTED_SIGN = re.compile(
    r"(?:chcę |proszę )?bez (?:wyznaczania kierunku|kierunku|strzałek) "
    r"(?:i (?:bez )?|ani )(?:numeracji|numerów)[.!]\s*"
    r"(?:jak pomóc tym osobom jednym oznaczeniem\?|"
    r"podaj jeden sposób (?:oznaczenia|orientacji)[.!])",
    re.I,
)

_COURTYARD = re.compile(
    r"^(?:(?:podczas [^.!?]{12,110} chce |jak(?: w dwóch zdaniach)? ))?"
    r"(?:wyjaśni[ćj]|wytłumacz(?:yć)?) różnicę między "
    r"(?P<object>dziedzińcem|podwórzem) otwartym (?:od ulicy|na ulicę),?"
    r" a (?:(?:dziedzińcem|podwórzem) )?(?:zamkniętym bramą|z wejściem przez bramę)"
    r"(?: w (?:pół minuty|dwóch zdaniach))?"
    r"(?:[.!]\s+ma na to [^.!?]{1,145}[.!]\s+pomóż (?:jej|mu)[.!]|[.!?])$",
    re.I,
)
_GATE_SCOPE = re.compile(
    r"(?:tylko )?nie (?:wyciągaj z bramy wniosku, że ktoś (?:tam )?nie wpuszcza gości"
    r"|zakładaj(?: na podstawie bramy)?, że (?:teren jest prywatny|goście nie mogą wejść))"
    r"[.!]",
    re.I,
)
_GATE_OPEN = re.compile(
    r"a (?:jeśli|gdy) brama (?:akurat )?jest (?:akurat )?otwarta"
    r"(?:, (?:to cały podział się sypie|czy to zmienia układ wejścia))?\?",
    re.I,
)

_MUSIC_ON_TABLE = re.compile(r"\bna (?:\w+ )?stole\s+(?:płyty|winyle|nagrania)\b", re.I)
_ARTIST_INDEX = re.compile(
    r"\balfabetyczn(?:ie|ej) (?:według|wg) (?:nazw )?wykonawców\b",
    re.I,
)
_MUSIC_CATEGORY = re.compile(
    rf"(?P<organizer>{_NAME}) (?:chce|woli|proponuje) (?:je )?"
    r"(?:ułożyć|posortować|pogrupować)(?: (?:je|płyty|winyle|nagrania))? "
    r"według (?:stylu|gatunku)\b",
    re.I,
)
_COMPARE_STORAGE = re.compile(
    r"\b(?:co warto wziąć pod uwagę|jakie są zalety obu układów)\?$", re.I
)
_SELECT_CATEGORY = re.compile(
    rf"(?:^|(?<=[.!])\s+)zachowujemy tylko (?:układ|podział|wariant) "
    rf"(?P<choice>według (?:stylu|gatunku)|{_NAME})[.!]\s*"
    r"(?:jak go uczytelnić|jak oznaczyć grupy)\?",
    re.I,
)
_TABLE_SIGN = re.compile(
    r"bez (?:tablic wiszących|wiszących tablic)[.!]\s*"
    r"(?:podaj )?jeden sposób(?: oznaczenia)?,? który mieści się na stole[.!]",
    re.I,
)


def _display_plan(text: str) -> str | None:
    options = _DISPLAY_OPTIONS.search(text)
    if _ORIENTATION_GOAL.search(text) and options:
        if options["line"].casefold() != options["rooms"].casefold():
            return options["line"]
    return None


def _display_reply(text: str, previous: str, earlier: str) -> str | None:
    if plan := _display_plan(text):
        return (
            f"Wariant {plan} ułatwi orientację osobom, które widzą wystawę po raz pierwszy. "
            "Jeden rząd łatwiej objąć wzrokiem niż ekspozycję rozdzieloną między sale."
        )
    if _BOTH_ENTRANCES.fullmatch(text) and _display_plan(previous):
        return (
            "Do rzędu można wejść z dwóch stron, więc jedna strzałka przy jednym wejściu "
            "pomoże tylko części osób. Przy obu wejściach sprawdzi się ten sam schemat rzędu."
        )
    if (
        _UNDIRECTED_SIGN.fullmatch(text)
        and _BOTH_ENTRANCES.fullmatch(previous)
        and _display_plan(earlier)
    ):
        return "Umieść przy obu wejściach ten sam prosty schemat pokazujący układ ekspozycji w jednym rzędzie."
    return None


def _courtyard_kind(text: str) -> str | None:
    if comparison := _COURTYARD.search(without_quotes(text)):
        return {"dziedzińcem": "dziedziniec", "podwórzem": "podwórze"}[
            comparison["object"].casefold()
        ]
    return None


def _courtyard_reply(text: str, previous: str, earlier: str) -> str | None:
    kind = _courtyard_kind(text)
    if not kind and _GATE_SCOPE.fullmatch(text):
        kind = _courtyard_kind(previous)
    if kind:
        return (
            f"Na {kind} w pierwszym układzie wchodzi się od razu z ulicy. "
            "W drugim wejście prowadzi przez bramę."
        )
    if _GATE_OPEN.fullmatch(text) and (
        _courtyard_kind(previous)
        or (_GATE_SCOPE.fullmatch(previous) and _courtyard_kind(earlier))
    ):
        return (
            "To rozróżnienie nadal działa. Nawet przy otwartej bramie przejście przez nią "
            "jest elementem układu wejścia, a jej otwarcie może być chwilowe."
        )
    return None


def _category_organizer(text: str) -> str | None:
    artist_index = _ARTIST_INDEX.search(text)
    category = _MUSIC_CATEGORY.search(text)
    if (
        _MUSIC_ON_TABLE.search(text)
        and _COMPARE_STORAGE.search(text)
        and artist_index
        and category
        and artist_index.end() < category.start()
    ):
        return category["organizer"].casefold()
    return None


def _uses_category_order(text: str, organizer: str | None) -> bool:
    decision = _SELECT_CATEGORY.search(text)
    if organizer is None or decision is None:
        return False
    choice = decision["choice"].casefold()
    if choice.startswith("według "):
        return True
    forms = {organizer}
    if organizer.endswith("a"):
        stem = organizer[:-1]
        forms.update((f"{stem}y", f"{stem}i"))
    else:
        forms.add(f"{organizer}a")
        if organizer.endswith("ek"):
            forms.add(f"{organizer[:-2]}ka")
    return choice in forms


def _music_reply(text: str, previous: str, earlier: str) -> str | None:
    if _category_organizer(text):
        return (
            "Alfabet według wykonawców pomaga znaleźć konkretną osobę lub zespół. "
            "Podział według stylu ułatwia przeglądanie nagrań z wybranego gatunku."
        )
    dividers = "Ustaw między grupami na stole stojące przekładki z nazwami stylów."
    if _uses_category_order(text, _category_organizer(previous)):
        return f"{dividers} Odwiedzający trafią do właściwej grupy samodzielnie."
    if _TABLE_SIGN.fullmatch(text) and _uses_category_order(
        previous, _category_organizer(earlier)
    ):
        return dividers
    return None


def layout_reply(text: str, history: Sequence[HistoryMessage]) -> str | None:
    """Resolve layout questions from the current and two most recent user turns."""
    users = [
        " ".join(message.content.split())
        for message in history[-4:]
        if message.role == "user"
    ]
    previous = users[-1] if users else ""
    earlier = users[-2] if len(users) >= 2 else ""
    return (
        _display_reply(text, previous, earlier)
        or _courtyard_reply(text, previous, earlier)
        or _music_reply(text, previous, earlier)
    )
