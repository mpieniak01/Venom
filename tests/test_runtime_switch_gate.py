from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from venom_core.services import runtime_switch_gate as gate


@pytest.fixture(autouse=True)
def reset_runtime_switch_gate():
    with gate._STATE_LOCK:  # noqa: SLF001
        gate._STATE = gate._RuntimeSwitchGateState()  # noqa: SLF001
    yield
    with gate._STATE_LOCK:  # noqa: SLF001
        gate._STATE = gate._RuntimeSwitchGateState()  # noqa: SLF001


def test_runtime_request_guard_blocks_when_switch_is_active():
    snapshot = gate.begin_runtime_switch(
        source="ui",
        from_runtime="ollama",
        to_runtime="multi_runtime",
        reason="test",
    )

    with pytest.raises(HTTPException) as exc_info:

        async def _blocked():
            async with gate.runtime_request_guard(request_kind="simple_chat"):
                return None

        asyncio.run(_blocked())

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "runtime_switch_in_progress"

    gate.finish_runtime_switch(switch_id=snapshot.switch_id)


@pytest.mark.asyncio
async def test_runtime_switch_waits_for_active_requests_to_drain():
    entered = asyncio.Event()
    release = asyncio.Event()

    async def _active_request():
        async with gate.runtime_request_guard(
            request_kind="voice_chat",
            provider="ollama",
            model="qwen3.5:latest",
        ):
            entered.set()
            await release.wait()

    task = asyncio.create_task(_active_request())
    await entered.wait()

    snapshot = gate.begin_runtime_switch(
        source="ui",
        from_runtime="ollama",
        to_runtime="multi_runtime",
        reason="test",
    )

    drain_task = asyncio.create_task(gate.wait_for_runtime_requests_to_drain())
    await asyncio.sleep(0.05)
    assert not drain_task.done()

    release.set()
    assert await drain_task is True

    gate.finish_runtime_switch(switch_id=snapshot.switch_id)
    await task


def test_finish_runtime_switch_ignores_mismatched_switch_id():
    snapshot = gate.begin_runtime_switch(
        source="ui",
        from_runtime="ollama",
        to_runtime="multi_runtime",
        reason="test",
    )

    gate.finish_runtime_switch(switch_id="different-switch-id")
    current = gate.get_runtime_switch_gate_snapshot()
    assert current.in_progress is True
    assert current.switch_id == snapshot.switch_id

    gate.finish_runtime_switch(switch_id=snapshot.switch_id)
    closed = gate.get_runtime_switch_gate_snapshot()
    assert closed.in_progress is False
    assert closed.switch_id is None
