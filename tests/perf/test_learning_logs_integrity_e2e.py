"""E2E testy integralności learning logs na realnych danych."""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from venom_core.core.orchestrator.constants import LEARNING_LOG_PATH

from .chat_pipeline import is_backend_available, stream_task, submit_task

pytestmark = [pytest.mark.asyncio, pytest.mark.performance]
MAX_RETRIES = int(os.getenv("VENOM_E2E_RETRIES", "4"))


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


async def _submit_and_wait_finished(prompt: str, session_id: str) -> str:
    """Tworzy task i czeka na `task_finished` z retry przy błędach transportu."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            task_id = await submit_task(
                prompt, store_knowledge=True, session_id=session_id
            )
            async for event, _payload in stream_task(task_id):
                if event == "task_finished":
                    return task_id
            raise RuntimeError("Stream zakończył się bez eventu task_finished")
        except (
            httpx.ReadError,
            httpx.ReadTimeout,
            httpx.RemoteProtocolError,
            httpx.ConnectError,
            TimeoutError,
        ) as exc:
            if attempt >= MAX_RETRIES:
                pytest.skip(
                    "Backend/SSE niestabilny podczas learning_logs E2E "
                    f"po {MAX_RETRIES} próbach: {exc}"
                )
            await asyncio.sleep(min(2 ** (attempt - 1), 5))


@pytest.mark.smoke
async def test_learning_logs_integrity_e2e():
    await _skip_if_backend_unavailable()

    session_id = f"learning-integrity-{uuid4()}"
    task_ids: list[str] = []
    for idx in range(2):
        prompt = f"Learning log test {session_id} #{idx}: odpowiedz krótko OK."
        task_id = await _submit_and_wait_finished(prompt, session_id)
        task_ids.append(task_id)

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
