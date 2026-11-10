"""Recognize a pilot screen and resolve explicit Polish references to its cards."""

from __future__ import annotations

import re
from typing import TypedDict

MAX_CARDS = 8
LAYOUTS = ("vertical", "horizontal", "single", "unknown")
COLORS = {
    "red": r"czerwon\w*|bordow\w*",
    "blue": r"niebiesk\w*|granatow\w*|błękitn\w*",
    "green": r"zielon\w*",
    "brown": r"brązow\w*",
    "yellow": r"żółt\w*",
    "orange": r"pomarańczow\w*|bursztynow\w*",
    "purple": r"fioletow\w*",
    "gray": r"szar\w*",
    "white": r"biał\w*",
    "black": r"czarn\w*",
}
CODE = re.compile(r"VEN-\d{3}", re.ASCII)
SPOKEN_CODE = re.compile(r"\b(?:ven|van|vn)[ -]*((?a:\d{3}))\b")
POSITION = (
    ("vertical", 0, r"\b(?:na górze|u góry|górn\w*)\b"),
    ("vertical", -1, r"\b(?:na dole|u dołu|doln\w*)\b"),
    ("horizontal", 0, r"\b(?:po lewej|z lewej|lew[eyą]\w*)\b"),
    ("horizontal", -1, r"\b(?:po prawej|z prawej|praw[eyą]\w*)\b"),
)
ORDINAL = re.compile(
    r"\b(pierwsz\w*|drug\w*|trzeci\w*|czwart\w*|piąt\w*|szóst\w*|siódm\w*|ósm\w*)"
    r"\s+(?:komunikat|kart|wpis)\w*\b"
)
ORDINALS = ("pierwsz", "drug", "trzeci", "czwart", "piąt", "szóst", "siódm", "ósm")

SCREEN_PROMPT = (
    "Identify each visible rectangular VEN error card. If all cards are one below "
    "the other, report vertical. If all cards appear on the same line side by side, "
    "report horizontal. Report single for one card and unknown for a grid or "
    "unclear layout. Then transcribe all error codes exactly in reading order "
    "and name the color of each card's own background. Ignore the page heading "
    "and all non-card text."
)
SCREEN_SCHEMA = {
    "type": "object",
    "properties": {
        "layout": {"type": "string", "enum": list(LAYOUTS)},
        "cards": {
            "type": "array",
            "maxItems": MAX_CARDS,
            "items": {
                "type": "object",
                "properties": {
                    "code": {"type": "string"},
                    "color": {"type": "string", "enum": [*COLORS, "other"]},
                },
                "required": ["code", "color"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["layout", "cards"],
    "additionalProperties": False,
}


class ScreenCard(TypedDict):
    code: str
    color: str


class PilotScreen(TypedDict):
    layout: str
    cards: list[ScreenCard]


def parse_screen(value: object) -> PilotScreen | None:
    """Accept only a bounded, complete inventory with validated codes and colors."""
    if not isinstance(value, dict) or value.keys() != {"layout", "cards"}:
        return None
    layout, cards = value["layout"], value["cards"]
    if layout not in LAYOUTS or not isinstance(cards, list):
        return None
    if not 1 <= len(cards) <= MAX_CARDS or (layout == "single") != (len(cards) == 1):
        return None
    parsed: list[ScreenCard] = []
    for card in cards:
        checked = _parse_card(card)
        if checked is None:
            return None
        parsed.append(checked)
    return {"layout": layout, "cards": parsed}


def _parse_card(card: object) -> ScreenCard | None:
    if not isinstance(card, dict) or card.keys() != {"code", "color"}:
        return None
    code, color = card["code"], card["color"]
    if not isinstance(code, str) or not CODE.fullmatch(code):
        return None
    if not isinstance(color, str) or color not in (*COLORS, "other"):
        return None
    return {"code": code, "color": color}


def previous_screen(history: list[dict[str, object]]) -> PilotScreen | None:
    """Read the latest pilot inventory, including an explicit reset on a new screen."""
    for row in reversed(history):
        if row.get("mode") == "omni_pilot" and "omni_pilot_screen" in row:
            return parse_screen(row["omni_pilot_screen"])
    return None


def _keywords(text: str) -> set[str]:
    """Match distinctive title words across common Polish inflections."""
    return {word[:5] for word in re.findall(r"[^\W\d_]{5,}", text.casefold())}


def resolve_reference(
    question: str, screen: PilotScreen | None, documents: dict[str, dict[str, str]]
) -> tuple[bool, str | None]:
    """Resolve a screen reference only when its criteria identify exactly one card."""
    text = question.casefold()
    explicit = set(SPOKEN_CODE.findall(text))
    if explicit:
        return True, f"VEN-{explicit.pop()}" if len(explicit) == 1 else None

    cards = screen["cards"] if screen is not None else []
    colors = {
        color
        for color, pattern in COLORS.items()
        if re.search(rf"\b(?:{pattern})\b", text)
    }
    positions = [
        (axis, end) for axis, end, pattern in POSITION if re.search(pattern, text)
    ]
    ordinal = ORDINAL.search(text)
    if colors or positions or ordinal:
        layout = screen["layout"] if screen is not None else ""
        return True, _resolve_card(layout, cards, colors, positions, ordinal)

    words = _keywords(text)
    matching = [
        card["code"]
        for card in cards
        if words & _keywords(documents.get(card["code"], {}).get("title", ""))
    ]
    return bool(matching), matching[0] if len(matching) == 1 else None


def _resolve_card(
    layout: str,
    cards: list[ScreenCard],
    colors: set[str],
    positions: list[tuple[str, int]],
    ordinal: re.Match[str] | None,
) -> str | None:
    if not cards or len(colors) > 1:
        return None
    indices = set(range(len(cards)))
    for axis, end in positions:
        if layout != axis:
            return None
        indices.intersection_update({end % len(cards)})
    if colors:
        indices.intersection_update(
            i for i, card in enumerate(cards) if card["color"] in colors
        )
    if ordinal:
        position = next(
            i for i, prefix in enumerate(ORDINALS) if ordinal[1].startswith(prefix)
        )
        ordered = sorted(indices)
        indices = {ordered[position]} if position < len(ordered) else set()
    return cards[indices.pop()]["code"] if len(indices) == 1 else None
