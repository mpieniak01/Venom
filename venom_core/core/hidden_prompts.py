"""Moduł: hidden_prompts - agregacja i podgląd ukrytych promptów."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from venom_core.utils.boot_id import BOOT_ID
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

HIDDEN_PROMPTS_PATH = Path("./data/learning/hidden_prompts.jsonl")
ACTIVE_HIDDEN_PROMPTS_PATH = Path("./data/learning/active_hidden_prompts.json")
HIDDEN_PROMPTS_META_PATH = Path("./data/learning/hidden_prompts_meta.json")
_cache_mtime: Optional[float] = None
_cache_entries: List[Dict[str, Any]] = []


def _normalize(text: str) -> str:
    return " ".join((text or "").lower().strip().split())


def _load_hidden_prompts() -> List[Dict[str, Any]]:
    global _cache_mtime, _cache_entries
    _ensure_boot_id()
    if not HIDDEN_PROMPTS_PATH.exists():
        _cache_entries = []
        _cache_mtime = None
        return []

    mtime = HIDDEN_PROMPTS_PATH.stat().st_mtime
    if _cache_mtime is not None and _cache_mtime == mtime:
        return _cache_entries

    entries: List[Dict[str, Any]] = []
    try:
        for line in HIDDEN_PROMPTS_PATH.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except Exception as exc:
        logger.warning("Nie udało się wczytać hidden prompts: %s", exc)
        entries = []

    _cache_entries = entries
    _cache_mtime = mtime
    return entries


def _load_active_hidden_prompts() -> List[Dict[str, Any]]:
    _ensure_boot_id()
    if not ACTIVE_HIDDEN_PROMPTS_PATH.exists():
        return []
    try:
        payload = json.loads(ACTIVE_HIDDEN_PROMPTS_PATH.read_text(encoding="utf-8"))
        items = payload.get("items", [])
        return [item for item in items if isinstance(item, dict)]
    except Exception as exc:
        logger.warning("Nie udało się wczytać aktywnych hidden prompts: %s", exc)
        return []


def _ensure_boot_id() -> None:
    """Czyści hidden prompts po restarcie backendu (zmiana boot_id)."""
    try:
        meta_path = HIDDEN_PROMPTS_PATH.parent / "hidden_prompts_meta.json"
        if meta_path.exists():
            payload = json.loads(meta_path.read_text(encoding="utf-8"))
            stored_boot = payload.get("boot_id")
            if stored_boot and stored_boot != BOOT_ID:
                if HIDDEN_PROMPTS_PATH.exists():
                    HIDDEN_PROMPTS_PATH.unlink(missing_ok=True)
                if ACTIVE_HIDDEN_PROMPTS_PATH.exists():
                    ACTIVE_HIDDEN_PROMPTS_PATH.unlink(missing_ok=True)
                global _cache_entries, _cache_mtime
                _cache_entries = []
                _cache_mtime = None
        else:
            meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(
            json.dumps({"boot_id": BOOT_ID}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as exc:
        logger.warning("Nie udało się sprawdzić boot_id hidden prompts: %s", exc)


def _save_active_hidden_prompts(items: List[Dict[str, Any]]) -> None:
    ACTIVE_HIDDEN_PROMPTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {"items": items, "updated_at": datetime.now().isoformat()}
    ACTIVE_HIDDEN_PROMPTS_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def get_active_hidden_prompts(intent: Optional[str] = None) -> List[Dict[str, Any]]:
    items = _load_active_hidden_prompts()
    if intent:
        items = [
            item
            for item in items
            if str(item.get("intent") or "").upper() == intent.upper()
        ]
    items.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
    return items


def set_active_hidden_prompt(
    entry: Dict[str, Any], active: bool, actor: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Aktywuje lub wyłącza hidden prompt (po prompt_hash lub intent+prompt)."""
    items = _load_active_hidden_prompts()
    intent = entry.get("intent") or "UNKNOWN"
    prompt_hash = entry.get("prompt_hash")
    prompt_norm = _normalize(entry.get("prompt") or "")

    def matches(item: Dict[str, Any]) -> bool:
        if prompt_hash and item.get("prompt_hash") == prompt_hash:
            return True
        return (
            _normalize(item.get("prompt") or "") == prompt_norm
            and str(item.get("intent") or "").upper() == str(intent).upper()
        )

    if active:
        items = [
            item
            for item in items
            if str(item.get("intent") or "").upper() != str(intent).upper()
        ]
        items.append(
            {
                "intent": intent,
                "prompt": entry.get("prompt"),
                "approved_response": entry.get("approved_response"),
                "prompt_hash": prompt_hash,
                "updated_at": datetime.now().isoformat(),
                "activated_by": actor or "unknown",
                "activated_at": datetime.now().isoformat(),
            }
        )
    else:
        items = [item for item in items if not matches(item)]

    _save_active_hidden_prompts(items)
    return items


def aggregate_hidden_prompts(
    limit: int = 50,
    intent: Optional[str] = None,
    min_score: int = 1,
) -> List[Dict[str, Any]]:
    """Zwraca zagregowane hidden prompts z deduplikacją i score."""
    entries = _load_hidden_prompts()
    aggregated: Dict[str, Dict[str, Any]] = {}

    for entry in entries:
        prompt = entry.get("prompt") or ""
        response = entry.get("approved_response") or ""
        entry_intent = entry.get("intent") or "UNKNOWN"
        if intent and entry_intent.upper() != intent.upper():
            continue
        if not prompt.strip():
            continue

        prompt_hash = entry.get("prompt_hash")
        key = prompt_hash or f"{_normalize(entry_intent)}::{_normalize(prompt)}"
        current = aggregated.get(key)
        timestamp = entry.get("timestamp")
        if current is None:
            aggregated[key] = {
                "intent": entry_intent,
                "prompt": prompt,
                "approved_response": response,
                "prompt_hash": prompt_hash,
                "score": 1,
                "last_timestamp": timestamp,
            }
        else:
            current["score"] += 1
            if timestamp and _is_newer(timestamp, current.get("last_timestamp")):
                current["last_timestamp"] = timestamp
                if response:
                    current["approved_response"] = response

    items = [item for item in aggregated.values() if item["score"] >= min_score]
    items.sort(
        key=lambda item: (item.get("score", 0), item.get("last_timestamp") or ""),
        reverse=True,
    )
    return items[:limit]


def _is_newer(candidate: Optional[str], current: Optional[str]) -> bool:
    if not candidate:
        return False
    if not current:
        return True
    try:
        return datetime.fromisoformat(candidate) > datetime.fromisoformat(current)
    except Exception:
        return candidate > current


def build_hidden_prompts_context(
    intent: str,
    limit: int = 3,
    min_score: int = 1,
) -> str:
    """Buduje sekcję kontekstu z hidden prompts dla podanej intencji."""
    active_items = get_active_hidden_prompts(intent=intent)
    aggregated = aggregate_hidden_prompts(
        limit=limit, intent=intent, min_score=min_score
    )
    active_hashes = {
        item.get("prompt_hash") for item in active_items if item.get("prompt_hash")
    }
    items = active_items + [
        item for item in aggregated if item.get("prompt_hash") not in active_hashes
    ]
    items = items[:limit]
    if not items:
        return ""
    lines = ["\n\n🧠 HIDDEN PROMPTS (sprawdzone odpowiedzi):"]
    for idx, item in enumerate(items, 1):
        prompt = (item.get("prompt") or "")[:300]
        response = (item.get("approved_response") or "")[:400]
        lines.append(f"\n[Hidden {idx}]")
        lines.append(f"Prompt: {prompt}")
        lines.append(f"Odpowiedź: {response}")
    return "\n".join(lines)


def get_cached_hidden_response(
    prompt: str, intent: Optional[str] = None, min_score: int = 1
) -> Optional[str]:
    """
    Zwraca zaakceptowaną odpowiedź dla identycznego promptu (cache), bez budowania kontekstu.

    Priorytet:
    1) aktywne hidden prompts (whitelist)
    2) zagregowane wpisy spełniające min_score
    """
    prompt_norm = _normalize(prompt)

    for item in get_active_hidden_prompts(intent=intent):
        if _normalize(item.get("prompt") or "") == prompt_norm:
            return item.get("approved_response")

    for item in aggregate_hidden_prompts(intent=intent, min_score=min_score, limit=100):
        if _normalize(item.get("prompt") or "") == prompt_norm:
            return item.get("approved_response")

    # Fallback: Semantic Cache (Vector Search)
    try:
        from venom_core.core.orchestrator.constants import (
            SEMANTIC_CACHE_COLLECTION_NAME,
            SEMANTIC_CACHE_THRESHOLD,
        )
        from venom_core.memory.vector_store import VectorStore

        # Użyj singletona lub nowej instancji (VectorStore jest lekki, connection jest lazy)
        store = VectorStore(collection_name=SEMANTIC_CACHE_COLLECTION_NAME)
        results = store.search(query=prompt, limit=1)

        if results:
            best_match = results[0]
            # LanceDB zwraca _distance (cosine distance), gdzie 0 = identyczny, 1 = przeciwny.
            # Dla sentence-transformers i LanceDB, score często jest distance.
            # Ale VectorStore.search zwraca `score` jako `_distance`.
            # Zatem similarity = 1 - distance.
            # Jeśli SEMANTIC_CACHE_THRESHOLD = 0.85, to szukamy distance < 0.15.
            distance = best_match.get("score")
            # Zabezpieczenie przed None
            if distance is not None:
                similarity = 1.0 - float(distance)
                if similarity >= SEMANTIC_CACHE_THRESHOLD:
                    meta = best_match.get("metadata") or {}
                    # Sprawdź intent (opcjonalnie)
                    cached_intent = meta.get("intent")
                    if not intent or (
                        cached_intent and cached_intent.upper() == intent.upper()
                    ):
                        logger.info(
                            f"Semantic Cache HIT: similarity={similarity:.4f} for '{prompt[:50]}...'"
                        )
                        return meta.get("response")

    except Exception as exc:
        logger.warning(f"Semantic Cache lookup failed: {exc}")

    return None


def cache_hidden_prompt_semantic(
    prompt: str, response: str, intent: str = "general"
) -> None:
    """Zapisuje parę prompt-odpowiedź do Semantic Cache (Vector Store)."""
    try:
        from venom_core.core.orchestrator.constants import (
            SEMANTIC_CACHE_COLLECTION_NAME,
        )
        from venom_core.memory.vector_store import VectorStore

        store = VectorStore(collection_name=SEMANTIC_CACHE_COLLECTION_NAME)

        # Zapisujemy Prompt jako `text` (by po nim szukać embeddingiem)
        # Odpowiedź w metadata
        metadata = {
            "response": response,
            "intent": intent,
            "timestamp": datetime.now().isoformat(),
            "type": "hidden_prompt",
        }

        # Używamy prompt jako text do embeddingu
        store.upsert(
            text=prompt,
            metadata=metadata,
            chunk_text=False,  # Prompty są zwykle krótkie, nie dzielimy
        )
        logger.info(f"Zapisano do Semantic Cache: {prompt[:30]}...")

    except Exception as exc:
        logger.warning(f"Nie udało się zapisać do Semantic Cache: {exc}")
