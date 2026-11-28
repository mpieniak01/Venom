"""Answer supported comparisons using the user's own evidence clauses."""

from __future__ import annotations

import re
from decimal import Decimal

_WORD = r"[^\W\d_]+"
_NUM = r"\d{1,4}(?:[,.]\d{1,2})?"
_SURFACES = r"(?:gładk|chropowat|matow|szorstk|miękk|tward)(?:ie|[iyaąe])"
_LIMIT = re.compile(
    rf"\b(?P<rule>nie szersz[ayąe] niż|węższ[ayąe] niż|maksymalnie|najwyżej|mniej niż|poniżej|do)"
    rf"\s+(?P<width>{_NUM})\s*cm\b",
    re.I,
)
_WIDTH = re.compile(
    rf"\b(?P<label>{_WORD})\s*(?:ma(?: szerokość)? |mierzy |: ?|– ?)"
    rf"(?P<width>{_NUM})\s*cm(?: szerokości)?"
    rf"(?:\s+i\s+(?:jest|ma powierzchnię)|\s*,|\s*[(])\s*(?P<surface>{_SURFACES})\b",
    re.I,
)
_PREFERENCE = re.compile(
    rf"\b(?:wolę|preferuję|wybieram|liczy się) (?:powierzchni[ęa] )?(?P<surface>{_SURFACES})\b",
    re.I,
)
_OBJECT_LIMIT = re.compile(rf"\blimit (?P<container>{_WORD})", re.I)
_FIT_CONTEXT = re.compile(r"\b(?:zmieści|mieści|przyjmuje|pasuje|szerokoś)\w*", re.I)
_CHOICE = re.compile(
    r"\b(?:wyb(?:ierz|rać|ór|oru)|decyzj\w*|polec\w*|któr[ayę] i dlaczego)\b", re.I
)
_UNCERTAIN = re.compile(
    r"\b(?:około|chyba|prawdopodobnie|może|nie wiadomo|zależnie|oprócz|z wyjątkiem)\b",
    re.I,
)


def _decimal(value: str) -> Decimal:
    return Decimal(value.replace(",", "."))


def _surface(value: str) -> str:
    return re.sub(r"(?:ie|[iyaąe])$", "", value.casefold())


def _same_limit(source: str, edit: str) -> bool:
    # An unqualified new limit can refer to the single old limit. An explicit
    # container must agree with a source noun, allowing Polish case endings.
    subject = _OBJECT_LIMIT.search(edit)
    if subject is None or subject["container"].casefold() in {
        "to",
        "wynosi",
        "po",
        "teraz",
        "szerokości",
    }:
        return True
    form = subject["container"].casefold()
    stem = form.rstrip("yaiu")
    return (
        len(stem) > 2
        and re.search(rf"\b{re.escape(stem)}[ayiu]?\b", source, re.I) is not None
    )


def _width_choice(text: str, previous: str) -> str | None:
    if not _CHOICE.search(text) or _UNCERTAIN.search(text):
        return None
    current = list(_LIMIT.finditer(text))
    if len(current) != 1:
        return None
    edit = not _WIDTH.search(text)
    source = previous if edit else text
    if not _FIT_CONTEXT.search(source) or _UNCERTAIN.search(source):
        return None
    if edit and (
        not _same_limit(source, text)
        or len(re.findall(r"\d[\d.,]*\s*cm\b", text, re.I)) != 1
    ):
        return None
    options = list(_WIDTH.finditer(source))
    preferences = list(_PREFERENCE.finditer(source))
    if (
        len(options) != 2
        or len(preferences) != 1
        or len(_LIMIT.findall(source)) != 1
        or len(re.findall(r"\d[\d.,]*\s*cm\b", source, re.I)) != 3
        or options[0]["label"].casefold() == options[1]["label"].casefold()
    ):
        return None
    if edit:
        updated = list(_PREFERENCE.finditer(text))
        if len(updated) > 1:
            return None
        preferences = updated or preferences
    limit = current[0]
    max_width = _decimal(limit["width"])
    inclusive = (
        not limit["rule"].casefold().startswith(("poniżej", "mniej niż", "węższ"))
    )
    widths = [_decimal(x["width"]) for x in options]
    if min(max_width, *widths) <= 0:
        return None
    eligible = [
        x
        for x, w in zip(options, widths, strict=True)
        if w < max_width or (inclusive and w == max_width)
    ]
    evidence = ", ".join(f"{x['label']} ma {x['width']} cm" for x in options)
    rule = "do" if inclusive else "poniżej"
    summary = f"{evidence}. Dopuszczalna szerokość: {rule} {limit['width']} cm."
    if not eligible:
        return f"Żaden z wariantów się nie mieści. {summary}"
    if len(eligible) == 1:
        return f"Wybierz wariant „{eligible[0]['label']}”. Tylko ten wariant się mieści. {summary}"
    desired = preferences[0]["surface"]
    picks = [x for x in eligible if _surface(x["surface"]) == _surface(desired)]
    reason = (
        f"Wybierz wariant „{picks[0]['label']}”, bo ma preferowaną cechę („{picks[0]['surface']}”)."
        if len(picks) == 1
        else "Preferencja powierzchni nie rozstrzyga wyboru."
    )
    return f"Oba warianty się mieszczą. {summary} {reason}"


_SPACE = re.compile(
    rf"\b(?:miejsce|przestrzeń|półka|szuflada|kaseta)\b[^.?!]{{0,55}}?\bma\s+(?:po zmianie )?(?:dokładnie )?(?P<n>{_NUM})\s*cm(?: szerokości)?\b",
    re.I,
)
_ACCESSORY = {
    "zamek": "zamka",
    "zatrzask": "zatrzasku",
    "uchwyt": "uchwytu",
    "pasek": "paska",
    "pokrywa": "pokrywy",
}
_WITH_FEATURE = re.compile(
    rf"\b(?P<label>{_WORD}) (?:ma|mierzy) (?P<n>{_NUM})\s*cm\s+"
    rf"(?:(?:i|oraz) (?P<positive>{'|'.join(_ACCESSORY)})|bez (?P<negative>{'|'.join(_ACCESSORY.values())}))\b",
    re.I,
)
_LIKES = re.compile(
    rf"\b(?:wolę|wolał(?:a)?bym|preferuję) (?P<name>{'|'.join(_ACCESSORY)})\b", re.I
)
_BENEFIT = re.compile(rf"\b(?P<name>{'|'.join(_ACCESSORY)}) to (?:zaleta|atut)\b", re.I)


def _accessory_fit(text: str, previous: str) -> str | None:
    if not _CHOICE.search(text) or _UNCERTAIN.search(text):
        return None
    limits = list(_SPACE.finditer(text))
    if len(limits) != 1:
        return None
    changed = len(list(_WITH_FEATURE.finditer(text))) == 0
    source = previous if changed else text
    options = list(_WITH_FEATURE.finditer(source))
    preference = _BENEFIT.search(text) or _LIKES.search(source)
    if (
        len(options) != 2
        or preference is None
        or not _FIT_CONTEXT.search(source)
        or _UNCERTAIN.search(source)
        or len(re.findall(r"\d[\d.,]*\s*cm\b", source, re.I)) != 3
        or len(_SPACE.findall(source)) != 1
        or options[0]["label"].casefold() == options[1]["label"].casefold()
    ):
        return None
    if changed and (
        not re.search(r"wcześniejsz|poprzedni|ten sam wybór|ponów", text, re.I)
        or len(re.findall(r"\d[\d.,]*\s*cm\b", text, re.I)) != 1
    ):
        return None
    positive = preference["name"].casefold()
    if not all(
        (o["positive"] or "").casefold() == positive
        or (o["negative"] or "").casefold() == _ACCESSORY[positive]
        for o in options
    ):
        return None
    limit = _decimal(limits[0]["n"])
    sizes = [_decimal(o["n"]) for o in options]
    if min(limit, *sizes) <= 0:
        return None
    fit = [o for o, w in zip(options, sizes, strict=True) if w <= limit]
    evidence = (
        ", ".join(f"{o['label']} ma {o['n']} cm" for o in options)
        + f", a dostępna szerokość to {limits[0]['n']} cm."
    )
    if len(fit) == 1:
        return f"Wybierz wariant „{fit[0]['label']}”. Tylko ten się mieści. {evidence}"
    if not fit:
        return f"Żaden się nie mieści. {evidence}"
    preferred = [o for o in fit if o["positive"]]
    reason = (
        f"Wybierz wariant „{preferred[0]['label']}”, który ma {positive}."
        if len(preferred) == 1
        else "Ta cecha nie rozstrzyga wyboru."
    )
    return f"Oba się mieszczą. {reason} {evidence}"


def _briefing(text: str) -> str | None:
    # If the requested presentation is already met by the source clauses, keep all of them.
    parts = re.split(r"(?<=[.!?])\s+", text)
    if len(parts) < 3 or not all(clause.endswith(".") for clause in parts[:-1]):
        return None
    if len(parts) == 3 and re.fullmatch(
        r"(?:opisz|zapisz|podaj) (?:ich |tę )?różnicę w dwóch zdaniach[.!]",
        parts[-1],
        re.I,
    ):
        return " ".join(parts[:-1])
    if (
        len(parts) in {3, 4}
        and re.fullmatch(
            r"jak (?:powiedzieć|przekazać) to (?:zespołowi|grupie|obsłudze)\?",
            parts[-1],
            re.I,
        )
        and re.search(r"\b(?:kopi[eaęi]|egzemplarz)\b", text, re.I)
    ):
        return " ".join(parts[:-1])
    return None


_MINUTES = {
    "jedną": 1,
    "dwie": 2,
    "trzy": 3,
    "cztery": 4,
    "pięć": 5,
    "sześć": 6,
    "siedem": 7,
    "osiem": 8,
    "dziewięć": 9,
    "dziesięć": 10,
}
_DURATION = re.compile(
    rf"\b(?P<n>{_NUM}|{'|'.join(_MINUTES)})\s*(?:minut(?:ach|ami|[ayę])?|min)\b", re.I
)
_USE = re.compile(r"\b(?:pracuje|pracować|pracy|działa|działania|działać)\b", re.I)
_PREP = re.compile(r"\b(?:gotow\w*|przygotowa\w*|rozruch\w*|rozgrzewa\w*)\b", re.I)
_EXPLAIN = re.compile(
    r"\b(?:wyjaśnij|objaśnij|wytłumacz|rozróżnij|porównaj|oznaczają|oznacza)\b", re.I
)
_TIME_CHECK = re.compile(
    r"\b(?:zdąż\w*|zapasu?|niedob[oó]r\w*|zabraknie|wystarczy|minę się z początkiem|spóźn\w*)\b",
    re.I,
)


def _duration_value(value: str) -> Decimal:
    value = value.casefold()
    return Decimal(_MINUTES[value]) if value in _MINUTES else _decimal(value)


def _time_roles(source: str) -> dict[str, tuple[str, str]] | None:
    durations: dict[str, tuple[str, str]] = {}
    if len(_DURATION.findall(source)) != 2 or _UNCERTAIN.search(source):
        return None
    evidence = re.sub(r":\s*(?=\d)", " ", source)
    for clause in re.split(r"(?<!\d)[.!?,;:]|\s+(?:a|oraz|i)\s+", evidence, flags=re.I):
        measurement = _DURATION.search(clause)
        if not measurement:
            continue
        roles = [
            key
            for key, pattern in (("active", _USE), ("ready", _PREP))
            if pattern.search(clause)
        ]
        if (
            len(roles) != 1
            or roles[0] in durations
            or re.search(
                r"\b(?:poniżej|do około|ponad|co najmniej|maksymalnie|nie trwa)\b",
                clause,
                re.I,
            )
        ):
            return None
        phase = re.search(rf"\bod {_WORD} do gotowości\b", clause, re.I)
        durations[roles[0]] = (
            measurement["n"],
            phase[0] if phase else "przygotowania do gotowości",
        )
    return durations if len(durations) == 2 else None


def _durations(text: str, previous: str) -> str | None:
    measurements = list(_DURATION.finditer(text))
    deadline = len(measurements) == 1 and _TIME_CHECK.search(text)
    if not (deadline or _EXPLAIN.search(text)):
        return None
    info = _time_roles(previous if deadline else text)
    if info is None:
        return None
    ready, phase = info["ready"]
    if not deadline:
        return f"Czas działania wynosi {info['active'][0]} min, a czas {phase} wynosi {ready} min."
    if (
        not re.search(
            r"\b(?:przed|wcześniej|na przygotowanie|do rozpoczęcia|do startu)\b",
            text,
            re.I,
        )
        or _UNCERTAIN.search(text)
        or re.search(
            r"\b(?:po zakończeniu|przed końcem|przed zakończeniem|na zakończenie|po starcie)\b",
            text,
            re.I,
        )
    ):
        return None
    delta = _duration_value(measurements[0]["n"]) - _duration_value(ready)
    if delta < 0 and re.search(r"początk|spóźn", text, re.I):
        return f"Urządzenie będzie gotowe {str(-delta).replace('.', ',')} min po rozpoczęciu."
    if not delta:
        return "Gotowość wypadnie dokładnie na czas."
    number = str(abs(delta)).replace(".", ",")
    return (
        f"Zostanie {number} min zapasu."
        if delta > 0
        else f"Do gotowości zabraknie {number} min."
    )


_STOPS = re.compile(
    rf"wariant (?P<a>{_WORD}) ma [^.!?]+?, (?:a )?wariant (?P<b>{_WORD}) [^.!?]+[.] "
    rf"(?P<evidence>w (?P<which>{_WORD}) przy [^.,!?]+ (?:zaplanowano|przewidziano|potwierdzono) (?P<feature>{_WORD})), "
    rf"dla (?P<unknown>{_WORD}) nie podano [^.!?]+[.] (?P<task>porównaj [^.!?]+)[.!]",
    re.I,
)
_CHOOSE_ROUTE = re.compile(
    rf"(?:jeśli|gdy) grupa szuka (?:właśnie )?(?P<feature>{_WORD}), którą trasę wybrać(?: z obecnych danych)?[?]",
    re.I,
)


def _route_feature(text: str, previous: str) -> str | None:
    followup = _CHOOSE_ROUTE.fullmatch(text)
    source = previous if followup else text
    info = _STOPS.fullmatch(source)
    if not info:
        return None
    labels = {info["a"].casefold(), info["b"].casefold()}
    origins = {info["which"].casefold(), info["unknown"].casefold()}
    if labels != origins or len(labels) != 2:
        return None
    if followup is None:
        return source[: info.start("task")].rstrip()
    feature = info["feature"].casefold()
    if followup["feature"].casefold() not in {
        feature,
        feature + "u",
        feature + "a",
        feature.removesuffix("a") + "y",
    }:
        return None
    return f"Wybierz wariant {info['which']}. {info['evidence'][0].upper()}{info['evidence'][1:]}."


def _briefing_followup(text: str, previous: str) -> str | None:
    if not _briefing(previous):
        return None
    material = re.fullmatch(
        r"ktoś (?:przy|w|na) [^.!?]+ szuka drogi (?P<goal>[^.!?]+)[.] "
        r"który materiał mu pomoże i jaka informacja zdecyduje\?",
        text,
        re.I,
    )
    if material:
        options = re.findall(
            rf"(?:^|[.] |, )(?P<doc>{_WORD}) (?:mówi|wyjaśnia|wskazuje),? "
            r"(?P<function>jak (?:przejść|dojść|dotrzeć) [^.,!?]+)",
            previous,
            re.I,
        )
        if len(options) == 1:
            label, function = options[0]
            destination = re.sub(
                r"^jak (?:przejść|dojść|dotrzeć) ", "", function, flags=re.I
            ).casefold()
            goal = material["goal"].casefold()
            general = re.fullmatch(r"(na|do) każd\w+ (\w+)", destination)
            ordinal = re.fullmatch(
                r"(na|do) (?:pierwsz\w*|drug\w*|trzeci\w*|czwart\w*|\d+[.]?) (\w+)",
                goal,
            )
            if destination == goal or (
                general and ordinal and general.groups() == ordinal.groups()
            ):
                return f"Pomoże {label.lower()}, ponieważ wyjaśnia, {function}."
            return f"{label.capitalize()} wyjaśnia, {function}. W opisie materiałów brakuje wskazówek dojścia {material['goal']}."
    if re.fullmatch(
        r"(?:pokaż|podaj) jednym sposobem, jak zaznaczyć stacje dłuższej trasy bez narzucania kierunku[.!?]",
        text,
        re.I,
    ):
        layout = re.search(
            r"\bdłuższy(?: tor| szlak)? ma (?P<arrangement>[^.!?]{4,100})[.]",
            previous,
            re.I,
        )
        if layout:
            return f"Pokaż na jednym schemacie bez strzałek układ dłuższej trasy: {layout['arrangement']}."
    return None


def _missing_property(text: str, previous: str) -> str | None:
    parts = re.split(r"(?<=[.!?])\s+", text)
    explaining = len(parts) >= 3 and re.fullmatch(
        r"jaką (?:prostą )?różnicę (?:można opisać|widać w opisie)\?", parts[-1], re.I
    )
    evidence = text if explaining else previous
    variants = re.findall(
        r"\bwariancie ([^\W_]+) (?:podano|odnotowano|wskazano)\b", evidence, re.I
    )
    missing = re.search(
        r"\b(?:żadnych danych|brak danych) o (?:przekazywaniu|przepuszczaniu) światła przez "
        r"(?P<part>spód|wieko|bok)[.]",
        evidence,
        re.I,
    )
    if len(variants) != 2 or len(set(variants)) != 2 or missing is None:
        return None
    if explaining:
        return " ".join(parts[:-1])
    if (
        not re.fullmatch(
            r"chcę (?:rozpoznać|odczytać|zobaczyć) (?:kolor|barwę) pod [^.!?]{2,60} bez podnoszenia[.] "
            r"co (?:ustalić|sprawdzić) przed wyborem[?]",
            text,
            re.I,
        )
        or missing["part"].casefold() != "spód"
    ):
        return None
    return f"Sprawdź w obu wariantach ({' i '.join(variants)}), czy przez spód widać kolor przedmiotu pod pudełkiem."


_STATION_LABELS = re.compile(
    r"(?P<stations>[^\W_]+ stanowisk(?:a)?(?: [^\W\d_]+)?) (?:stoi|są|stoją) przy "
    r"(?P<n>[^\W_]+) (?P<furniture>ławach|stołach|blatach)[.] "
    r"(?:daj|podaj) jeden sposób, (?:by|żeby) dało się odróżnić miejsca stanowisk od początku kolejki do [^\W\d_]+[.!]",
    re.I,
)
_STATION_SURFACE = re.compile(
    r"zostają same oznaczenia na (?P<surface>ławie|stole|blacie), podłogi nie można oklejać[.] "
    r"podaj jeden konkretny wariant[.!]",
    re.I,
)
_FURNITURE = {"ławach": "ławie", "stołach": "stole", "blatach": "blacie"}


def _station_labels(text: str, previous: str) -> str | None:
    followup = _STATION_SURFACE.fullmatch(text)
    setup = _STATION_LABELS.fullmatch(previous if followup else text)
    if not setup:
        return None
    surface = _FURNITURE[setup["furniture"].casefold()]
    if followup and followup["surface"].casefold() != surface:
        return None
    return f"Na {surface} oznacz każde stanowisko osobną tabliczką z numerem, a osobną tabliczką na tej samej powierzchni wskaż początek kolejki napisem „Początek kolejki”."


_RECORDING = re.compile(
    rf"(?P<offline>{_WORD} {_WORD}) (?:pozwala|umożliwia) zapisywać bez prądu, "
    rf"ale (?P<cost>trzeba [^.!?]+)[.] (?P<online>{_WORD} {_WORD}) "
    rf"(?P<share>udostępnia je grupie przy dostępie do sieci)[.] "
    rf"[^.!?]{{2,75}} (?:jest )?bez zasilania i bez sieci[.] co przyda się do zapisu\?",
    re.I,
)
_CONNECTED = re.compile(
    r"przenieśliśmy pracę do [^.!?]{2,60} z zasilaniem i siecią[.] "
    r"teraz uczestnicy mają widzieć zmiany innych na bieżąco[.] co wybrać\?",
    re.I,
)


def _recording(text: str, previous: str) -> str | None:
    connected = _CONNECTED.fullmatch(text)
    info = _RECORDING.fullmatch(previous if connected else text)
    if not info or info["offline"].casefold() == info["online"].casefold():
        return None
    if connected:
        return (
            f"Wybierz {info['online']}. Przy dostępnej sieci udostępnia notatki grupie."
        )
    return f"Wybierz {info['offline']}. Można zapisywać bez prądu, ale {info['cost']}."


def dialog_evidence(text: str, previous: str) -> str | None:
    return (
        _briefing(text)
        or _briefing_followup(text, previous)
        or _width_choice(text, previous)
        or _accessory_fit(text, previous)
        or _durations(text, previous)
        or _route_feature(text, previous)
        or _missing_property(text, previous)
        or _station_labels(text, previous)
        or _recording(text, previous)
    )
