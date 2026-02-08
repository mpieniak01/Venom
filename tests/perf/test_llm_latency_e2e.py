"""E2E testy latencji LLM: aktywacja modelu + pomiar odpowiedzi."""

from __future__ import annotations

import os
import time
from typing import Dict, List, Tuple

import pytest

from .chat_pipeline import API_BASE, is_backend_available, stream_task, submit_task
from .latency_api_helpers import (
    get_active_runtime,
    list_models,
    resolve_active_model,
    resolve_timeout_result,
    skip_if_backend_unavailable,
)
from .latency_helpers import (
    extract_first_token_elapsed,
    finalize_on_task_finished,
    handle_stream_timeout,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.performance]

MODEL_NAME = os.getenv("VENOM_LLM_MODEL", "gemma3")
REPEATS = int(os.getenv("VENOM_LLM_REPEATS", "2"))
STREAM_TIMEOUT = float(os.getenv("VENOM_STREAM_TIMEOUT", "60"))
STATUS_TIMEOUT = float(os.getenv("VENOM_STATUS_TIMEOUT", "20"))
STATUS_POLL_INTERVAL = float(os.getenv("VENOM_STATUS_POLL_INTERVAL", "1.0"))


async def _skip_if_backend_unavailable():
    await skip_if_backend_unavailable(
        is_backend_available, "Backend FastAPI jest niedostępny – pomiń testy E2E LLM."
    )


async def _list_models() -> Dict[str, object]:
    return await list_models(API_BASE)


async def _get_active_runtime() -> Dict[str, object]:
    return await get_active_runtime(API_BASE)


async def _resolve_timeout_result(
    task_id: str, start: float, first_token_time: float | None, event: str
) -> Tuple[float, float]:
    return await resolve_timeout_result(
        task_id,
        start=start,
        first_token_time=first_token_time,
        event=event,
        api_base=API_BASE,
        status_timeout=STATUS_TIMEOUT,
        status_poll_interval=STATUS_POLL_INTERVAL,
        stream_timeout=STREAM_TIMEOUT,
    )


async def _measure_latency(prompt: str) -> Tuple[float, float]:
    task_id = await submit_task(prompt, store_knowledge=False)
    start = time.perf_counter()
    first_token_time = None
    async for event, payload in stream_task(task_id):
        elapsed = time.perf_counter() - start
        first_token_time = extract_first_token_elapsed(
            event, payload, elapsed, first_token_time
        )
        if event == "task_finished":
            return finalize_on_task_finished(first_token_time, elapsed)
        timeout_result = await handle_stream_timeout(
            elapsed,
            STREAM_TIMEOUT,
            _resolve_timeout_result,
            task_id,
            start,
            first_token_time,
            event,
        )
        if timeout_result is not None:
            return timeout_result
    raise RuntimeError("Stream zakończył się bez eventu task_finished")


def _resolve_active_model(payload: Dict[str, object]) -> str:
    return resolve_active_model(payload, MODEL_NAME)


def _print_latency_summary(
    model_to_use: str,
    runtime_info: Dict[str, object],
    first_tokens: List[float],
    totals: List[float],
):
    print(
        "LLM latency summary:",
        f"model={model_to_use}",
        f"runtime={runtime_info.get('active_server')}@{runtime_info.get('active_endpoint')}",
        f"first_token avg={sum(first_tokens) / len(first_tokens):.2f}s",
        f"total avg={sum(totals) / len(totals):.2f}s",
        f"min={min(totals):.2f}s",
        f"max={max(totals):.2f}s",
    )


async def _collect_latency_samples(
    model_to_use: str,
) -> Tuple[List[float], List[float]]:
    first_tokens: List[float] = []
    totals: List[float] = []
    for idx in range(REPEATS):
        prompt = f"Latency test {model_to_use} #{idx}: odpowiedz krótko OK."
        first_token, total = await _measure_latency(prompt)
        first_tokens.append(first_token)
        totals.append(total)
    return first_tokens, totals


@pytest.mark.smoke
async def test_llm_latency_e2e():
    await _skip_if_backend_unavailable()

    payload = await _list_models()
    model_to_use = _resolve_active_model(payload)
    runtime_info = await _get_active_runtime()
    first_tokens, totals = await _collect_latency_samples(model_to_use)

    assert all(value > 0 for value in first_tokens)
    assert all(value > 0 for value in totals)
    _print_latency_summary(model_to_use, runtime_info, first_tokens, totals)
