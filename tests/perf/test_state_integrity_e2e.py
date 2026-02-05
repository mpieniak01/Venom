"""E2E testy integralności StateManager na realnych danych."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from uuid import uuid4

import pytest

from venom_core.config import SETTINGS

from .chat_pipeline import is_backend_available, stream_task, submit_task

pytestmark = [pytest.mark.asyncio, pytest.mark.performance]

STATE_PATH = Path(getattr(SETTINGS, "STATE_FILE_PATH", "data/memory/state_dump.json"))


async def _skip_if_backend_unavailable():
    if not await is_backend_available():
        pytest.skip("Backend FastAPI jest niedostępny – pomiń testy E2E.")


def _load_state_file() -> dict:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


async def _wait_for_task_in_state(task_id: str, timeout: float = 10.0) -> dict | None:
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        data = _load_state_file()
        for task in data.get("tasks", []) or []:
            if str(task.get("id")) == task_id:
                return task
        await asyncio.sleep(0.25)
    return None


@pytest.mark.smoke
async def test_state_integrity_e2e():
    await _skip_if_backend_unavailable()

    session_id = f"state-integrity-{uuid4()}"
    prompt = f"State integrity test {session_id}: odpowiedz krótko OK."
    task_id = await submit_task(prompt, store_knowledge=False, session_id=session_id)

    async for event, _payload in stream_task(task_id):
        if event == "task_finished":
            break

    task = await _wait_for_task_in_state(task_id)
    assert task is not None, "Brak zadania w state_dump.json"
    assert task.get("status") in {"COMPLETED", "FAILED"}
    assert task.get("result") is not None
    logs = task.get("logs") or []
    assert isinstance(logs, list) and len(logs) > 0
    context = task.get("context_history") or {}
    assert isinstance(context, dict)
