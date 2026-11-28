"""Allowlisted, version-pinned cards for qualified Studio advice."""

from __future__ import annotations

import json
from functools import lru_cache
from hashlib import sha256
from pathlib import Path

_CARDS = {
    "hand_pump": (
        "qualified_card_hand_pump.json",
        "69bdb76ef5eaa00b3fd41d6a2317c81e91303d8c502cea0d8411238e9607f3a6",
        "PUMP-CHECK-1",
        "https://patents.google.com/patent/EP0366859A2/en",
    ),
    "ventilation": (
        "qualified_card_ventilation.json",
        "7f4aae0d8226571f2e83c7ac782e757ef242f3be35257395495a995f8acbf5cf",
        "EPA-VENT-1",
        "https://www.epa.gov/mold/brief-guide-mold-moisture-and-your-home",
    ),
    "irrigation": (
        "qualified_card_irrigation.json",
        "848eaedba77ddc245113f1b451886beeb0776cec1eee038ea0a148bfb1963cf4",
        "OSU-IRR-1",
        "https://extension.oregonstate.edu/catalog/em-9869-inspecting-maintaining-irrigation-systems",
    ),
}


@lru_cache(maxsize=len(_CARDS))
def read_card(name: str) -> dict[str, object] | None:
    filename, digest, card_id, url = _CARDS[name]
    try:
        raw = Path(__file__).with_name(filename).read_bytes()
        if sha256(raw).hexdigest() != digest:
            return None
        record = json.loads(raw)
    except (OSError, ValueError):
        return None
    if (
        isinstance(record, dict)
        and record.get("id") == card_id
        and record.get("url") == url
    ):
        return record
    return None


def card_link(card: dict[str, object], label: str) -> str:
    return f"[{label}]({card['url']})"
