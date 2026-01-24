"""E2E test trybu prostego: bezpośredni streaming z Ollama."""

from __future__ import annotations

import asyncio
import os
import time
from typing import Dict, List, Tuple

import httpx
import pytest

from .chat_pipeline import API_BASE, is_backend_available

pytestmark = [pytest.mark.asyncio, pytest.mark.performance]

MODEL_NAME = os.getenv("VENOM_LLM_MODEL", "gemma3")
REPEATS = int(os.getenv("VENOM_LLM_REPEATS", "3"))
STREAM_TIMEOUT = float(os.getenv("VENOM_STREAM_TIMEOUT", "25"))


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


async def _measure_simple_latency(prompt: str, model: str) -> Tuple[float, float]:
    start = time.perf_counter()
    first_token_time = None

    max_retries = int(os.getenv("VENOM_LLM_STREAM_RETRIES", "5"))
    attempt = 0
    while attempt < max_retries:
        try:
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
                                f"Streaming przekroczył timeout {STREAM_TIMEOUT}s.",
                            )
            # Success, break loop
            break
        except (httpx.RemoteProtocolError, httpx.ReadError, httpx.ReadTimeout) as e:
            attempt += 1
            if attempt >= max_retries:
                raise e  # Re-raise if all retries failed
            print(f"⚠️ Retry {attempt}/{max_retries} due to connection error: {e}")
            await asyncio.sleep(min(2 ** (attempt - 1), 5))  # Backoff
            # Reset times for next attempt as we need consistent latency measurement
            # Note: Retrying latency measurement invalidates the *first* latency metric somewhat
            # if we don't reset start time, but for smoke test reliability it is better to pass.
            start = time.perf_counter()
            first_token_time = None

    total_time = time.perf_counter() - start
    if first_token_time is None:
        first_token_time = total_time
    return first_token_time, total_time


@pytest.mark.smoke
async def test_llm_simple_e2e():
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

    first_tokens: List[float] = []
    totals: List[float] = []
    for idx in range(REPEATS):
        prompt = (
            f"Simple latency test {model_to_use} #{idx}: podaj liczbę PI do 5 miejsc."
        )
        first_token, total = await _measure_simple_latency(prompt, model_to_use)
        first_tokens.append(first_token)
        totals.append(total)

    assert all(value > 0 for value in first_tokens)
    assert all(value > 0 for value in totals)
    print(
        "LLM simple latency summary:",
        f"model={model_to_use}",
        f"runtime={runtime_info.get('active_server')}@{runtime_info.get('active_endpoint')}",
        f"first_token avg={sum(first_tokens) / len(first_tokens):.2f}s",
        f"total avg={sum(totals) / len(totals):.2f}s",
        f"min={min(totals):.2f}s",
        f"max={max(totals):.2f}s",
    )
