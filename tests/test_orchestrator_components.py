import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from venom_core.core.models import TaskExtraContext, TaskRequest
from venom_core.core.orchestrator.event_broadcaster import EventBroadcasterClient
from venom_core.core.orchestrator.kernel_lifecycle import KernelLifecycleManager
from venom_core.core.orchestrator.orchestrator_events import (
    broadcast_event,
    build_error_envelope,
    set_runtime_error,
    trace_llm_start,
    trace_step_async,
)
from venom_core.core.orchestrator.orchestrator_submit import should_use_fast_path
from venom_core.core.orchestrator.task_manager import TaskManager
from venom_core.core.orchestrator.task_pipeline.context_builder import (
    ContextBuilder,
    format_extra_context,
)
from venom_core.core.slash_commands import SlashCommandResult


class DummyQueueManager:
    def __init__(self):
        self.is_paused = False
        self.active_tasks = {"t1": "task"}
        self.last_register = None
        self.last_unregister = None
        self.aborted = None

    async def check_capacity(self):
        await asyncio.sleep(0)
        return True, 1

    async def register_task(self, task_id, task_handle):
        await asyncio.sleep(0)
        self.last_register = (task_id, task_handle)

    async def unregister_task(self, task_id):
        await asyncio.sleep(0)
        self.last_unregister = task_id

    async def pause(self):
        await asyncio.sleep(0)
        self.is_paused = True
        return {"ok": True}

    async def resume(self):
        await asyncio.sleep(0)
        self.is_paused = False
        return {"ok": True}

    async def purge(self):
        await asyncio.sleep(0)
        return {"purged": True}

    async def abort_task(self, task_id):
        await asyncio.sleep(0)
        self.aborted = task_id
        return {"aborted": True}

    async def emergency_stop(self):
        await asyncio.sleep(0)
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
            await asyncio.sleep(0)
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


def test_should_use_fast_path_negative_cases():
    assert should_use_fast_path(TaskRequest(content="x" * 600)) is False
    assert should_use_fast_path(TaskRequest(content="ok", images=["img"])) is False
    assert (
        should_use_fast_path(TaskRequest(content="ok", forced_tool="browser")) is False
    )
    assert (
        should_use_fast_path(TaskRequest(content="ok", forced_provider="ollama"))
        is False
    )


def test_context_builder_perf_prompt_uses_default_keywords_when_invalid_type():
    class DummyIntentManager:
        PERF_TEST_KEYWORDS = "not-a-list"

    class DummyOrch:
        intent_manager = DummyIntentManager()

    builder = ContextBuilder(DummyOrch())
    assert builder.is_perf_test_prompt("Latency benchmark run") is True


def test_context_builder_perf_prompt_uses_custom_keywords():
    class DummyIntentManager:
        PERF_TEST_KEYWORDS = ["wydajnosc", "pomiar"]

    class DummyOrch:
        intent_manager = DummyIntentManager()

    builder = ContextBuilder(DummyOrch())
    assert builder.is_perf_test_prompt("To jest pomiar obciążenia") is True
    assert builder.is_perf_test_prompt("Zwykłe zadanie") is False


def test_context_builder_perf_prompt_handles_none_content():
    class DummyIntentManager:
        PERF_TEST_KEYWORDS = ["perf"]

    class DummyOrch:
        intent_manager = DummyIntentManager()

    builder = ContextBuilder(DummyOrch())
    assert builder.is_perf_test_prompt(None) is False


@pytest.mark.asyncio
async def test_context_builder_preprocess_request_updates_forced_route(monkeypatch):
    state_calls = []

    class DummyState:
        def update_context(self, task_id, payload):
            state_calls.append((task_id, payload))

        def add_log(self, *_args, **_kwargs):
            pass

    class DummyTracer:
        def set_forced_route(self, *args, **kwargs):
            return None

        def add_step(self, *args, **kwargs):
            return None

    orch = SimpleNamespace(
        state_manager=DummyState(),
        request_tracer=DummyTracer(),
        session_handler=SimpleNamespace(session_store=None),
    )
    builder = ContextBuilder(orch)

    monkeypatch.setattr(
        "venom_core.core.orchestrator.task_pipeline.context_builder.parse_slash_command",
        lambda _content: SlashCommandResult(
            token="git",
            cleaned="status",
            forced_tool="git",
            forced_intent="VERSION_CONTROL",
        ),
    )

    task_id = uuid4()
    request = TaskRequest(content="/git status")
    await builder.preprocess_request(task_id, request)

    assert request.content == "status"
    assert request.forced_tool == "git"
    assert any("forced_route" in call[1] for call in state_calls)


@pytest.mark.asyncio
async def test_context_builder_add_hidden_prompts_skips_for_small_vllm(monkeypatch):
    logs = []

    class DummyState:
        def add_log(self, _task_id, message):
            logs.append(message)

    orch = SimpleNamespace(
        state_manager=DummyState(),
        request_tracer=None,
        _get_runtime_context_char_limit=lambda _runtime: 5000,
    )
    builder = ContextBuilder(orch)

    monkeypatch.setattr(
        "venom_core.core.orchestrator.task_pipeline.context_builder.get_active_llm_runtime",
        lambda: SimpleNamespace(provider="vllm"),
    )
    monkeypatch.setattr(
        "venom_core.core.orchestrator.task_pipeline.context_builder.SETTINGS.VLLM_MAX_MODEL_LEN",
        512,
        raising=False,
    )

    out = await builder.add_hidden_prompts(uuid4(), "ctx", intent="GENERAL_CHAT")
    assert out == "ctx"
    assert any("Pominięto hidden prompts" in line for line in logs)


def test_trace_llm_start_adds_tracer_step_when_present():
    calls = []

    class DummyTracer:
        def add_step(self, *args, **kwargs):
            calls.append((args, kwargs))

    orch = SimpleNamespace(request_tracer=DummyTracer())
    task_id = uuid4()

    trace_llm_start(orch, task_id, "intent-x")

    assert len(calls) == 1
    assert calls[0][0][1:] == ("LLM", "start")
    assert calls[0][1]["details"] == "intent=intent-x"


def test_set_runtime_error_updates_context_and_tracer():
    class DummyStateManager:
        def __init__(self):
            self.last = None

        def update_context(self, task_id, payload):
            self.last = (task_id, payload)

    class DummyTracer:
        def __init__(self):
            self.last = None

        def set_error_metadata(self, task_id, envelope):
            self.last = (task_id, envelope)

    state = DummyStateManager()
    tracer = DummyTracer()
    orch = SimpleNamespace(state_manager=state, request_tracer=tracer)
    task_id = uuid4()
    envelope = {"error_code": "E", "error_message": "msg"}

    set_runtime_error(orch, task_id, envelope)

    assert state.last[0] == task_id
    assert state.last[1]["llm_runtime"]["status"] == "error"
    assert state.last[1]["llm_runtime"]["error"] == envelope
    assert "last_error_at" in state.last[1]["llm_runtime"]
    assert tracer.last == (task_id, envelope)


@pytest.mark.asyncio
async def test_broadcast_event_delegates_to_event_client():
    event_client = SimpleNamespace(broadcast=AsyncMock())
    orch = SimpleNamespace(event_client=event_client)

    await broadcast_event(
        orch,
        event_type="TEST_EVENT",
        message="hello",
        agent="tester",
        data={"x": 1},
    )

    event_client.broadcast.assert_awaited_once_with(
        event_type="TEST_EVENT",
        message="hello",
        agent="tester",
        data={"x": 1},
    )


@pytest.mark.asyncio
async def test_trace_step_async_swallow_exceptions_from_tracer():
    class FailingTracer:
        def add_step(self, *_args, **_kwargs):
            raise RuntimeError("tracer failed")

    orch = SimpleNamespace(request_tracer=FailingTracer())
    await trace_step_async(orch, uuid4(), "actor", "action", status="ok")
