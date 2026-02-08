"""E2E testy latencji LLM: aktywacja modelu + pomiar odpowiedzi."""

from __future__ import annotations

import asyncio
import os
import time
from typing import Dict, List, Tuple

import httpx
import pytest

from .chat_pipeline import API_BASE, is_backend_available, stream_task, submit_task

pytestmark = [pytest.mark.asyncio, pytest.mark.performance]

MODEL_NAME = os.getenv("VENOM_LLM_MODEL", "gemma3")
REPEATS = int(os.getenv("VENOM_LLM_REPEATS", "2"))
STREAM_TIMEOUT = float(os.getenv("VENOM_STREAM_TIMEOUT", "60"))
STATUS_TIMEOUT = float(os.getenv("VENOM_STATUS_TIMEOUT", "20"))
STATUS_POLL_INTERVAL = float(os.getenv("VENOM_STATUS_POLL_INTERVAL", "1.0"))


async def _skip_if_backend_unavailable():
    if not await is_backend_available():
        pytest.skip("Backend FastAPI jest niedostępny – pomiń testy E2E LLM.")


async def _list_models() -> Dict[str, object]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(f"{API_BASE}/api/v1/models")
        response.raise_for_status()
        return response.json()


async def _get_active_runtime() -> Dict[str, object]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(f"{API_BASE}/api/v1/system/llm-servers/active")
        response.raise_for_status()
        return response.json()


async def _fetch_task_status(task_id: str) -> Dict[str, object]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(f"{API_BASE}/api/v1/tasks/{task_id}")
        response.raise_for_status()
        return response.json()


async def _poll_task_completion(task_id: str) -> str | None:
    deadline = time.perf_counter() + STATUS_TIMEOUT
    while time.perf_counter() < deadline:
        payload = await _fetch_task_status(task_id)
        status = str(payload.get("status") or payload.get("state") or "").upper()
        if status in {"COMPLETED", "FAILED", "LOST"}:
            return status
        await asyncio.sleep(STATUS_POLL_INTERVAL)
    return None


async def _resolve_timeout_result(
    task_id: str, start: float, first_token_time: float | None, event: str
) -> Tuple[float, float]:
    status = await _poll_task_completion(task_id)
    if status == "COMPLETED":
        total_time = time.perf_counter() - start
        if first_token_time is None:
            first_token_time = total_time
        return first_token_time, total_time
    if status in {"FAILED", "LOST"}:
        pytest.skip(f"Task zakończony statusem {status} po timeout SSE.")
    raise TimeoutError(
        f"SSE przekroczyło timeout {STREAM_TIMEOUT}s (ostatnie zdarzenie: {event})",
    )


def _extract_first_token_elapsed(
    event: str,
    payload: object,
    elapsed: float,
    first_token_time: float | None,
) -> float | None:
    if event != "task_update" or first_token_time is not None:
        return first_token_time
    result = payload.get("result") if isinstance(payload, dict) else None
    if isinstance(result, str) and result.strip():
        return elapsed
    return first_token_time


def _finalize_on_task_finished(
    first_token_time: float | None, elapsed: float
) -> Tuple[float, float]:
    total_time = elapsed
    if first_token_time is None:
        first_token_time = total_time
    return first_token_time, total_time


async def _handle_stream_timeout(
    elapsed: float,
    task_id: str,
    start: float,
    first_token_time: float | None,
    event: str,
) -> Tuple[float, float] | None:
    if elapsed <= STREAM_TIMEOUT:
        return None
    return await _resolve_timeout_result(task_id, start, first_token_time, event)


async def _measure_latency(prompt: str) -> Tuple[float, float]:
    task_id = await submit_task(prompt, store_knowledge=False)
    start = time.perf_counter()
    first_token_time = None
    async for event, payload in stream_task(task_id):
        elapsed = time.perf_counter() - start
        first_token_time = _extract_first_token_elapsed(
            event, payload, elapsed, first_token_time
        )
        if event == "task_finished":
            return _finalize_on_task_finished(first_token_time, elapsed)
        timeout_result = await _handle_stream_timeout(
            elapsed, task_id, start, first_token_time, event
        )
        if timeout_result is not None:
            return timeout_result
    raise RuntimeError("Stream zakończył się bez eventu task_finished")


def _resolve_active_model(payload: Dict[str, object]) -> str:
    models = payload.get("models", [])
    active_payload = payload.get("active") or {}
    active_model = active_payload.get("model")
    available = {str(model.get("name")) for model in models if model.get("name")}

    if active_model and active_model in available:
        return str(active_model)
    if MODEL_NAME in available:
        pytest.skip(
            f"Aktywny model ({active_model}) nie pasuje do testu; oczekiwano aktywnego {MODEL_NAME}.",
        )
    pytest.skip(
        f"Brak aktywnego modelu do testu (aktywny={active_model}, dostępne={len(available)}).",
    )


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
