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
    orchestrator = SimpleNamespace(active_tasks={"task": object()})
    with pytest.raises(asyncio.CancelledError):
        await priority.wait_for_interactive_idle(orchestrator)


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
    assert threads
    assert threads[0] != loop_thread


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


@pytest.mark.asyncio
async def test_drainable_thread_returns_result_and_worker_error():
    assert (
        await priority.run_drainable_thread(
            lambda value, *, extra: value + extra, 2, extra=3
        )
        == 5
    )

    def fail():
        raise ValueError("worker failure")

    with pytest.raises(ValueError, match="worker failure"):
        await priority.run_drainable_thread(fail)


@pytest.mark.asyncio
@pytest.mark.parametrize("worker_fails", [False, True])
async def test_drainable_thread_finishes_real_work_after_repeated_cancel(worker_fails):
    entered = threading.Event()
    finish = threading.Event()
    completed = threading.Event()

    def work():
        entered.set()
        assert finish.wait(3)
        completed.set()
        if worker_fails:
            raise RuntimeError("retired worker")
        return 1

    task = asyncio.create_task(priority.run_drainable_thread(work))
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        assert not completed.is_set()
    finally:
        finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert completed.is_set()


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["changes", "complexity"])
async def test_gardener_stop_drains_periodic_and_complexity_workers(
    monkeypatch, tmp_path, phase
):
    from datetime import datetime, timedelta, timezone

    from venom_core.agents import gardener as module

    entered = threading.Event()
    finish = threading.Event()
    completed = threading.Event()

    def work():
        entered.set()
        assert finish.wait(3)
        completed.set()
        return False if phase == "changes" else []

    monkeypatch.setattr(module, "wait_for_interactive_idle", AsyncMock())
    monkeypatch.setattr(module.SETTINGS, "ENABLE_AUTO_GARDENING", True)
    orch = SimpleNamespace(
        active_tasks={},
        last_activity=datetime.now(timezone.utc) - timedelta(days=1),
    )
    agent = module.GardenerAgent(
        graph_store=Mock(),
        workspace_root=str(tmp_path),
        scan_interval=0,
        orchestrator=orch,
    )
    monkeypatch.setattr(agent, "scan_and_update", lambda: {})
    monkeypatch.setattr(
        agent, "_check_for_changes", work if phase == "changes" else lambda: False
    )
    monkeypatch.setattr(
        agent, "_find_complex_files", work if phase == "complexity" else lambda: []
    )
    await agent.start()
    stopping = None
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        stopping = asyncio.create_task(agent.stop())
        await asyncio.sleep(0)
        assert not stopping.done()
    finally:
        finish.set()
    assert stopping is not None
    await stopping
    assert completed.is_set()
    assert not agent.is_running


@pytest.mark.asyncio
async def test_documenter_stop_cancels_live_handler_without_post_stop_work(
    monkeypatch, tmp_path
):
    from venom_core.agents.documenter import DocumenterAgent

    agent = DocumenterAgent(workspace_root=str(tmp_path))
    entered = asyncio.Event()
    release = asyncio.Event()
    writes = []

    async def process(_path):
        entered.set()
        await release.wait()
        writes.append("unexpected")

    monkeypatch.setattr(agent, "_process_file_change", process)
    handler = asyncio.create_task(agent.handle_code_change("fixture.py"))
    await entered.wait()
    await agent.stop()
    release.set()
    assert handler.cancelled()
    assert not writes
    assert not agent._active_handlers
    assert not agent._background_tasks
    assert not agent._last_processed_files


@pytest.mark.asyncio
async def test_documenter_stop_drains_git_author_thread(monkeypatch, tmp_path):
    from venom_core.agents import documenter as module

    entered = threading.Event()
    finish = threading.Event()
    completed = threading.Event()

    def read_author():
        entered.set()
        assert finish.wait(3)
        completed.set()
        return False

    monkeypatch.setattr(module.SETTINGS, "ENABLE_AUTO_DOCUMENTATION", True)
    monkeypatch.setattr(module, "wait_for_interactive_idle", AsyncMock())
    agent = module.DocumenterAgent(workspace_root=str(tmp_path))
    monkeypatch.setattr(agent, "_is_bot_commit_author", read_author)
    diff = AsyncMock(return_value="diff --git")
    monkeypatch.setattr(agent, "_get_file_diff", diff)
    handler = asyncio.create_task(agent.handle_code_change("fixture.py"))
    stopping = None
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        stopping = asyncio.create_task(agent.stop())
        await asyncio.sleep(0)
        assert not stopping.done()
    finally:
        finish.set()
    assert stopping is not None
    await stopping
    assert completed.is_set()
    assert handler.cancelled()
    assert not agent._active_handlers
    diff.assert_not_awaited()


@pytest.mark.asyncio
async def test_documenter_stop_does_not_cancel_its_own_handler(monkeypatch, tmp_path):
    from venom_core.agents.documenter import DocumenterAgent

    agent = DocumenterAgent(workspace_root=str(tmp_path))

    async def process(_path):
        await agent.stop()

    monkeypatch.setattr(agent, "_process_file_change", process)
    await agent.handle_code_change("fixture.py")
    assert agent._stopping
    assert not agent._active_handlers
    assert not agent._background_tasks


@pytest.mark.asyncio
async def test_documenter_stop_retires_handler_waiting_for_processing_lock(
    monkeypatch, tmp_path
):
    from venom_core.agents.documenter import DocumenterAgent

    agent = DocumenterAgent(workspace_root=str(tmp_path))
    process = AsyncMock()
    monkeypatch.setattr(agent, "_process_file_change", process)
    await agent._processing_lock.acquire()
    try:
        handler = asyncio.create_task(agent.handle_code_change("fixture.py"))
        await asyncio.sleep(0)
        await agent.stop()
        assert handler.cancelled()
        assert not agent._active_handlers
    finally:
        agent._processing_lock.release()
    process.assert_not_awaited()


@pytest.mark.asyncio
async def test_documenter_skips_commit_if_stopped_during_update(monkeypatch, tmp_path):
    from venom_core.agents.documenter import DocumenterAgent

    agent = DocumenterAgent(workspace_root=str(tmp_path))

    async def update(*_args):
        agent._stopping = True

    commit = AsyncMock()
    monkeypatch.setattr(agent, "_update_documentation", update)
    monkeypatch.setattr(agent, "_commit_documentation_changes", commit)
    await agent._apply_documentation_update("fixture.py", "fixture.py", "diff --git")
    commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_idle_wait_drains_inflight_admission_read_on_cancel(monkeypatch):
    entered = threading.Event()
    finish = threading.Event()
    completed = threading.Event()

    def snapshot():
        entered.set()
        assert finish.wait(3)
        completed.set()
        return {"status": "available"}

    monkeypatch.setattr(
        priority, "get_runtime_admission", lambda: SimpleNamespace(snapshot=snapshot)
    )
    waiting = asyncio.create_task(priority.wait_for_interactive_idle())
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        waiting.cancel()
        await asyncio.sleep(0)
        assert not waiting.done()
    finally:
        finish.set()
    with pytest.raises(asyncio.CancelledError):
        await waiting
    assert completed.is_set()


@pytest.mark.asyncio
async def test_initial_gardener_failure_does_not_terminate_monitoring(
    monkeypatch, tmp_path
):
    from venom_core.agents import gardener as module

    idle = AsyncMock(
        side_effect=[RuntimeError("initial idle failure"), None, None, None]
    )
    monkeypatch.setattr(module, "wait_for_interactive_idle", idle)
    gardener = module.GardenerAgent(
        graph_store=Mock(), workspace_root=str(tmp_path), scan_interval=0.01
    )
    changed = Mock(return_value=True)
    scan = Mock(return_value={})
    monkeypatch.setattr(gardener, "_check_for_changes", changed)
    monkeypatch.setattr(gardener, "scan_and_update", scan)
    await gardener.start()
    try:

        async def until_scanned():
            while not scan.called:
                await asyncio.sleep(0.01)

        await asyncio.wait_for(until_scanned(), timeout=2)
        assert gardener.is_running
        assert not gardener._task.done()
    finally:
        await gardener.stop()
    assert scan.called
