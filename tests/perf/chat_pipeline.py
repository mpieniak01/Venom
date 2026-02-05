"""Helper utilities for chat latency / SSE performance tests."""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any, AsyncGenerator, Dict, List, Tuple

import httpx


def _resolve_api_base() -> str:
    env_base = (
        os.getenv("VENOM_API_BASE")
        or os.getenv("API_PROXY_TARGET")
        or os.getenv("NEXT_PUBLIC_API_BASE")
        or os.getenv("API_BASE_URL")
    )
    if env_base:
        return env_base
    return f"http://localhost:{os.getenv('APP_PORT', '8000')}"


API_BASE = _resolve_api_base()
TASKS_ENDPOINT = f"{API_BASE}/api/v1/tasks"
STREAM_TIMEOUT = float(os.getenv("VENOM_STREAM_TIMEOUT", "25"))
PIPELINE_CONCURRENCY = int(os.getenv("VENOM_PIPELINE_CONCURRENCY", "3"))
PIPELINE_BATCH_BUDGET_SECONDS = float(os.getenv("VENOM_PIPELINE_BUDGET", "6.0"))


async def submit_task(
    content: str,
    store_knowledge: bool = True,
    session_id: str | None = None,
    forced_intent: str | None = None,
    forced_tool: str | None = None,
    forced_provider: str | None = None,
) -> str:
    """Utwórz nowe zadanie i zwróć jego ID."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        payload: Dict[str, object] = {
            "content": content,
            "store_knowledge": store_knowledge,
        }
        if session_id:
            payload["session_id"] = session_id
        effective_intent = forced_intent or os.getenv("VENOM_FORCE_INTENT")
        if effective_intent:
            payload["forced_intent"] = effective_intent
        if forced_tool:
            payload["forced_tool"] = forced_tool
        if forced_provider:
            payload["forced_provider"] = forced_provider
        response = await client.post(
            TASKS_ENDPOINT,
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
        return str(data["task_id"])


async def stream_task(
    task_id: str,
    timeout: float | None = None,
) -> AsyncGenerator[Tuple[str, Dict[str, Any]], None]:
    """Strumieniuj zdarzenia SSE dla danego zadania."""
    stream_url = f"{TASKS_ENDPOINT}/{task_id}/stream"
    overall_timeout = timeout or STREAM_TIMEOUT
    timeout_cfg = httpx.Timeout(connect=5.0, read=overall_timeout, write=5.0, pool=5.0)
    start = time.perf_counter()
    async with httpx.AsyncClient(timeout=timeout_cfg) as client:
        async with client.stream("GET", stream_url) as response:
            response.raise_for_status()
            event_name: str | None = None
            data_buffer: List[str] = []
            async for line in response.aiter_lines():
                if time.perf_counter() - start > overall_timeout:
                    raise TimeoutError(
                        f"SSE przekroczyło timeout {overall_timeout}s (brak task_finished)",
                    )
                if line is None:
                    continue
                stripped = line.strip()
                if not stripped:
                    if event_name:
                        payload = (
                            json.loads("\n".join(data_buffer)) if data_buffer else {}
                        )
                        yield event_name, payload
                    event_name = None
                    data_buffer = []
                    continue
                if stripped.startswith("event:"):
                    event_name = stripped.split("event:", 1)[1].strip()
                elif stripped.startswith("data:"):
                    data_buffer.append(stripped.split("data:", 1)[1].strip())


async def measure_task_duration(
    content: str,
    forced_intent: str | None = None,
) -> Tuple[float, Dict[str, Any]]:
    """Wyślij zadanie i zwróć czas do `task_finished` wraz z payloadem."""
    task_id = await submit_task(content, forced_intent=forced_intent)
    start = time.perf_counter()
    try:
        async with asyncio.timeout(STREAM_TIMEOUT):
            async for event, payload in stream_task(task_id):
                elapsed = time.perf_counter() - start
                if event == "task_finished":
                    return elapsed, payload
    except TimeoutError as exc:
        raise TimeoutError(
            f"SSE przekroczyło timeout {STREAM_TIMEOUT}s (brak task_finished)",
        ) from exc
    raise RuntimeError("Stream zakończył się bez eventu task_finished")


async def measure_concurrent_tasks(
    concurrency: int,
    prefix: str = "Parallel perf",
    forced_intent: str | None = None,
) -> Tuple[float, List[float]]:
    """Uruchom wiele zadań równolegle i zwróć max + listę czasów."""
    tasks = [
        asyncio.create_task(
            measure_task_duration(
                f"{prefix} #{idx}",
                forced_intent=forced_intent,
            ),
        )
        for idx in range(concurrency)
    ]
    results = await asyncio.gather(*tasks)
    durations: List[float] = [duration for duration, _ in results]
    max_duration = max(durations) if durations else 0.0
    return max_duration, durations


async def is_backend_available() -> bool:
    """Sprawdź, czy backend odpowiada na /healthz."""
    healthz = f"{API_BASE}/healthz"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(healthz)
            return response.status_code == 200
    except httpx.HTTPError:
        return False
