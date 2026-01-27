import asyncio

import pytest

from venom_core.core.models import TaskExtraContext, TaskRequest
from venom_core.core.orchestrator.event_broadcaster import EventBroadcasterClient
from venom_core.core.orchestrator.kernel_lifecycle import KernelLifecycleManager
from venom_core.core.orchestrator.orchestrator_events import build_error_envelope
from venom_core.core.orchestrator.orchestrator_submit import should_use_fast_path
from venom_core.core.orchestrator.task_manager import TaskManager
from venom_core.core.orchestrator.task_pipeline.context_builder import (
    format_extra_context,
)


class DummyQueueManager:
    def __init__(self):
        self.is_paused = False
        self.active_tasks = {"t1": "task"}
        self.last_register = None
        self.last_unregister = None
        self.aborted = None

    async def check_capacity(self):
        return True, 1

    async def register_task(self, task_id, task_handle):
        self.last_register = (task_id, task_handle)

    async def unregister_task(self, task_id):
        self.last_unregister = task_id

    async def pause(self):
        self.is_paused = True
        return {"ok": True}

    async def resume(self):
        self.is_paused = False
        return {"ok": True}

    async def purge(self):
        return {"purged": True}

    async def abort_task(self, task_id):
        self.aborted = task_id
        return {"aborted": True}

    async def emergency_stop(self):
        return {"stopped": True}

    def get_status(self):
        return {"paused": self.is_paused}


@pytest.mark.asyncio
async def test_task_manager_delegates_to_queue_manager():
    queue_manager = DummyQueueManager()
    manager = TaskManager(queue_manager)

    assert manager.is_paused is False
    assert manager.active_tasks == {"t1": "task"}

    ok, active = await manager.check_capacity()
    assert ok is True
    assert active == 1

    task_handle = asyncio.current_task()
    await manager.register_task("task-1", task_handle)
    assert queue_manager.last_register == ("task-1", task_handle)

    await manager.unregister_task("task-1")
    assert queue_manager.last_unregister == "task-1"

    assert await manager.pause() == {"ok": True}
    assert manager.is_paused is True
    assert await manager.resume() == {"ok": True}
    assert manager.is_paused is False
    assert await manager.purge() == {"purged": True}
    assert await manager.abort_task("task-2") == {"aborted": True}
    assert queue_manager.aborted == "task-2"
    assert await manager.emergency_stop() == {"stopped": True}
    assert manager.get_status() == {"paused": False}


@pytest.mark.asyncio
async def test_event_broadcaster_client_noop_when_missing():
    client = EventBroadcasterClient(None)
    await client.broadcast(event_type="TEST", message="ok", agent="agent", data={})


@pytest.mark.asyncio
async def test_event_broadcaster_client_calls_broadcaster():
    class DummyBroadcaster:
        def __init__(self):
            self.last = None

        async def broadcast_event(self, event_type, message, agent=None, data=None):
            self.last = (event_type, message, agent, data)

    broadcaster = DummyBroadcaster()
    client = EventBroadcasterClient(broadcaster)
    await client.broadcast(
        event_type="TEST", message="hello", agent="agent", data={"a": 1}
    )
    assert broadcaster.last == ("TEST", "hello", "agent", {"a": 1})


def test_kernel_lifecycle_manager_wraps_kernel_manager(monkeypatch):
    class DummyKernelManager:
        def __init__(self, task_dispatcher, event_broadcaster=None, node_manager=None):
            self.task_dispatcher = task_dispatcher
            self.refreshed_with = None
            self.refresh_checked = False

        def refresh_kernel(self, runtime_info=None):
            self.refreshed_with = runtime_info
            return f"dispatcher:{runtime_info}"

        def refresh_kernel_if_needed(self):
            self.refresh_checked = True
            return True

    monkeypatch.setattr(
        "venom_core.core.orchestrator.kernel_lifecycle.KernelManager",
        DummyKernelManager,
    )

    manager = KernelLifecycleManager(
        task_dispatcher="dispatcher", event_broadcaster="b"
    )
    assert manager.task_dispatcher == "dispatcher"
    assert manager.refresh_kernel("runtime") == "dispatcher:runtime"
    assert manager.refresh_kernel_if_needed() is True


def test_format_extra_context_builds_sections():
    extra = TaskExtraContext(
        files=[" a.py ", "b.py"],
        links=["https://example.com"],
        paths=[],
        notes=["note"],
    )
    text = format_extra_context(extra)
    assert "Pliki:" in text
    assert "- a.py" in text
    assert "Linki:" in text
    assert "Ścieżki" not in text
    assert "Notatki:" in text


def test_build_error_envelope_defaults():
    envelope = build_error_envelope(error_code="ERR", error_message="msg")
    assert envelope["error_code"] == "ERR"
    assert envelope["error_class"] == "ERR"
    assert envelope["error_message"] == "msg"
    assert envelope["error_details"] == {}


def test_should_use_fast_path():
    request = TaskRequest(content="hello", store_knowledge=True)
    assert should_use_fast_path(request) is True
    request = TaskRequest(content="", store_knowledge=True)
    assert should_use_fast_path(request) is False
