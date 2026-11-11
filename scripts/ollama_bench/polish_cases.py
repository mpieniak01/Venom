"""Versioned case definitions for the Polish assistant benchmark."""

from __future__ import annotations

from dataclasses import dataclass

VERSION = "pl-assistant-v1"

# Validation and final cases use different source families, documents and speakers.
CORRECTIONS = {
    "final": (
        ("próba chóru", "sala", ("Aster", "Brzoza", "Cedr", "Dereń", "Ekran")),
        (
            "zbiórka kajakowa",
            "punkt spotkania",
            ("Przystań", "Ponton", "Plaża", "Pomost", "Kładka"),
        ),
        (
            "odbiór oprawionego plakatu",
            "dzień",
            ("poniedziałek", "wtorek", "środa", "czwartek", "piątek"),
        ),
        ("dyżur w pracowni", "osoba", ("Adela", "Bartek", "Celina", "Daniel", "Eliza")),
        ("dostawa karmy", "paczkomat", ("KOM17", "KOM23", "KOM42", "KOM56", "KOM81")),
        (
            "lekcja ceramiki",
            "materiał",
            ("szamot", "porcelana", "fajans", "kamionka", "terakota"),
        ),
        ("przegląd łodzi", "godzina", ("10:15", "12:30", "14:20", "16:45", "18:10")),
        (
            "wycieczka rowerowa",
            "miejscowość",
            ("Orneta", "Reszel", "Lidzbark", "Pasym", "Barczewo"),
        ),
    ),
    "validation": (
        (
            "czytanie performatywne",
            "rekwizyt",
            ("dzwonek", "parasol", "koc", "świeca", "piłka"),
        ),
        ("kurs nurkowania", "basen", ("Płetwa", "Rafa", "Bryza", "Sygnał", "Zatoka")),
    ),
}
DOCUMENTS = {
    "final": (
        (
            "instrukcja wypalania szkła",
            "tryb chłodzenia",
            "powolny",
            "strefa dostępu",
            "czerwona",
        ),
        (
            "harmonogram zbiórki elektroodpadów",
            "rejon zbiórki",
            "Ruczaj",
            "punkt przyjęcia",
            "Magazyn B",
        ),
        (
            "regulamin schroniska górskiego",
            "zamknięcie wejścia",
            "22:15",
            "miejsce klucza",
            "portiernia",
        ),
        (
            "protokół prób instalacji wodnej",
            "ciśnienie próbne",
            "8 bar",
            "czas próby",
            "45 minut",
        ),
        (
            "karta przeglądu wózka",
            "numer smaru",
            "LQ-37",
            "następny przegląd",
            "listopad",
        ),
        (
            "cennik archiwum fotograficznego",
            "format kopii",
            "TIFF",
            "czas realizacji",
            "4 dni",
        ),
        (
            "komunikat o zamknięciu ścieżki",
            "odcinek zamknięty",
            "Most Leśny",
            "objazd",
            "Droga Stawowa",
        ),
        (
            "instrukcja pakowania nasion",
            "pojemnik",
            "papierowy",
            "temperatura",
            "6 stopni",
        ),
        (
            "zawiadomienie o przeglądzie windy",
            "numer szybu",
            "W-29",
            "wejście zastępcze",
            "wejście C",
        ),
        (
            "rozpiska zawodów szachowych",
            "sala finałowa",
            "sala 204",
            "kontrola zegarów",
            "9:40",
        ),
    ),
    "validation": (
        ("karta przyjęcia rzeźby", "numer gabloty", "G-66", "opiekun", "Marta"),
        (
            "plan serwisowy lodowiska",
            "godzina otwarcia",
            "8:35",
            "wejście zastępcze",
            "brama D",
        ),
    ),
}
SPEECH = {
    "final": (
        (
            "odbiór gościa",
            "Kogo odbieramy z dworca?",
            ("Łucja", "Jerzy", "Grzegorz", "Żaneta", "Róża"),
        ),
        (
            "adres dostawy",
            "Do której miejscowości ma dotrzeć paczka?",
            ("Żyrardów", "Szczawnica", "Pszczyna", "Łęczyca", "Przemyśl"),
        ),
        (
            "etykieta przesyłki",
            "Jaką etykietę nakleić na paczkę?",
            ("żółta", "błękitna", "szara", "fioletowa", "bursztynowa"),
        ),
        (
            "ilość wyposażenia",
            "Ile krzeseł dostawić?",
            (
                "siedem",
                "jedenaście",
                "piętnaście",
                "dwadzieścia siedem",
                "trzydzieści cztery",
            ),
        ),
        (
            "dyspozycja w pracowni",
            "Gdzie zostawić próbki?",
            ("pod stołem", "na półce", "w szufladzie", "nad zlewem", "obok drzwi"),
        ),
        (
            "potoczna organizacja odbioru",
            "Co mam ogarnąć po drodze?",
            ("rachunki", "klucze", "paragon", "karton", "kurtkę"),
        ),
        (
            "przekazanie godziny",
            "O której jest odprawa?",
            (
                "o siódmej",
                "o dziewiątej",
                "o jedenastej",
                "o trzynastej",
                "o siedemnastej",
            ),
        ),
        (
            "rozróżnienie terminów",
            "Który dzień wybieramy?",
            ("czwartek", "środa", "sobota", "piątek", "niedziela"),
        ),
    ),
    "validation": (
        (
            "obsada przedstawienia",
            "Kogo wpisać na listę?",
            ("Grażyna", "Michał", "Przemysław", "Iga", "Józef"),
        ),
        (
            "zakupy w kwiaciarni",
            "Co zamówić do bukietu?",
            ("goździki", "piwonie", "wrzos", "frezje", "tulipany"),
        ),
    ),
}
SCENES = {
    "final": (
        ("Tablica odjazdów", ("Elbląg", "Toruń", "Grudziądz")),
        ("Lista gabinetów", ("Ortopedia", "Okulistyka", "Rehabilitacja")),
        ("Regały biblioteki", ("Historia", "Poezja", "Przyroda")),
        ("Tablica zapasów", ("Wkręty", "Wiertła", "Śruby")),
        ("Plan szklarni", ("Pomidory", "Papryka", "Ogórki")),
        ("Stanowiska basenu", ("Brokat", "Perła", "Koral")),
        ("Szafki szatni", ("Żółw", "Ryś", "Bóbr")),
        ("Rejestr eksponatów", ("Moździerz", "Czajnik", "Dzbanek")),
    ),
    "validation": (
        ("Plan warsztatów", ("Wiklina", "Tkactwo", "Rzeźba")),
        ("Kontrola żagli", ("Sztorm", "Fala", "Wiatr")),
    ),
}
TOOL_FAMILIES = {
    "final": (
        ("magazyn narzędzi", "lookup_stock", "MN", "17"),
        ("przydział sal", "lookup_owner", "PS", "Adela"),
        ("zajętość promu", "lookup_status", "ZP", "wolny"),
        ("rozkład kolejki", "lookup_time", "RK", "9:35"),
        ("magazyn pasz", "lookup_stock", "MP", "43"),
        ("pokoje gościnne", "lookup_owner", "PG", "Łukasz"),
        ("stacje ładowania", "lookup_status", "SL", "zajęty"),
        ("plan przeglądów", "lookup_time", "PP", "13:20"),
    ),
    "validation": (
        ("skład opakowań", "lookup_stock", "SO", "9"),
        ("dyżury w galerii", "lookup_owner", "DG", "Alicja"),
    ),
}
TOOL_LABELS = {
    "lookup_stock": "stan magazynowy",
    "lookup_owner": "opiekuna rekordu",
    "lookup_status": "bieżący status",
    "lookup_time": "godzinę w harmonogramie",
}
NUMBER_ALIASES = {
    "siedem": "7",
    "jedenaście": "11",
    "piętnaście": "15",
    "dwadzieścia siedem": "27",
    "trzydzieści cztery": "34",
    "o siódmej": "7:00",
    "o dziewiątej": "9:00",
    "o jedenastej": "11:00",
    "o trzynastej": "13:00",
    "o siedemnastej": "17:00",
}


@dataclass(frozen=True)
class Scenario:
    id: str
    group: str
    family: str
    prompt: str
    expected: tuple[str, ...]
    history: tuple[tuple[str, str], ...] = ()
    document: str = ""
    voice: bool = False
    noise: bool = False
    critical: tuple[tuple[str, ...], ...] = ()
    scene: tuple[tuple[str, str], ...] = ()
    scene_title: str = ""
    horizontal: bool = False
    tool: tuple[str, str] | None = None
    tool_error: bool = False
    clarify_tool: bool = False


def build_cases(split: str) -> list[Scenario]:
    if split not in {"final", "validation"}:
        raise ValueError(f"Unknown benchmark split: {split}")
    prefix = "F" if split == "final" else "V"
    cases = []
    for family_no, (family, field, options) in enumerate(CORRECTIONS[split], 1):
        for index, updated in enumerate(options):
            original = options[index - 1]
            cases.append(
                Scenario(
                    f"{prefix}-C{family_no:02}-{index + 1}",
                    "conversation",
                    family,
                    f"Jaka jest aktualna wartość pola «{field}»? Podaj samą wartość.",
                    (updated,),
                    history=(
                        (
                            "user",
                            f"Zapamiętaj ustalenie dotyczące sprawy «{family}». Pole «{field}» ma wartość {original}.",
                        ),
                        ("assistant", "Zapamiętane."),
                        (
                            "user",
                            f"Poprawka do tego ustalenia. Pole «{field}» ma teraz wartość {updated}.",
                        ),
                        ("assistant", "Zaktualizowane."),
                    ),
                )
            )
    for family_no, (family, first, a, second, b) in enumerate(DOCUMENTS[split], 1):
        excerpt = f"Dokument: {family}.\n{first.capitalize()}: {a}.\n{second.capitalize()}: {b}."
        questions = (
            (first, a),
            (second, b),
            ("osoba zatwierdzająca", "brak danych"),
            ("numer telefonu", "brak danych"),
        )
        for index, (field, answer) in enumerate(questions, 1):
            cases.append(
                Scenario(
                    f"{prefix}-I{family_no:02}-{index}",
                    "information",
                    family,
                    f"Jaka jest wartość pola «{field}» w dokumencie? Podaj samą wartość. Gdy jej brakuje, odpowiedz «brak danych».",
                    (answer,),
                    document=excerpt,
                )
            )
    for family_no, (family, question, options) in enumerate(SPEECH[split], 1):
        for index, value in enumerate(options, 1):
            alternatives = (
                (value, NUMBER_ALIASES[value]) if value in NUMBER_ALIASES else (value,)
            )
            prompt = f"{question} Ustalenie to {value}. Podaj samą wartość."
            cases.append(
                Scenario(
                    f"{prefix}-S{family_no:02}-{index}",
                    "speech",
                    family,
                    prompt,
                    alternatives,
                    voice=True,
                    noise=index in {2, 5},
                    critical=(alternatives,),
                )
            )
    for family_no, (family, labels) in enumerate(SCENES[split], 1):
        horizontal = family_no % 2 == 0
        for index in range(1, 6):
            scene = tuple(
                (
                    label,
                    str(
                        (600 if split == "final" else 800)
                        + family_no * 31
                        + index * 4
                        + row
                    ),
                )
                for row, label in enumerate(labels)
            )
            positions = (
                "po lewej stronie" if horizontal else "na górze",
                "po prawej stronie" if horizontal else "na dole",
                "w drugiej pozycji",
                f"przy nazwie {labels[0]}",
                f"przy nazwie {labels[2]}",
            )
            cue = positions[index - 1]
            answer = scene[(0, 2, 1, 0, 2)[index - 1]][1]
            anchor = (
                ("lewej", "lewo") if horizontal else ("górze", "góra"),
                ("prawej", "prawo") if horizontal else ("dole", "dół"),
                ("drugiej", "drugi"),
                (labels[0],),
                (labels[2],),
            )[index - 1]
            cases.append(
                Scenario(
                    f"{prefix}-V{family_no:02}-{index}",
                    "vision_speech",
                    family,
                    (
                        f"Jaki numer widzisz {cue}? Podaj sam numer."
                        if split == "final"
                        else f"Odczytaj oznaczenie {cue}. Zwróć wyłącznie cyfry."
                    ),
                    (answer,),
                    voice=True,
                    noise=index == 3,
                    critical=(anchor,),
                    scene=scene,
                    scene_title=family,
                    horizontal=horizontal,
                )
            )
    for family_no, (family, function, tag, value) in enumerate(TOOL_FAMILIES[split], 1):
        for index in range(1, 6):
            missing = index == 5
            record = f"{tag}-{20 + index}"
            target = "" if missing else f" dla rekordu {record}"
            error = index == 4
            answer = (
                "podaj identyfikator"
                if missing
                else "odczyt niedostępny"
                if error
                else value
            )
            cases.append(
                Scenario(
                    f"{prefix}-T{family_no:02}-{index}",
                    "tools",
                    family,
                    f"Sprawdź {TOOL_LABELS[function]}{target}. Podaj sam wynik.",
                    (answer,),
                    tool=None if missing else (function, record),
                    tool_error=error,
                    clarify_tool=missing,
                )
            )
    return cases
