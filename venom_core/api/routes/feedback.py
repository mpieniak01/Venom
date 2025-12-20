"""Moduł: routes/feedback - Endpointy API dla feedbacku użytkownika."""

import json
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Optional
from uuid import UUID

import aiofiles
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from venom_core.core import metrics as metrics_module
from venom_core.core.models import TaskRequest
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["feedback"])

FEEDBACK_LOG_PATH = Path("./data/feedback/feedback.jsonl")
HIDDEN_PROMPT_LOG_PATH = Path("./data/learning/hidden_prompts.jsonl")

_orchestrator = None
_state_manager = None


def set_dependencies(orchestrator, state_manager):
    """Ustaw zależności dla routera."""
    global _orchestrator, _state_manager
    _orchestrator = orchestrator
    _state_manager = state_manager


class FeedbackRequest(BaseModel):
    task_id: UUID
    rating: str = Field(description="up/down")
    comment: Optional[str] = None


class FeedbackResponse(BaseModel):
    status: str
    feedback_saved: bool
    follow_up_task_id: Optional[str] = None


@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(payload: FeedbackRequest):
    """Zapisuje feedback użytkownika i opcjonalnie uruchamia rundę doprecyzowania."""
    if payload.rating not in ("up", "down"):
        raise HTTPException(status_code=400, detail="rating musi być 'up' albo 'down'")
    if payload.rating == "down" and not (payload.comment or "").strip():
        raise HTTPException(status_code=400, detail="comment wymagany dla oceny 'down'")

    if _state_manager is None:
        raise HTTPException(status_code=503, detail="StateManager nie jest dostępny")

    task = _state_manager.get_task(payload.task_id)
    if task is None:
        raise HTTPException(
            status_code=404, detail=f"Zadanie {payload.task_id} nie istnieje"
        )

    context = getattr(task, "context_history", {}) or {}
    intent_debug = context.get("intent_debug") or {}
    tool_requirement = context.get("tool_requirement") or {}
    prompt = getattr(task, "content", "") or ""
    result = getattr(task, "result", "") or ""

    entry = {
        "task_id": str(payload.task_id),
        "timestamp": datetime.now().isoformat(),
        "rating": payload.rating,
        "comment": payload.comment,
        "prompt": prompt,
        "result": result,
        "intent": intent_debug.get("intent") or tool_requirement.get("intent"),
        "tool_required": tool_requirement.get("required"),
    }

    try:
        FEEDBACK_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(FEEDBACK_LOG_PATH, "a", encoding="utf-8") as handle:
            await handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("Nie udało się zapisać feedbacku: %s", exc)
        raise HTTPException(status_code=500, detail="Nie udało się zapisać feedbacku")

    collector = metrics_module.metrics_collector
    if collector:
        if payload.rating == "up":
            collector.increment_feedback_up()
        else:
            collector.increment_feedback_down()

    follow_up_task_id = None
    if payload.rating == "down" and _orchestrator is not None:
        refinement = payload.comment.strip()
        follow_up_prompt = (
            "Poprzednia odpowiedź była niepoprawna lub nie spełniła celu.\n"
            f"Uwagi użytkownika: {refinement}\n\n"
            "Popraw odpowiedź i doprecyzuj wynik."
        )
        follow_up_request = TaskRequest(
            content=f"{prompt}\n\n---\n\n{follow_up_prompt}",
            store_knowledge=True,
        )
        try:
            response = await _orchestrator.submit_task(follow_up_request)
            follow_up_task_id = str(response.task_id)
        except Exception as exc:
            logger.warning("Nie udało się uruchomić rundy doprecyzowania: %s", exc)
    elif payload.rating == "up":
        prompt_hash = sha256(
            f"{entry.get('intent') or ''}:{prompt}".encode("utf-8")
        ).hexdigest()
        hidden_prompt_entry = {
            "task_id": str(payload.task_id),
            "timestamp": datetime.now().isoformat(),
            "intent": entry.get("intent"),
            "prompt": prompt,
            "approved_response": result,
            "prompt_hash": prompt_hash,
            "note": "Ukryty prompt może zostać utworzony na podstawie tej pary.",
        }
        try:
            HIDDEN_PROMPT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            async with aiofiles.open(
                HIDDEN_PROMPT_LOG_PATH, "a", encoding="utf-8"
            ) as handle:
                await handle.write(
                    json.dumps(hidden_prompt_entry, ensure_ascii=False) + "\n"
                )
        except Exception as exc:
            logger.warning("Nie udało się zapisać hidden prompt: %s", exc)

    return FeedbackResponse(
        status="ok",
        feedback_saved=True,
        follow_up_task_id=follow_up_task_id,
    )


@router.get("/feedback/logs")
async def get_feedback_logs(limit: int = 50, rating: Optional[str] = None) -> dict:
    """Zwraca ostatnie wpisy feedbacku użytkownika."""
    if limit < 1:
        limit = 1
    if limit > 500:
        limit = 500

    if rating and rating not in ("up", "down"):
        raise HTTPException(status_code=400, detail="rating musi być 'up' albo 'down'")

    if not FEEDBACK_LOG_PATH.exists():
        return {"count": 0, "items": []}

    items = []
    try:
        async with aiofiles.open(FEEDBACK_LOG_PATH, "r", encoding="utf-8") as handle:
            lines = await handle.readlines()
        for line in reversed(lines):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rating and entry.get("rating") != rating:
                continue
            items.append(entry)
            if len(items) >= limit:
                break
    except Exception:
        return {"count": 0, "items": []}

    return {"count": len(items), "items": list(reversed(items))}
