"""Guide title generation and preserve the selected title in invitation drafts."""

from __future__ import annotations

import re
from collections.abc import Sequence

from venom_core.services.chat_policy.direct_correction import CorrectionContext

_TITLE_REQUEST = re.compile(
    r"^(?:podaj|wymyśl|zaproponuj)\s+dwie(?:\s+(?:krótkie|polskie)){0,2}"
    r"\s+nazwy dla (?:sąsiedzkiej )?wymiany sadzonek(?P<herbs>\s+ziół)?"
    r"(?=[.!?,:]|$)",
    re.I,
)
_TITLE_FORMAT = re.compile(
    r"[.!?]?(?:\s+(?:"
    r"każdą nazwę zapisz w osobnym wierszu, bez wstępu"
    r"|podaj wyłącznie nazwy, po jednej w wierszu"
    r"|zapisz je w dwóch wierszach, bez objaśnień"
    r")[.!?]?)?",
    re.I,
)
_TITLE_LIST_INTRO = re.compile(r"oto (?:dwie (?:propozycje|nazwy)|propozycje):", re.I)
_TITLE_ITEM = re.compile(r"^(?:[-*•]|(?P<number>\d)[.)])\s+")
_TITLE_WORD = r"[^\W\d_]+(?:-[^\W\d_]+)*"
_TITLE = re.compile(rf"{_TITLE_WORD}(?:\s+{_TITLE_WORD}){{0,6}}")
_INVITATION_REQUEST = re.compile(
    r"(?:użyj drugiej nazwy|weź drugą nazwę) i (?:napisz|ułóż|przygotuj) jedno "
    r"(?:serdeczne|ciepłe|przyjazne) zdanie zapraszające sąsiadów"
    r"(?: na wymianę sadzonek(?: ziół)?)?\.\s*"
    r"(?:zachęć do przyniesienia|poproś o przyniesienie) jednej sadzonki"
    r", bez (?:podawania )?daty ani miejsca[.!]?",
    re.I,
)
_REMINDER_REQUEST = re.compile(
    r"(?:napisz|ułóż|przygotuj) jednozdaniowe przypomnienie dla "
    r"(?:uczestników|sąsiadów|osób, które już się wybierają)\.\s*"
    r"zachowaj (?:tę samą|wybraną) nazwę i "
    r"(?:wspomnij, że warto podpisać (?:swoją )?doniczkę"
    r"|przypomnij o podpisaniu (?:swojej )?doniczki)[.!]?",
    re.I,
)
_SHORT_REMINDER = re.compile(
    r"skróć przypomnienie(?: do jednej linijki)?(?:, zachowując|\.\s*zachowaj)"
    r" nazwę i prośbę o podpisanie doniczki\."
    r"(?:\s*pomiń wstęp i komentarz[.!]?)?",
    re.I,
)


def exchange_title_context(content: str) -> CorrectionContext | None:
    """Give the model linguistic guidance for a standalone two-name request."""
    current = content.strip()
    topic = _TITLE_REQUEST.match(current)
    if topic is None or _TITLE_FORMAT.fullmatch(current, topic.end()) is None:
        return None
    return CorrectionContext(
        "exchange_title_generation",
        "Zaproponuj dwie różne, krótkie nazwy wydarzenia w naturalnej polszczyźnie. "
        "Każda ma być samodzielną nazwą pasującą do podanego rodzaju wymiany. "
        "Użyj naturalnego szyku oraz zgodnego gramatycznie połączenia słów, "
        "np. przymiotnika z rzeczownikiem albo rzeczownika z określeniem "
        "w odpowiednim przypadku. Unikaj sklejania rzeczowników w mianowniku. "
        "Zapisz każdą nazwę w oddzielnym wierszu, bez numeracji i komentarza.",
    )


def _titles(text: str) -> list[str]:
    """Parse two bare items, without using descriptions as titles."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if lines and _TITLE_LIST_INTRO.fullmatch(lines[0]):
        lines = lines[1:]
    if len(lines) == 1 and lines[0].count(",") == 1:
        lines = [part.strip() for part in lines[0].split(",")]
    if len(lines) != 2:
        return []
    titles = []
    for index, line in enumerate(lines, 1):
        marker = _TITLE_ITEM.match(line)
        if marker and marker["number"] and marker["number"] != str(index):
            return []
        title = line[marker.end() :] if marker else line
        for left, right in (("**", "**"), ("„", "”"), ('"', '"'), ("«", "»")):
            if title.startswith(left) and title.endswith(right):
                title = title[len(left) : -len(right)].strip()
        if len(title) > 70 or _TITLE.fullmatch(title) is None:
            return []
        titles.append(" ".join(title.split()))
    return titles if titles[0].casefold() != titles[1].casefold() else []


def _holds_title(text: str, title: str) -> bool:
    text, title = text.casefold().strip(), title.casefold()
    return (
        any(
            f"{left}{title}{right}" in text
            for left, right in (("„", "”"), ('"', '"'), ("«", "»"))
        )
        or re.match(rf"{re.escape(title)}(?=,|\s*[–—:]|$)", text) is not None
    )


def _selected_exchange(
    history: Sequence[dict[str, str]], depth: int
) -> tuple[str, str] | None:
    """Use only the most recent contiguous sequence of title and draft turns."""
    recent = history[-depth:]
    if [row["role"] for row in recent] != ["user", "assistant"] * (depth // 2):
        return None
    topic = _TITLE_REQUEST.match(recent[0]["content"])
    titles = _titles(recent[1]["content"])
    if topic is None or not titles:
        return None
    title = titles[1]
    if depth >= 4 and not (
        _INVITATION_REQUEST.fullmatch(recent[2]["content"].strip())
        and _holds_title(recent[3]["content"], title)
    ):
        return None
    if depth == 6 and not (
        _REMINDER_REQUEST.fullmatch(recent[4]["content"].strip())
        and _holds_title(recent[5]["content"], title)
    ):
        return None
    exchange = "wymianę sadzonek ziół" if topic["herbs"] else "wymianę sadzonek"
    return title, exchange


def invitation_context(
    content: str, history: Sequence[dict[str, str]]
) -> CorrectionContext | None:
    """Prepare a bounded draft and preserve the title actually selected in chat."""
    current = content.strip()
    if _INVITATION_REQUEST.fullmatch(current):
        selected = _selected_exchange(history, 2)
        if selected is None:
            return None
        title, exchange = selected
        draft = f"Sąsiedzi, zapraszamy na {exchange} „{title}” – przynieście po jednej sadzonce!"
        return CorrectionContext("invitation_draft", draft, verified_reply=draft)
    short = _SHORT_REMINDER.fullmatch(current) is not None
    if not short and _REMINDER_REQUEST.fullmatch(current) is None:
        return None
    selected = _selected_exchange(history, 6 if short else 4)
    if selected is None:
        return None
    title, _ = selected
    draft = (
        f"„{title}”: podpiszcie doniczki!"
        if short
        else f"Przed wymianą „{title}” pamiętajcie o podpisaniu swoich doniczek."
    )
    return CorrectionContext("reminder_draft", draft, verified_reply=draft)
