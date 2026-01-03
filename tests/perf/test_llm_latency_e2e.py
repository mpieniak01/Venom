"""E2E testy latencji LLM: aktywacja modelu + pomiar odpowiedzi."""

from __future__ import annotations

import os
import time
from typing import Dict, List, Tuple

import httpx
import pytest

from .chat_pipeline import API_BASE, is_backend_available, stream_task, submit_task

pytestmark = [pytest.mark.asyncio, pytest.mark.performance]

MODEL_NAME = os.getenv("VENOM_LLM_MODEL", "gemma3")
SERVER_NAME = os.getenv("VENOM_LLM_SERVER", "ollama")
REPEATS = int(os.getenv("VENOM_LLM_REPEATS", "3"))
STREAM_TIMEOUT = float(os.getenv("VENOM_STREAM_TIMEOUT", "25"))


async def _skip_if_backend_unavailable():
    if not await is_backend_available():
        pytest.skip("Backend FastAPI jest niedostępny – pomiń testy E2E LLM.")


async def _set_active_llm_server(server_name: str) -> Dict[str, object] | None:
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                f"{API_BASE}/api/v1/system/llm-servers/active",
                json={"server_name": server_name},
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError:
            return None


async def _list_models() -> Dict[str, object]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(f"{API_BASE}/api/v1/models")
        response.raise_for_status()
        return response.json()


async def _activate_model(name: str) -> Dict[str, object]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{API_BASE}/api/v1/models/switch",
            json={"name": name},
        )
        response.raise_for_status()
        return response.json()


async def _measure_latency(prompt: str) -> Tuple[float, float]:
    task_id = await submit_task(prompt, store_knowledge=False)
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
            raise TimeoutError(
                f"SSE przekroczyło timeout {STREAM_TIMEOUT}s (ostatnie zdarzenie: {event})",
            )
    raise RuntimeError("Stream zakończył się bez eventu task_finished")


@pytest.mark.smoke
async def test_llm_latency_e2e():
    await _skip_if_backend_unavailable()

    await _set_active_llm_server(SERVER_NAME)

    payload = await _list_models()
    models = payload.get("models", [])
    active_payload = payload.get("active") or {}
    active_model = active_payload.get("model")
    available = {str(model.get("name")) for model in models if model.get("name")}

    if MODEL_NAME in available:
        model_to_use = MODEL_NAME
    elif active_model and active_model in available:
        model_to_use = active_model
    else:
        pytest.fail(
            f"Brak dostępnego modelu do testu. Oczekiwano {MODEL_NAME} lub aktywnego modelu.",
        )

    if model_to_use != active_model:
        await _activate_model(model_to_use)

    first_tokens: List[float] = []
    totals: List[float] = []
    for idx in range(REPEATS):
        prompt = f"Latency test {model_to_use} #{idx}: podaj liczbę PI do 5 miejsc."
        first_token, total = await _measure_latency(prompt)
        first_tokens.append(first_token)
        totals.append(total)

    assert all(value > 0 for value in first_tokens)
    assert all(value > 0 for value in totals)
    print(
        "LLM latency summary:",
        f"model={model_to_use}",
        f"first_token avg={sum(first_tokens) / len(first_tokens):.2f}s",
        f"total avg={sum(totals) / len(totals):.2f}s",
        f"min={min(totals):.2f}s",
        f"max={max(totals):.2f}s",
    )
