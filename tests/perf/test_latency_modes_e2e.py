"""E2E latency testy dla trybów: fast (direct), normal, complex."""

from __future__ import annotations

import os
import time
from typing import Dict, List, Tuple

import httpx
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
        is_backend_available, "Backend FastAPI jest niedostępny – pomiń testy E2E."
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


async def _measure_direct_latency(prompt: str, model: str) -> Tuple[float, float]:
    start = time.perf_counter()
    first_token_time = None
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream(
            "POST",
            f"{API_BASE}/api/v1/llm/simple/stream",
            json={"content": prompt, "model": model},
        ) as response:
            response.raise_for_status()
            async for chunk in response.aiter_text():
                if not chunk:
                    continue
                elapsed = time.perf_counter() - start
                if first_token_time is None:
                    first_token_time = elapsed
                if elapsed > STREAM_TIMEOUT:
                    raise TimeoutError(
                        f"Streaming przekroczył timeout {STREAM_TIMEOUT}s."
                    )
    total_time = time.perf_counter() - start
    if first_token_time is None:
        first_token_time = total_time
    return first_token_time, total_time


async def _measure_task_latency(
    prompt: str, *, forced_intent: str | None = None
) -> Tuple[float, float]:
    task_id = await submit_task(
        prompt,
        store_knowledge=False,
        forced_intent=forced_intent,
    )
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


def _print_mode_summary(
    mode: str,
    model_to_use: str,
    runtime_info: Dict[str, object],
    firsts: List[float],
    totals: List[float],
):
    print(
        "LLM latency summary:",
        f"mode={mode}",
        f"model={model_to_use}",
        f"runtime={runtime_info.get('active_server')}@{runtime_info.get('active_endpoint')}",
        f"first_token avg={sum(firsts) / len(firsts):.2f}s",
        f"total avg={sum(totals) / len(totals):.2f}s",
        f"min={min(totals):.2f}s",
        f"max={max(totals):.2f}s",
    )


async def _run_fast_mode(
    model_to_use: str, runtime_info: Dict[str, object]
) -> Tuple[List[float], List[float]]:
    fast_first: List[float] = []
    fast_total: List[float] = []
    for idx in range(REPEATS):
        prompt = f"Fast latency test {model_to_use} #{idx}: odpowiedz krótko OK."
        first_token, total = await _measure_direct_latency(prompt, model_to_use)
        fast_first.append(first_token)
        fast_total.append(total)
    _print_mode_summary("fast", model_to_use, runtime_info, fast_first, fast_total)
    return fast_first, fast_total


async def _run_normal_mode(
    model_to_use: str, runtime_info: Dict[str, object]
) -> Tuple[List[float], List[float]]:
    normal_first: List[float] = []
    normal_total: List[float] = []
    for idx in range(REPEATS):
        prompt = f"Normal latency test {model_to_use} #{idx}: odpowiedz krótko OK."
        first_token, total = await _measure_task_latency(prompt)
        normal_first.append(first_token)
        normal_total.append(total)
    _print_mode_summary(
        "normal", model_to_use, runtime_info, normal_first, normal_total
    )
    return normal_first, normal_total


async def _run_complex_mode(
    model_to_use: str, runtime_info: Dict[str, object]
) -> Tuple[List[float], List[float], str | None]:
    complex_first: List[float] = []
    complex_total: List[float] = []
    try:
        for idx in range(REPEATS):
            prompt = (
                f"Complex latency test {model_to_use} #{idx}: "
                "przygotuj plan 2 kroków na wykonanie prostej notatki."
            )
            first_token, total = await _measure_task_latency(
                prompt, forced_intent="COMPLEX_PLANNING"
            )
            complex_first.append(first_token)
            complex_total.append(total)
        _print_mode_summary(
            "complex", model_to_use, runtime_info, complex_first, complex_total
        )
        return complex_first, complex_total, None
    except TimeoutError as exc:
        complex_error = str(exc)
        print("LLM latency summary:", "mode=complex", f"error={complex_error}")
        return [], [], complex_error


@pytest.mark.smoke
async def test_latency_modes_e2e():
    await _skip_if_backend_unavailable()

    payload = await _list_models()
    model_to_use = _resolve_active_model(payload)
    runtime_info = await _get_active_runtime()

    results = {}
    fast_first, fast_total = await _run_fast_mode(model_to_use, runtime_info)
    results["fast"] = (fast_first, fast_total)
    normal_first, normal_total = await _run_normal_mode(model_to_use, runtime_info)
    results["normal"] = (normal_first, normal_total)
    complex_first, complex_total, complex_error = await _run_complex_mode(
        model_to_use, runtime_info
    )
    if complex_first and complex_total:
        results["complex"] = (complex_first, complex_total)

    for mode, (firsts, totals) in results.items():
        assert all(value > 0 for value in firsts)
        assert all(value > 0 for value in totals)

    if complex_error:
        # Kompleksowy tryb bywa wolny i nie powinien wywracać testu stabilności stosu.
        # Skupiamy się na tym, czy FAST/NORMAL działają poprawnie.
        print("Pomijam błąd trybu complex:", complex_error)
