"""Moduł: routes/feedback - Endpointy API dla feedbacku użytkownika."""

import json
from hashlib import sha256
from pathlib import Path
from typing import Optional
from uuid import UUID

import aiofiles
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from venom_core.core import metrics as metrics_module
from venom_core.core.models import TaskRequest
from venom_core.utils.helpers import get_utc_now_iso
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["feedback"])

FEEDBACK_LOG_PATH = Path("./data/feedback/feedback.jsonl")
HIDDEN_PROMPT_LOG_PATH = Path("./data/learning/hidden_prompts.jsonl")

_orchestrator = None
_state_manager = None
_request_tracer = None


def set_dependencies(orchestrator, state_manager, request_tracer=None):
    """Ustaw zależności dla routera."""
    global _orchestrator, _state_manager, _request_tracer
    _orchestrator = orchestrator
    _state_manager = state_manager
    _request_tracer = request_tracer


class FeedbackRequest(BaseModel):
    task_id: UUID
    rating: str = Field(description="up/down")
    comment: Optional[str] = None


class FeedbackResponse(BaseModel):
    status: str
    feedback_saved: bool
    follow_up_task_id: Optional[str] = None


@router.post(
    "/feedback",
    response_model=FeedbackResponse,
    responses={
        400: {"description": "Nieprawidłowy rating lub brak komentarza dla oceny down"},
        503: {"description": "StateManager nie jest dostępny"},
        404: {"description": "Zadanie nie istnieje"},
        500: {"description": "Błąd wewnętrzny podczas zapisu feedbacku"},
    },
)
async def submit_feedback(payload: FeedbackRequest):
    """Zapisuje feedback użytkownika i opcjonalnie uruchamia rundę doprecyzowania."""
    if payload.rating not in ("up", "down"):
        raise HTTPException(status_code=400, detail="rating musi być 'up' albo 'down'")
    comment = payload.comment or ""
    if payload.rating == "down" and not comment.strip():
        raise HTTPException(status_code=400, detail="comment wymagany dla oceny 'down'")

    if _state_manager is None:
        raise HTTPException(status_code=503, detail="StateManager nie jest dostępny")

    prompt = ""
    result = ""
    intent = None
    tool_required = None

    task = _state_manager.get_task(payload.task_id)
    if task:
        context = getattr(task, "context_history", {}) or {}
        intent_debug = context.get("intent_debug") or {}
        tool_requirement = context.get("tool_requirement") or {}
        prompt = getattr(task, "content", "") or ""
        result = getattr(task, "result", "") or ""
        intent = intent_debug.get("intent") or tool_requirement.get("intent")
        tool_required = tool_requirement.get("required")
    elif _request_tracer:
        # Fallback do tracera (SimpleMode)
        trace = _request_tracer.get_trace(payload.task_id)
        if trace:
            prompt = trace.prompt
            # Spróbuj wyciągnąć odpowiedź z kroków
            for step in reversed(trace.steps):
                if (
                    step.component == "SimpleMode"
                    and step.action == "response"
                    and step.details
                ):
                    try:
                        details_json = json.loads(step.details)
                        result = details_json.get("response", "")
                        break
                    except Exception as exc:
                        # Ignorujemy błędy parsowania JSON - przechodzimy do kolejnego kroku
                        logger.debug(
                            "Nieudane parsowanie JSON w kroku feedbacku: %s",
                            exc,
                        )
        else:
            raise HTTPException(
                status_code=404, detail=f"Zadanie {payload.task_id} nie istnieje"
            )
    else:
        raise HTTPException(
            status_code=404, detail=f"Zadanie {payload.task_id} nie istnieje"
        )

    entry = {
        "task_id": str(payload.task_id),
        "timestamp": get_utc_now_iso(),
        "rating": payload.rating,
        "comment": payload.comment,
        "prompt": prompt,
        "result": result,
        "intent": intent,
        "tool_required": tool_required,
    }

    try:
        FEEDBACK_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(FEEDBACK_LOG_PATH, "a", encoding="utf-8") as handle:
            await handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("Nie udało się zapisać feedbacku: %s", exc)
        raise HTTPException(status_code=500, detail="Nie udało się zapisać feedbacku")

    if _request_tracer:
        _request_tracer.set_feedback(payload.task_id, entry)

    collector = metrics_module.metrics_collector
    if collector:
        if payload.rating == "up":
            collector.increment_feedback_up()
        else:
            collector.increment_feedback_down()

    follow_up_task_id = None
    if payload.rating == "down" and _orchestrator is not None:
        refinement = comment.strip()
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
            "timestamp": get_utc_now_iso(),
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


@router.get(
    "/feedback/logs",
    responses={
        400: {"description": "Nieprawidłowa wartość parametru rating"},
    },
)
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

    return {"count": len(items), "items": items}
