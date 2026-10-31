"""A chat Stop owns one session/task and never resumes cancelled queued work."""

import asyncio
from contextlib import suppress
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from venom_core.api.dependencies import get_orchestrator
from venom_core.api.routes import chat_tasks
from venom_core.api.routes.chat_tasks import CancelChatTask, cancel_chat_task
from venom_core.api.schemas.tasks import TaskRequest
from venom_core.core.models import TaskStatus, VenomTask
from venom_core.core.orchestrator.orchestrator_submit import (
    run_task_fastpath,
    run_task_with_queue,
)
from venom_core.core.queue_manager import QueueManager


class State:
    def __init__(self, *tasks):
        self.tasks = {task.id: task for task in tasks}

    def get_task(self, task_id):
        return self.tasks.get(task_id)

    async def update_status(self, task_id, status, result=None):
        task = self.tasks[task_id]
        task.status, task.result = status, result

    def add_log(self, *_args):
        pass


@pytest.mark.asyncio
async def test_cancel_owns_one_pending_task_and_is_idempotent():
    owned = VenomTask(
        content="owned", context_history={"session": {"session_id": "one"}}
    )
    foreign = VenomTask(
        content="foreign", context_history={"session": {"session_id": "two"}}
    )
    state = State(owned, foreign)
    manager = QueueManager(state)
    orch = SimpleNamespace(state_manager=state, abort_task=manager.abort_task)
    response = await cancel_chat_task(owned.id, CancelChatTask(session_id="one"), orch)
    assert response.status == "cancelled"
    assert owned.status == TaskStatus.FAILED
    assert foreign.status == TaskStatus.PENDING
    again = await cancel_chat_task(owned.id, CancelChatTask(session_id="one"), orch)
    assert again.status == "already_finished"
    for task_id in (foreign.id, uuid4()):
        with pytest.raises(HTTPException) as error:
            await cancel_chat_task(task_id, CancelChatTask(session_id="one"), orch)
        assert error.value.status_code == 404
    assert foreign.status == TaskStatus.PENDING


@pytest.mark.asyncio
async def test_active_cancel_only_cancels_owned_handle():
    owned = VenomTask(
        content="owned",
        status=TaskStatus.PROCESSING,
        context_history={"session": {"session_id": "one"}},
    )
    foreign = VenomTask(
        content="foreign",
        status=TaskStatus.PROCESSING,
        context_history={"session": {"session_id": "two"}},
    )
    state = State(owned, foreign)
    manager = QueueManager(state)
    handles = [asyncio.create_task(asyncio.Event().wait()) for _ in range(2)]
    manager.active_tasks.update({owned.id: handles[0], foreign.id: handles[1]})
    try:
        orch = SimpleNamespace(state_manager=state, abort_task=manager.abort_task)
        await cancel_chat_task(owned.id, CancelChatTask(session_id="one"), orch)
        await asyncio.sleep(0)
        assert handles[0].cancelled()
        assert not handles[1].done()
        assert foreign.id in manager.active_tasks
        assert not manager.is_paused
    finally:
        for handle in handles:
            handle.cancel()
            with suppress(asyncio.CancelledError):
                await handle


@pytest.mark.asyncio
async def test_queued_stop_before_capacity_prevents_later_inference():
    owned = VenomTask(
        content="queued", context_history={"session": {"session_id": "one"}}
    )
    state = State(owned)
    manager = QueueManager(state)
    manager.is_paused = True
    orch = SimpleNamespace(
        state_manager=state,
        task_manager=manager,
        abort_task=manager.abort_task,
        _run_task=AsyncMock(),
    )
    wrapper = asyncio.create_task(
        run_task_with_queue(orch, owned.id, TaskRequest(content="queued"))
    )
    await asyncio.sleep(0)
    await cancel_chat_task(owned.id, CancelChatTask(session_id="one"), orch)
    manager.is_paused = False
    await asyncio.wait_for(wrapper, 1)
    orch._run_task.assert_not_awaited()
    assert owned.id not in manager.active_tasks


@pytest.mark.asyncio
@pytest.mark.parametrize("runner", [run_task_fastpath, run_task_with_queue])
async def test_cancel_during_registration_never_runs_and_unregisters(runner):
    owned = VenomTask(content="queued")
    state = State(owned)

    async def cancelled_while_registering(*_args):
        owned.status = TaskStatus.FAILED

    manager = SimpleNamespace(
        is_paused=False,
        check_capacity=AsyncMock(return_value=(True, 0)),
        register_task=AsyncMock(side_effect=cancelled_while_registering),
        unregister_task=AsyncMock(),
    )
    orch = SimpleNamespace(
        state_manager=state, task_manager=manager, _run_task=AsyncMock()
    )
    await runner(orch, owned.id, TaskRequest(content="queued"))
    orch._run_task.assert_not_awaited()
    manager.unregister_task.assert_awaited_once_with(owned.id)


@pytest.mark.asyncio
async def test_task_finishing_during_abort_is_idempotent_not_an_error():
    owned = VenomTask(
        content="owned",
        status=TaskStatus.PROCESSING,
        context_history={"session": {"session_id": "one"}},
    )
    state = State(owned)

    async def finished(_task_id):
        owned.status = TaskStatus.COMPLETED
        return {"success": False}

    result = await cancel_chat_task(
        owned.id,
        CancelChatTask(session_id="one"),
        SimpleNamespace(state_manager=state, abort_task=finished),
    )
    assert result.status == "already_finished"
    owned.status = TaskStatus.PROCESSING
    with pytest.raises(HTTPException) as error:
        await cancel_chat_task(
            owned.id,
            CancelChatTask(session_id="one"),
            SimpleNamespace(
                state_manager=state,
                abort_task=AsyncMock(return_value={"success": False}),
            ),
        )
    assert error.value.status_code == 409


def test_cancel_endpoint_requires_operator_and_ownership():
    owned = VenomTask(
        content="owned",
        status=TaskStatus.COMPLETED,
        context_history={"session": {"session_id": "one"}},
    )
    app = FastAPI()
    app.include_router(chat_tasks.router)
    app.dependency_overrides[get_orchestrator] = lambda: SimpleNamespace(
        state_manager=State(owned)
    )
    path = f"/api/v1/chat/tasks/{owned.id}/cancel"
    with TestClient(app, client=("127.0.0.1", 1)) as client:
        assert client.post(path, json={"session_id": "two"}).status_code == 404
        assert (
            client.post(path, json={"session_id": "one"}).json()["status"]
            == "already_finished"
        )
    with TestClient(app, client=("192.0.2.1", 1)) as client:
        assert client.post(path, json={"session_id": "one"}).status_code == 403


@pytest.mark.asyncio
async def test_cancel_during_capacity_wait_never_registers_or_runs():
    owned = VenomTask(content="queued")
    state = State(owned)

    async def capacity_after_cancel():
        owned.status = TaskStatus.FAILED
        return True, 0

    manager = SimpleNamespace(
        is_paused=False, check_capacity=capacity_after_cancel, register_task=AsyncMock()
    )
    orch = SimpleNamespace(
        state_manager=state, task_manager=manager, _run_task=AsyncMock()
    )
    await run_task_with_queue(orch, owned.id, TaskRequest(content="queued"))
    manager.register_task.assert_not_awaited()
    orch._run_task.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("runner", [run_task_fastpath, run_task_with_queue])
@pytest.mark.parametrize("status", [TaskStatus.COMPLETED, TaskStatus.FAILED])
async def test_finished_queued_task_cannot_be_resurrected(runner, status):
    owned = VenomTask(content="finished", status=status)
    manager = SimpleNamespace(register_task=AsyncMock())
    orch = SimpleNamespace(
        state_manager=State(owned), task_manager=manager, _run_task=AsyncMock()
    )
    await runner(orch, owned.id, TaskRequest(content="finished"))
    manager.register_task.assert_not_awaited()
    orch._run_task.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("initial", [TaskStatus.PENDING, TaskStatus.PROCESSING])
@pytest.mark.parametrize("terminal", [TaskStatus.COMPLETED, TaskStatus.FAILED])
async def test_stop_waiting_for_queue_lock_cannot_overwrite_terminal_result(
    initial, terminal
):
    task = VenomTask(
        content="owned",
        status=initial,
        context_history={"session": {"session_id": "one"}},
    )
    state = State(task)
    manager = QueueManager(state)
    orch = SimpleNamespace(state_manager=state, abort_task=manager.abort_task)
    await manager._queue_lock.acquire()
    stop = asyncio.create_task(
        cancel_chat_task(task.id, CancelChatTask(session_id="one"), orch)
    )
    await asyncio.sleep(0)
    task.status, task.result = terminal, "final answer"
    manager.active_tasks.pop(task.id, None)
    manager._queue_lock.release()
    response = await stop
    assert response.status == "already_finished"
    assert task.status == terminal
    assert task.result == "final answer"


@pytest.mark.asyncio
async def test_scoped_stop_preserves_existing_streamed_partial_output():
    task = VenomTask(
        content="owned",
        status=TaskStatus.PROCESSING,
        context_history={"session": {"session_id": "one"}},
        result="already generated words",
    )
    state = State(task)
    manager = QueueManager(state)
    running = asyncio.create_task(asyncio.Event().wait())
    manager.active_tasks[task.id] = running
    try:
        response = await cancel_chat_task(
            task.id,
            CancelChatTask(session_id="one"),
            SimpleNamespace(state_manager=state, abort_task=manager.abort_task),
        )
        assert response.status == "cancelled"
        assert task.result == "already generated words"
    finally:
        running.cancel()
        with suppress(asyncio.CancelledError):
            await running
