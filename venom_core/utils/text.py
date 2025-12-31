"""Pomocnicze funkcje tekstowe."""

from __future__ import annotations


def trim_to_char_limit(text: str, limit: int) -> tuple[str, bool]:
    """
    Proste obcięcie tekstu do limitu znaków (przybliżenie budżetu tokenów).

    Zwraca obcięty tekst oraz flagę, czy obcięto.
    """
    if limit <= 0:
        return "", True
    if not text or len(text) <= limit:
        return text, False
    trimmed = text[:limit]
    return trimmed, True
