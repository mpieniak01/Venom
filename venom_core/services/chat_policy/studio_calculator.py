"""Bind straightforward Studio calculations to the user's current quantities."""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from venom_core.api.schemas.llm_simple import HistoryMessage
from venom_core.services.chat_policy.direct_calculator import (
    CalculatorRequest,
    execute_calculator,
)
from venom_core.services.chat_policy.qualified_chat_quote import (
    is_text_transformation,
    without_quotes,
)
from venom_core.services.grounded_calculator import calculate

_NUMBER = r"[0-9]{1,7}(?:[.,][0-9]{1,4})?"
_WORD_COUNTS = {
    "dwa": 2,
    "dwie": 2,
    "dwóch": 2,
    "trzy": 3,
    "trzech": 3,
    "cztery": 4,
    "czterech": 4,
    "pięć": 5,
    "pięciu": 5,
    "sześć": 6,
    "sześciu": 6,
    "siedem": 7,
    "siedmiu": 7,
    "osiem": 8,
    "ośmiu": 8,
    "dziewięć": 9,
    "dziewięciu": 9,
    "dziesięć": 10,
    "dziesięciu": 10,
}
_COUNT = rf"(?:[1-9][0-9]{{0,3}}|{'|'.join(_WORD_COUNTS)})"
_LENGTH = rf"(?P<value>{_NUMBER})\s*(?P<unit>mm|cm|m)\b"
_LENGTH_VALUE = re.compile(rf"\b{_LENGTH}", re.I)
_WORD = r"[^\W\d_]+"
_LENGTH_GROUP = re.compile(
    rf"\b(?P<count>{_COUNT})\s+(?P<label>{_WORD}(?:\s+{_WORD}){{0,3}}?)"
    rf"\s+po\s+{_LENGTH}",
    re.I,
)
_LENGTH_TOTAL = re.compile(
    r"\b(?:ile\s+(?:dokładnie\s+)?(?:cm|centymetr\w*|łącznie|razem)"
    r"|(?:policz|oblicz|podaj)\s+łączną\s+długość)\b",
    re.I,
)
_OTHER_LENGTH_UNIT = re.compile(
    r"\b(?:w\s+(?:milimetrach|metrach|kilometrach)|"
    r"ile\s+(?:(?:razem|łącznie)\s+)?(?:milimetr\w*|metr\w*|kilometr\w*|mm|m|km))\b",
    re.I,
)
_LENGTH_GAP = re.compile(
    r"\bile\s+(?:dokładnie\s+|jeszcze\s+)?(?:(?:cm|centymetr\w*)\s+)?brakuje\b", re.I
)
_LENGTH_CHANGE = re.compile(
    rf"\b(?P<each>każd[ay]\s+)?(?P<label>krót(?:k|sz)\w*|dłu(?:g|ż)\w*)\s+"
    rf"(?(each)(?:ma(?:\s+mieć)?|zmieniam\s+na)|mają\s+(?:jednak\s+|teraz\s+)?po)\s+{_LENGTH}",
    re.I,
)
_AVAILABLE = re.compile(
    rf"(?:\b(?:odciął[ae]m|odcięt[eo]|odmierzy[łl][ae]m)|(?:^|[.!]\s+)mam[y]?\s+już)\s+{_LENGTH}",
    re.I,
)

_RATE_NAME = r"krajow\w*|zagraniczn\w*|normaln\w*|zwykł\w*|ulgow\w*"
_RATE = re.compile(
    rf"\b(?P<count>[1-9][0-9]{{0,3}})\s+(?:{_WORD}\s+)?(?P<label>{_RATE_NAME})"
    rf"\s+(?:(?:kosztuje|kosztują)\s+)?po\s+(?P<value>{_NUMBER})\s*zł\b",
    re.I,
)
_RATE_CHANGE = re.compile(
    rf"\b(?P<label>{_RATE_NAME})\s+(?:(?:są|był[yo]|były|jednak|teraz)\s+){{0,3}}"
    rf"(?:po|kosztują)\s+(?P<value>{_NUMBER})\s*zł\b",
    re.I,
)
_MONEY_VALUE = re.compile(rf"\b{_NUMBER}\s*zł\b", re.I)
_RATE_ONLY = re.compile(
    rf"\b(?:tylko\s+(?:za\s+)?|sam(?:ych|e|ymi)\s+)(?P<label>{_RATE_NAME})\b", re.I
)
_RATE_TOTAL = re.compile(
    r"(?:\b(?:kwot[ayę]|koszt|ile|sum[ayę])\b[^.!?\n]{0,42}"
    r"\b(?:wszystk\w*|całoś\w*|łącznie|razem)\b)"
    r"|\bile\s+łącznie\s+za\s+obie\s+grupy\b",
    re.I,
)

_RATE_KINDS = {
    "kaucje": "kaucja",
    "opłaty": "opłata",
    "ceny": "cena",
    "stawki": "stawka",
}
_RATE_GROUP_ACCUSATIVES = {
    "przegród": "przegrodę",
    "przegrody": "przegrodę",
    "skrytek": "skrytkę",
    "skrytki": "skrytkę",
    "szafek": "szafkę",
    "szafki": "szafkę",
}
_RELATIVE_RATE = re.compile(
    rf"(?P<kind>{'|'.join(_RATE_KINDS)}): (?P<a_count>{_COUNT}) (?P<a_group>{_WORD})"
    rf" (?:ma|kosztuje) po (?P<a>{_NUMBER}) zł, (?P<b_count>{_COUNT})"
    rf"(?: (?P<b_group>{_WORD}))? (?:ma|kosztuje) po (?P<b>{_NUMBER}) zł[.!] (?P<query>[^.!?]+)\?",
    re.I,
)
_RELATIVE_RATE_PICK = re.compile(
    r"(?:jaka jest suma [^.!?]{2,30} |ile (?:zapłacimy|zapłacę) )?"
    r"tylko za (?P<range>droższe|tańsze)",
    re.I,
)
_RELATIVE_RATE_UPDATE = re.compile(
    rf"(?P<kind>{'|'.join(_RATE_KINDS.values())}) za (?P<range>tańszą|droższą) (?P<group>{_WORD}) "
    rf"(?P<direction>spada|rośnie|zmienia się) z (?P<old>{_NUMBER}) zł do (?P<new>{_NUMBER}) zł[.!] "
    r"(?:ile zapłacimy za wszystkie razem|jaka jest suma obu stawek)\?",
    re.I,
)


_MASS = rf"(?P<value>{_NUMBER})\s*(?P<unit>kg|g)\b"
_MASS_VALUE = re.compile(rf"\b{_MASS}", re.I)
_MASS_SCOPE = re.compile(r"\b(?:obciążniki|odważniki)\b", re.I)
_MASS_ENTRY = re.compile(
    rf"(?:^|,\s*)(?P<label>{_WORD}(?:\s+{_WORD}){{0,2}}?)\s+(?:waży\s+)?{_MASS}",
    re.I,
)
_MASS_UPDATE = re.compile(
    rf"^(?P<label>{_WORD})\s+(?:pomylon\w*[^.!?]{{0,42}},\s*właściw\w* waży"
    rf"|jednak waży|waży teraz)\s+{_MASS}[.!]",
    re.I,
)
_MASS_WITH_CASE = re.compile(
    r"\b(?:mas[ęay]|waż\w*)\b[^.!?]{0,45}\bkomplet\w*\s+z\s+"
    r"(?:pokrowcem|etui|opakowaniem)\b",
    re.I,
)
_MASS_WITHOUT_CASE = re.compile(
    r"\bile ważą same (?:obciążniki|odważniki) w gramach\b", re.I
)
_MASS_CASE = re.compile(r"\b(?:pokrowiec|etui|opakowanie)$", re.I)

_MASS_ITEMS = {
    "worki": ("worek", "worków"),
    "paczki": ("paczka", "paczek"),
    "kartony": ("karton", "kartonów"),
}
_MASS_CONTAINERS = {
    "kufer": "kufrem",
    "kosz": "koszem",
    "pojemnik": "pojemnikiem",
    "karton": "kartonem",
    "opakowanie": "opakowaniem",
}
_MASS_LIST = re.compile(
    rf"(?P<count>{_COUNT}) (?P<items>{'|'.join(_MASS_ITEMS)}) ważą "
    rf"(?P<weights>{_NUMBER}\s*(?:kg|g)(?:, {_NUMBER}\s*(?:kg|g)){{0,5}} i {_NUMBER}\s*(?:kg|g))[.!] "
    rf"pust[ye] (?P<container>{'|'.join(_MASS_CONTAINERS)}) waży {_MASS}[.!] "
    rf"ile ważą same (?P=items)(?: łącznie)?,? w gramach\?",
    re.I,
)
_MASS_ORDINAL_UPDATE = re.compile(
    rf"(?P<ordinal>pierwsz[ya]|drug[ia]|trzeci(?:a)?|czwart[ya]|piąt[ya]|szóst[ya]|siódm[ya]|ósm[ya]) "
    rf"(?P<item>{_WORD}) waży (?:jednak|teraz) {_MASS}[.!] "
    rf"(?:podaj(?: teraz)? masę (?P<scope>{_WORD})(?: razem)? z (?P<container>{_WORD}),? w gramach[.!?]?)",
    re.I,
)
_ORDINAL_STEMS = ("pierwsz", "drug", "trzec", "czwart", "piąt", "szóst", "siódm", "ósm")


_WIDTHS = re.compile(
    r"(?:\b(?:odczyt(?:y)?\s+)?szerokości(?:\s+desek|\s+listew|\s+płyt)?"
    rf"|^na liście (?:są|wymieniono) (?P<count>{_COUNT}) {_WORD})\s*:\s*",
    re.I,
)
_WIDTH = re.compile(
    rf"(?:^|[,;]\s*|\s+(?:i|oraz)\s+)(?P<label>{_WORD}(?:\s+{_WORD}){{0,3}}?)"
    rf"\s+(?:o\s+szerokości\s+)?{_LENGTH}",
    re.I,
)
_WIDTH_CHANGE = re.compile(
    rf"\b(?:poszerz\w*|zwę[żz]\w*|zmieniam)\s+(?P<label>{_WORD}(?:\s+{_WORD}){{0,3}}?)"
    rf"\s+(?:do|na)\s+{_LENGTH}",
    re.I,
)
_WIDTH_REPLACEMENT = re.compile(
    rf"\b(?:deskę|listwę|płytę)\s+(?P<label>{_WORD})\s+wymieniliśm[yi]\s+na\s+{_LENGTH}",
    re.I,
)
_WIDTH_NAMED_REPLACEMENT = re.compile(
    rf"^(?P<label>{_WORD}(?:\s+{_WORD}){{0,3}}?)\s+wymieniono\s+na\s+{_WORD}\s+"
    rf"o\s+szerokości\s+{_LENGTH}",
    re.I,
)
_WIDTH_QUERY = re.compile(r"\b(?P<widest>najszer\w*)\b|\bnajwęż\w*\b", re.I)
_INTERVAL_EDGE = r"włącznie|bez punktu granicznego"
_INTERVAL_SOURCE = re.compile(
    rf"(?:obowiązuje )?zakres od (?P<lower>{_NUMBER}) (?P<lower_unit>mm|cm|m) "
    rf"(?P<lower_edge>{_INTERVAL_EDGE}) do (?P<less>mniej niż )?"
    rf"(?P<upper>{_NUMBER}) (?P<upper_unit>mm|cm|m)(?: (?P<upper_edge>{_INTERVAL_EDGE}))?[.!] "
    r"(?:próbka |próbki:\s*)(?P<items>[^?!\n]{3,260}?)[.!] "
    r"(?:wypisz|wskaż) (?:spełniające zakres|pasujące próbki)[.!?]?",
    re.I,
)
_INTERVAL_ITEM = re.compile(
    rf"(?P<item>[A-Z][A-Z0-9-]{{0,8}})(?: ma)? {_LENGTH}",
    re.I,
)
_INTERVAL_UPDATE = re.compile(
    rf"dolna granica (?:od teraz )?(?P<lower_edge>{_INTERVAL_EDGE}), "
    rf"górna (?P<upper_edge>{_INTERVAL_EDGE})[.!] "
    r"(?:wypisz|wskaż) ponownie[.!?]?",
    re.I,
)


_UNCERTAIN = re.compile(
    r"\b(?:około|maksymalnie|co najmniej|co najwyżej|chyba|albo|nie wiem|nie znam)\b",
    re.I,
)
_NO_CALCULATION = re.compile(
    r"\bnie\s+(?:licz|obliczaj|przeliczaj|podawaj\s+wyniku)\b", re.I
)
_SCALES = {"mm": -1, "cm": 0, "m": 2}


_COUNTED_SEQUENCE = re.compile(
    rf"\bzużycie\s+(?P<item>{_WORD})\s+w\s+(?P<groups>{_COUNT}) (?:aktywnych )?grupach?\s+"
    rf"(?:to|wynosi)\s+(?P<values>[0-9]+(?:, [0-9]+){{0,6}} i [0-9]+)\.",
    re.I,
)
_MEAN = re.compile(r"\b(?:jaka jest|podaj|oblicz) średni[ąa]\b", re.I)
_COUNT_DELTA = re.compile(
    rf"(?P<ordinal>pierwszej|drugiej|trzeciej|czwartej|piątej|szóstej|siódmej|ósmej) "
    rf"grupie (?P<operation>dolicz|odejmij)(?: jeszcze)? (?P<delta>jedną|{_COUNT}) "
    rf"(?P<item>{_WORD})[.!]",
    re.I,
)
_ORDINALS = (
    "pierwszej",
    "drugiej",
    "trzeciej",
    "czwartej",
    "piątej",
    "szóstej",
    "siódmej",
    "ósmej",
)
_PLACES = re.compile(
    r"\bdo (?P<places>jednego miejsca|dwóch miejsc|trzech miejsc)(?: po przecinku)?\b",
    re.I,
)
_PRECISION = {"jednego miejsca": 1, "dwóch miejsc": 2, "trzech miejsc": 3}
_ROUNDING = re.compile(r"\b(?:zaokrągl|po przecinku|do \w+ miejsc)", re.I)
_SERIES_NUMBER = rf"-?{_NUMBER}"
_SERIES_VALUES = (
    rf"{_SERIES_NUMBER}(?:, {_SERIES_NUMBER}){{0,6}}(?:, | i ){_SERIES_NUMBER}"
)
_MEDIAN_SOURCE = re.compile(
    rf"(?:(?P<count>{_COUNT}) )?(?:wyniki|wyników) {_WORD}: (?P<values>{_SERIES_VALUES})"
    r"(?: jednostek)?[.!] (?:oblicz|podaj) medianę"
    r"(?: i (?:krótko )?pokaż dane środkowe)?[.!?]?",
    re.I,
)
_MEDIAN_REMOVE = re.compile(
    rf"wynik (?P<value>{_SERIES_NUMBER}) (?:był zdublowany|był duplikatem|jest kopią)"
    r" i (?:znika z listy|usuwamy z listy)[.!] "
    r"(?:podaj|oblicz) medianę(?:, reszta danych zostaje)?[.!?]?",
    re.I,
)
_MEASURE_UNITS = {
    "ml": ("volume", 0),
    "l": ("volume", 3),
    "g": ("mass", 0),
    "kg": ("mass", 3),
}
_MEASURE_UNIT = "|".join(_MEASURE_UNITS)
_MEASURED_MEAN = re.compile(
    rf"zużyto (?P<values>{_SERIES_VALUES}) (?P<unit>{_MEASURE_UNIT}) {_WORD} "
    rf"w (?P<count>{_COUNT}) (?:pomiarach|próbach)[.!] "
    r"(?:(?:odrzuć|pomiń) niewykonaną [^\W\d_]+ próbę i )?"
    r"(?:podaj|oblicz) średnią[.!?]?",
    re.I,
)
_MEASURED_MEAN_DELTA = re.compile(
    r"(?P<verb>zwiększ|zmniejsz) (?:zapis |wartość )?"
    r"(?P<ordinal>pierwszego|drugiego|trzeciego|czwartego|piątego|szóstego|siódmego|ósmego) "
    rf"(?:pomiaru|odczytu) o (?P<amount>{_NUMBER}) (?P<unit>{_MEASURE_UNIT})[.!] "
    r"(?:podaj|oblicz) średnią(?: tych samych prób)?"
    rf"(?: {_PLACES.pattern})?[.!?]?",
    re.I,
)


_DISTRIBUTION = re.compile(
    rf"(?:z|mamy) (?P<stock>{_COUNT}) (?P<item>{_WORD})[:,]? (?P<reserve>{_COUNT}) odkładamy[.!] "
    rf"resztę dzielimy równo na (?P<groups>{_COUNT}) (?P<group>{_WORD})[.!] "
    rf"ile (?P=item) w każdej\?",
    re.I,
)
_CLOSED_GROUP = re.compile(
    rf"jedną pełną (?P<group>{_WORD}) (?:zamknęliśmy|odłożyliśmy) na zapas[.!] "
    rf"ile (?P<item>{_WORD}) jest w (?:otwartych|pozostałych)\?",
    re.I,
)
_DAYS = r"poniedziałek|wtorek|środę|czwartek|piątek|sobotę|niedzielę"
_COUNT_CELL = r"[0-9]{1,6}"
_DAY_TABLE = re.compile(
    rf"w(?:e)? (?P<day1>{_DAYS}) było (?P<a1>{_COUNT_CELL}) (?P<kind>{_WORD}) dla (?P<scope>{_WORD}) "
    rf"(?P<a>[A-Z]) i (?P<b1>{_COUNT_CELL}) dla (?P<b>[A-Z])[.!] "
    rf"w(?:e)? (?P<day2>{_DAYS}) (?P=a) (?P<a2>{_COUNT_CELL}), (?P=b) (?P<b2>{_COUNT_CELL})[.!] "
    rf"ile (?P=kind) dla (?P<asked>[A-Z]) w oba dni\?",
    re.I,
)
_DAY_MOVE = re.compile(
    rf"w(?:e)? (?P<day>{_DAYS}) (?P<count>{_COUNT}) (?P<kind>{_WORD}) by(?:ło|ły) błędnie w "
    r"(?P<from>[A-Z]), przenieś je do (?P<to>[A-Z])[.!] podaj poprawn[ąy] "
    rf"(?P=day)[.!]?",
    re.I,
)
_DAY_SUM = re.compile(
    rf"(?:a teraz |teraz )?ile (?:(?P<kind>{_WORD}) dla )?(?P<column>[A-Z]) (?:po dwóch dniach|w oba dni)\?",
    re.I,
)


_COUNT_KINDS = {
    "wpis": "wpisów",
    "wpisy": "wpisów",
    "zgłoszenie": "zgłoszeń",
    "zgłoszenia": "zgłoszeń",
    "bilet": "biletów",
    "bilety": "biletów",
}

_PACK_COUNTS = re.compile(
    rf"(?:są|mam[y]?|w {_WORD} jest) (?P<a_count>{_COUNT}) (?:wielopak\w*|opakowa\w+) "
    rf"(?P<a>{_WORD}) po (?P<a_size>{_COUNT})(?: sztuk)? "
    rf"i (?P<b_count>{_COUNT}) (?:wielopak\w*|opakowa\w+) "
    rf"(?P<b>{_WORD}) po (?P<b_size>{_COUNT})(?: sztuk)?[.!] "
    rf"ile (?P<pick>{_WORD})(?: sztuk)?\?",
    re.I,
)
_PACK_EXCEPTION = re.compile(
    rf"w ostatnim wielopaku (?P<item>{_WORD}) było tylko (?P<count>{_COUNT}), "
    r"a pozostałe są bez zmiany[.!] ile sztuk łącznie\?",
    re.I,
)
_PACK_NAMED_EXCEPTION = re.compile(
    rf"ostatnie (?P<item>{_WORD}) opakowanie ma tylko (?P<count>{_COUNT})[.!] "
    r"ile sztuk (?:obu kolorów )?razem\?",
    re.I,
)
_PACK_TAKE = re.compile(
    rf"oddaliśm[yi] (?P<count>{_COUNT}) (?P<kind>{_WORD})[.!] "
    rf"(?:podaj pozostałe (?P<a>{_WORD}) i (?P<b>{_WORD}) oddzielnie"
    r"|podaj osobno(?:,)? ile zostało obu kolorów)[.!?]?",
    re.I,
)


def _decimal(value: str) -> Decimal:
    return Decimal(value.replace(",", "."))


def _length_in_cm(match: re.Match[str]) -> Decimal:
    return _decimal(match["value"]).scaleb(_SCALES[match["unit"].casefold()])


def _number(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _polish(value: Decimal) -> str:
    return _number(value).replace(".", ",")


def _rate_key(text: str) -> str:
    text = text.casefold()
    if text.startswith("zwykł"):
        return "normaln"
    return next(
        key
        for key in ("krajow", "zagraniczn", "normaln", "ulgow")
        if text.startswith(key)
    )


def _length_key(text: str) -> str:
    if re.search(r"\bdłu(?:g|ż)\w*", text, re.I):
        return "dług"
    if re.search(r"\bkrót(?:k|sz)\w*", text, re.I):
        return "krótk"
    return ""


@dataclass(frozen=True)
class _Term:
    count: int
    value: Decimal

    @property
    def expression(self) -> str:
        return f"{self.count}*{_number(self.value)}"

    def readable(self, unit: str) -> str:
        return f"{self.count} × {_polish(self.value)} {unit}"


@dataclass(frozen=True)
class StudioCalculation:
    expression: str
    unit: str | None
    render: Callable[[str], str]

    def publish(self) -> dict[str, Any]:
        reply = execute_calculator(CalculatorRequest(self.expression, self.unit))
        if reply["tool_result"]["status"] == "succeeded":
            reply["text"] = self.render(reply["text"])
        return reply


def _read_total_lengths(message: str) -> dict[str, _Term]:
    groups = list(_LENGTH_GROUP.finditer(message))
    if (
        not _LENGTH_TOTAL.search(message)
        or re.search(r"\d", _LENGTH_GROUP.sub("", message))
        or len(groups) != 2
        or len(_LENGTH_VALUE.findall(message)) != len(groups)
    ):
        return {}
    terms = [
        _Term(
            int(m["count"])
            if m["count"].isdecimal()
            else _WORD_COUNTS[m["count"].casefold()],
            _length_in_cm(m),
        )
        for m in groups
    ]
    keys = [_length_key(m["label"]) for m in groups]
    if set(keys) == {"dług", "krótk"}:
        return dict(zip(keys, terms, strict=True))
    labels = {m["label"].casefold() for m in groups}
    if not any(keys) and len(labels) == 1 and terms[0].value != terms[1].value:
        shorter, longer = sorted(terms, key=lambda term: term.value)
        return {"krótk": shorter, "dług": longer}
    return {}


def _length_calculation(turns: Sequence[str]) -> StudioCalculation | None:
    lengths: dict[str, _Term] = {}
    available = None
    for message in turns:
        available = list(_AVAILABLE.finditer(message))
        changes = list(_LENGTH_CHANGE.finditer(message))
        if current := _read_total_lengths(message):
            lengths = current
        elif (
            lengths
            and len(changes) == 1
            and len(_LENGTH_VALUE.findall(message)) == 1 + len(available)
        ):
            change = changes[0]
            key = _length_key(change["label"])
            lengths[key] = replace(lengths[key], value=_length_in_cm(change))
        elif not (
            lengths
            and len(available) == 1
            and not changes
            and len(_LENGTH_VALUE.findall(message)) == 1
        ):
            lengths = {}
    if not lengths or _OTHER_LENGTH_UNIT.search(turns[-1]):
        return None
    total = "+".join(term.expression for term in lengths.values())
    formula = " + ".join(term.readable("cm") for term in lengths.values())
    if available and _LENGTH_GAP.search(turns[-1]):
        measured = _length_in_cm(available[0])
        difference = f"({total})-{_number(measured)}"

        def render_gap(result: str) -> str:
            result_quantity = result.removeprefix("-")
            if result.startswith("-"):
                return f"Jest o {result_quantity} więcej, niż potrzeba."
            return f"Brakuje {result} ({formula} − {_polish(measured)} cm)."

        return StudioCalculation(difference, "cm", render_gap)
    if available:
        return None
    return StudioCalculation(total, "cm", lambda result: f"{formula} = {result}.")


def _rate_calculation(turns: Sequence[str]) -> StudioCalculation | None:
    rates: dict[str, _Term] = {}
    for message in turns:
        entries = list(_RATE.finditer(message))
        changes = list(_RATE_CHANGE.finditer(message))
        amount_count = len(_MONEY_VALUE.findall(message))
        if len(entries) >= 2 and amount_count == len(entries):
            rates = {
                _rate_key(m["label"]): _Term(int(m["count"]), _decimal(m["value"]))
                for m in entries
            }
            if len(entries) != len(rates):
                rates = {}
        elif (
            len(changes) == amount_count == 1
            and not re.search(r"\d", _RATE_CHANGE.sub("", message))
            and (key := _rate_key(changes[0]["label"])) in rates
        ):
            rates[key] = replace(rates[key], value=_decimal(changes[0]["value"]))
        elif (
            entries
            or re.search(r"\d", message)
            or not (_RATE_ONLY.search(message) or _RATE_TOTAL.search(message))
        ):
            rates = {}
    if wanted := _RATE_ONLY.search(turns[-1]):
        term = rates.get(_rate_key(wanted["label"]))
        return (
            StudioCalculation(
                term.expression,
                "zł",
                lambda result: f"{term.readable('zł')} = {result}.",
            )
            if term is not None
            else None
        )
    if len(rates) < 2 or not _RATE_TOTAL.search(turns[-1]):
        return None
    parts = [_polish(_decimal(calculate(term.expression))) for term in rates.values()]
    formula = " + ".join(f"{part} zł" for part in parts)
    expression = "+".join(term.expression for term in rates.values())
    return StudioCalculation(expression, "zł", lambda result: f"{formula} = {result}.")


def _relative_rate_calculation(turns: Sequence[str]) -> StudioCalculation | None:
    source = _RELATIVE_RATE.fullmatch(turns[-1])
    update = None
    if source is None and len(turns) > 1:
        source = _RELATIVE_RATE.fullmatch(turns[-2])
        update = _RELATIVE_RATE_UPDATE.fullmatch(turns[-1])
        if source is None or update is None:
            return None
    if source is None or (
        source["b_group"]
        and source["a_group"].casefold() != source["b_group"].casefold()
    ):
        return None
    pick = _RELATIVE_RATE_PICK.fullmatch(source["query"])
    if pick is None:
        return None
    groups = sorted(
        (_Term(_count(source[f"{key}_count"]), _decimal(source[key])) for key in "ab"),
        key=lambda term: term.value,
    )
    if groups[0].value == groups[1].value:
        return None
    if update is None:
        term = groups[int(pick["range"].casefold() == "droższe")]
        return StudioCalculation(
            term.expression, "zł", lambda result: f"{term.readable('zł')} = {result}."
        )
    index = int(update["range"].casefold() == "droższą")
    current = groups[index]
    new_rate = _decimal(update["new"])
    direction = update["direction"].casefold()
    source_group = source["a_group"].casefold()
    bound_group = _RATE_GROUP_ACCUSATIVES.get(source_group, source_group)
    if (
        _RATE_KINDS[source["kind"].casefold()] != update["kind"].casefold()
        or _decimal(update["old"]) != current.value
        or bound_group != update["group"].casefold()
        or (direction == "spada" and new_rate >= current.value)
        or (direction == "rośnie" and new_rate <= current.value)
    ):
        return None
    groups[index] = replace(current, value=new_rate)
    parts = " + ".join(f"({term.readable('zł')})" for term in groups)
    return StudioCalculation(
        "+".join(term.expression for term in groups),
        "zł",
        lambda result: f"Razem {result}: {parts}.",
    )


def _width_key(label: str) -> str:
    return label.casefold().rstrip("aąęy")


def _width_calculation(turns: Sequence[str]) -> StudioCalculation | None:
    widths: dict[str, tuple[str, Decimal]] = {}
    for message in turns:
        if header := _WIDTHS.search(message):
            fields = message[header.end() :].split(". ", 1)[0].rstrip(".?!")
            matches = list(_WIDTH.finditer(fields))
            if (
                not 2 <= len(matches) <= 6
                or _WIDTH.sub("", fields).strip(" ,;")
                or header["count"]
                and (
                    _count(header["count"]) != len(matches)
                    or not re.search(r"\bo szerokości\b", fields, re.I)
                )
            ):
                return None
            widths = {
                _width_key(m["label"]): (m["label"], _length_in_cm(m)) for m in matches
            }
            if len(widths) != len(matches):
                return None
        elif widths and (
            update := _WIDTH_CHANGE.search(message)
            or _WIDTH_REPLACEMENT.search(message)
            or _WIDTH_NAMED_REPLACEMENT.search(message)
        ):
            key = _width_key(update["label"])
            if key not in widths or len(_LENGTH_VALUE.findall(message)) != 1:
                return None
            widths[key] = (widths[key][0], _length_in_cm(update))
        elif not _WIDTH_QUERY.search(message) or _LENGTH_VALUE.search(message):
            widths = {}
    question = _WIDTH_QUERY.search(turns[-1])
    if not widths or question is None or len(_WIDTH_QUERY.findall(turns[-1])) != 1:
        return None
    label, amount = (max if question["widest"] else min)(
        widths.values(), key=lambda item: item[1]
    )
    if sum(value == amount for _, value in widths.values()) != 1:
        return None
    comparison = (
        "Największa szerokość" if question["widest"] else "Najmniejsza szerokość"
    )
    choices = ", ".join(
        f"{name} {_polish(value)} cm" for name, value in widths.values()
    )
    return StudioCalculation(
        _number(amount),
        "cm",
        lambda result: f"{comparison}: {label}, {result}. Porównanie: {choices}.",
    )


def _interval_choices(items: str) -> list[tuple[str, Decimal]]:
    choices = []
    for item in re.split(r", | i | oraz ", items, maxsplit=7, flags=re.I):
        match = _INTERVAL_ITEM.fullmatch(item)
        if match is None:
            return []
        choices.append((match["item"], _length_in_cm(match)))
    return choices


def _interval_calculation(turns: Sequence[str]) -> StudioCalculation | None:
    match = _measurement_source(turns, _INTERVAL_SOURCE)
    if match is None:
        return None
    source, followups = match
    # Endpoints must be stated. "Do" alone does not say if the end belongs.
    if bool(source["less"]) == bool(source["upper_edge"]):
        return None
    lower = _decimal(source["lower"]).scaleb(_SCALES[source["lower_unit"].casefold()])
    upper = _decimal(source["upper"]).scaleb(_SCALES[source["upper_unit"].casefold()])
    choices = _interval_choices(source["items"])
    if (
        lower >= upper
        or len(choices) < 2
        or len({label.casefold() for label, _ in choices}) != len(choices)
    ):
        return None
    edges = (source["lower_edge"], source["upper_edge"] or "")
    for followup in followups:
        update = _INTERVAL_UPDATE.fullmatch(followup)
        if update is None:
            return None
        edges = (update["lower_edge"], update["upper_edge"])
    low_closed, high_closed = (edge.casefold() == "włącznie" for edge in edges)
    selected = [
        label
        for label, value in choices
        if (lower < value or low_closed and lower == value)
        and (value < upper or high_closed and value == upper)
    ]
    labels = ", ".join(selected) or "żadna próbka"
    expression = "+".join("1" for _ in selected) or "0"
    return StudioCalculation(
        expression, "szt.", lambda result: f"Zakres spełniają: {labels} ({result})."
    )


def _grams(match: re.Match[str]) -> Decimal:
    value = _decimal(match["value"])
    return value.scaleb(3) if match["unit"].casefold() == "kg" else value


def _mass_start(text: str) -> tuple[dict[str, Decimal], str] | None:
    *lead, rest = text.split(". ", 1)
    if not lead or not _MASS_SCOPE.search(lead[0]):
        return None
    raw, _, _ = rest.partition(". ")
    fields = list(_MASS_ENTRY.finditer(raw))
    if len(fields) != 3 or _MASS_ENTRY.sub("", raw).strip(" ,."):
        return None
    weights = {entry["label"].casefold(): _grams(entry) for entry in fields}
    containers = [label for label in weights if _MASS_CASE.search(label)]
    return (
        (weights, containers[0]) if len(weights) == 3 and len(containers) == 1 else None
    )


def _mass_calculation(turns: Sequence[str]) -> StudioCalculation | None:
    current = turns[-1]
    if not (_MASS_WITHOUT_CASE.search(current) or _MASS_WITH_CASE.search(current)):
        return None
    initial = _mass_start(current)
    start = initial or (_mass_start(turns[-2]) if len(turns) > 1 else None)
    if start is None:
        return None
    weights, container = start
    if initial is None:
        update = _MASS_UPDATE.match(current)
        if update is None or len(_MASS_VALUE.findall(current)) != 1:
            return None
        label = update["label"].casefold()
        if label not in weights or label == container:
            return None
        weights[label] = _grams(update)
    if not _MASS_WITH_CASE.search(current):
        del weights[container]
    expression = "+".join(_number(value) for value in weights.values())
    formula = " + ".join(f"{_polish(value)} g" for value in weights.values())
    return StudioCalculation(expression, "g", lambda result: f"{formula} = {result}.")


def _measurement_source(
    turns: Sequence[str], anchor: re.Pattern[str]
) -> tuple[re.Match[str], Sequence[str]] | None:
    for index in reversed(range(len(turns))):
        if source := anchor.fullmatch(turns[index]):
            return source, turns[index + 1 :]
    return None


def _ordinal_index(text: str) -> int:
    word = text.casefold()
    return next(
        index for index, stem in enumerate(_ORDINAL_STEMS) if word.startswith(stem)
    )


def _replace_raw_mass(
    weights: list[Decimal], source: re.Match[str], update: re.Match[str]
) -> bool:
    item, scope = _MASS_ITEMS[source["items"].casefold()]
    container = _MASS_CONTAINERS[source["container"].casefold()]
    index = _ordinal_index(update["ordinal"])
    if (
        update["item"].casefold() != item
        or update["scope"].casefold() != scope
        or update["container"].casefold() != container
        or index >= len(weights)
    ):
        return False
    weights[index] = _grams(update)
    return True


def _mass_list_calculation(turns: Sequence[str]) -> StudioCalculation | None:
    match = _measurement_source(turns, _MASS_LIST)
    if match is None:
        return None
    source, followups = match
    weights = [_grams(m) for m in _MASS_VALUE.finditer(source["weights"])]
    if len(weights) != _count(source["count"]):
        return None
    for followup in followups:
        update = _MASS_ORDINAL_UPDATE.fullmatch(followup)
        if update is None or not _replace_raw_mass(weights, source, update):
            return None
    if followups:
        weights.append(_grams(source))
    expression = "+".join(_number(value) for value in weights)
    formula = " + ".join(f"{_polish(value)} g" for value in weights)
    return StudioCalculation(expression, "g", lambda result: f"{formula} = {result}.")


def _count(text: str) -> int:
    word = text.casefold()
    if word.isdecimal():
        return int(word)
    return 1 if word == "jedną" else _WORD_COUNTS[word]


def _same_distribution_group(source: str, closed: str) -> bool:
    source, closed = source.casefold(), closed.casefold()
    if closed.endswith("ń"):
        return source == closed[:-1] + "ni"
    return source.rstrip("yi") == closed.rstrip("ęą")


def _same_count_kind(source: str, updated: str) -> bool:
    left, right = source.casefold(), updated.casefold()
    return _COUNT_KINDS.get(left, left) == _COUNT_KINDS.get(right, right)


def _distribution_calculation(turns: Sequence[str]) -> StudioCalculation | None:
    current = turns[-1]
    source = _DISTRIBUTION.fullmatch(current)
    groups_closed = 0
    if source is None and len(turns) > 1:
        source = _DISTRIBUTION.fullmatch(turns[-2])
        change = _CLOSED_GROUP.fullmatch(current)
        if (
            source is None
            or change is None
            or source["item"].casefold() != change["item"].casefold()
            or not _same_distribution_group(source["group"], change["group"])
        ):
            return None
        groups_closed = 1
    if source is None:
        return None
    stock, reserve, groups = (
        _count(source[key]) for key in ("stock", "reserve", "groups")
    )
    if stock <= reserve or groups <= groups_closed or (stock - reserve) % groups:
        return None
    each = (stock - reserve) // groups
    if groups_closed:
        return StudioCalculation(
            f"{groups - 1}*{each}",
            source["item"],
            lambda result: f"W pozostałych jest {result} ({groups - 1} × {each}).",
        )
    return StudioCalculation(
        f"({stock}-{reserve})/{groups}",
        source["item"],
        lambda result: f"Po {result} w każdej ({stock} − {reserve}) ÷ {groups}.",
    )


def _mean_calculation(turns: Sequence[str]) -> StudioCalculation | None:
    current = turns[-1]
    if not _MEAN.search(current):
        return None
    start = _COUNTED_SEQUENCE.search(current)
    change = None
    if start is None and len(turns) > 1:
        previous = turns[-2]
        start = _COUNTED_SEQUENCE.search(previous) if _MEAN.search(previous) else None
        change = _COUNT_DELTA.match(current)
        if change is None or re.search(r"\d", current[change.end() :]):
            return None
    if start is None:
        return None
    source_text = turns[-2] if change else current
    if re.search(r"\d", source_text[start.end() :]) and not _PLACES.search(
        source_text[start.end() :]
    ):
        return None
    raw = re.findall(r"[0-9]+", start["values"])
    if any(len(value) > 6 for value in raw) or len(raw) != _count(start["groups"]):
        return None
    values = [int(value) for value in raw]
    if change is not None:
        measure = start["item"].casefold()
        changed_measure = change["item"].casefold().rstrip("ęiy")
        if changed_measure not in {measure, measure.removesuffix("ek") + "k"}:
            return None
        i = _ORDINALS.index(change["ordinal"].casefold())
        if i >= len(values):
            return None
        delta = _count(change["delta"])
        values[i] += delta if change["operation"].casefold() == "dolicz" else -delta
        if values[i] < 0:
            return None
    precision = _PLACES.search(current)
    if precision is None and _ROUNDING.search(current):
        return None
    places = _PRECISION[precision["places"].casefold()] if precision else None
    terms = " + ".join(map(str, values))

    def render(result: str) -> str:
        if places is not None:
            quantum = Decimal(1).scaleb(-places)
            result = format(
                _decimal(result).quantize(quantum, rounding=ROUND_HALF_UP), "f"
            )
        return f"Średnia z {len(values)} grup to {result.replace('.', ',')} (({terms}) ÷ {len(values)})."

    return StudioCalculation(f"({terms})/{len(values)}", None, render)


def _series_values(source: re.Match[str]) -> list[Decimal]:
    return [_decimal(raw) for raw in re.findall(_SERIES_NUMBER, source["values"])]


def _median_calculation(turns: Sequence[str]) -> StudioCalculation | None:
    match = _measurement_source(turns, _MEDIAN_SOURCE)
    if match is None:
        return None
    source, followups = match
    values = _series_values(source)
    if source["count"] and _count(source["count"]) != len(values):
        return None
    for followup in followups:
        update = _MEDIAN_REMOVE.fullmatch(followup)
        if update is None or len(values) < 2:
            return None
        removed = _decimal(update["value"])
        if values.count(removed) != 1:
            return None
        values.remove(removed)
    values.sort()
    mid = len(values) // 2
    if len(values) % 2:
        return StudioCalculation(
            _number(values[mid]), None, lambda result: f"Mediana: {result}."
        )
    left, right = values[mid - 1 : mid + 1]
    return StudioCalculation(
        f"({_number(left)}+{_number(right)})/2",
        None,
        lambda result: f"Środkowe wartości: {_polish(left)} i {_polish(right)}. Mediana: {result}.",
    )


def _adjust_mean_value(values: list[Decimal], unit: str, update: re.Match[str]) -> bool:
    dimension, scale = _MEASURE_UNITS[unit]
    delta_dimension, delta_scale = _MEASURE_UNITS[update["unit"].casefold()]
    index = _ordinal_index(update["ordinal"])
    if index >= len(values) or dimension != delta_dimension:
        return False
    delta = _decimal(update["amount"]).scaleb(delta_scale - scale)
    if update["verb"].casefold() == "zmniejsz":
        delta = -delta
    values[index] += delta
    return values[index] >= 0


def _measured_mean_calculation(turns: Sequence[str]) -> StudioCalculation | None:
    match = _measurement_source(turns, _MEASURED_MEAN)
    if match is None:
        return None
    source, followups = match
    values = _series_values(source)
    if len(values) != _count(source["count"]) or min(values) < 0:
        return None
    unit = source["unit"].casefold()
    precision = None
    for followup in followups:
        update = _MEASURED_MEAN_DELTA.fullmatch(followup)
        if update is None or not _adjust_mean_value(values, unit, update):
            return None
        precision = update["places"]
    places = _PRECISION[precision.casefold()] if precision else None
    terms = " + ".join(_polish(value) for value in values)
    expression = "+".join(_number(value) for value in values)

    def render(result: str) -> str:
        if places is not None:
            quantum = Decimal(1).scaleb(-places)
            rounded = _decimal(result.split()[0]).quantize(
                quantum, rounding=ROUND_HALF_UP
            )
            result = f"{format(rounded, 'f').replace('.', ',')} {unit}"
        return (
            f"Średnia z {len(values)} pomiarów: {result} (({terms}) ÷ {len(values)})."
        )

    return StudioCalculation(f"({expression})/{len(values)}", unit, render)


def _day_calculation(turns: Sequence[str]) -> StudioCalculation | None:
    active = turns[-3:]
    for index in range(len(active) - 1, -1, -1):
        if source := _DAY_TABLE.fullmatch(active[index]):
            break
    else:
        return None
    rest = active[index + 1 :]
    day1, day2, a, b, asked = (
        source[key].casefold() for key in ("day1", "day2", "a", "b", "asked")
    )
    if day1 == day2 or a == b or asked not in {a, b}:
        return None
    ledger = {
        day1: {a: int(source["a1"]), b: int(source["b1"])},
        day2: {a: int(source["a2"]), b: int(source["b2"])},
    }
    if rest:
        move = _DAY_MOVE.fullmatch(rest[0])
        if move is None or not _same_count_kind(move["kind"], source["kind"]):
            return None
        day, origin, target = (move[key].casefold() for key in ("day", "from", "to"))
        cells = ledger.get(day, {})
        count = _count(move["count"])
        if (
            origin == target
            or origin not in cells
            or target not in cells
            or cells[origin] < count
        ):
            return None
        cells[origin] -= count
        cells[target] += count
        if len(rest) == 1:
            report = ", ".join(f"{col.upper()} {value}" for col, value in cells.items())
            return StudioCalculation(
                "+".join(map(str, cells.values())),
                source["kind"],
                lambda result: f"Aktualny zapis: {report}. Razem {result}.",
            )
        query = _DAY_SUM.fullmatch(rest[1])
        if query is None or (
            query["kind"] and not _same_count_kind(query["kind"], source["kind"])
        ):
            return None
        asked = query["column"].casefold()
        if asked not in {a, b}:
            return None
    left, right = ledger[day1][asked], ledger[day2][asked]
    return StudioCalculation(
        f"{left}+{right}",
        source["kind"],
        lambda result: f"Dla {asked.upper()} w oba dni: {left} + {right} = {result}.",
    )


def _pack_calculation(turns: Sequence[str]) -> StudioCalculation | None:
    active = turns[-3:]
    for i in range(len(active) - 1, -1, -1):
        if source := _PACK_COUNTS.fullmatch(active[i]):
            break
    else:
        return None
    labels = [source[slot].casefold() for slot in ("a", "b")]
    pick = source["pick"].casefold()
    if (
        labels[0] == labels[1]
        or pick not in labels
        or not all(label.endswith(("ych", "ich")) for label in labels)
    ):
        return None
    terms = {
        label: _Term(
            _count(source[f"{slot}_count"]), Decimal(_count(source[f"{slot}_size"]))
        )
        for slot, label in zip(("a", "b"), labels, strict=True)
    }
    updates = active[i + 1 :]
    unit = "szt."
    if not updates:
        return StudioCalculation(
            terms[pick].expression,
            unit,
            lambda result: f"{pick.capitalize()}: {result}",
        )
    scopes = {
        label[:-3] + ("e" if label.endswith("ych") else "ie"): label for label in labels
    }
    if len(scopes) != len(labels):
        return None
    exception = _PACK_EXCEPTION.fullmatch(updates[0])
    if exception:
        label = exception["item"].casefold()
    elif exception := _PACK_NAMED_EXCEPTION.fullmatch(updates[0]):
        label = scopes.get(exception["item"].casefold(), "")
    else:
        return None
    if label not in terms:
        return None
    changed = terms[label]
    count = _count(exception["count"])
    if count >= changed.value:
        return None
    adjusted = {name: int(term.count * term.value) for name, term in terms.items()}
    adjusted[label] += count - int(changed.value)
    if len(updates) == 1:
        formula = " + ".join(str(value) for value in adjusted.values())
        parts = ", ".join(f"{name}: {value}" for name, value in adjusted.items())
        return StudioCalculation(
            formula, unit, lambda result: f"Razem {result} ({parts})."
        )
    removal = _PACK_TAKE.fullmatch(updates[1])
    if removal is None or (kind := removal["kind"].casefold()) not in adjusted:
        return None
    remaining = _count(removal["count"])
    requested = (
        [removal[key].casefold() for key in ("a", "b")]
        if removal["a"]
        else list(scopes)
    )
    if set(requested) != set(scopes) or remaining > adjusted[kind]:
        return None
    adjusted[kind] -= remaining
    name = next(display for display in requested if scopes[display] == kind)
    other = next(display for display in requested if display != name)
    return StudioCalculation(
        f"{adjusted[kind] + remaining}-{remaining}",
        unit,
        lambda result: f"Pozostałe: {name} {result}, {other} {adjusted[scopes[other]]} szt.",
    )


def plan_studio_calculation(
    content: str, history: Sequence[HistoryMessage]
) -> StudioCalculation | None:
    """Rebuild a supported calculation from the recent user turns only."""
    users = [turn.content for turn in history if turn.role == "user"][-5:]
    turns = [without_quotes(text) for text in (*users, content)]
    if is_text_transformation(content) or _NO_CALCULATION.search(turns[-1]):
        return None
    latest_uncertain = max(
        (
            i
            for i, turn in enumerate(turns)
            if len(turn) > 512
            or _UNCERTAIN.search(turn)
            or _NO_CALCULATION.search(turn)
        ),
        default=-1,
    )
    active = turns[latest_uncertain + 1 :]
    if not active:
        return None
    return (
        _length_calculation(active)
        or _rate_calculation(active)
        or _relative_rate_calculation(active)
        or _width_calculation(active)
        or _interval_calculation(active)
        or _mass_calculation(active)
        or _mass_list_calculation(active)
        or _distribution_calculation(active)
        or _mean_calculation(active)
        or _measured_mean_calculation(active)
        or _median_calculation(active)
        or _day_calculation(active)
        or _pack_calculation(active)
    )
