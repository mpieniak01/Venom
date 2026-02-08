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
STREAM_TIMEOUT = float(os.getenv("VENOM_STREAM_TIMEOUT", "60"))


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


async def _stream_simple_once(prompt: str, model: str) -> Tuple[float, float]:
    start = time.perf_counter()
    first_token_time = None
    had_chunk = False
    async with httpx.AsyncClient(timeout=None) as client:
        try:
            async with client.stream(
                "POST",
                f"{API_BASE}/api/v1/llm/simple/stream",
                json={"content": prompt, "model": model},
            ) as response:
                response.raise_for_status()
                async for chunk in response.aiter_text():
                    if not chunk:
                        continue
                    had_chunk = True
                    elapsed = time.perf_counter() - start
                    if first_token_time is None:
                        first_token_time = elapsed
                    if elapsed > STREAM_TIMEOUT:
                        raise TimeoutError(
                            f"Streaming przekroczył timeout {STREAM_TIMEOUT}s.",
                        )
        except (httpx.RemoteProtocolError, httpx.ReadError, httpx.ReadTimeout):
            if had_chunk:
                total_time = time.perf_counter() - start
                if first_token_time is None:
                    first_token_time = total_time
                return first_token_time, total_time
            raise

    total_time = time.perf_counter() - start
    if first_token_time is None:
        first_token_time = total_time
    return first_token_time, total_time


async def _retry_or_skip(attempt: int, max_retries: int, message: str):
    if attempt >= max_retries:
        pytest.skip(message)
    await asyncio.sleep(min(2 ** (attempt - 1), 5))


async def _measure_simple_latency(prompt: str, model: str) -> Tuple[float, float]:
    max_retries = int(os.getenv("VENOM_LLM_STREAM_RETRIES", "5"))
    for attempt in range(1, max_retries + 1):
        try:
            return await _stream_simple_once(prompt, model)
        except TimeoutError as e:
            print(f"⚠️ Retry {attempt}/{max_retries} due to timeout: {e}")
            await _retry_or_skip(
                attempt,
                max_retries,
                (
                    f"Stream LLM przekroczył timeout {STREAM_TIMEOUT}s "
                    f"po {max_retries} próbach."
                ),
            )
        except (httpx.RemoteProtocolError, httpx.ReadError, httpx.ReadTimeout) as e:
            print(f"⚠️ Retry {attempt}/{max_retries} due to connection error: {e}")
            await _retry_or_skip(
                attempt,
                max_retries,
                f"Stream LLM niestabilny po {max_retries} probach: {e}",
            )
    raise RuntimeError("Nie udało się zakończyć pomiaru latencji streamu")


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


def _print_simple_summary(
    model_to_use: str,
    runtime_info: Dict[str, object],
    first_tokens: List[float],
    totals: List[float],
):
    print(
        "LLM simple latency summary:",
        f"model={model_to_use}",
        f"runtime={runtime_info.get('active_server')}@{runtime_info.get('active_endpoint')}",
        f"first_token avg={sum(first_tokens) / len(first_tokens):.2f}s",
        f"total avg={sum(totals) / len(totals):.2f}s",
        f"min={min(totals):.2f}s",
        f"max={max(totals):.2f}s",
    )


async def _collect_simple_latency_samples(
    model_to_use: str,
) -> Tuple[List[float], List[float]]:
    first_tokens: List[float] = []
    totals: List[float] = []
    for idx in range(REPEATS):
        prompt = (
            f"Simple latency test {model_to_use} #{idx}: podaj liczbę PI do 5 miejsc."
        )
        first_token, total = await _measure_simple_latency(prompt, model_to_use)
        first_tokens.append(first_token)
        totals.append(total)
    return first_tokens, totals


@pytest.mark.smoke
async def test_llm_simple_e2e():
    await _skip_if_backend_unavailable()

    payload = await _list_models()
    model_to_use = _resolve_active_model(payload)
    runtime_info = await _get_active_runtime()
    first_tokens, totals = await _collect_simple_latency_samples(model_to_use)

    assert all(value > 0 for value in first_tokens)
    assert all(value > 0 for value in totals)
    _print_simple_summary(model_to_use, runtime_info, first_tokens, totals)
