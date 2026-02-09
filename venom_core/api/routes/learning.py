"""Moduł: routes/learning - Endpointy API dla logów nauki."""

import importlib
import json
from pathlib import Path
from typing import Any, List, Optional

from fastapi import APIRouter

from venom_core.core.hidden_prompts import (
    aggregate_hidden_prompts,
    get_active_hidden_prompts,
    set_active_hidden_prompt,
)
from venom_core.core.learning_log import ensure_learning_log_boot_id

aiofiles: Any = None
try:  # pragma: no cover - zależne od środowiska
    aiofiles = importlib.import_module("aiofiles")
except Exception:  # pragma: no cover
    aiofiles = None

router = APIRouter(prefix="/api/v1/learning", tags=["learning"])

LEARNING_READ_RESPONSES: dict[int | str, dict[str, Any]] = {
    500: {"description": "Błąd wewnętrzny podczas pobierania danych learning"},
}
LEARNING_TOGGLE_RESPONSES: dict[int | str, dict[str, Any]] = {
    500: {"description": "Błąd wewnętrzny podczas aktualizacji danych learning"},
}


def set_dependencies(orchestrator=None, state_manager=None, _request_tracer=None):
    """Ustawia zależności (używane głównie w testach)."""
    from venom_core.api import dependencies as api_deps

    if orchestrator:
        api_deps.set_orchestrator(orchestrator)
    if state_manager:
        api_deps.set_state_manager(state_manager)


LEARNING_LOG_PATH = Path("./data/learning/requests.jsonl")


def _normalize_limit(limit: int, *, minimum: int = 1, maximum: int = 500) -> int:
    if limit < minimum:
        return minimum
    if limit > maximum:
        return maximum
    return limit


def _parse_learning_entry(line: str) -> dict[str, Any] | None:
    if not line.strip():
        return None
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None


def _matches_filters(
    entry: dict[str, Any],
    *,
    intent: Optional[str],
    success: Optional[bool],
    tag: Optional[str],
) -> bool:
    if intent and str(entry.get("intent") or "").upper() != intent.upper():
        return False
    if success is not None and entry.get("success") is not success:
        return False
    if not tag:
        return True
    tags = entry.get("tags") or []
    return isinstance(tags, list) and tag in tags


@router.get("/logs", responses=LEARNING_READ_RESPONSES)
async def get_learning_logs(
    limit: int = 50,
    intent: Optional[str] = None,
    success: Optional[bool] = None,
    tag: Optional[str] = None,
) -> dict:
    """Zwraca ostatnie wpisy procesu nauki (JSONL) z opcjonalnym filtrowaniem."""
    ensure_learning_log_boot_id()
    limit = _normalize_limit(limit)

    if not LEARNING_LOG_PATH.exists():
        return {"count": 0, "items": []}
    if aiofiles is None:
        return {"count": 0, "items": []}

    items: List[dict] = []
    try:
        async with aiofiles.open(LEARNING_LOG_PATH, "r", encoding="utf-8") as handle:
            lines = await handle.readlines()
        for line in reversed(lines):
            entry = _parse_learning_entry(line)
            if entry is None:
                continue
            if not _matches_filters(entry, intent=intent, success=success, tag=tag):
                continue
            items.append(entry)
            if len(items) >= limit:
                break
    except Exception:
        return {"count": 0, "items": []}

    return {"count": len(items), "items": items}


@router.get("/hidden-prompts", responses=LEARNING_READ_RESPONSES)
def get_hidden_prompts(
    limit: int = 50,
    intent: Optional[str] = None,
    min_score: int = 1,
) -> dict:
    """Zwraca zagregowane hidden prompts (deduplikacja + score)."""
    limit = _normalize_limit(limit)
    if min_score < 1:
        min_score = 1

    items = aggregate_hidden_prompts(limit=limit, intent=intent, min_score=min_score)
    return {"count": len(items), "items": items}


@router.get("/hidden-prompts/active", responses=LEARNING_READ_RESPONSES)
def get_active_hidden_prompts_endpoint(intent: Optional[str] = None) -> dict:
    """Zwraca aktywne hidden prompts."""
    items = get_active_hidden_prompts(intent=intent)
    return {"count": len(items), "items": items}


@router.post("/hidden-prompts/active", responses=LEARNING_TOGGLE_RESPONSES)
def set_active_hidden_prompt_endpoint(payload: dict) -> dict:
    """Aktywuje lub wyłącza hidden prompt."""
    active = bool(payload.get("active", True))
    actor = payload.get("actor")
    entry = {
        "intent": payload.get("intent"),
        "prompt": payload.get("prompt"),
        "approved_response": payload.get("approved_response"),
        "prompt_hash": payload.get("prompt_hash"),
    }
    items = set_active_hidden_prompt(entry, active=active, actor=actor)
    return {"count": len(items), "items": items}
