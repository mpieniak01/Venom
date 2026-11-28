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
_ROW_PROJECTS = re.compile(
    rf"(?:na [^.!?]{{2,45}} są|mamy|rozważam) dwa (?:projekty|układy): "
    rf"(?P<line>{_NAME}) to (?:jedna kolejka|jeden rząd|jedna linia) "
    rf"(?:stanowisk|stoisk), (?:a )?(?P<rooms>{_NAME}) to kilka (?:stołów|stanowisk|stoisk) "
    r"w dwóch (?:pokojach|salach)[.]",
    re.I,
)
_ORIENTATION_GOAL = re.compile(
    r"(?:[.!]\s*|[,;] (?:a )?)(?:zależy mi na (?:prostej|łatwej) orientacji"
    r"|chcę ułatwić orientację(?: [^.!?]{1,55})?"
    r"|zależy mi na tym, żeby (?:osoba pierwszy raz|nowa osoba) (?:łatwo|od razu) "
    r"zobaczyła wszystkie (?:stanowiska|stoiska))[.!]\s*"
    r"(?:który (?:wariant|plan) (?:bardziej do tego pasuje|(?:będzie )?lepszy)"
    r"|który wybrać|co wybrać)\?$",
    re.I,
)
_BOTH_ENTRANCES = re.compile(
    rf"(?:W {_NAME} )?(?:da się (?:jednak )?wejść|można wejść) do rzędu z obu stron"
    r"[.!]\s*czy (?:jedna )?strzałka od wejścia (?:nadal )?jest dobrym pomysłem\?",
    re.I,
)
_AMBIGUOUS_DOORS = re.compile(
    rf"do (?P<name>{_NAME}) (?:wchodzi się|można wejść) z (?:dwóch|obu) końców[.] "
    r"czy (?:informacja|napis) [„\"]zacznij przy (?:drzwiach|wejściu)[”\"] wystarczy\?",
    re.I,
)
_NEUTRAL_PLAN = re.compile(
    r"(?:daj|podaj) jeden neutralny sposób (?:na pokazanie|pokazania) układu "
    r"bez narzucania kolejności[.!?]",
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


_BROWSE_EXHIBITS = re.compile(
    r"(?:przeglądający|oglądający) (?:plakaty|zdjęcia|wydruki|ilustracje) mogą szukać "
    r"konkretnego (?:autora|twórcy) albo (?:poznawać temat, którego wcześniej nie widzieli"
    r"|odkrywać nowe tematy)[.] "
    r"po co grupować według (?:autorów|twórców), a po co według tematów\?",
    re.I,
)
_THEME_CHOICE = re.compile(
    r"(?:zostajemy przy tematach|wybieramy podział tematyczny)[.] "
    r"(?:na (?:płaskim )?stole chcę prosty sposób orientacji"
    r"|na stole potrzebujemy czytelnych oznaczeń)[.!]",
    re.I,
)
_THEME_LABEL = re.compile(
    r"(?:wybierz|podaj) jeden sposób, bez (?:aplikacji, )?(?:wiszących tablic i strzałek"
    r"|strzałek i wiszących tablic)[.!]",
    re.I,
)


def _display_plan(text: str) -> str | None:
    options = _DISPLAY_OPTIONS.search(text) or _ROW_PROJECTS.match(text)
    if _ORIENTATION_GOAL.search(text) and options:
        if options["line"].casefold() != options["rooms"].casefold():
            return options["line"]
    return None


def _door_question(text: str, plan: str | None) -> bool:
    doors = _AMBIGUOUS_DOORS.fullmatch(text)
    if doors and plan:
        name = plan.casefold()
        return doors["name"].casefold() in {name, f"{name}u", f"{name}a"}
    return False


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
    if _door_question(text, _display_plan(previous)):
        return (
            "Sama wskazówka nie wystarczy. Są dwa wejścia, więc nie wiadomo, "
            "przy którym zacząć."
        )
    if _NEUTRAL_PLAN.fullmatch(text) and _door_question(
        previous, _display_plan(earlier)
    ):
        return "Umieść przy obu wejściach ten sam prosty plan jednego rzędu stanowisk."
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


def _theme_reply(text: str, previous: str, earlier: str) -> str | None:
    if _BROWSE_EXHIBITS.fullmatch(text):
        return (
            "Grupy według autorów pomagają znaleźć prace konkretnej osoby. "
            "Podział tematyczny pomaga odkrywać nowe tematy."
        )
    if (_THEME_CHOICE.fullmatch(text) and _BROWSE_EXHIBITS.fullmatch(previous)) or (
        _THEME_LABEL.fullmatch(text)
        and _THEME_CHOICE.fullmatch(previous)
        and _BROWSE_EXHIBITS.fullmatch(earlier)
    ):
        return "Ustaw na stole przy każdej grupie kartę z nazwą tematu."
    return None


_DISPLAY_FIELDS = re.compile(
    r"do (?P<first>gabloty|witryny|szafki) pasuje etykieta z (?P<label>nazwą [^\W\d_]+) i "
    r"(?P<field>datą|godziną), a do (?P<second>katalogu|rejestru) nazwa i "
    r"(?P<other>numer [^\W\d_]+)[.!] przygotuj osobne listy[.!]?",
    re.I,
)
_DISPLAY_ONLY = re.compile(
    r"pokaż mi tylko część dla (?P<scope>gabloty|witryny|szafki)[.!]?", re.I
)
_DISPLAY_CHANGE = re.compile(
    r"w (?P<scope>gablocie|witrynie|szafce) (?:[^.!?]{2,40}?) zastąp "
    r"(?P<replacement>kodem [^\W\d_]+|nazwą [^\W\d_]+)\? "
    r"chodzi mi o (?P<field>datę|godzinę), resztę zostaw[.!]?",
    re.I,
)
_DISPLAY_SCOPE = {
    "gabloty": ("Gablota", "gablocie"),
    "witryny": ("Witryna", "witrynie"),
    "szafki": ("Szafka", "szafce"),
}
_DISPLAY_FIELDS_NOM = {"datą": "Data", "godziną": "Godzina"}
_DISPLAY_FIELDS_ACC = {"datę": "datą", "godzinę": "godziną"}


def _display_field_reply(current: str, previous: str, earlier: str) -> str | None:
    source = _DISPLAY_FIELDS.fullmatch(current)
    scope = _DISPLAY_ONLY.fullmatch(current)
    edit = _DISPLAY_CHANGE.fullmatch(current)
    if scope:
        source = _DISPLAY_FIELDS.fullmatch(previous)
    elif edit and (scope := _DISPLAY_ONLY.fullmatch(previous)):
        source = _DISPLAY_FIELDS.fullmatch(earlier)
    if source is None or (
        scope and scope["scope"].casefold() != source["first"].casefold()
    ):
        return None
    title, locative = _DISPLAY_SCOPE[source["first"].casefold()]
    label = "Nazwa " + source["label"].split(maxsplit=1)[1]
    field = _DISPLAY_FIELDS_NOM[source["field"].casefold()]
    if edit:
        if (
            edit["scope"].casefold() != locative
            or _DISPLAY_FIELDS_ACC[edit["field"].casefold()]
            != source["field"].casefold()
        ):
            return None
        head, rest = edit["replacement"].split(maxsplit=1)
        field = ("Kod" if head.casefold() == "kodem" else "Nazwa") + " " + rest
    result = f"{title}:\n- {label}\n- {field}"
    if not scope:
        catalog = "Katalog" if source["second"].casefold() == "katalogu" else "Rejestr"
        result += f"\n\n{catalog}:\n- Nazwa\n- {source['other'].capitalize()}"
    return result


_STATION_COUNT = r"(?:[1-9][0-9]?|jedn[oaą]|dw(?:ie|a)|trzy|cztery|pięć|sześć|siedem|osiem|dziewięć|dziesięć)"
_STATION_NOUN = r"(?:stacj[aei]|stanowisk[oa]?)"
_STATION_PAIR = re.compile(
    rf"(?:są|mamy) dwa układy stanowisk(?: do ćwiczeń)?[.] "
    rf"w (?P<row>{_NAME}) są (?P<length>{_STATION_COUNT} {_STATION_NOUN}) "
    rf"w jednym (?P<shape>szeregu|rzędzie), (?:a )?w (?P<split>{_NAME}) "
    rf"(?P<left>{_STATION_COUNT}(?: {_STATION_NOUN})?) po lewej i "
    rf"(?P<right>{_STATION_COUNT}(?: {_STATION_NOUN})?) po prawej od wejścia[.] "
    r"(?:porównaj układ|porównaj układy|opisz oba układy) w dwóch zdaniach[.!]",
    re.I,
)
_STATION_SIGN = re.compile(
    rf"(?:wybieramy|wybieram) (?P<choice>{_NAME})[.] "
    r"(?:jak jednym środkiem pokazać rozmieszczenie przed wejściem, "
    r"nie narzucając kolejności odwiedzania\?"
    r"|podaj jeden sposób pokazania układu przed wejściem bez narzucania kolejności[.!])",
    re.I,
)


def _station_pair(text: str) -> re.Match[str] | None:
    layout = _STATION_PAIR.fullmatch(text)
    if layout and layout["row"].casefold() != layout["split"].casefold():
        return layout
    return None


def _station_reply(current: str, previous: str) -> str | None:
    if layout := _station_pair(current):
        return (
            f"W układzie {layout['row']} w jednym {layout['shape']} znajdują się {layout['length']}. "
            f"W układzie {layout['split']} po lewej stronie wejścia rozmieszczono "
            f"{layout['left']}, a po prawej {layout['right']}."
        )
    choice = _STATION_SIGN.fullmatch(current)
    if choice is None or (layout := _station_pair(previous)) is None:
        return None
    selected = choice["choice"].casefold()
    if selected == layout["split"].casefold():
        shape = "stanowiska po lewej i po prawej stronie wejścia"
    elif selected == layout["row"].casefold():
        shape = f"stanowiska w jednym {layout['shape']}"
    else:
        return None
    return f"Ustaw przed wejściem jeden schemat pokazujący {shape}, bez strzałek i numeracji."


_GROUP_COUNTS = {"dwie": 2, "dwa": 2, "trzy": 3, "cztery": 4, "pięć": 5, "sześć": 6}
_GROUP_COUNT = rf"(?P<count>[2-6]|{'|'.join(_GROUP_COUNTS)})"
_GROUP_CATEGORY = r"techniki|technik|tematy|tematów|gatunki|gatunków"
_GROUP_DEFINITION = re.compile(
    rf"(?:plakaty|wydruki|zdjęcia|prace|ilustracje) na (?:\w+ )?stołach "
    rf"(?:dzielimy|grupujemy) na (?:{_GROUP_COUNT} )?(?:{_GROUP_CATEGORY}): "
    rf"(?P<items>{_NAME}(?:, {_NAME}){{0,4}} (?:i|oraz) {_NAME})[.] "
    r"(?:jak jednym prostym sposobem pokazać odwiedzającym, "
    r"gdzie w układzie stołów zaczyna się każda grupa"
    r"|jak jednym sposobem oznaczyć początek każdej grupy)\?",
    re.I,
)
_GROUP_MOVE = re.compile(
    r"stoły (?:trzeba odsunąć|odsuwamy|przesuwamy) od ściany, "
    r"a (?:etykiety|oznaczenia) mają zostać na blatach[.] "
    r"(?:podaj jedno konkretne rozwiązanie|podaj jeden sposób)[.!]",
    re.I,
)


def _has_named_groups(text: str) -> bool:
    source = _GROUP_DEFINITION.fullmatch(text)
    if source is None:
        return False
    names = re.split(r", | i | oraz ", source["items"].casefold())
    if len(set(names)) != len(names):
        return False
    if not (count := source["count"]):
        return True
    expected = (
        int(count)
        if count.isascii() and count.isdecimal()
        else _GROUP_COUNTS[count.casefold()]
    )
    return len(names) == expected


def _group_labels_reply(current: str, previous: str) -> str | None:
    if _has_named_groups(current) or (
        _GROUP_MOVE.fullmatch(current) and _has_named_groups(previous)
    ):
        return "Na początku każdej grupy ustaw na blacie samostojącą etykietę z nazwą tej grupy."
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
        or _display_field_reply(text, previous, earlier)
        or _courtyard_reply(text, previous, earlier)
        or _music_reply(text, previous, earlier)
        or _theme_reply(text, previous, earlier)
        or _station_reply(text, previous)
        or _group_labels_reply(text, previous)
    )
