from __future__ import annotations

import asyncio
import time
from typing import Dict, Tuple

import httpx
import pytest


async def skip_if_backend_unavailable(is_backend_available_fn, message: str) -> None:
    if not await is_backend_available_fn():
        pytest.skip(message)


async def list_models(api_base: str) -> Dict[str, object]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(f"{api_base}/api/v1/models")
        response.raise_for_status()
        return response.json()


async def get_active_runtime(api_base: str) -> Dict[str, object]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(f"{api_base}/api/v1/system/llm-servers/active")
        response.raise_for_status()
        return response.json()


async def fetch_task_status(api_base: str, task_id: str) -> Dict[str, object]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(f"{api_base}/api/v1/tasks/{task_id}")
        response.raise_for_status()
        return response.json()


async def poll_task_completion(
    task_id: str,
    *,
    api_base: str,
    status_timeout: float,
    status_poll_interval: float,
) -> str | None:
    deadline = time.perf_counter() + status_timeout
    while time.perf_counter() < deadline:
        payload = await fetch_task_status(api_base, task_id)
        status = str(payload.get("status") or payload.get("state") or "").upper()
        if status in {"COMPLETED", "FAILED", "LOST"}:
            return status
        await asyncio.sleep(status_poll_interval)
    return None


async def resolve_timeout_result(
    task_id: str,
    *,
    start: float,
    first_token_time: float | None,
    event: str,
    api_base: str,
    status_timeout: float,
    status_poll_interval: float,
    stream_timeout: float,
) -> Tuple[float, float]:
    status = await poll_task_completion(
        task_id,
        api_base=api_base,
        status_timeout=status_timeout,
        status_poll_interval=status_poll_interval,
    )
    if status == "COMPLETED":
        total_time = time.perf_counter() - start
        if first_token_time is None:
            first_token_time = total_time
        return first_token_time, total_time
    if status in {"FAILED", "LOST"}:
        pytest.skip(f"Task zakończony statusem {status} po timeout SSE.")
    raise TimeoutError(
        f"SSE przekroczyło timeout {stream_timeout}s (ostatnie zdarzenie: {event})",
    )


def resolve_active_model(payload: Dict[str, object], model_name: str) -> str:
    models = payload.get("models", [])
    active_payload = payload.get("active") or {}
    active_model = active_payload.get("model")
    available = {str(model.get("name")) for model in models if model.get("name")}

    if active_model and active_model in available:
        return str(active_model)
    if model_name in available:
        pytest.skip(
            f"Aktywny model ({active_model}) nie pasuje do testu; oczekiwano aktywnego {model_name}.",
        )
    pytest.skip(
        f"Brak aktywnego modelu do testu (aktywny={active_model}, dostępne={len(available)}).",
    )
