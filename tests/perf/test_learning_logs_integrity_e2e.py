"""E2E testy integralności learning logs na realnych danych."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from uuid import uuid4

import pytest

from venom_core.core.orchestrator.constants import LEARNING_LOG_PATH

from .chat_pipeline import is_backend_available, stream_task, submit_task

pytestmark = [pytest.mark.asyncio, pytest.mark.performance]


async def _skip_if_backend_unavailable():
    if not await is_backend_available():
        pytest.skip("Backend FastAPI jest niedostępny – pomiń testy E2E.")


def _read_learning_log() -> list[dict]:
    path = Path(LEARNING_LOG_PATH)
    if not path.exists():
        return []
    entries: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entries.append(json.loads(line))
        except Exception:
            continue
    return entries


async def _wait_for_log_entries(
    task_ids: set[str], timeout: float = 10.0
) -> list[dict]:
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        entries = _read_learning_log()
        found = {str(entry.get("task_id")) for entry in entries if entry.get("task_id")}
        if task_ids.issubset(found):
            return entries
        await asyncio.sleep(0.25)
    return _read_learning_log()


@pytest.mark.smoke
async def test_learning_logs_integrity_e2e():
    await _skip_if_backend_unavailable()

    session_id = f"learning-integrity-{uuid4()}"
    task_ids: list[str] = []
    for idx in range(2):
        prompt = f"Learning log test {session_id} #{idx}: odpowiedz krótko OK."
        task_id = await submit_task(prompt, store_knowledge=True, session_id=session_id)
        task_ids.append(task_id)
        async for event, _payload in stream_task(task_id):
            if event == "task_finished":
                break

    entries = await _wait_for_log_entries(set(task_ids))
    entries_by_task = {}
    for entry in entries:
        tid = str(entry.get("task_id") or "")
        if tid in task_ids:
            entries_by_task.setdefault(tid, 0)
            entries_by_task[tid] += 1

    for task_id in task_ids:
        assert entries_by_task.get(task_id, 0) == 1, (
            f"Niepoprawna liczba wpisów dla task_id={task_id} "
            f"(znaleziono {entries_by_task.get(task_id, 0)})"
        )
