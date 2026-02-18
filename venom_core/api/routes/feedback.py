"""Moduł: routes/feedback - Endpointy API dla feedbacku użytkownika."""

import json
from hashlib import sha256
from pathlib import Path
from typing import Optional
from uuid import UUID

import aiofiles
from fastapi import APIRouter, HTTPException

from venom_core.api.schemas.feedback import (
    FeedbackLogsResponse,
    FeedbackRequest,
    FeedbackResponse,
)
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


def _clamp_feedback_limit(limit: int) -> int:
    if limit < 1:
        return 1
    if limit > 500:
        return 500
    return limit


def _validate_feedback_rating(rating: Optional[str]) -> None:
    if rating and rating not in ("up", "down"):
        raise HTTPException(status_code=400, detail="rating musi być 'up' albo 'down'")


def _parse_feedback_line(line: str) -> Optional[dict]:
    if not line.strip():
        return None
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None


def _matches_feedback_rating(entry: dict, rating: Optional[str]) -> bool:
    if rating is None:
        return True
    return entry.get("rating") == rating


def _validate_feedback_payload(payload: FeedbackRequest) -> str:
    if payload.rating not in ("up", "down"):
        raise HTTPException(status_code=400, detail="rating musi być 'up' albo 'down'")
    comment = payload.comment or ""
    if payload.rating == "down" and not comment.strip():
        raise HTTPException(status_code=400, detail="comment wymagany dla oceny 'down'")
    return comment


def _extract_result_from_trace(trace) -> str:
    if not trace:
        return ""
    for step in reversed(trace.steps):
        if (
            step.component != "SimpleMode"
            or step.action != "response"
            or not step.details
        ):
            continue
        try:
            details_json = json.loads(step.details)
            return details_json.get("response", "")
        except Exception as exc:
            logger.debug("Nieudane parsowanie JSON w kroku feedbacku: %s", exc)
    return ""


def _resolve_feedback_context(
    task_id: UUID, state_manager
) -> tuple[str, str, Optional[str], Optional[bool]]:
    prompt = ""
    result = ""
    intent = None
    tool_required = None
    task = state_manager.get_task(task_id)
    if task:
        context = getattr(task, "context_history", {}) or {}
        intent_debug = context.get("intent_debug") or {}
        tool_requirement = context.get("tool_requirement") or {}
        prompt = getattr(task, "content", "") or ""
        result = getattr(task, "result", "") or ""
        intent = intent_debug.get("intent") or tool_requirement.get("intent")
        tool_required = tool_requirement.get("required")
        return prompt, result, intent, tool_required

    if not _request_tracer:
        raise HTTPException(status_code=404, detail=f"Zadanie {task_id} nie istnieje")

    trace = _request_tracer.get_trace(task_id)
    if not trace:
        raise HTTPException(status_code=404, detail=f"Zadanie {task_id} nie istnieje")
    return trace.prompt, _extract_result_from_trace(trace), intent, tool_required


async def _save_jsonl_entry(path: Path, entry: dict, error_message: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(path, "a", encoding="utf-8") as handle:
            await handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("%s: %s", error_message, exc)
        raise


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
    comment = _validate_feedback_payload(payload)

    if _state_manager is None:
        raise HTTPException(status_code=503, detail="StateManager nie jest dostępny")

    assert _state_manager is not None
    prompt, result, intent, tool_required = _resolve_feedback_context(
        payload.task_id, _state_manager
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
        await _save_jsonl_entry(
            FEEDBACK_LOG_PATH, entry, "Nie udało się zapisać feedbacku"
        )
    except Exception:
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
        follow_up_prompt = (
            "Poprzednia odpowiedź była niepoprawna lub nie spełniła celu.\n"
            f"Uwagi użytkownika: {comment.strip()}\n\n"
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
            await _save_jsonl_entry(
                HIDDEN_PROMPT_LOG_PATH,
                hidden_prompt_entry,
                "Nie udało się zapisać hidden prompt",
            )
        except Exception as exc:
            logger.warning("%s", exc)

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
async def get_feedback_logs(
    limit: int = 50, rating: Optional[str] = None
) -> FeedbackLogsResponse:
    """Zwraca ostatnie wpisy feedbacku użytkownika."""
    limit = _clamp_feedback_limit(limit)
    _validate_feedback_rating(rating)

    if not FEEDBACK_LOG_PATH.exists():
        return FeedbackLogsResponse(count=0, items=[])

    items = []
    try:
        async with aiofiles.open(FEEDBACK_LOG_PATH, "r", encoding="utf-8") as handle:
            lines = await handle.readlines()
        for line in reversed(lines):
            entry = _parse_feedback_line(line)
            if entry is None:
                continue
            if not _matches_feedback_rating(entry, rating):
                continue
            items.append(entry)
            if len(items) >= limit:
                break
    except Exception:
        return FeedbackLogsResponse(count=0, items=[])

    return FeedbackLogsResponse(count=len(items), items=items)
