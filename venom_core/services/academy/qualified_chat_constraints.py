"""Bounded Polish checks for explicitly excluded material in proposed options.

Only user turns set a rule. A rule is selected by affirmative instructions with
a supported noun phrase. Draft text has separate evidence and uncertainty
checks, since the content behind an unspecified attachment is unavailable.
"""

import re
from collections.abc import Iterable, Sequence
from typing import NamedTuple


class Rule(NamedTuple):
    label: str
    declaration: str
    evidence: str


_RULES = {
    "photos": Rule(
        "bez zdjęć, również w galerii, linku do zdjęć lub załączniku",
        r"(?:(?:wspólnych|podpisanych|grupowych|pamiątkowych)\s+)?"
        r"(?:zdję(?:ć|ci(?:e|a|ami|om|ach|u|em))|fotograf(?:ii|ię|ie|ia|ią|iami|iach)|fotek|fotk(?:a|i|ę|ą|ami))",
        r"(?:zdję(?:ć|ci(?:e|a|ami|om|ach|u|em|ową|owe|owy|owych))"
        r"|fotograf(?:ii|ię|ie|ia|ią|iami|iach|iczną|iczne|icznych)"
        r"|fotek|fotk(?:a|i|ę|ą|ami)|foto|photos?|fotorelacj\w+|(?:album|galeri(?:a|ę|i|ą))\s+fotograficzn\w+)",
    ),
    "surnames": Rule(
        "bez nazwisk",
        r"nazwisk(?:a|o|ami|ach|om|iem|u)?",
        r"(?:nazwisk(?:a|o|ami|ach|om|iem|u)?|pełn(?:e|ych)\s+(?:dane|danych)\s+osobow\w+)",
    ),
    "added_sugar": Rule(
        "bez dodatku cukru, miodu i słodzonych syropów",
        r"(?:(?:dodatek|dodatku|dodanego)\s+)?(?:cuk(?:ier|ru|rem)|miod(?:u|em|y)|miód|"
        r"słodzon(?:ego|ych)\s+syrop(?:u|ów)|syrop(?:u|ów|em)?|słodzeni[ea])",
        r"(?:cuk(?:ier|ru|rem)|miod(?:u|em|y)|miód|"
        r"syrop(?:u|ów|em|y|ami)?|dosł(?:odź|adzaj|odzeni[ea])|posł(?:odź|odzeni[ea]))",
    ),
    "coffee": Rule(
        "bez kawy",
        r"kaw(?:a|y|ę|ą|ie)",
        r"(?:kaw(?:a|y|ę|ą|ie)|espresso|latte|cappuccino|americano|kawow(?:y|a|e|ą|ego))",
    ),
    "water": Rule(
        "bez wody",
        r"wod(?:a|y|ę|ą|zie)",
        r"(?:wod(?:a|y|ę|ą|zie)|napełnij|podlej|podlewani[ea])",
    ),
    "glue": Rule(
        "bez kleju",
        r"klej(?:u|em|e|ów|ami)?",
        r"(?:klej(?:u|em|e|ów|ami)?|przyklej\w*|podklej\w*|sklej\w*|taśm(?:a|ę|y|ą)\s+(?:klejąc\w+|dwustronn\w+))",
    ),
    "screen": Rule(
        "bez ekranu i oglądania filmów",
        r"ekran(?:u|y|ów|em|ie|ami)?",
        r"(?:ekran(?:u|y|ów|em|ie|ami)?|telewizor(?:a|em|ze)?"
        r"|(?:włącz|obejrzyj|obejrzeć|oglądaj)\s+(?:sobie\s+)?(?:film|serial|telewizję|filmik))",
    ),
    "loud_sound": Rule(
        "bez głośnych dźwięków",
        r"głośn(?:ych|e|ymi)\s+(?:dźwięk(?:ów|i|ami)|odgłos(?:ów|y|ami))",
        r"(?:głośn(?:ych|e|ymi)\s+(?:dźwięk(?:ów|i|ami)|odgłos(?:ów|y|ami))"
        r"|głośn(?:ą|a|ej|o)\s+(?:muzyk\w+|odtwarz\w+|graj)|krzycz\w*)",
    ),
}


def _named_phrases(attribute: str) -> re.Pattern:
    names = [rf"(?P<{key}>{getattr(rule, attribute)})" for key, rule in _RULES.items()]
    return re.compile(r"\b(?:" + "|".join(names) + r")\b", re.I)


_DECLARATION = _named_phrases("declaration")
_EVIDENCE = _named_phrases("evidence")
_QUOTED = re.compile(r'„[^”\n]*”|«[^»\n]*»|"[^"\n]*"|“[^”\n]*”')
_WITHOUT_PREFIX = (
    r"\b(?:bez|wyklucz(?:am)?|odpada(?:ją)?|pomiń|"
    r"obowiązuje\s+zakaz|zrezygnuj\s+z|wykluczone(?:\s+są)?|"
    r"nie\s+(?:możesz|można|wolno)\s+(?:użyć|dodać|pokazać|udostępnić|wysłać|załączyć)|"
    r"nie\s+(?:rób|używaj|dodawaj|dodaj|proponuj|pokazuj|publikuj|"
    r"udostępniaj|wysyłaj|załączaj|dołączaj|umieszczaj|podawaj|zamieszczaj|wstawiaj))\s+"
)
_WITHOUT = re.compile(
    _WITHOUT_PREFIX
    + r"(?:(?:żadnych|jakichkolwiek|dodawania|publikowania|udostępniania|użycia|używania|"
    r"zamieszczania|robienia|galerii|folderu|załączników\s+ze|link(?:u|ów)\s+do(?:\s+galerii)?)\s+){0,2}",
    re.I,
)
_ALLOW = re.compile(
    r"(?:^|(?<=[.!?;,:]))\s*(?:(?:ale|a|jednak|teraz|już|od teraz)\s+){0,2}"
    r"(?:możesz\s+(?:(?:już|jednak|teraz)\s+)?(?:użyć|dodać|załączyć|pokazać|wysłać|udostępnić)|"
    r"dopuszczam|zezwalam\s+na|znoszę\s+zakaz|odwołuję\s+zakaz)\s+",
    re.I,
)
_AFTER_ALLOW = re.compile(
    r"\s+(?:są\s+teraz\s+dozwolone|są\s+już\s+dozwolone|są\s+teraz\s+dopuszczalne)\b",
    re.I,
)
_LINKER = re.compile(r"\s*(?:,\s*(?:(?:i|oraz|ani)\s+)?|(?:i|oraz|ani)\s+)", re.I)
_REPORTED = re.compile(
    r"\b(?:proponuje|zaproponował[ao]?|sugeruje|zasugerował[ao]?|mówi|powiedział[ao]?|napisał[ao]?)\b",
    re.I,
)
_CLAUSE = re.compile(r"[!?;\n]|\.(?=\s|$)")
_POST_NEGATED = re.compile(
    r"\s+(?:w\s+ogóle\s+)?nie\s+(?:dołączaj|dodawaj|używaj|wysyłaj|udostępniaj|zamieszczaj)\b",
    re.I,
)
_MEDIA_FILE = re.compile(
    r"\.(?:jpeg|jpg|png|gif|webp|heic|avif|svg)(?=$|[\s)\]?!#.,])", re.I
)
_OPAQUE_MEDIA = re.compile(
    r"\b(?:galeri(?:a|ę|i|ą)|(?:link|odsyłacz)\s+do\s+(?:galerii|albumu)|"
    r"załącznik(?:a|u|i|ów|iem|ach)?)\b",
    re.I,
)
_TEXTUAL = re.compile(
    r"\b(?:dokument\w*|plik\w*|album\w*|galeri\w*|załącznik\w*)\s+tekstow\w*\b"
    r"|\b(?:z|ze|do)\s+(?:samym\s+|samego\s+)?tekst(?:em|u)|\bplik\w*\s+txt\b|\b\w+\.txt\b",
    re.I,
)


def _matched_items(text: str, start: int) -> list[re.Match]:
    """Read a consecutive list of explicit material names from this position."""
    items = []
    while match := _DECLARATION.match(text, start):
        items.append(match)
        joiner = _LINKER.match(text, match.end())
        if not joiner:
            break
        start = joiner.end()
    return items


def _negations(text: str) -> set[tuple[int, int]]:
    """Return only the noun spans governed by an explicit exclusion."""
    return {
        item.span()
        for lead in _WITHOUT.finditer(text)
        for item in _matched_items(text, lead.end())
    }


def _unconditional_release(text: str, end: int) -> bool:
    boundary = _CLAUSE.search(text, end)
    if boundary and boundary[0] == "?":
        return False
    tail = text[end : boundary.start() if boundary else len(text)].strip()
    return not tail or bool(re.match(r",\s*(?:ale|lecz)\s+", tail, re.I))


def _turn_bans(text: str) -> set[str]:
    bans = set()
    for clause in _CLAUSE.split(text):
        for lead in _WITHOUT.finditer(clause):
            if _REPORTED.search(clause[: lead.start()]):
                continue
            bans.update(item.lastgroup for item in _matched_items(clause, lead.end()))
    return bans


def _allow_releases(text: str) -> set[str]:
    releases = set()
    for lead in _ALLOW.finditer(text):
        start = max(
            (sep.end() for sep in _CLAUSE.finditer(text, 0, lead.start())), default=0
        )
        if _REPORTED.search(text[start : lead.start()]):
            continue
        items = _matched_items(text, lead.end())
        if items and _unconditional_release(text, items[-1].end()):
            releases.update(item.lastgroup for item in items)
    return releases


def _declared_releases(text: str) -> set[str]:
    releases = set()
    for item in _DECLARATION.finditer(text):
        allowed = _AFTER_ALLOW.match(text, item.end())
        if not allowed or not _unconditional_release(text, allowed.end()):
            continue
        start = max(
            (sep.end() for sep in _CLAUSE.finditer(text, 0, item.start())), default=0
        )
        prefix = text[start : item.start()].strip().casefold()
        if not prefix or prefix in {"jednak", "teraz", "od teraz"}:
            releases.add(item.lastgroup)
    return releases


def _turn_effects(text: str) -> tuple[set[str], set[str]]:
    text = _QUOTED.sub(lambda m: " " * len(m[0]), text)
    return _turn_bans(text), _allow_releases(text) | _declared_releases(text)


def _state(history: Sequence[dict[str, str]]) -> tuple[frozenset[str], frozenset[str]]:
    active: set[str] = set()
    unresolved: set[str] = set()
    for turn in history:
        if turn["role"] != "user":
            continue
        bans, releases = _turn_effects(turn["content"])
        conflicts = bans & releases
        active.difference_update(releases - conflicts)
        active.update(bans)
        unresolved.difference_update(bans | releases)
        unresolved.update(conflicts)
    return frozenset(active), frozenset(unresolved)


def active_constraints(history: Sequence[dict[str, str]]) -> frozenset[str]:
    """Return supported, explicit exclusions carried by user history."""
    return _state(history)[0]


def constraint_conflicts(history: Sequence[dict[str, str]]) -> frozenset[str]:
    """Return currently contradictory affirmative and negative user directives."""
    return _state(history)[1]


def constraint_labels(restrictions: Iterable[str]) -> tuple[str, ...]:
    """Stable Polish instructions for the recognized conditions."""
    return tuple(_RULES[key].label for key in sorted(set(restrictions)))


def _find_violations(text: str, restrictions: Iterable[str]) -> tuple[str, ...]:
    """Report bounded lexical evidence of actual use outside a scoped negation."""
    active = set(restrictions)
    ignored = _negations(text)
    violations = set()
    for found in _EVIDENCE.finditer(text):
        key = found.lastgroup
        if key not in active:
            continue
        inside_exclusion = any(
            start <= found.start() and found.end() <= end for start, end in ignored
        )
        if not inside_exclusion and not _POST_NEGATED.match(text, found.end()):
            violations.add(key)
    if "photos" in active and _MEDIA_FILE.search(text):
        violations.add("photos")
    return tuple(sorted(violations))


_MEDIA_PREFIX_DENIAL = re.compile(
    r"\b(?:bez|nie\s+(?:dołączaj|dodawaj|wysyłaj|udostępniaj))\s+"
    r"(?:(?:linku|linków|odsyłacza)\s+do\s+)?$",
    re.I,
)


def _has_opaque_photo_reference(text: str) -> bool:
    """Identify a potential gallery whose content is unavailable for review."""
    for clause in _CLAUSE.split(text):
        if _TEXTUAL.search(clause):
            continue
        for opaque in _OPAQUE_MEDIA.finditer(clause):
            if _MEDIA_PREFIX_DENIAL.search(clause[: opaque.start()]):
                continue
            described = _DECLARATION.match(clause, opaque.end() + 1)
            end = (
                described.end()
                if described and described.lastgroup == "photos"
                else opaque.end()
            )
            if not _POST_NEGATED.match(clause, end):
                return True
    return False


_REPLACED = re.compile(r"\bzamiast\s+(?:(?:użycia|dodawania|zamieszczania)\s+)?", re.I)
_NEGATED_REPLACEMENT = re.compile(r"\b(?:nie|raczej\s+nie)\s+$", re.I)


def _mask_replaced_materials(text: str) -> str:
    """Mask only named objects of a positive replacement, never a later use."""
    pieces = []
    cursor = 0
    for lead in _REPLACED.finditer(text):
        lead_start = max(0, lead.start() - 20)
        if _NEGATED_REPLACEMENT.search(text[lead_start : lead.start()]):
            continue
        for item in _matched_items(text, lead.end()):
            start, end = item.span()
            pieces.extend((text[cursor:start], " " * (end - start)))
            cursor = end
    pieces.append(text[cursor:])
    return "".join(pieces)


def find_violations(text: str, restrictions: Iterable[str]) -> tuple[str, ...]:
    return _find_violations(_mask_replaced_materials(text), restrictions)


def uncertain_constraints(text: str, restrictions: Iterable[str]) -> tuple[str, ...]:
    uncertain = []
    if "photos" in restrictions:
        draft = _mask_replaced_materials(text)
        if not find_violations(draft, ("photos",)) and _has_opaque_photo_reference(
            draft
        ):
            uncertain.append("photos")
    return tuple(uncertain)
