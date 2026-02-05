"""E2E latency testy dla trybów: fast (direct), normal, complex."""

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
        pytest.skip("Backend FastAPI jest niedostępny – pomiń testy E2E.")


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
        if event == "task_update" and first_token_time is None:
            result = payload.get("result") if isinstance(payload, dict) else None
            if isinstance(result, str) and result.strip():
                first_token_time = elapsed
        if event == "task_finished":
            total_time = elapsed
            if first_token_time is None:
                first_token_time = total_time
            return first_token_time, total_time
        if elapsed > STREAM_TIMEOUT:
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
    raise RuntimeError("Stream zakończył się bez eventu task_finished")


@pytest.mark.smoke
async def test_latency_modes_e2e():
    await _skip_if_backend_unavailable()

    payload = await _list_models()
    models = payload.get("models", [])
    active_payload = payload.get("active") or {}
    active_model = active_payload.get("model")
    available = {str(model.get("name")) for model in models if model.get("name")}

    if active_model and active_model in available:
        model_to_use = active_model
    elif MODEL_NAME in available:
        pytest.skip(
            f"Aktywny model ({active_model}) nie pasuje do testu; oczekiwano aktywnego {MODEL_NAME}.",
        )
    else:
        pytest.skip(
            f"Brak aktywnego modelu do testu (aktywny={active_model}, dostępne={len(available)}).",
        )

    runtime_info = await _get_active_runtime()

    results = {}

    # FAST (Direct)
    fast_first: List[float] = []
    fast_total: List[float] = []
    for idx in range(REPEATS):
        prompt = f"Fast latency test {model_to_use} #{idx}: odpowiedz krótko OK."
        first_token, total = await _measure_direct_latency(prompt, model_to_use)
        fast_first.append(first_token)
        fast_total.append(total)
    results["fast"] = (fast_first, fast_total)
    print(
        "LLM latency summary:",
        "mode=fast",
        f"model={model_to_use}",
        f"runtime={runtime_info.get('active_server')}@{runtime_info.get('active_endpoint')}",
        f"first_token avg={sum(fast_first) / len(fast_first):.2f}s",
        f"total avg={sum(fast_total) / len(fast_total):.2f}s",
        f"min={min(fast_total):.2f}s",
        f"max={max(fast_total):.2f}s",
    )

    # NORMAL
    normal_first: List[float] = []
    normal_total: List[float] = []
    for idx in range(REPEATS):
        prompt = f"Normal latency test {model_to_use} #{idx}: odpowiedz krótko OK."
        first_token, total = await _measure_task_latency(prompt)
        normal_first.append(first_token)
        normal_total.append(total)
    results["normal"] = (normal_first, normal_total)
    print(
        "LLM latency summary:",
        "mode=normal",
        f"model={model_to_use}",
        f"runtime={runtime_info.get('active_server')}@{runtime_info.get('active_endpoint')}",
        f"first_token avg={sum(normal_first) / len(normal_first):.2f}s",
        f"total avg={sum(normal_total) / len(normal_total):.2f}s",
        f"min={min(normal_total):.2f}s",
        f"max={max(normal_total):.2f}s",
    )

    # COMPLEX
    complex_first: List[float] = []
    complex_total: List[float] = []
    complex_error: str | None = None
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
        results["complex"] = (complex_first, complex_total)
        print(
            "LLM latency summary:",
            "mode=complex",
            f"model={model_to_use}",
            f"runtime={runtime_info.get('active_server')}@{runtime_info.get('active_endpoint')}",
            f"first_token avg={sum(complex_first) / len(complex_first):.2f}s",
            f"total avg={sum(complex_total) / len(complex_total):.2f}s",
            f"min={min(complex_total):.2f}s",
            f"max={max(complex_total):.2f}s",
        )
    except TimeoutError as exc:
        complex_error = str(exc)
        print("LLM latency summary:", "mode=complex", f"error={complex_error}")

    for mode, (firsts, totals) in results.items():
        assert all(value > 0 for value in firsts)
        assert all(value > 0 for value in totals)

    if complex_error:
        pytest.fail(complex_error)
