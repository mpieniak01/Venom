from __future__ import annotations

from typing import Awaitable, Callable, Tuple


def extract_first_token_elapsed(
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


def finalize_on_task_finished(
    first_token_time: float | None, elapsed: float
) -> Tuple[float, float]:
    total_time = elapsed
    if first_token_time is None:
        first_token_time = total_time
    return first_token_time, total_time


async def handle_stream_timeout(
    elapsed: float,
    stream_timeout: float,
    resolve_timeout_result: Callable[
        [str, float, float | None, str], Awaitable[Tuple[float, float]]
    ],
    task_id: str,
    start: float,
    first_token_time: float | None,
    event: str,
) -> Tuple[float, float] | None:
    if elapsed <= stream_timeout:
        return None
    return await resolve_timeout_result(task_id, start, first_token_time, event)
