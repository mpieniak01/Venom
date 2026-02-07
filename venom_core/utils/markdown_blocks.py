"""Narzędzia do pracy z fenced code blocks w markdown (```...```)."""

from typing import Optional


def extract_fenced_block(text: str, language: Optional[str] = None) -> Optional[str]:
    """
    Zwraca pierwszy blok fenced (```...```), opcjonalnie dla konkretnego języka.
    """
    cursor = 0
    target_language = language.lower() if language else None
    while True:
        start = text.find("```", cursor)
        if start == -1:
            return None
        header_end = text.find("\n", start + 3)
        if header_end == -1:
            return None
        header = text[start + 3 : header_end].strip().lower()
        block_end = text.find("```", header_end + 1)
        if block_end == -1:
            return None
        if target_language is None or header == target_language:
            return text[header_end + 1 : block_end].strip()
        cursor = block_end + 3


def strip_fenced_blocks(text: str) -> str:
    """
    Usuwa wszystkie poprawnie domknięte fenced blocki (```...```).
    """
    parts: list[str] = []
    cursor = 0
    while True:
        start = text.find("```", cursor)
        if start == -1:
            parts.append(text[cursor:])
            break
        header_end = text.find("\n", start + 3)
        if header_end == -1:
            parts.append(text[cursor:])
            break
        block_end = text.find("```", header_end + 1)
        if block_end == -1:
            parts.append(text[cursor:])
            break
        parts.append(text[cursor:start])
        cursor = block_end + 3
    return "".join(parts)
