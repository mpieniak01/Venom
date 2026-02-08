"""Wspólne scenariusze E2E dla testów latencji."""

from __future__ import annotations

import os
import time
from typing import Dict, List, Tuple

import httpx

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

MODEL_NAME = os.getenv("VENOM_LLM_MODEL", "gemma3")
REPEATS = int(os.getenv("VENOM_LLM_REPEATS", "2"))
STREAM_TIMEOUT = float(os.getenv("VENOM_STREAM_TIMEOUT", "60"))
STATUS_TIMEOUT = float(os.getenv("VENOM_STATUS_TIMEOUT", "20"))
STATUS_POLL_INTERVAL = float(os.getenv("VENOM_STATUS_POLL_INTERVAL", "1.0"))


async def _skip_if_backend_unavailable(message: str) -> None:
    await skip_if_backend_unavailable(is_backend_available, message)


async def _resolve_timeout_for_stream(
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


async def _measure_task_latency(
    prompt: str, *, forced_intent: str | None = None
) -> Tuple[float, float]:
    task_id = await submit_task(
        prompt, store_knowledge=False, forced_intent=forced_intent
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
            _resolve_timeout_for_stream,
            task_id,
            start,
            first_token_time,
            event,
        )
        if timeout_result is not None:
            return timeout_result
    raise RuntimeError("Stream zakończył się bez eventu task_finished")


def _print_latency_summary(
    model_to_use: str,
    runtime_info: Dict[str, object],
    first_tokens: List[float],
    totals: List[float],
) -> None:
    print(
        "LLM latency summary:",
        f"model={model_to_use}",
        f"runtime={runtime_info.get('active_server')}@{runtime_info.get('active_endpoint')}",
        f"first_token avg={sum(first_tokens) / len(first_tokens):.2f}s",
        f"total avg={sum(totals) / len(totals):.2f}s",
        f"min={min(totals):.2f}s",
        f"max={max(totals):.2f}s",
    )


def _print_mode_summary(
    mode: str,
    model_to_use: str,
    runtime_info: Dict[str, object],
    firsts: List[float],
    totals: List[float],
) -> None:
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


async def run_llm_latency_e2e() -> None:
    await _skip_if_backend_unavailable(
        "Backend FastAPI jest niedostępny – pomiń testy E2E LLM."
    )

    payload = await list_models(API_BASE)
    model_to_use = resolve_active_model(payload, MODEL_NAME)
    runtime_info = await get_active_runtime(API_BASE)

    first_tokens: List[float] = []
    totals: List[float] = []
    for idx in range(REPEATS):
        prompt = f"Latency test {model_to_use} #{idx}: odpowiedz krótko OK."
        first_token, total = await _measure_task_latency(prompt)
        first_tokens.append(first_token)
        totals.append(total)

    assert all(value > 0 for value in first_tokens)
    assert all(value > 0 for value in totals)
    _print_latency_summary(model_to_use, runtime_info, first_tokens, totals)


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


async def run_latency_modes_e2e() -> None:
    await _skip_if_backend_unavailable(
        "Backend FastAPI jest niedostępny – pomiń testy E2E."
    )

    payload = await list_models(API_BASE)
    model_to_use = resolve_active_model(payload, MODEL_NAME)
    runtime_info = await get_active_runtime(API_BASE)

    results: dict[str, tuple[list[float], list[float]]] = {}

    fast_first: List[float] = []
    fast_total: List[float] = []
    for idx in range(REPEATS):
        prompt = f"Fast latency test {model_to_use} #{idx}: odpowiedz krótko OK."
        first_token, total = await _measure_direct_latency(prompt, model_to_use)
        fast_first.append(first_token)
        fast_total.append(total)
    _print_mode_summary("fast", model_to_use, runtime_info, fast_first, fast_total)
    results["fast"] = (fast_first, fast_total)

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
    results["normal"] = (normal_first, normal_total)

    complex_error: str | None = None
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
        results["complex"] = (complex_first, complex_total)
    except TimeoutError as exc:
        complex_error = str(exc)
        print("LLM latency summary:", "mode=complex", f"error={complex_error}")

    for mode, (firsts, totals) in results.items():
        assert all(value > 0 for value in firsts)
        assert all(value > 0 for value in totals)

    if complex_error:
        print("Pomijam błąd trybu complex:", complex_error)
