"""Session-aware chat retrieval shared by Full and standalone Studio."""

import re
from typing import Any, Optional


def named_memory_subject(query: str) -> str | None:
    """Use a title-cased subject for explicit source lookups."""
    subject = r"([A-ZĄĆĘŁŃÓŚŹŻ][^\W\d_]+(?:[ \t]+[A-ZĄĆĘŁŃÓŚŹŻ][^\W\d_]+){1,3})\b"
    match = re.search(
        r"\b(?:projekt(?:u)?|project|stanowisk[ao]|station)\s+" + subject, query
    )
    if not match:
        # A bare "for" can also introduce dates and other ordinary chat context.
        match = re.search(
            r"\b(?i:according to (?:the (?:retrieved )?notes|this session)\b"
            r"[^.!?\n]{0,256}?\bfor)[ \t]+" + subject,
            query,
        )
    return match.group(1) if match else None


def select_relevant_memory_items(
    results: list[dict], session_id: Optional[str]
) -> list[dict]:
    """Keep global and same-session results without falling back to other sessions."""
    if not results:
        return []
    filtered = []
    for item in results:
        meta = item.get("metadata") or {}
        item_session_id = meta.get("session_id")
        if item_session_id and item_session_id != session_id:
            continue
        filtered.append(item)
    return filtered[:3]


def format_memory_context(items: list[dict]) -> tuple[str, list[str]]:
    lines: list[str] = []
    ids: list[str] = []
    for idx, item in enumerate(items, 1):
        text = truncate_memory_text(item.get("text", ""))
        meta = item.get("metadata") or {}
        entry_id = item.get("id") or meta.get("id")
        if entry_id:
            ids.append(str(entry_id))
        lines.append(f"[{idx}] ({meta.get('type', 'fact')}) {text}")
    return "\n".join(lines), ids


def truncate_memory_text(text: str, limit: int = 400) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def retrieve_chat_memory(
    store: Any, query: str, session_id: str | None
) -> tuple[str, list[str]]:
    """Find matching notes within the existing session/global scope."""
    subject = named_memory_subject(query)
    pattern = None
    if subject:
        words = r"[ \t]+".join(re.escape(word) for word in subject.split())
        pattern = rf"(?i)\b{words}\b"
    results = store.search(
        subject or query,
        limit=8,
        session_scope=True,
        session_id=session_id,
        text_pattern=pattern,
    )
    if pattern:
        phrase = re.compile(pattern)
        results = [item for item in results if phrase.search(item.get("text", ""))]
    return format_memory_context(select_relevant_memory_items(results, session_id))
