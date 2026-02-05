"""E2E testy integralności SessionStore na realnych danych."""

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

SESSION_STORE_PATH = Path(SETTINGS.MEMORY_ROOT) / "session_store.json"


async def _skip_if_backend_unavailable():
    if not await is_backend_available():
        pytest.skip("Backend FastAPI jest niedostępny – pomiń testy E2E.")


def _load_session_store() -> dict:
    if not SESSION_STORE_PATH.exists():
        return {}
    try:
        return json.loads(SESSION_STORE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


async def _wait_for_session_history(
    session_id: str, expected_min: int, timeout: float = 10.0
) -> list:
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        data = _load_session_store()
        session = (data.get("sessions") or {}).get(session_id) or {}
        history = session.get("history") or []
        if isinstance(history, list) and len(history) >= expected_min:
            return history
        await asyncio.sleep(0.25)
    return []


@pytest.mark.smoke
async def test_session_store_integrity_e2e():
    await _skip_if_backend_unavailable()

    session_id = f"session-integrity-{uuid4()}"
    task_ids = []
    prompts = [
        f"Session integrity test {session_id} #1: OK.",
        f"Session integrity test {session_id} #2: OK.",
        f"Session integrity test {session_id} #3: OK.",
    ]

    for prompt in prompts:
        task_id = await submit_task(
            prompt, store_knowledge=False, session_id=session_id
        )
        task_ids.append(task_id)
        async for event, _payload in stream_task(task_id):
            if event == "task_finished":
                break

    history = await _wait_for_session_history(session_id, expected_min=len(prompts) * 2)
    assert history, "Brak historii w session_store.json"

    request_ids = {
        entry.get("request_id") for entry in history if isinstance(entry, dict)
    }
    for task_id in task_ids:
        assert task_id in request_ids, f"Brak wpisu historycznego dla task_id={task_id}"
