"""Event and tracing helpers for Orchestrator."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Optional
from uuid import UUID

from venom_core.utils.helpers import get_utc_now_iso
from venom_core.utils.logger import get_logger

if TYPE_CHECKING:
    from .orchestrator_core import Orchestrator

logger = get_logger(__name__)


async def broadcast_event(
    orch: "Orchestrator",
    event_type: str,
    message: str,
    agent: Optional[str] = None,
    data: Optional[dict[str, Any]] = None,
) -> None:
    await orch.event_client.broadcast(
        event_type=event_type, message=message, agent=agent, data=data
    )


def trace_llm_start(orch: "Orchestrator", task_id: UUID, intent: str) -> None:
    if not orch.request_tracer:
        return
    orch.request_tracer.add_step(
        task_id,
        "LLM",
        "start",
        status="ok",
        details=f"intent={intent}",
    )


async def trace_step_async(
    orch: "Orchestrator", task_id: UUID, actor: str, action: str, **kwargs
) -> None:
    await asyncio.sleep(0)
    if not orch.request_tracer:
        return
    try:
        orch.request_tracer.add_step(task_id, actor, action, **kwargs)
    except Exception:  # pragma: no cover - log only
        logger.debug("Tracer step failed")


def build_error_envelope(
    *,
    error_code: str,
    error_message: str,
    error_details: Optional[dict] = None,
    stage: Optional[str] = None,
    retryable: bool = False,
    error_class: Optional[str] = None,
) -> dict:
    return {
        "error_code": error_code,
        "error_class": error_class or error_code,
        "error_message": error_message,
        "error_details": error_details or {},
        "stage": stage,
        "retryable": retryable,
    }


def set_runtime_error(orch: "Orchestrator", task_id: UUID, envelope: dict) -> None:
    orch.state_manager.update_context(
        task_id,
        {
            "llm_runtime": {
                "status": "error",
                "error": envelope,
                "last_error_at": get_utc_now_iso(),
            }
        },
    )
    if orch.request_tracer:
        orch.request_tracer.set_error_metadata(task_id, envelope)
