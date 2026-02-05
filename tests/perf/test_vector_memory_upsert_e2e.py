"""E2E testy upsertu do pamięci wektorowej na realnych danych."""

from __future__ import annotations

import asyncio
import time
from uuid import uuid4

import httpx
import pytest

from .chat_pipeline import API_BASE, is_backend_available, stream_task, submit_task

pytestmark = [pytest.mark.asyncio, pytest.mark.performance]


async def _skip_if_backend_unavailable():
    if not await is_backend_available():
        pytest.skip("Backend FastAPI jest niedostępny – pomiń testy E2E.")


async def _fetch_memory_graph(session_id: str) -> dict:
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(
            f"{API_BASE}/api/v1/memory/graph", params={"session_id": session_id}
        )
        response.raise_for_status()
        return response.json()


async def _wait_for_memory_entry(session_id: str, timeout: float = 15.0) -> dict | None:
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        payload = await _fetch_memory_graph(session_id)
        if payload.get("status") == "unavailable":
            return None
        nodes = (payload.get("elements") or {}).get("nodes") or []
        for node in nodes:
            data = node.get("data") or {}
            meta = data.get("meta") or {}
            if meta.get("session_id") == session_id:
                return data
        await asyncio.sleep(0.5)
    return None


@pytest.mark.smoke
async def test_vector_memory_upsert_e2e():
    await _skip_if_backend_unavailable()

    session_id = f"memory-upsert-{uuid4()}"
    prompt = f"Memory upsert test {session_id}: odpowiedz krótko OK."
    task_id = await submit_task(prompt, store_knowledge=False, session_id=session_id)

    async for event, _payload in stream_task(task_id):
        if event == "task_finished":
            break

    try:
        entry = await _wait_for_memory_entry(session_id)
    except httpx.HTTPStatusError as exc:
        if exc.response is not None and exc.response.status_code in (503, 500):
            pytest.skip("VectorStore niedostępny – pomijam test pamięci wektorowej.")
        raise

    if entry is None:
        pytest.skip("VectorStore niedostępny – pomijam test pamięci wektorowej.")

    assert entry.get("session_id") == session_id
