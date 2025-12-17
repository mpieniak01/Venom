"""Testy wydajnościowe backendowego pipeline'u chatu."""

from __future__ import annotations

import os

import pytest

from .chat_pipeline import (
    PIPELINE_BATCH_BUDGET_SECONDS,
    PIPELINE_CONCURRENCY,
    STREAM_TIMEOUT,
    is_backend_available,
    measure_concurrent_tasks,
    measure_task_duration,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.performance]


async def _skip_if_backend_unavailable():
    if not await is_backend_available():
        pytest.skip("Backend FastAPI jest niedostępny – pomiń testy wydajnościowe.")


@pytest.mark.smoke
async def test_chat_pipeline_smoke_latency():
    """Powinienem otrzymać task_finished w limicie STREAM_TIMEOUT."""
    await _skip_if_backend_unavailable()
    duration, payload = await measure_task_duration(
        f"Smoke latency test {os.getpid()}",
    )
    assert duration > 0, "Zadanie powinno zwrócić dodatni czas"
    timeout_msg = (
        f"Czas {duration:.2f}s przekroczył STREAM_TIMEOUT {STREAM_TIMEOUT:.2f}s"
    )
    assert duration <= STREAM_TIMEOUT, timeout_msg
    assert payload.get("status") in {"COMPLETED", "FAILED"}


async def test_chat_pipeline_parallel_batch():
    """Kilka zadań równolegle nie powinno przekroczyć budżetu."""
    await _skip_if_backend_unavailable()
    max_duration, durations = await measure_concurrent_tasks(
        PIPELINE_CONCURRENCY,
        prefix=f"Parallel perf PID {os.getpid()}",
    )
    assert max_duration <= PIPELINE_BATCH_BUDGET_SECONDS, (
        f"Maksymalny czas {max_duration:.2f}s przekroczył budżet "
        f"{PIPELINE_BATCH_BUDGET_SECONDS:.2f}s dla równoległej partii. "
        f"Czasy zadań: {', '.join(f'{d:.2f}s' for d in durations)}"
    )
