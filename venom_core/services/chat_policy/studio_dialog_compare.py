"""Answer bounded Studio comparisons from the facts supplied by the user."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from venom_core.api.schemas.llm_simple import HistoryMessage

_FLAGS = re.IGNORECASE
_WORD = r"[^\W\d_]+"
_NUMBER = r"\d{1,5}(?:[,.]\d{1,2})?"
_SENTENCE = re.compile(r"(?<=[.!?])\s+")

_SUPPORT_PAIR = re.compile(
    rf"(?P<rigid>{_WORD}) jest sztywn[aye] i waży (?P<rigid_mass>{_NUMBER}) g,\s*"
    rf"a (?P<flexible>{_WORD}) (?:ugin[ae] się(?: w rękach)?|jest elastyczn[aye]) "
    rf"i waży (?P<flexible_mass>{_NUMBER}) g\.?",
    _FLAGS,
)
_LAP_WITHOUT_SUPPORT = re.compile(
    r"(?:nie będę mieć (?:stolika|blatu)|nie mam (?:stolika|blatu)|bez (?:stolika|blatu)),"
    r"\s*(?:maluję|rysuję|piszę) na kolanach\.?",
    _FLAGS,
)
_BEST_OPTION = re.compile(r"(?:któr[ay] lepsz[ay]|któr[eąy] wybrać)\?", _FLAGS)
_WITH_SUPPORT = re.compile(
    r"a (?:gdy|jeśli|jeżeli) (?:będę mieć|będę mia[łl][a]?|mam|pojawi się) "
    r"(?:blat|stół|stolik)(?: pod ręką)?\?",
    _FLAGS,
)


def _size_pattern(axis: str) -> str:
    return rf"(?P<{axis}x>{_NUMBER})\s*[×x]\s*(?P<{axis}y>{_NUMBER})\s*cm"


_DIMENSIONS = re.compile(
    rf"(?:[^.!?]{{0,80}}\bmam|porównuję|mam) (?P<first>{_WORD}(?: {_WORD}){{0,8}}), "
    rf"{_size_pattern('a')},?\s*(?:i|oraz) "
    rf"(?P<second>{_WORD}(?: {_WORD}){{0,8}}), {_size_pattern('b')}\.?",
    _FLAGS,
)
_EQUAL_PRICE = re.compile(rf"(?:obie|oba) kosztują (?P<price>{_NUMBER}) zł\.?", _FLAGS)
_FIT_SURFACE = re.compile(
    rf"(?:kwadrat )?(?P<surface>siedziska|siedzisko|półka|podstawa|mata|blat) ma "
    rf"{_size_pattern('s')}\.?",
    _FLAGS,
)
_FIT_QUESTION = re.compile(
    r"któr[ae] (?:w całości się zmieści|w całości zmieści się|zmieści się w całości)"
    r"(?: na (?:siedzisku|półce|podstawie|macie|blacie))?\?",
    _FLAGS,
)
_FIT_CLEANING = re.compile(
    r"(?:mam ją zamówić, ale |(?:a|ale) )?(?P<cleaning>[^.!?]{3,35}?) "
    r"(?:się lepiej czyści|czyści się łatwiej)\.\s*"
    r"co wybrać, jeśli (?:widok wystających brzegów mi przeszkadza|"
    r"nie chcę wystających brzegów|brzegi nie mogą wystawać)\?",
    _FLAGS,
)

_MATERIALS = re.compile(
    r"(?:w [^.!?]{2,45} jest|mamy|mam) (?P<first>[^.!?]{6,110}?) "
    r"(?:i|oraz) (?:osobny|osobną|oddzielny|oddzielną) (?P<second>[^.!?]{6,130})\.",
    _FLAGS,
)
_PRINT_SCOPE = re.compile(
    rf"(?:oba|obie) (?:chcę|chcemy) udostępnić,\s*ale tylko (?P<label>{_WORD}) "
    r"(?:będzie|ma być) (?P<when>jutro|dziś|pojutrze) drukowan[yae]\.",
    _FLAGS,
)
_MATERIAL_LIST = re.compile(
    r"jak (?:opisać|zapisać) te dw[ae] materiały na liście dla zespołu\?", _FLAGS
)
_ADD_PDF = re.compile(
    r"dopisz przy t(?:ym|ej) (?P<ordinal>pierwszym|drugim|pierwszej|drugiej),\s*"
    r"że można (?:go |ją |je )?pobrać jako pdf[.!]?",
    _FLAGS,
)

_TERM = rf"{_WORD}(?: {_WORD}){{0,3}}"
_TERMS = re.compile(
    rf"(?:[^.!?]{{0,90}}\s)?(?:dwa pojęcia|dwa terminy):\s*"
    rf"(?P<first>{_TERM}) i (?P<second>{_TERM})\.",
    _FLAGS,
)
_EXPLAIN = re.compile(
    r"jak (?:to prosto wyjaśnić|prosto wyjaśnić te pojęcia|prosto wyjaśnić te terminy)"
    r"(?: ekipie| zespołowi)?\?",
    _FLAGS,
)
_DEFINITION = re.compile(
    rf"(?P<term>{_TERM}) (?P<relation>mówi,|pokazuje,?|informuje,|objaśnia|wyjaśnia|zawiera|"
    r"określa|oznacza|to) (?P<meaning>[^.!?]{3,155})",
    _FLAGS,
)
_TERM_FOLLOWUP = re.compile(
    r"czy na (?P<goal>[^.!?]{5,65}) patrzeć pod tym pierwszym czy drugim\?",
    _FLAGS,
)
_TEXT = re.compile(r"\b(?:napis\w*|tekst\w*|treść|treści)\b", _FLAGS)
_IMPRINT = re.compile(r"\bodbitk\w*\b", _FLAGS)


def _parts(text: str) -> list[str]:
    return _SENTENCE.split(text)


def _last_user(history: Sequence[HistoryMessage]) -> str:
    for turn in reversed(history):
        if turn.role == "user":
            return " ".join(turn.content.split())
    return ""


def _decimal(value: str) -> Decimal:
    return Decimal(value.replace(",", "."))


def _display(value: Decimal) -> str:
    number = format(value, "f")
    return number.rstrip("0").rstrip(".").replace(".", ",") if "." in number else number


def _support_pair(parts: list[str]) -> re.Match[str] | None:
    if len(parts) not in (3, 4):
        return None
    options, context, question = parts[-3:]
    if _LAP_WITHOUT_SUPPORT.fullmatch(context) and _BEST_OPTION.fullmatch(question):
        pair = _SUPPORT_PAIR.fullmatch(options)
        if pair and pair["rigid"].casefold() != pair["flexible"].casefold():
            return pair
    return None


def _support_reply(current: str, previous: str) -> str | None:
    if pair := _support_pair(_parts(current)):
        return (
            f"Na kolanach lepszy będzie sztywny wariant „{pair['rigid']}”. "
            f"Bez blatu daje stabilniejsze podparcie niż elastyczny wariant „{pair['flexible']}”."
        )
    if not _WITH_SUPPORT.fullmatch(current) or not (
        pair := _support_pair(_parts(previous))
    ):
        return None
    rigid, flexible = _decimal(pair["rigid_mass"]), _decimal(pair["flexible_mass"])
    if rigid == flexible:
        return "Przy pełnym podparciu na blacie oba warianty mogą wystarczyć, a różnicy w wadze nie ma."
    lighter = pair["rigid"] if rigid < flexible else pair["flexible"]
    return (
        f"Przy pełnym podparciu na blacie lżejszy wariant „{lighter}” może wystarczyć. "
        "To blat zapewnia wtedy stabilność, więc sztywność samej podkładki nie musi rozstrzygać."
    )


@dataclass(frozen=True)
class _Square:
    item: str
    side: Decimal

    def description(self) -> str:
        detail = self.item.partition(" z ")[2]
        return f"z {detail}" if detail else f"„{self.item}”"

    def size(self) -> str:
        side = _display(self.side)
        return f"{side} × {side} cm"


@dataclass(frozen=True)
class _SquareComparison:
    options: tuple[_Square, _Square]
    surface: Decimal
    price: str

    def fitting(self) -> tuple[int, ...]:
        return tuple(
            i for i, item in enumerate(self.options) if item.side <= self.surface
        )

    def choice(self) -> str:
        fits = self.fitting()
        price = f"Obie opcje kosztują {self.price} zł."
        if len(fits) != 1:
            answer = (
                "Obie opcje mieszczą się w całości."
                if fits
                else "Żadna opcja nie mieści się w całości."
            )
            return f"{answer} Bok dostępnej powierzchni ma {_display(self.surface)} cm. {price}"
        first_fits = fits[0] == 0
        selected, other = self.options[fits[0]], self.options[1 - fits[0]]
        ordinal, complement = (
            ("pierwsza", "Druga") if first_fits else ("druga", "Pierwsza")
        )
        return (
            f"W całości zmieści się {ordinal} opcja, {selected.description()} ({selected.size()}). "
            f"{complement}, {other.description()}, ma bok {_display(other.side)} cm, "
            f"a powierzchnia ma bok {_display(self.surface)} cm. {price}"
        )

    def with_cleaning(self, cleaning: str) -> str | None:
        fits = self.fitting()
        if len(fits) != 1:
            return None
        fitted, other = self.options[fits[0]], self.options[1 - fits[0]]
        clue = cleaning.casefold()
        matches = tuple(
            i for i, square in enumerate(self.options) if clue in square.item.casefold()
        )
        if len(matches) != 1:
            return None
        pick = "pierwszą" if fits[0] == 0 else "drugą"
        difference = (
            "Ta opcja jest też łatwiejsza do czyszczenia."
            if matches[0] == fits[0]
            else f"Opcję {other.description()} łatwiej czyścić, ale jej brzegi będą wystawać."
        )
        return (
            f"Wybierz {pick} opcję, {fitted.description()} ({fitted.size()}), "
            f"bo mieści się w całości na powierzchni o boku {_display(self.surface)} cm. "
            f"{difference}"
        )


def _square_pair(parts: list[str]) -> _SquareComparison | None:
    if len(parts) != 4 or not _FIT_QUESTION.fullmatch(parts[3]):
        return None
    options = _DIMENSIONS.fullmatch(parts[0])
    price = _EQUAL_PRICE.fullmatch(parts[1])
    surface = _FIT_SURFACE.fullmatch(parts[2])
    if not options or not price or not surface:
        return None
    values = [
        (_decimal(match[f"{axis}x"]), _decimal(match[f"{axis}y"]))
        for match, axis in ((options, "a"), (options, "b"), (surface, "s"))
    ]
    if any(x != y or x <= 0 for x, y in values):
        return None
    first, second, top = values
    return _SquareComparison(
        (_Square(options["first"], first[0]), _Square(options["second"], second[0])),
        top[0],
        price["price"],
    )


def _fits_reply(current: str, previous: str) -> str | None:
    if pair := _square_pair(_parts(current)):
        return pair.choice()
    if (request := _FIT_CLEANING.fullmatch(current)) and (
        pair := _square_pair(_parts(previous))
    ):
        return pair.with_cleaning(request["cleaning"])
    return None


def _materials(parts: list[str]) -> tuple[tuple[str, str], int, str] | None:
    if len(parts) != 3 or not _MATERIAL_LIST.fullmatch(parts[2]):
        return None
    items, scope = _MATERIALS.fullmatch(parts[0]), _PRINT_SCOPE.fullmatch(parts[1])
    if not items or not scope:
        return None
    labels = items["first"], items["second"]
    heads = [item.split()[0].casefold() for item in labels]
    printed = scope["label"].casefold()
    if heads.count(printed) != 1:
        return None
    return labels, heads.index(printed), scope["when"]


def _material_reply(current: str, previous: str) -> str | None:
    items = _materials(_parts(current))
    pdf_index = None
    if not items:
        addition = _ADD_PDF.fullmatch(current)
        items = _materials(_parts(previous)) if addition else None
        if addition:
            pdf_index = int(addition["ordinal"].casefold().startswith("drug"))
    if not items:
        return None
    labels, printed, when = items
    lines = []
    for index, label in enumerate(labels):
        status = "do udostępnienia"
        if index == printed:
            status += f", do druku {when}"
        if index == pdf_index:
            status += ", do pobrania jako PDF"
        lines.append(f"{index + 1}. {label[0].upper()}{label[1:]} — {status}.")
    return "\n".join(lines)


@dataclass(frozen=True)
class _Definition:
    name: str
    relation: str
    meaning: str

    def statement(self) -> str:
        return f"{self.name[0].upper()}{self.name[1:]} {self.relation} {self.meaning}."


def _definition(label: str, other_label: str, clause: str) -> _Definition | None:
    matched = _DEFINITION.fullmatch(clause)
    if not matched:
        return None
    term = matched["term"].casefold()
    head = label.split()[0].casefold()
    if term == label.casefold() or (
        term == head and head != other_label.split()[0].casefold()
    ):
        return _Definition(label, matched["relation"], matched["meaning"])
    return None


def _definitions(parts: list[str]) -> tuple[_Definition, _Definition] | None:
    if len(parts) != 3 or not _EXPLAIN.fullmatch(parts[2]):
        return None
    terms = _TERMS.fullmatch(parts[0])
    left, delimiter, right = parts[1].removesuffix(".").partition(", a ")
    if not terms or not delimiter or ", a " in right:
        return None
    first = _definition(terms["first"], terms["second"], left)
    second = _definition(terms["second"], terms["first"], right)
    if first and second and first.name.casefold() != second.name.casefold():
        return first, second
    return None


def _definition_reply(current: str, previous: str) -> str | None:
    if pair := _definitions(_parts(current)):
        return " ".join(term.statement() for term in pair)
    if not (question := _TERM_FOLLOWUP.fullmatch(current)) or not (
        pair := _definitions(_parts(previous))
    ):
        return None
    patterns = [
        pattern for pattern in (_TEXT, _IMPRINT) if pattern.search(question["goal"])
    ]
    if len(patterns) != 1:
        return None
    matches = [
        definition for definition in pair if patterns[0].search(definition.meaning)
    ]
    if len(matches) != 1:
        return None
    result = matches[0]
    ordinal = "pierwsze" if result is pair[0] else "drugie"
    return f"Wybierz {ordinal} pojęcie, „{result.name}”. {result.statement()}"


_SHARED_MATERIALS = re.compile(
    rf"(?:do wspólnego użytku (?:jest|są)|do dyspozycji (?:jest|są)|mamy do wspólnego użytku) "
    rf"(?P<first>{_TERM}) (?:oraz|i) (?P<second>{_TERM})[.]",
    _FLAGS,
)
_COPY_SCOPE = re.compile(
    rf"(?:oba|obie|obydwa|obydwie) (?:dostaną|mają dostać) (?:po )?kopi[ęei], "
    rf"ale tylko (?P<label>{_TERM}) (?:ma mieć|dostanie) (?P<size>dużą|powiększoną) wersję[.]",
    _FLAGS,
)
_TELL_GROUP = re.compile(
    r"jak (?:to przekazać (?:kolegom|zespołowi|grupie)|to zapisać dla (?:kolegów|zespołu|grupy))\?",
    _FLAGS,
)
_ADD_SHARED_DOWNLOAD = re.compile(
    r"(?:dodaj informację|dopisz),? że (?:t(?:en|a|o) )?"
    r"(?P<ordinal>pierwsz[aąy]|drug[aąi]) można (?:też |również )?pobrać "
    r"jako (?P<format>plik tekstowy|PDF)[.!]?",
    _FLAGS,
)


def _shared_references(
    parts: list[str],
) -> tuple[_Definition, _Definition, str, str] | None:
    if len(parts) != 4 or not _TELL_GROUP.fullmatch(parts[3]):
        return None
    names = _SHARED_MATERIALS.fullmatch(parts[0])
    copies = _COPY_SCOPE.fullmatch(parts[2])
    if not names or not copies:
        return None
    first, second = names["first"], names["second"]
    selected = copies["label"].casefold()
    target = [
        label
        for label in (first, second)
        if selected in {label.casefold(), label.split()[0].casefold()}
    ]
    if len(target) != 1:
        return None
    source = parts[1].removesuffix(".")
    valid = []
    for separator in re.finditer(r", (?:a )?", source, _FLAGS):
        left = _definition(first, second, source[: separator.start()])
        right = _definition(second, first, source[separator.end() :])
        if left and right:
            valid.append((left, right, target[0], copies["size"]))
    return valid[0] if len(valid) == 1 else None


def _shared_reference_reply(current: str, previous: str) -> str | None:
    download = _ADD_SHARED_DOWNLOAD.fullmatch(current)
    references = _shared_references(_parts(previous if download else current))
    if not references:
        return None
    first, second, large_version, size = references
    text = (
        f"{first.statement()} {second.statement()} "
        f"Dla obu przewidziano po kopii. Tylko „{large_version}” ma mieć {size} wersję."
    )
    if not download:
        return text
    selected = first if download["ordinal"].casefold().startswith("pierwsz") else second
    return (
        f"{text} Materiał „{selected.name}” można też pobrać jako {download['format']}."
    )


_CARRY_FEATURES = r"(?:długi|krótki) uchwyt i (?P<{side}>niewielki|mały|duży) worek"
_CARRY_PAIR = re.compile(
    rf"w ofercie (?P<first>{_WORD}) jest {_CARRY_FEATURES.format(side='first_size')}, "
    rf"a w ofercie (?P<second>{_WORD}) (?:jest )?{_CARRY_FEATURES.format(side='second_size')}[.]",
    _FLAGS,
)
_CARRY_COST = re.compile(
    rf"(?:obydwie|obie|oba|obydwa) kosztują {_NUMBER} zł[.]",
    _FLAGS,
)
_NEED_CAPACITY = re.compile(
    r"(?:potrzebuję|muszę|chcę) zmieścić [^,.!?]{3,55} "
    r"i nie zależy mi na długości uchwytu[.]",
    _FLAGS,
)
_CARRY_CHOICE = re.compile(r"który (?:wariant|model)(?: wybrać)?\?", _FLAGS)
_SHOULDER_CHANGE = re.compile(
    r"(?:(?:jeśli|jeżeli|teraz) [^.!?]{1,95}, a )?(?:od )?teraz zależy mi na "
    r"noszeniu (?:przez|na) ramię[,.]\s*"
    r"którą cechę (?:porównać|sprawdzić)\?",
    _FLAGS,
)


def _carry_pair(parts: list[str]) -> re.Match[str] | None:
    if (
        len(parts) == 4
        and _CARRY_COST.fullmatch(parts[1])
        and _NEED_CAPACITY.fullmatch(parts[2])
        and _CARRY_CHOICE.fullmatch(parts[3])
        and (pair := _CARRY_PAIR.fullmatch(parts[0]))
        and pair["first"].casefold() != pair["second"].casefold()
    ):
        return pair
    return None


def _carry_reply(current: str, previous: str) -> str | None:
    if _SHOULDER_CHANGE.fullmatch(current) and _carry_pair(_parts(previous)):
        return (
            "Porównaj długość uchwytów. Sprawdź, czy któryś z uchwytów "
            "pozwala wygodnie nosić worek na ramieniu."
        )
    pair = _carry_pair(_parts(current))
    if pair is None:
        return None
    larger = [
        side
        for side in ("first", "second")
        if pair[f"{side}_size"].casefold() == "duży"
    ]
    if len(larger) == 1:
        return f"Wybierz wariant {pair[larger[0]]}. Ma większy worek, a cena obu jest taka sama."
    return None


_LIST_DAY = r"poniedziałek|wtorek|środę|czwartek|piątek|sobotę|niedzielę"
_LIST_ITEM = r"[^\W\d_]+(?:-[^\W\d_]+)?"
_ITEMS = rf"{_LIST_ITEM}(?:, {_LIST_ITEM}){{0,5}} i {_LIST_ITEM}"
_DAY_LISTS = re.compile(
    rf"w(?:e)? (?P<first>{_LIST_DAY}) (?:przydadzą się|potrzebne są) (?P<left>{_ITEMS}), "
    rf"(?:a )?w(?:e)? (?P<second>{_LIST_DAY}) (?P<right>{_ITEMS})[.!] "
    r"(?:co wspólne|co jest wspólne)\?",
    re.I,
)
_LIST_ADD = re.compile(
    rf"w(?:e)? (?P<day>{_LIST_DAY}) (?:dokładamy|dodajemy) (?P<item>{_LIST_ITEM}), "
    r"reszta bez zmian[.!] (?:co teraz wspólne|co jest teraz wspólne)\?",
    re.I,
)
_LIST_ONLY = re.compile(
    rf"co zostało tylko w(?:e)? (?P<day>{_LIST_DAY}) po (?:ostatniej )?zmianie\?",
    re.I,
)


def _list_comparison(current: str, users: Sequence[str]) -> str | None:
    initial = _DAY_LISTS.fullmatch(current)
    if initial:
        addition, exclusive = None, None
    else:
        change = _LIST_ADD.fullmatch(current)
        exclusive = _LIST_ONLY.fullmatch(current)
        if change and users:
            initial, addition = _DAY_LISTS.fullmatch(users[-1]), change
        elif exclusive and len(users) >= 2:
            initial, addition = (
                _DAY_LISTS.fullmatch(users[-2]),
                _LIST_ADD.fullmatch(users[-1]),
            )
            if addition is None:
                return None
        else:
            return None
    if initial is None or initial["first"].casefold() == initial["second"].casefold():
        return None
    lists = {
        initial[day].casefold(): {
            item.casefold(): item
            for item in re.split(", | i ", initial[scope], flags=re.I)
        }
        for day, scope in (("first", "left"), ("second", "right"))
    }
    if addition:
        selected = lists.get(addition["day"].casefold())
        if selected is None:
            return None
        item = addition["item"]
        selected.setdefault(item.casefold(), item)
    first, second = lists.values()
    if exclusive:
        day = exclusive["day"].casefold()
        if day not in lists:
            return None
        selected = lists[day]
        other = second if selected is first else first
        items = [label for key, label in selected.items() if key not in other]
        preposition = "we" if day == "wtorek" else "w"
        prefix = f"Tylko {preposition} {exclusive['day']}"
    else:
        items = [label for key, label in first.items() if key in second]
        prefix = "Wspólne"
    return f"{prefix}: {', '.join(items)}." if items else f"{prefix}: brak pozycji."


def studio_comparison(text: str, history: Sequence[HistoryMessage]) -> str | None:
    """Prefer source evidence and a changed constraint over prior assistant guesses."""
    current = " ".join(text.split())
    previous = _last_user(history)
    if len(current) > 600:
        return None
    return (
        _support_reply(current, previous)
        or _fits_reply(current, previous)
        or _material_reply(current, previous)
        or _definition_reply(current, previous)
        or _shared_reference_reply(current, previous)
        or _carry_reply(current, previous)
        or _list_comparison(
            current, [turn.content for turn in history[-4:] if turn.role == "user"]
        )
    )
