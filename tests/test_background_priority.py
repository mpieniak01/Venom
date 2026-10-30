from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from venom_core.services import background_priority as priority


@pytest.mark.asyncio
async def test_background_waits_for_host_then_runtime_and_resumes(monkeypatch):
    orch = SimpleNamespace(active_tasks={"interactive": object()})
    state = {"status": "owned"}
    snapshot = Mock(side_effect=lambda: dict(state))
    monkeypatch.setattr(
        priority, "get_runtime_admission", lambda: SimpleNamespace(snapshot=snapshot)
    )
    waits = []

    async def advance(_seconds):
        waits.append(1)
        if len(waits) == 1:
            orch.active_tasks.clear()
        else:
            state["status"] = "available"

    monkeypatch.setattr(priority.asyncio, "sleep", advance)
    await priority.wait_for_interactive_idle(orch)
    assert len(waits) == 2
    assert snapshot.call_count == 2


@pytest.mark.asyncio
async def test_background_cancellation_does_not_start_work(monkeypatch):
    monkeypatch.setattr(
        priority.asyncio, "sleep", AsyncMock(side_effect=asyncio.CancelledError)
    )
    with pytest.raises(asyncio.CancelledError):
        await priority.wait_for_interactive_idle(
            SimpleNamespace(active_tasks={"task": object()})
        )


@pytest.mark.asyncio
async def test_ledger_read_is_off_the_event_loop(monkeypatch):
    loop_thread = threading.get_ident()
    threads = []

    def snapshot():
        threads.append(threading.get_ident())
        return {"status": "disabled"}

    monkeypatch.setattr(
        priority, "get_runtime_admission", lambda: SimpleNamespace(snapshot=snapshot)
    )
    await priority.wait_for_interactive_idle()
    assert threads and threads[0] != loop_thread


@pytest.mark.asyncio
async def test_gardener_starts_without_waiting_for_initial_scan_and_drains_on_stop(
    monkeypatch, tmp_path
):
    from venom_core.agents import gardener as module

    entered = threading.Event()
    finish = threading.Event()
    completed = threading.Event()

    def scan():
        entered.set()
        finish.wait(timeout=10)
        completed.set()
        return {}

    monkeypatch.setattr(module, "wait_for_interactive_idle", AsyncMock())
    gardener = module.GardenerAgent(graph_store=Mock(), workspace_root=str(tmp_path))
    monkeypatch.setattr(gardener, "scan_and_update", scan)
    await gardener.start()
    assert gardener.is_running
    assert not completed.is_set()
    try:
        assert await asyncio.to_thread(entered.wait, 5)
        stopping = asyncio.create_task(gardener.stop())
        await asyncio.sleep(0)
        assert not stopping.done()
    finally:
        finish.set()
    await stopping
    assert completed.is_set()
    assert not gardener.is_running


@pytest.mark.asyncio
async def test_documenter_stops_cleanup_and_rejects_new_work(monkeypatch, tmp_path):
    from venom_core.agents.documenter import DocumenterAgent

    agent = DocumenterAgent(workspace_root=str(tmp_path))
    process = AsyncMock()
    monkeypatch.setattr(agent, "_process_file_change", process)
    await agent.handle_code_change("example.py")
    assert agent._background_tasks
    await agent.stop()
    assert not agent._background_tasks
    assert not agent._last_processed_files
    await agent.handle_code_change("other.py")
    process.assert_awaited_once_with("example.py")
