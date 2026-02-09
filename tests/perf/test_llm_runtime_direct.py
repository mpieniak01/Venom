"""Testy bezpośredniego runtime LLM (bez warstwy API Venom)."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from typing import List

import httpx
import pytest

pytestmark = [pytest.mark.performance]

OLLAMA_ENDPOINT = os.getenv("VENOM_OLLAMA_ENDPOINT", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("VENOM_OLLAMA_MODEL", "gemma3")
REPEATS = int(os.getenv("VENOM_OLLAMA_REPEATS", "3"))
PROMPT = os.getenv("VENOM_OLLAMA_PROMPT", "Provide pi to 5 decimals.")


async def _ollama_available() -> bool:
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(f"{OLLAMA_ENDPOINT}/api/tags")
        return response.status_code < 400
    except httpx.HTTPError:
        return False


async def _ollama_has_model(model_name: str) -> bool:
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(f"{OLLAMA_ENDPOINT}/api/tags")
        response.raise_for_status()
        payload = response.json()
    models = payload.get("models") or []
    names = {str(entry.get("name")) for entry in models if entry.get("name")}
    if model_name in names:
        return True
    return any(name.startswith(f"{model_name}:") for name in names)


@pytest.mark.asyncio
async def test_ollama_direct_api_latency():
    if not await _ollama_available():
        pytest.skip("Ollama API niedostępne – pomiń testy direct API.")
    if not await _ollama_has_model(OLLAMA_MODEL):
        pytest.skip(f"Model {OLLAMA_MODEL} nie jest dostępny – pomiń test API.")

    timings: List[float] = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        for idx in range(REPEATS):
            payload = {
                "model": OLLAMA_MODEL,
                "prompt": f"{PROMPT} (direct api #{idx})",
                "stream": False,
            }
            start = time.perf_counter()
            try:
                response = await client.post(
                    f"{OLLAMA_ENDPOINT}/api/generate", json=payload
                )
            except httpx.TimeoutException:
                pytest.skip(
                    "Timeout Ollama direct API podczas testu perf – pomiń jako niestabilność środowiska."
                )
            elapsed = time.perf_counter() - start
            response.raise_for_status()
            timings.append(elapsed)

    assert all(value > 0 for value in timings)
    print(
        "Ollama direct API latency:",
        f"model={OLLAMA_MODEL}",
        f"avg={sum(timings) / len(timings):.2f}s",
        f"min={min(timings):.2f}s",
        f"max={max(timings):.2f}s",
    )


def _ollama_cli_available() -> bool:
    return shutil.which("ollama") is not None


def _ollama_cli_has_model(model_name: str) -> bool:
    try:
        result = subprocess.run(
            ["ollama", "list"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        return False
    return model_name in result.stdout or f"{model_name}:" in result.stdout


@pytest.mark.smoke
def test_ollama_cli_latency():
    if not _ollama_cli_available():
        pytest.skip("Brak CLI 'ollama' – pomiń test.")
    if not _ollama_cli_has_model(OLLAMA_MODEL):
        pytest.skip(f"Model {OLLAMA_MODEL} nie jest dostępny – pomiń test CLI.")

    timings: List[float] = []
    for idx in range(REPEATS):
        start = time.perf_counter()
        subprocess.run(
            ["ollama", "run", OLLAMA_MODEL, f"{PROMPT} (cli #{idx})"],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        elapsed = time.perf_counter() - start
        timings.append(elapsed)

    assert all(value > 0 for value in timings)
    print(
        "Ollama CLI latency:",
        f"model={OLLAMA_MODEL}",
        f"avg={sum(timings) / len(timings):.2f}s",
        f"min={min(timings):.2f}s",
        f"max={max(timings):.2f}s",
    )
